"""octoDNS processors specific to mirroring into Route53."""

import logging

from octodns.processor.base import BaseProcessor
from octodns.record import Record

log = logging.getLogger('pa_sync.processors')


def _dot(name):
    return name if not name or name.endswith('.') else name + '.'


class TargetFqdnNormalizer(BaseProcessor):
    """Treat dot-less target names already in Route53 as FQDNs, like Route53 itself does.

    Records created outside octoDNS (Terraform's ``.fqdn``, the console) often store
    ``www.example.com`` instead of ``www.example.com.``. Both resolve identically, but octoDNS would
    plan an Update for each one, which is noise at best and trips the update threshold at worst.
    Only the existing (Route53) side is normalised; nothing is written because of it.
    """

    def process_target_zone(self, existing, target, lenient=False):
        changed = 0
        for record in list(existing.records):
            data = record.data
            if record._type in ('CNAME', 'DNAME'):
                new = _dot(data['value'])
                if new == data['value']:
                    continue
                data['value'] = new
            elif record._type == 'PTR':
                values = data.get('values') or [data['value']]
                fixed = [_dot(v) for v in values]
                if fixed == values:
                    continue
                data.pop('value', None)
                data['values'] = fixed
            elif record._type in ('MX', 'SRV'):
                key = 'exchange' if record._type == 'MX' else 'target'
                values = [dict(v) for v in (data.get('values') or [data['value']])]
                fixed = [{**v, key: _dot(v[key])} for v in values]
                if fixed == values:
                    continue
                data.pop('value', None)
                data['values'] = fixed
            else:
                continue
            new_record = Record.new(existing, record.name, {'type': record._type, **data}, source=target, lenient=True)
            existing.add_record(new_record, replace=True, lenient=True)
            changed += 1
        if changed:
            log.info('normalized %d dot-less target names in %s', changed, existing.decoded_name)
        return existing
