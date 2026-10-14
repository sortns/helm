import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
from conftest import ZONE, octodns_config

from pa_sync.daemon import Daemon
from pa_sync.poweradmin import PoweradminError
from pa_sync.settings import Settings

APP_DIR = Path(__file__).resolve().parents[1]


class FakeClient:
    def __init__(self, serials):
        self.serials = list(serials)

    def find_zone_id(self, zone):
        return 1

    def soa_serial(self, zone_id):
        value = self.serials.pop(0) if len(self.serials) > 1 else self.serials[0]
        if isinstance(value, Exception):
            raise value
        return value


def run_loop(serials, results=None, iterations=8, **overrides):
    env = {
        'PA_SYNC_ZONE': ZONE,
        'PA_SYNC_POWERADMIN_URL': 'https://pa.example.net',
        'PA_SYNC_HOSTED_ZONE_ID': 'Z1',
        'PA_SYNC_POLL_INTERVAL': '1',
        'PA_SYNC_FULL_SYNC_INTERVAL': '1000',
        'PA_SYNC_RETRY_INTERVAL': '1000',
        **overrides,
    }
    settings = Settings.from_env(env)
    calls = []
    results = list(results or [])

    def sync(s, reason, serial):
        calls.append((reason, serial))
        return results.pop(0) if results else True

    daemon = Daemon(settings, client=FakeClient(serials), sync=sync)
    # Run the loop without waiting between iterations
    count = {'n': 0}

    def wait(_timeout):
        count['n'] += 1
        if count['n'] >= iterations:
            daemon.stop.set()
        return daemon.stop.is_set()

    daemon.stop.wait = wait
    daemon.run()
    return calls


def test_startup_then_only_on_serial_change():
    calls = run_loop([1, 1, 1, 2, 2, 3])
    assert calls == [('startup', 1), ('serial', 2), ('serial', 3)]


def test_poll_errors_do_not_trigger_sync():
    calls = run_loop([PoweradminError('down'), PoweradminError('down'), 5, 5])
    assert calls == [('startup', 5)]


def test_failed_sync_waits_for_retry_interval():
    # retry interval 1000s: after a failure nothing else runs during the test
    calls = run_loop([1, 2, 3, 4], results=[False])
    assert calls == [('startup', 1)]


def test_failed_sync_is_retried(monkeypatch):
    clock = {'t': 0.0}

    def monotonic():
        clock['t'] += 10
        return clock['t']

    monkeypatch.setattr('pa_sync.daemon.time.monotonic', monotonic)
    calls = run_loop([1, 1, 1, 1, 1, 1], results=[False, True], iterations=6, PA_SYNC_RETRY_INTERVAL='30')
    assert calls == [('startup', 1), ('retry', 1)]


def test_periodic_full_sync(monkeypatch):
    clock = {'t': 0.0}

    def monotonic():
        clock['t'] += 100
        return clock['t']

    monkeypatch.setattr('pa_sync.daemon.time.monotonic', monotonic)
    calls = run_loop([7], iterations=6, PA_SYNC_FULL_SYNC_INTERVAL='300')
    assert calls[0] == ('startup', 7)
    assert ('periodic', 7) in calls


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


class _Broken(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(500)
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *args):
        pass


def test_process_health_metrics_and_sigterm(pa, tmp_path):
    """The real entrypoint: secrets from files, /healthz, /metrics, graceful SIGTERM.

    Route53 answers HTTP 500 here, so syncs fail; the loop must keep running regardless.
    """
    broken = ThreadingHTTPServer(('127.0.0.1', 0), _Broken)
    threading.Thread(target=broken.serve_forever, daemon=True).start()
    port = _free_port()
    (tmp_path / 'secrets').mkdir()
    (tmp_path / 'secrets' / 'pa').write_text(pa.api_key + '\n')
    (tmp_path / 'secrets' / 'id').write_text('testing')
    (tmp_path / 'secrets' / 'secret').write_text('testing')
    config = tmp_path / 'octodns.yaml'
    config.write_text(yaml.safe_dump(octodns_config(pa.url)))
    env = {
        'PATH': os.environ.get('PATH', ''),
        'PYTHONPATH': str(APP_DIR),
        'PA_SYNC_ZONE': ZONE,
        'PA_SYNC_POWERADMIN_URL': pa.url,
        'PA_SYNC_ALLOW_HTTP': 'true',
        'PA_SYNC_HOSTED_ZONE_ID': 'Z1',
        'PA_SYNC_OCTODNS_CONFIG': str(config),
        'PA_SYNC_POLL_INTERVAL': '1',
        'PA_SYNC_LIVENESS_MAX_AGE': '30',
        'PA_SYNC_METRICS_PORT': str(port),
        'POWERADMIN_API_KEY__FILE': str(tmp_path / 'secrets' / 'pa'),
        'AWS_ACCESS_KEY_ID__FILE': str(tmp_path / 'secrets' / 'id'),
        'AWS_SECRET_ACCESS_KEY__FILE': str(tmp_path / 'secrets' / 'secret'),
        'AWS_ENDPOINT_URL': f'http://127.0.0.1:{broken.server_port}',
        'AWS_MAX_ATTEMPTS': '1',
        'AWS_DEFAULT_REGION': 'us-east-1',
        'AWS_EC2_METADATA_DISABLED': 'true',
        'AWS_CONFIG_FILE': os.devnull,
        'AWS_SHARED_CREDENTIALS_FILE': os.devnull,
    }
    proc = subprocess.Popen(
        [sys.executable, '-m', 'pa_sync', 'run'], env=env, stderr=subprocess.PIPE, text=True, cwd=tmp_path
    )
    stderr = []
    reader = threading.Thread(target=lambda: stderr.extend(proc.stderr), daemon=True)
    reader.start()
    try:
        deadline = time.time() + 20
        metrics = ''
        while time.time() < deadline:
            time.sleep(0.5)
            try:
                code, metrics = _get(f'http://127.0.0.1:{port}/metrics')
            except OSError:
                continue
            if 'pa_sync_source_serial 2.026101401e+09' in metrics and 'result="error"' in metrics:
                break
        assert 'pa_sync_source_serial 2.026101401e+09' in metrics, ''.join(stderr)
        assert 'pa_sync_syncs_total{reason="startup",result="error"} 1.0' in metrics
        assert 'pa_sync_dry_run 1.0' in metrics
        assert _get(f'http://127.0.0.1:{port}/healthz')[0] == 200

        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
        broken.shutdown()
    reader.join(timeout=2)
    log = ''.join(stderr)
    assert 'received SIGTERM' in log and 'stopped' in log
    # The API key never reaches the logs, and every request used the header
    assert pa.api_key not in log
    assert all(key == pa.api_key for _, _, key in pa.requests)
    assert all('api_key' not in query for _, query, _ in pa.requests)
