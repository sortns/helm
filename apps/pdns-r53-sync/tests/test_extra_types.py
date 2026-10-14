"""TLSA and SSHFP: supported by Route53, not mapped by octodns-route53, added in pa_sync.route53."""

from conftest import ZONE, rrsets
from test_e2e import change

from pa_sync import plan
from pa_sync.daemon import sync_once

TLSA_OLD = '3 1 1 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
TLSA_NEW = '3 1 1 fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210'
SSHFP = '4 2 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'


def tlsa_rr(aws):
    return rrsets(aws, aws.hosted_zone_id)[(f'_25._tcp.mail.{ZONE}.', 'TLSA')]['ResourceRecords']


def test_tlsa_and_sshfp_are_published_and_idempotent(make_settings, aws, pa):
    pa.add(pa.zone_id, f'_25._tcp.mail.{ZONE}', 'TLSA', TLSA_OLD)
    pa.add(pa.zone_id, f'host.{ZONE}', 'SSHFP', SSHFP)
    settings = make_settings(dry_run=False)
    assert sync_once(settings, 'startup', 1)
    assert tlsa_rr(aws) == [{'Value': TLSA_OLD}]
    assert rrsets(aws, aws.hosted_zone_id)[(f'host.{ZONE}.', 'SSHFP')]['ResourceRecords'] == [{'Value': SSHFP}]
    assert sync_once(settings, 'periodic', 1)
    assert plan.LAST == {'create': 0, 'update': 0, 'delete': 0}


def test_existing_tlsa_is_adopted_and_follows_key_rollover(make_settings, aws, pa):
    # Created by Terraform before the mirror existed
    change(aws, aws.hosted_zone_id, 'CREATE', f'_25._tcp.mail.{ZONE}.', 'TLSA', [TLSA_OLD])
    pa.add(pa.zone_id, f'_25._tcp.mail.{ZONE}', 'TLSA', TLSA_OLD)
    settings = make_settings(dry_run=False)
    assert sync_once(settings, 'startup', 1)
    assert plan.LAST['update'] == 0 and plan.LAST['delete'] == 0

    # Key rollover in PowerDNS: new record first (DANE 3 1 1 rollover publishes both), then old removed
    pa.add(pa.zone_id, f'_25._tcp.mail.{ZONE}', 'TLSA', TLSA_NEW)
    pa.bump_serial(pa.zone_id)
    assert sync_once(settings, 'serial', 2)
    assert plan.LAST == {'create': 0, 'update': 1, 'delete': 0}
    assert sorted(v['Value'] for v in tlsa_rr(aws)) == sorted([TLSA_OLD, TLSA_NEW])

    records = pa.zones[pa.zone_id]['records']
    records[:] = [r for r in records if not (r['type'] == 'TLSA' and r['content'] == TLSA_OLD)]
    pa.bump_serial(pa.zone_id)
    assert sync_once(settings, 'serial', 3)
    assert tlsa_rr(aws) == [{'Value': TLSA_NEW}]


def test_tlsa_removed_from_poweradmin_is_removed_from_route53(make_settings, aws):
    change(aws, aws.hosted_zone_id, 'CREATE', f'_25._tcp.mail.{ZONE}.', 'TLSA', [TLSA_OLD])
    assert sync_once(make_settings(dry_run=False), 'startup', 1)
    assert plan.LAST['delete'] == 1
    assert (f'_25._tcp.mail.{ZONE}.', 'TLSA') not in rrsets(aws, aws.hosted_zone_id)
