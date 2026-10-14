import os
import sys
from pathlib import Path

import boto3
import pytest
import yaml
from moto import mock_aws
from moto.core.responses import ActionResult
from moto.route53.responses import Route53 as MotoRoute53Responses

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_poweradmin import MockPoweradmin  # noqa: E402

from pa_sync.settings import REQUIRED_REJECT_NETWORKS, Settings  # noqa: E402

ZONE = 'example.com'
DKIM = '"v=DKIM1; k=rsa; p=' + 'A' * 230 + '" "' + 'B' * 120 + '"'


def populate_zone(pa):
    z = pa.add_zone(ZONE)
    add = pa.add
    add(z, ZONE, 'A', '192.0.2.1')
    add(z, f'www.{ZONE}', 'A', '192.0.2.10')
    add(z, f'www.{ZONE}', 'A', '192.0.2.11')
    add(z, f'*.apps.{ZONE}', 'A', '192.0.2.20')
    add(z, f'v6.{ZONE}', 'AAAA', '2001:db8::1')
    add(z, f'blog.{ZONE}', 'CNAME', f'www.{ZONE}')
    add(z, ZONE, 'MX', f'mail.{ZONE}', priority=10)
    add(z, ZONE, 'MX', f'mail2.{ZONE}', priority=20)
    add(z, f'legacy.{ZONE}', 'MX', '5 mx.example.net', priority=0)
    add(z, ZONE, 'TXT', '"v=spf1 include:_spf.example.net ~all"')
    add(z, f'_dmarc.{ZONE}', 'TXT', '"v=DMARC1; p=reject; rua=mailto:dmarc@example.com"')
    add(z, f'sel._domainkey.{ZONE}', 'TXT', DKIM)
    add(z, f'_sip._tcp.{ZONE}', 'SRV', f'5 5060 sip.{ZONE}', priority=10)
    add(z, ZONE, 'CAA', '0 issue "letsencrypt.org"')
    add(z, f'sip.{ZONE}', 'NAPTR', '100 10 "U" "E2U+sip" "!^.*$!sip:info@example.com!" .')
    # Never published
    add(z, f'internal.{ZONE}', 'A', '10.1.2.3')
    add(z, f'mixed.{ZONE}', 'A', '192.0.2.5')
    add(z, f'mixed.{ZONE}', 'A', '10.0.0.5')
    add(z, f'cgnat.{ZONE}', 'A', '100.64.1.1')
    add(z, f'ula.{ZONE}', 'AAAA', 'fd00::1')
    add(z, ZONE, 'NS', f'ns1.{ZONE}', ttl=3600)
    add(z, f'sub.{ZONE}', 'NS', 'ns.sub.example.com', ttl=3600)
    add(z, f'sub.{ZONE}', 'DS', '12345 13 2 abcdef0123456789', ttl=3600)
    add(z, f'ns.sub.{ZONE}', 'A', '192.0.2.53', auth=False)
    add(z, f'lua.{ZONE}', 'LUA', 'A "ifportup(443, {\'192.0.2.1\'})"')
    add(z, f'old.{ZONE}', 'A', '192.0.2.99', disabled=True)
    return z


# Record sets the source should publish for populate_zone()
PUBLISHED = {
    ('', 'A'),
    ('www', 'A'),
    ('*.apps', 'A'),
    ('v6', 'AAAA'),
    ('blog', 'CNAME'),
    ('', 'MX'),
    ('legacy', 'MX'),
    ('', 'TXT'),
    ('_dmarc', 'TXT'),
    ('sel._domainkey', 'TXT'),
    ('_sip._tcp', 'SRV'),
    ('', 'CAA'),
    ('sip', 'NAPTR'),
}
# ...of which these are dropped by the network filter
FILTERED = {('internal', 'A'), ('mixed', 'A'), ('cgnat', 'A'), ('ula', 'AAAA')}


def octodns_config(pa_url, zone=ZONE, dry_run=True, update=0.3, delete=0.2, networks=REQUIRED_REJECT_NETWORKS):
    return {
        'manager': {'max_workers': 1, 'plan_outputs': {'report': {'class': 'pa_sync.plan.PlanReporter'}}},
        'providers': {
            'poweradmin': {
                'class': 'pa_sync.source.PoweradminSource',
                'url': pa_url,
                'api_key': 'env/POWERADMIN_API_KEY',
                'timeout': 5,
            },
            'route53': {
                'class': 'octodns_route53.Route53Provider',
                'access_key_id': 'env/AWS_ACCESS_KEY_ID',
                'secret_access_key': 'env/AWS_SECRET_ACCESS_KEY',
                'private': False,
                'update_pcent_threshold': update,
                'delete_pcent_threshold': delete,
            },
        },
        'processors': {
            'reject-types': {
                'class': 'octodns.processor.filter.TypeRejectlistFilter',
                'rejectlist': ['NS', 'Route53Provider/ALIAS'],
            },
            'reject-names': {
                'class': 'octodns.processor.filter.NameRejectlistFilter',
                'rejectlist': ['/^_[0-9a-f]{32}(\\.|$)/'],
            },
            'reject-networks': {
                'class': 'octodns.processor.filter.NetworkValueRejectlistFilter',
                'rejectlist': list(networks),
            },
            'ignore-root-ns': {'class': 'octodns.processor.filter.IgnoreRootNsFilter'},
            'normalize-targets': {'class': 'pa_sync.processors.TargetFqdnNormalizer'},
        },
        'zones': {
            f'{zone}.': {
                'always-dry-run': dry_run,
                'sources': ['poweradmin'],
                'processors': ['reject-types', 'reject-networks', 'reject-names', 'ignore-root-ns', 'normalize-targets'],
                'targets': ['route53'],
            }
        },
    }


@pytest.fixture
def pa():
    with MockPoweradmin() as mock:
        mock.zone_id = populate_zone(mock)
        yield mock


def _list_health_checks(self):
    # moto omits the pagination fields real Route53 always returns (octodns-route53 reads IsTruncated)
    return ActionResult(
        {'HealthChecks': self.backend.list_health_checks(), 'IsTruncated': False, 'Marker': '', 'MaxItems': '100'}
    )


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setattr(MotoRoute53Responses, 'list_health_checks', _list_health_checks)
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.delenv('AWS_PROFILE', raising=False)
    with mock_aws():
        client = boto3.client('route53')
        hz = client.create_hosted_zone(Name=f'{ZONE}.', CallerReference='test')['HostedZone']
        client.hosted_zone_id = hz['Id'].split('/')[-1]
        yield client


@pytest.fixture
def make_settings(tmp_path, monkeypatch, pa, aws):
    monkeypatch.setenv('POWERADMIN_API_KEY', pa.api_key)

    def make(dry_run=True, **cfg):
        path = tmp_path / 'octodns.yaml'
        path.write_text(yaml.safe_dump(octodns_config(pa.url, dry_run=dry_run, **cfg)))
        env = {
            'PA_SYNC_ZONE': ZONE,
            'PA_SYNC_POWERADMIN_URL': pa.url,
            'PA_SYNC_ALLOW_HTTP': 'true',
            'PA_SYNC_HOSTED_ZONE_ID': aws.hosted_zone_id,
            'PA_SYNC_OCTODNS_CONFIG': str(path),
            'PA_SYNC_DRY_RUN': str(dry_run).lower(),
        }
        return Settings.from_env(env)

    return make


def rrsets(client, zone_id):
    out = {}
    for page in client.get_paginator('list_resource_record_sets').paginate(HostedZoneId=zone_id):
        for rr in page['ResourceRecordSets']:
            out[(rr['Name'], rr['Type'])] = rr
    return out


@pytest.fixture(autouse=True)
def _no_real_aws(monkeypatch):
    # Belt and braces: never let a test reach real AWS with ambient credentials
    monkeypatch.setenv('AWS_CONFIG_FILE', os.devnull)
    monkeypatch.setenv('AWS_SHARED_CREDENTIALS_FILE', os.devnull)
    monkeypatch.setenv('AWS_EC2_METADATA_DISABLED', 'true')
