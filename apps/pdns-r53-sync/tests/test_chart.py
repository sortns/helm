"""The Helm chart renders a config the daemon accepts, and keeps the deployment invariants."""

import json
import shutil
from dataclasses import replace
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import PUBLISHED, ZONE

from pa_sync import plan
from pa_sync.daemon import sync_once
from pa_sync.settings import Settings, validate_octodns_config

CHART = Path(__file__).resolve().parents[3] / 'charts' / 'pdns-r53-sync'
BASE = [
    '--set', f'zone={ZONE}',
    '--set', 'poweradmin.url=https://pa.example.net',
    '--set', 'route53.hostedZoneId=Z0123456789ABC',
]

pytestmark = pytest.mark.skipif(shutil.which('helm') is None, reason='helm not installed')


def render(*args):
    out = subprocess.run(
        ['helm', 'template', 'dns-sync', str(CHART), '--namespace', 'dns', *BASE, *args],
        check=True, capture_output=True, text=True,
    ).stdout
    return {(d['kind'], d['metadata']['name']): d for d in yaml.safe_load_all(out) if d}


def render_error(*args):
    proc = subprocess.run(
        ['helm', 'template', 'dns-sync', str(CHART), *BASE, *args], capture_output=True, text=True
    )
    assert proc.returncode != 0
    return proc.stderr


def deployment(docs):
    return next(d for (k, _), d in docs.items() if k == 'Deployment')


def env_of(docs):
    return {e['name']: e.get('value') for e in deployment(docs)['spec']['template']['spec']['containers'][0]['env']}


def octodns_yaml(docs):
    return next(d for (k, _), d in docs.items() if k == 'ConfigMap')['data']['octodns.yaml']


def settings_from(docs, tmp_path, url=None):
    config = yaml.safe_load(octodns_yaml(docs))
    if url:
        config['providers']['poweradmin']['url'] = url
    path = tmp_path / 'octodns.yaml'
    path.write_text(yaml.safe_dump(config))
    env = {k: v for k, v in env_of(docs).items() if v is not None}
    env['PA_SYNC_OCTODNS_CONFIG'] = str(path)
    if url:
        env['PA_SYNC_POWERADMIN_URL'] = url
        env['PA_SYNC_ALLOW_HTTP'] = 'true'
    return Settings.from_env(env)


def test_invariants_with_existing_secret(tmp_path):
    docs = render('--set', 'secretEnv.existingSecret=dns-sync')
    dep = deployment(docs)
    assert dep['spec']['replicas'] == 1
    assert dep['spec']['strategy'] == {'type': 'Recreate'}
    assert not any(k == 'Secret' for k, _ in docs)

    env = env_of(docs)
    assert env['PA_SYNC_DRY_RUN'] == 'true'
    secret_env = {k for k in env if k.startswith(('POWERADMIN', 'AWS'))}
    assert secret_env == {'POWERADMIN_API_KEY__FILE', 'AWS_ACCESS_KEY_ID__FILE', 'AWS_SECRET_ACCESS_KEY__FILE'}

    volume = next(v for v in dep['spec']['template']['spec']['volumes'] if v['name'] == 'secret-env')
    assert volume['secret']['secretName'] == 'dns-sync'
    assert {i['key'] for i in volume['secret']['items']} == {
        'POWERADMIN_API_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'
    }

    annotations = dep['spec']['template']['metadata']['annotations']
    assert annotations['prometheus.io/scrape'] == 'true' and annotations['prometheus.io/port'] == '9100'

    config = validate_octodns_config(settings_from(docs, tmp_path))
    assert config['zones'][f'{ZONE}.']['always-dry-run'] is True


def test_live_mode_and_extra_filters_still_valid(tmp_path):
    docs = render(
        '--set', 'secretEnv.existingSecret=dns-sync',
        '--set', 'sync.dryRun=false',
        '--set', 'filters.extraRejectTypes={LUA}',
        '--set', 'filters.extraRejectNetworks={198.51.100.0/24}',
        '--set', 'filters.rejectNames={/^_acme-challenge/}',
    )
    settings = settings_from(docs, tmp_path)
    assert settings.dry_run is False
    config = validate_octodns_config(settings)
    procs = config['processors']
    assert procs['reject-types']['rejectlist'] == ['NS', 'LUA', 'Route53Provider/ALIAS']
    assert '198.51.100.0/24' in procs['reject-networks']['rejectlist']
    assert procs['reject-names']['rejectlist'] == ['/^_acme-challenge/', '/^_[0-9a-f]{32}(\\.|$)/']
    assert config['zones'][f'{ZONE}.']['processors'][-1] == 'normalize-targets'


def test_route53_only_ignores_can_be_disabled():
    config = yaml.safe_load(octodns_yaml(render(
        '--set', 'secretEnv.existingSecret=x',
        '--set', 'filters.ignoreRoute53Aliases=false',
        '--set', 'filters.ignoreAcmValidation=false',
    )))
    assert config['processors']['reject-types']['rejectlist'] == ['NS']
    assert 'reject-names' not in config['processors']
    assert 'reject-names' not in config['zones'][f'{ZONE}.']['processors']


def test_secret_mapping_and_ambient_credentials(tmp_path):
    docs = render(
        '--set', 'secretEnv.existingSecret=vault-dns',
        '--set', 'secretEnv.existingSecretKeys.POWERADMIN_API_KEY=pa-key',
        '--set', 'route53.credentials=ambient',
    )
    env = env_of(docs)
    assert env['POWERADMIN_API_KEY__FILE'].endswith('/pa-key')
    assert not any(k.startswith('AWS_') for k in env)
    assert 'access_key_id' not in octodns_yaml(docs)


def test_chart_created_secret_stays_out_of_configmap_and_env():
    docs = render(
        '--set', 'secretEnv.values.POWERADMIN_API_KEY=pa-s3cr3t',
        '--set', 'secretEnv.values.AWS_ACCESS_KEY_ID=AKIAEXAMPLE',
        '--set', 'secretEnv.values.AWS_SECRET_ACCESS_KEY=aws-s3cr3t',
    )
    secret = next(d for (k, _), d in docs.items() if k == 'Secret')
    assert secret['stringData']['POWERADMIN_API_KEY'] == 'pa-s3cr3t'
    others = json.dumps([d for (k, _), d in docs.items() if k != 'Secret'])
    for value in ('pa-s3cr3t', 'AKIAEXAMPLE', 'aws-s3cr3t'):
        assert value not in others


def test_monitoring_objects():
    docs = render(
        '--set', 'secretEnv.existingSecret=x',
        '--set', 'serviceMonitor.enabled=true',
        '--set', 'prometheusRule.enabled=true',
        '--set', 'prometheusRule.metricSelector=namespace="dns"',
        '--set', 'networkPolicy.enabled=true',
    )
    kinds = {k for k, _ in docs}
    assert {'Service', 'ServiceMonitor', 'PrometheusRule', 'NetworkPolicy'} <= kinds
    rules = next(d for (k, _), d in docs.items() if k == 'PrometheusRule')['spec']['groups'][0]['rules']
    assert {r['alert'] for r in rules} == {
        'PdnsR53SyncStale', 'PdnsR53SyncPoweradminUnreachable', 'PdnsR53SyncUnsafePlan', 'PdnsR53SyncHostedZoneGuard'
    }
    assert all('{namespace="dns"}' in r['expr'] for r in rules)


@pytest.mark.parametrize(
    'args,message',
    [
        (['--set', 'replicaCount=2'], 'replicaCount'),
        (['--set-json', 'route53.deletePcentThreshold=0.21'], 'deletePcentThreshold'),
        (['--set-json', 'route53.updatePcentThreshold=0.5'], 'updatePcentThreshold'),
        (['--set', 'poweradmin.url=http://pa.example.net'], 'poweradmin.url'),
        (['--set', 'image.tag=latest'], 'image.tag'),
        ([], 'POWERADMIN_API_KEY is not provided'),
    ],
)
def test_rejected_values(args, message):
    extra = [] if not args or args[0] != '--set' or 'secretEnv' in args[1] else ['--set', 'secretEnv.existingSecret=x']
    error = render_error(*args, *extra)
    # Helm < 3.18 reports schema paths as "poweradmin.url", newer versions as "/poweradmin/url"
    assert message in error or '/' + message.replace('.', '/') in error, error


def test_rendered_config_runs_a_dry_run(tmp_path, pa, aws, monkeypatch):
    monkeypatch.setenv('POWERADMIN_API_KEY', pa.api_key)
    docs = render('--set', 'secretEnv.existingSecret=dns-sync')
    # moto zone ids do not follow the Z... format the chart schema enforces
    settings = replace(settings_from(docs, tmp_path, url=pa.url), hosted_zone_id=aws.hosted_zone_id)
    assert sync_once(settings, 'startup', 1)
    assert plan.LAST == {'create': len(PUBLISHED), 'update': 0, 'delete': 0}
