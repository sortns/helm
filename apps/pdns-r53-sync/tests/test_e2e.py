"""End-to-end: mock Poweradmin -> octoDNS -> moto Route53."""

from dataclasses import replace

from conftest import PUBLISHED, ZONE, rrsets

from pa_sync import metrics, plan
from pa_sync.daemon import sync_once


def change(client, zone_id, action, name, rtype, values, ttl=300):
    client.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch={
            'Changes': [
                {
                    'Action': action,
                    'ResourceRecordSet': {
                        'Name': name,
                        'Type': rtype,
                        'TTL': ttl,
                        'ResourceRecords': [{'Value': v} for v in values],
                    },
                }
            ]
        },
    )


def published_keys():
    return {(f'{n}.{ZONE}.' if n else f'{ZONE}.', t) for n, t in PUBLISHED}


def test_dry_run_changes_nothing(make_settings, aws):
    before = rrsets(aws, aws.hosted_zone_id)
    assert sync_once(make_settings(dry_run=True), 'startup', 1)
    assert plan.LAST == {'create': len(PUBLISHED), 'update': 0, 'delete': 0}
    assert rrsets(aws, aws.hosted_zone_id) == before


def test_live_sync_is_complete_and_idempotent(make_settings, aws):
    settings = make_settings(dry_run=False)
    root_ns = rrsets(aws, aws.hosted_zone_id)[(f'{ZONE}.', 'NS')]

    assert sync_once(settings, 'startup', 1)
    assert plan.LAST['create'] == len(PUBLISHED)
    after = rrsets(aws, aws.hosted_zone_id)
    assert set(after) == published_keys() | {(f'{ZONE}.', 'NS'), (f'{ZONE}.', 'SOA')}
    # Root NS stay the native ones
    assert after[(f'{ZONE}.', 'NS')] == root_ns
    assert after[(f'www.{ZONE}.', 'A')]['ResourceRecords'] == [{'Value': '192.0.2.10'}, {'Value': '192.0.2.11'}]
    assert after[(f'{ZONE}.', 'MX')]['ResourceRecords'] == [
        {'Value': f'10 mail.{ZONE}.'},
        {'Value': f'20 mail2.{ZONE}.'},
    ]
    assert after[(f'_sip._tcp.{ZONE}.', 'SRV')]['ResourceRecords'] == [{'Value': f'10 5 5060 sip.{ZONE}.'}]
    # octodns-route53 sends RFC 1035 escaped semicolons, which DNS serves as plain ';'
    assert after[(f'_dmarc.{ZONE}.', 'TXT')]['ResourceRecords'] == [
        {'Value': '"v=DMARC1\\; p=reject\\; rua=mailto:dmarc@example.com"'}
    ]
    dkim = after[(f'sel._domainkey.{ZONE}.', 'TXT')]['ResourceRecords'][0]['Value']
    assert dkim.startswith('"v=DKIM1\\; k=rsa\\; p=AAAA') and all(len(c) <= 255 for c in dkim[1:-1].split('" "'))

    # Second run: nothing to do (covers TXT chunking, CAA, NAPTR, SRV round trips)
    assert sync_once(settings, 'periodic', 1)
    assert plan.LAST == {'create': 0, 'update': 0, 'delete': 0}


def test_update_and_rollback_of_manual_edits(make_settings, aws, pa):
    settings = make_settings(dry_run=False)
    assert sync_once(settings, 'startup', 1)

    # Change in Poweradmin
    for rec in pa.zones[pa.zone_id]['records']:
        if rec['name'] == f'www.{ZONE}' and rec['content'] == '192.0.2.11':
            rec['content'] = '192.0.2.12'
    pa.bump_serial(pa.zone_id)
    # Manual edits in Route53: an extra record and a modified one
    change(aws, aws.hosted_zone_id, 'CREATE', f'rogue.{ZONE}.', 'A', ['198.51.100.1'])
    change(aws, aws.hosted_zone_id, 'UPSERT', f'v6.{ZONE}.', 'AAAA', ['2001:db8::99'])

    assert sync_once(settings, 'serial', 2)
    assert plan.LAST == {'create': 0, 'update': 2, 'delete': 1}
    after = rrsets(aws, aws.hosted_zone_id)
    assert (f'rogue.{ZONE}.', 'A') not in after
    assert after[(f'v6.{ZONE}.', 'AAAA')]['ResourceRecords'] == [{'Value': '2001:db8::1'}]
    assert {'Value': '192.0.2.12'} in after[(f'www.{ZONE}.', 'A')]['ResourceRecords']


def test_private_and_ns_records_in_route53_are_left_alone(make_settings, aws):
    change(aws, aws.hosted_zone_id, 'CREATE', f'legacy-internal.{ZONE}.', 'A', ['10.9.9.9'])
    change(aws, aws.hosted_zone_id, 'CREATE', f'delegated.{ZONE}.', 'NS', ['ns-1.awsdns-01.org.'])
    settings = make_settings(dry_run=False)
    assert sync_once(settings, 'startup', 1)
    assert plan.LAST['delete'] == 0
    after = rrsets(aws, aws.hosted_zone_id)
    assert (f'legacy-internal.{ZONE}.', 'A') in after
    assert (f'delegated.{ZONE}.', 'NS') in after
    assert not {(f'internal.{ZONE}.', 'A'), (f'mixed.{ZONE}.', 'A'), (f'ula.{ZONE}.', 'AAAA')} & set(after)


def test_too_much_change_is_refused(make_settings, aws):
    for i in range(20):
        change(aws, aws.hosted_zone_id, 'CREATE', f'old{i}.{ZONE}.', 'A', [f'198.51.100.{i + 1}'])
    before = rrsets(aws, aws.hosted_zone_id)
    unsafe = metrics.UNSAFE_PLANS._value.get()

    assert not sync_once(make_settings(dry_run=False), 'startup', 1)
    assert metrics.UNSAFE_PLANS._value.get() == unsafe + 1
    # The plan was still reported so a human can review it
    assert plan.LAST['delete'] == 20
    assert rrsets(aws, aws.hosted_zone_id) == before


def test_guard_wrong_zone_id(make_settings, aws):
    other = aws.create_hosted_zone(Name='example.org.', CallerReference='other')['HostedZone']['Id'].split('/')[-1]
    settings = replace(make_settings(dry_run=False), hosted_zone_id=other)
    assert not sync_once(settings, 'startup', 1)
    assert metrics.HOSTED_ZONE_OK._value.get() == 0


def test_guard_missing_zone_never_creates_one(make_settings, aws):
    settings = make_settings(dry_run=False)
    aws.delete_hosted_zone(Id=aws.hosted_zone_id)
    assert not sync_once(settings, 'startup', 1)
    assert aws.list_hosted_zones()['HostedZones'] == []


def test_guard_duplicate_public_zone(make_settings, aws):
    aws.create_hosted_zone(Name=f'{ZONE}.', CallerReference='dup')
    assert not sync_once(make_settings(dry_run=False), 'startup', 1)
    assert len(rrsets(aws, aws.hosted_zone_id)) == 2  # only SOA + NS


def test_poweradmin_down_fails_cleanly(make_settings, aws, pa):
    settings = make_settings(dry_run=False)
    pa.api_enabled = False
    assert not sync_once(settings, 'startup', 1)
    assert len(rrsets(aws, aws.hosted_zone_id)) == 2
