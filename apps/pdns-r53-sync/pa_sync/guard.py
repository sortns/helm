"""Route53 hosted zone guard.

octoDNS resolves the target zone by name and creates a new hosted zone when none is found.
Before every sync we make sure the zone it is going to pick is exactly the configured one.
"""

import boto3
from botocore.config import Config

# Fail fast when AWS is unreachable instead of hanging a sync (and SIGTERM) for minutes
BOTO_CONFIG = Config(connect_timeout=5, read_timeout=20, retries={'max_attempts': 3, 'mode': 'standard'})


class GuardError(Exception):
    pass


def check_hosted_zone(zone_fqdn, hosted_zone_id, client=None):
    client = client or boto3.client('route53', config=BOTO_CONFIG)
    try:
        hz = client.get_hosted_zone(Id=hosted_zone_id)['HostedZone']
    except client.exceptions.NoSuchHostedZone:
        raise GuardError(f'hosted zone {hosted_zone_id} does not exist') from None
    if hz['Name'].lower() != zone_fqdn.lower():
        raise GuardError(f'hosted zone {hosted_zone_id} is {hz["Name"]}, expected {zone_fqdn}')
    if hz.get('Config', {}).get('PrivateZone'):
        raise GuardError(f'hosted zone {hosted_zone_id} is private')

    resp = client.list_hosted_zones_by_name(DNSName=zone_fqdn, MaxItems='100')
    public = [
        z['Id'].split('/')[-1]
        for z in resp['HostedZones']
        if z['Name'].lower() == zone_fqdn.lower() and not z.get('Config', {}).get('PrivateZone')
    ]
    if public != [hosted_zone_id]:
        raise GuardError(f'expected exactly one public hosted zone {zone_fqdn} ({hosted_zone_id}), found {public}')
