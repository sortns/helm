"""Records that exist only in Route53, and data written by other tools (Terraform), survive the mirror."""

from conftest import ZONE, rrsets
from test_e2e import change

from pa_sync import metrics, plan
from pa_sync.daemon import sync_once


def alias(client, zone_id, name):
    client.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch={
            'Changes': [
                {
                    'Action': 'CREATE',
                    'ResourceRecordSet': {
                        'Name': name,
                        'Type': 'A',
                        'AliasTarget': {
                            'HostedZoneId': 'Z2FDTNDATAQYW2',
                            'DNSName': 'd111111abcdef8.cloudfront.net.',
                            'EvaluateTargetHealth': False,
                        },
                    },
                }
            ]
        },
    )


def test_aliases_and_acm_validation_survive(make_settings, aws):
    """CloudFront aliases and ACM validation CNAMEs cannot live in PowerDNS and must not be deleted."""
    alias(aws, aws.hosted_zone_id, f'cdn.{ZONE}.')
    acm = f'_0123456789abcdef0123456789abcdef.cdn.{ZONE}.'
    change(aws, aws.hosted_zone_id, 'CREATE', acm, 'CNAME', ['_fedcba9876543210fedcba9876543210.abcdefghij.acm-validations.aws.'], 60)
    apex_acm = f'_00112233445566778899aabbccddeeff.{ZONE}.'
    change(aws, aws.hosted_zone_id, 'CREATE', apex_acm, 'CNAME', ['_ffeeddccbbaa99887766554433221100.xyz.acm-validations.aws.'], 60)

    assert sync_once(make_settings(dry_run=False), 'startup', 1)
    assert plan.LAST['delete'] == 0
    after = rrsets(aws, aws.hosted_zone_id)
    assert 'AliasTarget' in after[(f'cdn.{ZONE}.', 'A')]
    assert (acm, 'CNAME') in after and (apex_acm, 'CNAME') in after


def test_other_underscore_names_are_still_managed(make_settings, aws):
    """Only exact ACM-shaped names are ignored; other _names are still mirrored (and cleaned up)."""
    change(aws, aws.hosted_zone_id, 'CREATE', f'_0123456789abcdef.{ZONE}.', 'CNAME', ['x.example.net.'])
    change(aws, aws.hosted_zone_id, 'CREATE', f'_acme-challenge.old.{ZONE}.', 'TXT', ['"token"'])
    assert sync_once(make_settings(dry_run=False), 'startup', 1)
    assert plan.LAST['delete'] == 2


def test_dotless_targets_in_route53_are_not_updates(make_settings, aws):
    """Terraform's .fqdn has no trailing dot; Route53 treats such names as FQDNs, so do we."""
    settings = make_settings(dry_run=False)
    assert sync_once(settings, 'startup', 1)
    change(aws, aws.hosted_zone_id, 'UPSERT', f'blog.{ZONE}.', 'CNAME', [f'www.{ZONE}'])
    change(aws, aws.hosted_zone_id, 'UPSERT', f'{ZONE}.', 'MX', [f'10 mail.{ZONE}', f'20 mail2.{ZONE}'])
    change(aws, aws.hosted_zone_id, 'UPSERT', f'_sip._tcp.{ZONE}.', 'SRV', [f'10 5 5060 sip.{ZONE}'])
    assert sync_once(settings, 'periodic', 1)
    assert plan.LAST == {'create': 0, 'update': 0, 'delete': 0}


def test_dotless_target_with_real_change_is_updated(make_settings, aws):
    settings = make_settings(dry_run=False)
    assert sync_once(settings, 'startup', 1)
    change(aws, aws.hosted_zone_id, 'UPSERT', f'blog.{ZONE}.', 'CNAME', [f'elsewhere.{ZONE}'])
    assert sync_once(settings, 'periodic', 1)
    assert plan.LAST == {'create': 0, 'update': 1, 'delete': 0}
    assert rrsets(aws, aws.hosted_zone_id)[(f'blog.{ZONE}.', 'CNAME')]['ResourceRecords'] == [{'Value': f'www.{ZONE}.'}]


def test_txt_whitespace_is_preserved(make_settings, aws, pa):
    pa.add(pa.zone_id, f'_trail.{ZONE}', 'TXT', '"v=DMARC1; p=none; sp=none "')
    settings = make_settings(dry_run=False)
    assert sync_once(settings, 'startup', 1)
    value = rrsets(aws, aws.hosted_zone_id)[(f'_trail.{ZONE}.', 'TXT')]['ResourceRecords'][0]['Value']
    assert value == '"v=DMARC1\\; p=none\\; sp=none "'
    assert sync_once(settings, 'periodic', 1)
    assert plan.LAST == {'create': 0, 'update': 0, 'delete': 0}


def test_unusual_records_are_mirrored_not_deleted(make_settings, aws, pa):
    """octoDNS rejects an SRV named "dc._msdcs"; skipping it would delete the live record."""
    change(aws, aws.hosted_zone_id, 'CREATE', f'dc._msdcs.{ZONE}.', 'SRV', [f'0 100 389 dc1.{ZONE}'], 600)
    pa.add(pa.zone_id, f'dc._msdcs.{ZONE}', 'SRV', f'100 389 dc1.{ZONE}', ttl=600, priority=0)
    assert sync_once(make_settings(dry_run=False), 'startup', 1)
    assert plan.LAST['delete'] == 0
    assert (f'dc._msdcs.{ZONE}.', 'SRV') in rrsets(aws, aws.hosted_zone_id)
    assert metrics.LENIENT_RECORDS._value.get() == 1
