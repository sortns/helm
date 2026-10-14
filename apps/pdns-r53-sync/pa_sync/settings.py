"""Runtime settings, secret files and safety invariants."""

import ipaddress
import os
from dataclasses import dataclass

import yaml

MAX_UPDATE_PCENT = 0.3
MAX_DELETE_PCENT = 0.2
# Private / special ranges that must never be published, whatever the values say
REQUIRED_REJECT_NETWORKS = (
    '0.0.0.0/8',
    '10.0.0.0/8',
    '100.64.0.0/10',
    '127.0.0.0/8',
    '169.254.0.0/16',
    '172.16.0.0/12',
    '192.168.0.0/16',
    '::1/128',
    'fc00::/7',
    'fe80::/10',
)
SECRET_NAMES = ('POWERADMIN_API_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN')


class ConfigError(Exception):
    pass


def load_secret_files(environ=os.environ):
    """Resolve <NAME>__FILE variables into <NAME> inside this process only."""
    for key in [k for k in environ if k.endswith('__FILE')]:
        name = key[: -len('__FILE')]
        if environ.get(name):
            raise ConfigError(f'both {name} and {key} are set')
        path = environ[key]
        try:
            with open(path, encoding='utf-8') as fh:
                environ[name] = fh.read().strip()
        except OSError as e:
            raise ConfigError(f'{key}: cannot read secret file: {e.strerror}') from None
        del environ[key]


def _bool(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass(frozen=True)
class Settings:
    zone: str
    poweradmin_url: str
    hosted_zone_id: str
    octodns_config: str
    dry_run: bool
    poll_interval: float
    full_sync_interval: float
    retry_interval: float
    metrics_port: int
    liveness_max_age: float
    http_timeout: float
    verify_tls: bool

    @property
    def zone_fqdn(self):
        return self.zone.rstrip('.') + '.'

    @classmethod
    def from_env(cls, environ=os.environ):
        def req(name):
            value = environ.get(name, '').strip()
            if not value:
                raise ConfigError(f'{name} is required')
            return value

        s = cls(
            zone=req('PA_SYNC_ZONE').rstrip('.').lower(),
            poweradmin_url=req('PA_SYNC_POWERADMIN_URL'),
            hosted_zone_id=req('PA_SYNC_HOSTED_ZONE_ID').split('/')[-1],
            octodns_config=environ.get('PA_SYNC_OCTODNS_CONFIG', '/config/octodns.yaml'),
            # Anything but an explicit "false" keeps the safe mode
            dry_run=environ.get('PA_SYNC_DRY_RUN', 'true').strip().lower() != 'false',
            poll_interval=float(environ.get('PA_SYNC_POLL_INTERVAL', '5')),
            full_sync_interval=float(environ.get('PA_SYNC_FULL_SYNC_INTERVAL', '300')),
            retry_interval=float(environ.get('PA_SYNC_RETRY_INTERVAL', '60')),
            metrics_port=int(environ.get('PA_SYNC_METRICS_PORT', '9100')),
            liveness_max_age=float(environ.get('PA_SYNC_LIVENESS_MAX_AGE', '300')),
            http_timeout=float(environ.get('PA_SYNC_HTTP_TIMEOUT', '10')),
            verify_tls=_bool(environ.get('PA_SYNC_VERIFY_TLS', 'true')),
        )
        if not s.poweradmin_url.startswith('https://') and not _bool(environ.get('PA_SYNC_ALLOW_HTTP', 'false')):
            raise ConfigError('PA_SYNC_POWERADMIN_URL must be https://')
        if s.poll_interval < 1 or s.full_sync_interval < s.poll_interval or s.retry_interval < 1:
            raise ConfigError('intervals must satisfy poll >= 1, fullSync >= poll, retry >= 1')
        if s.liveness_max_age < 3 * s.poll_interval:
            raise ConfigError('PA_SYNC_LIVENESS_MAX_AGE must be at least 3 poll intervals')
        return s


def _classes(config, section, names):
    out = []
    for name in names:
        item = (config.get(section) or {}).get(name) or {}
        out.append((name, item.get('class', ''), item))
    return out


def validate_octodns_config(settings, path=None):
    """Refuse to run with an octoDNS config that breaks the deployment invariants."""
    with open(path or settings.octodns_config, encoding='utf-8') as fh:
        config = yaml.safe_load(fh)

    zones = config.get('zones') or {}
    if list(zones) != [settings.zone_fqdn]:
        raise ConfigError(f'octoDNS config must contain exactly zone {settings.zone_fqdn}, got {list(zones)}')
    zone = zones[settings.zone_fqdn]

    sources = _classes(config, 'providers', zone.get('sources') or [])
    if [c for _, c, _ in sources] != ['pa_sync.source.PoweradminSource']:
        raise ConfigError('the only source must be pa_sync.source.PoweradminSource')

    targets = _classes(config, 'providers', zone.get('targets') or [])
    if [c for _, c, _ in targets] != ['octodns_route53.Route53Provider']:
        raise ConfigError('the only target must be octodns_route53.Route53Provider')
    target = targets[0][2]
    update = float(target.get('update_pcent_threshold', 1))
    delete = float(target.get('delete_pcent_threshold', 1))
    if update > MAX_UPDATE_PCENT or delete > MAX_DELETE_PCENT:
        raise ConfigError(
            f'Route53 thresholds too loose: update={update} (max {MAX_UPDATE_PCENT}), '
            f'delete={delete} (max {MAX_DELETE_PCENT})'
        )
    if target.get('private') is not False:
        raise ConfigError('Route53 provider must set private: false')

    processors = _classes(config, 'processors', zone.get('processors') or [])
    reject_types = [p for _, c, p in processors if c == 'octodns.processor.filter.TypeRejectlistFilter']
    if not any('NS' in (p.get('rejectlist') or []) for p in reject_types):
        raise ConfigError('zone must use a TypeRejectlistFilter that rejects NS')
    networks = []
    for _, c, p in processors:
        if c == 'octodns.processor.filter.NetworkValueRejectlistFilter':
            networks += [ipaddress.ip_network(n) for n in p.get('rejectlist') or []]
    for required in map(ipaddress.ip_network, REQUIRED_REJECT_NETWORKS):
        if not any(required.version == n.version and required.subnet_of(n) for n in networks):
            raise ConfigError(f'NetworkValueRejectlistFilter must cover {required}')
    if settings.dry_run and not zone.get('always-dry-run'):
        raise ConfigError('dry-run requested but the zone is not marked always-dry-run')
    return config
