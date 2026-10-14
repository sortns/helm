"""Route53 provider with the record types octodns-route53 does not map yet.

Route53 accepts TLSA and SSHFP (see botocore's RRType enum) and octoDNS core models both, but
octodns-route53 1.3.x has no converters for them, so such records were invisible: never published
and never updated (a TLSA/DANE record left frozen is a mail outage waiting for the next key
rollover). The converters are plain RFC presentation format in both directions.
"""

from octodns.record import Record
from octodns_route53 import provider as _r53

EXTRA_TYPES = ('TLSA', 'SSHFP')


def _values_for_rdata(self, record):
    return [value.to_rdata_text() for value in record.values]


# _Route53Record dispatches on _values_for_<TYPE>; it has no hook for new types otherwise
for _type in EXTRA_TYPES:
    if not hasattr(_r53._Route53Record, f'_values_for_{_type}'):
        setattr(_r53._Route53Record, f'_values_for_{_type}', _values_for_rdata)


class Route53Provider(_r53.Route53Provider):
    SUPPORTS = set(_r53.Route53Provider.SUPPORTS) | set(EXTRA_TYPES)

    def _data_for_rdata(self, rrset):
        value_type = Record.registered_types()[rrset['Type']]._value_type
        return {
            'type': rrset['Type'],
            'ttl': int(rrset['TTL']),
            'values': [dict(value_type.from_rdata_text(rr['Value'])) for rr in rrset['ResourceRecords']],
        }

    _data_for_TLSA = _data_for_rdata
    _data_for_SSHFP = _data_for_rdata
