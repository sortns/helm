"""Poll the zone's SOA serial in Poweradmin and mirror the zone to Route53 when it changes."""

import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from octodns.manager import Manager
from octodns.provider.plan import UnsafePlan
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import metrics, plan
from .guard import GuardError, check_hosted_zone
from .poweradmin import Poweradmin, PoweradminError, ZoneNotFound
from .settings import validate_octodns_config

log = logging.getLogger('pa_sync.daemon')


class Heartbeat:
    def __init__(self):
        self.last = time.monotonic()

    def beat(self):
        self.last = time.monotonic()

    def age(self):
        return time.monotonic() - self.last


def serve_http(port, heartbeat, max_age):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/metrics':
                body, ctype, code = generate_latest(), CONTENT_TYPE_LATEST, 200
            elif self.path == '/healthz':
                age = heartbeat.age()
                code = 200 if age < max_age else 503
                body, ctype = f'loop heartbeat {age:.0f}s ago\n'.encode(), 'text/plain'
            else:
                body, ctype, code = b'not found\n', 'text/plain', 404
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('', port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name='http', daemon=True).start()
    return server


def sync_once(settings, reason, serial=None, dry_run=None):
    """Run one octoDNS sync. Returns True on success."""
    dry_run = settings.dry_run if dry_run is None else dry_run
    started = time.time()
    metrics.LAST_ATTEMPT.set(started)
    result = 'error'
    try:
        validate_octodns_config(settings)
        check_hosted_zone(settings.zone_fqdn, settings.hosted_zone_id)
        metrics.HOSTED_ZONE_OK.set(1)
        manager = Manager(settings.octodns_config)
        applied = manager.sync(eligible_zones=[settings.zone_fqdn], dry_run=dry_run)
        planned = sum(plan.LAST.values())
        result = 'success'
        metrics.LAST_SUCCESS.set(time.time())
        if not dry_run:
            metrics.APPLIED_CHANGES.inc(applied)
        log.info(
            'sync reason=%s serial=%s dry_run=%s changes=%d applied=%d',
            reason,
            serial,
            str(dry_run).lower(),
            planned,
            applied,
        )
        return True
    except UnsafePlan as e:
        result = 'unsafe'
        metrics.UNSAFE_PLANS.inc()
        log.error('sync reason=%s refused by octoDNS safety check: %s; not forcing, needs a human decision', reason, e)
    except GuardError as e:
        result = 'guard'
        metrics.HOSTED_ZONE_OK.set(0)
        log.error('sync reason=%s blocked by hosted zone guard: %s', reason, e)
    except Exception as e:  # noqa: BLE001 - keep the loop alive, surface via metrics/logs
        log.error('sync reason=%s failed: %s: %s', reason, e.__class__.__name__, e)
        log.debug('sync failure details', exc_info=True)
    finally:
        metrics.SYNCS.labels(reason, result).inc()
        metrics.SYNC_DURATION.observe(time.time() - started)
    return False


class Daemon:
    def __init__(self, settings, client=None, sync=sync_once):
        self.s = settings
        self.client = client
        self.sync = sync
        self.stop = threading.Event()
        self.heartbeat = Heartbeat()
        self.zone_id = None
        self.synced_serial = None

    def _poll(self):
        try:
            if self.zone_id is None:
                self.zone_id = self.client.find_zone_id(self.s.zone)
            serial = self.client.soa_serial(self.zone_id)
        except ZoneNotFound as e:
            self.zone_id = None
            metrics.POLL_ERRORS.inc()
            log.error('poll: %s', e)
            return None
        except PoweradminError as e:
            metrics.POLL_ERRORS.inc()
            log.error('poll: %s', e)
            return None
        metrics.POLLS.inc()
        metrics.SOURCE_SERIAL.set(serial)
        return serial

    def run(self):
        if self.client is None:
            self.client = Poweradmin(
                self.s.poweradmin_url, os.environ.get('POWERADMIN_API_KEY', ''), timeout=self.s.http_timeout, verify_tls=self.s.verify_tls
            )
        metrics.DRY_RUN.set(1 if self.s.dry_run else 0)
        log.info(
            'starting: zone=%s hosted_zone=%s dry_run=%s poll=%ss full_sync=%ss',
            self.s.zone,
            self.s.hosted_zone_id,
            str(self.s.dry_run).lower(),
            self.s.poll_interval,
            self.s.full_sync_interval,
        )
        pending = 'startup'
        next_full = 0.0
        not_before = 0.0
        while not self.stop.is_set():
            self.heartbeat.beat()
            serial = self._poll()
            now = time.monotonic()
            reason = None
            if serial is not None and now >= not_before:
                if pending:
                    reason = pending
                elif serial != self.synced_serial:
                    reason = 'serial'
                elif now >= next_full:
                    reason = 'periodic'
            if reason:
                # The serial is read before the sync, so edits made during a sync trigger another one
                if self.sync(self.s, reason, serial):
                    self.synced_serial = serial
                    metrics.SYNCED_SERIAL.set(serial)
                    pending = None
                else:
                    pending = 'retry'
                    not_before = time.monotonic() + self.s.retry_interval
                next_full = time.monotonic() + self.s.full_sync_interval
                self.heartbeat.beat()
            self.stop.wait(self.s.poll_interval)
        log.info('stopped')


def main(settings):
    validate_octodns_config(settings)
    daemon = Daemon(settings)

    def _stop(signum, _frame):
        log.info('received %s, finishing current iteration', signal.Signals(signum).name)
        daemon.stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    serve_http(settings.metrics_port, daemon.heartbeat, settings.liveness_max_age)
    daemon.run()
