"""pdns-r53-sync entrypoint.

  python -m pa_sync run     # daemon (default)
  python -m pa_sync plan    # one dry-run sync, prints the plan; never applies, whatever PA_SYNC_DRY_RUN says
  python -m pa_sync check   # connectivity and configuration self-test, prints no secrets
"""

import argparse
import logging
import os
import sys
from collections import Counter

from . import __version__
from .daemon import main as run_daemon
from .daemon import sync_once
from .guard import GuardError, check_hosted_zone
from .poweradmin import Poweradmin, PoweradminError
from .settings import ConfigError, Settings, load_secret_files, validate_octodns_config
from .source import convert


def _logging():
    level = os.environ.get('PA_SYNC_LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(level=level, format='%(asctime)s %(levelname)s %(name)s %(message)s', stream=sys.stderr)
    if level != 'DEBUG':
        # octoDNS and boto are chatty at INFO; our own loggers carry the useful lines
        for name in ('octodns', 'Manager', 'Plan', 'Route53Provider', 'botocore', 'boto3', 'urllib3'):
            logging.getLogger(name).setLevel(logging.WARNING)


def check(settings):
    ok = True

    def report(name, passed, detail):
        nonlocal ok
        ok = ok and passed
        print(f'[{"ok" if passed else "FAIL"}] {name}: {detail}')

    try:
        validate_octodns_config(settings)
        report('octodns config', True, settings.octodns_config)
    except (ConfigError, OSError) as e:
        report('octodns config', False, e)

    try:
        client = Poweradmin(
            settings.poweradmin_url,
            os.environ.get('POWERADMIN_API_KEY', ''),
            timeout=settings.http_timeout,
            verify_tls=settings.verify_tls,
        )
        zone_id = client.find_zone_id(settings.zone)
        serial = client.soa_serial(zone_id)
        records = client.records(zone_id)
        rrsets, skipped = convert(settings.zone, records)
        report('poweradmin', True, f'zone id={zone_id} serial={serial} records={len(records)} rrsets={len(rrsets)}')
        for (rtype, reason), count in sorted(Counter((t, r) for t, r, _ in skipped).items()):
            print(f'       skipped {rtype} ({reason}): {count}')
        for rtype, reason, fqdn in sorted(set(skipped)):
            if reason not in ('ns',):
                print(f'         - {rtype} {fqdn} ({reason})')
    except PoweradminError as e:
        report('poweradmin', False, e)

    try:
        check_hosted_zone(settings.zone_fqdn, settings.hosted_zone_id)
        report('route53', True, f'hosted zone {settings.hosted_zone_id} is the only public {settings.zone_fqdn}')
    except GuardError as e:
        report('route53', False, e)
    except Exception as e:  # noqa: BLE001 - credentials / IAM errors
        report('route53', False, f'{e.__class__.__name__}: {e}')

    print(f'dry_run={str(settings.dry_run).lower()}')
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog='pa_sync', description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('command', nargs='?', default='run', choices=('run', 'plan', 'check'))
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)

    _logging()
    try:
        load_secret_files()
        settings = Settings.from_env()
    except ConfigError as e:
        logging.getLogger('pa_sync').error('configuration error: %s', e)
        return 2

    if args.command == 'check':
        return check(settings)
    if args.command == 'plan':
        return 0 if sync_once(settings, 'manual', dry_run=True) else 1
    try:
        run_daemon(settings)
    except ConfigError as e:
        logging.getLogger('pa_sync').error('configuration error: %s', e)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
