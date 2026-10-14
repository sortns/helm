import pytest
import yaml
from conftest import octodns_config

from pa_sync.settings import (
    REQUIRED_REJECT_NETWORKS,
    ConfigError,
    Settings,
    load_secret_files,
    validate_octodns_config,
)

BASE_ENV = {
    'PA_SYNC_ZONE': 'example.com.',
    'PA_SYNC_POWERADMIN_URL': 'https://pa.example.net',
    'PA_SYNC_HOSTED_ZONE_ID': '/hostedzone/Z123',
}


def test_defaults_are_safe():
    s = Settings.from_env(BASE_ENV)
    assert s.dry_run is True
    assert s.zone == 'example.com' and s.zone_fqdn == 'example.com.'
    assert s.hosted_zone_id == 'Z123'
    assert (s.poll_interval, s.full_sync_interval) == (5, 300)


@pytest.mark.parametrize('value,expected', [('false', False), ('False', False), ('true', True), ('no', True), ('', True)])
def test_only_explicit_false_disables_dry_run(value, expected):
    assert Settings.from_env({**BASE_ENV, 'PA_SYNC_DRY_RUN': value}).dry_run is expected


def test_http_url_rejected():
    with pytest.raises(ConfigError, match='https'):
        Settings.from_env({**BASE_ENV, 'PA_SYNC_POWERADMIN_URL': 'http://pa.example.net'})


@pytest.mark.parametrize('missing', sorted(BASE_ENV))
def test_required(missing):
    env = {k: v for k, v in BASE_ENV.items() if k != missing}
    with pytest.raises(ConfigError, match=missing):
        Settings.from_env(env)


def test_secret_files(tmp_path):
    (tmp_path / 'key').write_text('s3cr3t\n')
    env = {'POWERADMIN_API_KEY__FILE': str(tmp_path / 'key')}
    load_secret_files(env)
    assert env == {'POWERADMIN_API_KEY': 's3cr3t'}


def test_secret_file_missing(tmp_path):
    with pytest.raises(ConfigError, match='cannot read'):
        load_secret_files({'X__FILE': str(tmp_path / 'nope')})


def test_secret_value_and_file_conflict(tmp_path):
    with pytest.raises(ConfigError, match='both'):
        load_secret_files({'X': 'a', 'X__FILE': str(tmp_path / 'x')})


def _validate(tmp_path, dry_run=True, mutate=None, **cfg):
    config = octodns_config('https://pa.example.net', dry_run=dry_run, **cfg)
    if mutate:
        mutate(config)
    path = tmp_path / 'octodns.yaml'
    path.write_text(yaml.safe_dump(config))
    settings = Settings.from_env({**BASE_ENV, 'PA_SYNC_DRY_RUN': str(dry_run).lower()})
    return validate_octodns_config(settings, path)


def test_valid_config(tmp_path):
    _validate(tmp_path)
    _validate(tmp_path, dry_run=False)


@pytest.mark.parametrize('update,delete', [(0.31, 0.2), (0.3, 0.21), (1, 1)])
def test_loose_thresholds_rejected(tmp_path, update, delete):
    with pytest.raises(ConfigError, match='thresholds'):
        _validate(tmp_path, update=update, delete=delete)


def test_missing_thresholds_rejected(tmp_path):
    def drop(c):
        del c['providers']['route53']['delete_pcent_threshold']

    with pytest.raises(ConfigError, match='thresholds'):
        _validate(tmp_path, mutate=drop)


def test_ns_filter_required(tmp_path):
    def drop(c):
        c['processors']['reject-types']['rejectlist'] = ['LUA']

    with pytest.raises(ConfigError, match='NS'):
        _validate(tmp_path, mutate=drop)


def test_weakened_network_filter_rejected(tmp_path):
    weakened = ['10.0.0.0/16' if n == '10.0.0.0/8' else n for n in REQUIRED_REJECT_NETWORKS]
    with pytest.raises(ConfigError, match='10.0.0.0/8'):
        _validate(tmp_path, networks=weakened)


def test_wider_network_filter_ok(tmp_path):
    _validate(tmp_path, networks=['0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16',
                                  '172.16.0.0/12', '192.168.0.0/16', '198.51.100.0/24', '::/0'])


def test_dry_run_needs_always_dry_run(tmp_path):
    def flip(c):
        c['zones']['example.com.']['always-dry-run'] = False

    with pytest.raises(ConfigError, match='always-dry-run'):
        _validate(tmp_path, mutate=flip)


def test_private_must_be_false(tmp_path):
    def drop(c):
        del c['providers']['route53']['private']

    with pytest.raises(ConfigError, match='private'):
        _validate(tmp_path, mutate=drop)


def test_extra_zone_rejected(tmp_path):
    def add(c):
        c['zones']['other.example.com.'] = c['zones']['example.com.']

    with pytest.raises(ConfigError, match='exactly zone'):
        _validate(tmp_path, mutate=add)
