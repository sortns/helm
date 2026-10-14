"""octoDNS source that reads one zone from the Poweradmin API v2.

The source is the single place where Poweradmin's storage quirks are translated into
standard record data:
  * names are FQDNs without the trailing dot;
  * MX/SRV priority lives in a separate ``priority`` field (PowerDNS 4 may also embed it in content);
  * single-string TXT values come back with the outer quotes stripped, multi-string ones raw;
  * disabled records are returned too.
NS records are never offered to octoDNS: root NS in Route53 stay the native awsdns ones and
delegations are not mirrored. Consequently DS records (only valid next to a delegation) and
non-authoritative rows (glue / records below a delegation, ``auth: false``) are skipped too.
"""

import logging
from collections import Counter, defaultdict

from octodns.record import Record
from octodns.record.exception import ValidationError
from octodns.source.base import BaseSource

from . import metrics
from .poweradmin import Poweradmin

SUPPORTED = ('A', 'AAAA', 'CAA', 'CNAME', 'MX', 'NAPTR', 'PTR', 'SPF', 'SRV', 'TXT')
# Only meaningful together with a delegation, which is never mirrored
DELEGATION = {'NS', 'DS'}
# Not records to mirror: SOA belongs to Route53, NS are excluded by design
IGNORED = {'SOA'}


def _fqdn(target):
    target = target.strip()
    if not target or target == '.':
        return '.'
    return target if target.endswith('.') else target + '.'


def _txt(content):
    # Multi-string values come back in presentation format; single strings lost their outer quotes
    # and must be kept byte for byte (leading/trailing spaces are part of the value)
    if content.strip().startswith('"') and content.strip().endswith('"'):
        content = content.strip()
    else:
        content = f'"{content}"'
    return Record.registered_types()['TXT']._value_type.normalize_raw_text(content)


def _value(rtype, content, priority):
    """Convert one Poweradmin record into an octoDNS value (str or dict)."""
    value_type = Record.registered_types()[rtype]._value_type
    if rtype in ('A', 'AAAA'):
        return content.strip()
    if rtype in ('CNAME', 'PTR'):
        return _fqdn(content)
    if rtype in ('TXT', 'SPF'):
        return _txt(content)
    if rtype == 'MX':
        parts = content.split()
        if len(parts) == 2 and parts[0].isdigit():
            pref, exchange = parts
        elif len(parts) == 1:
            pref, exchange = priority or 0, parts[0]
        else:
            raise ValueError(f'unexpected MX content {content!r}')
        return {'preference': int(pref), 'exchange': _fqdn(exchange)}
    if rtype == 'SRV':
        parts = content.split()
        if len(parts) == 3:
            parts = [priority or 0] + parts
        if len(parts) != 4:
            raise ValueError(f'unexpected SRV content {content!r}')
        prio, weight, port, target = parts
        return {'priority': int(prio), 'weight': int(weight), 'port': int(port), 'target': _fqdn(target)}
    value = dict(value_type.from_rdata_text(content.strip()))
    if rtype == 'NAPTR':
        value['replacement'] = _fqdn(value['replacement'])
    return value


def convert(zone_name, records):
    """Group Poweradmin records into octoDNS record sets.

    Returns ``(rrsets, skipped)`` where rrsets maps (name, type) -> {'type', 'ttl', 'values'}
    and skipped is a list of (type, reason, fqdn) tuples.
    """
    zone = zone_name.rstrip('.').lower()
    grouped = defaultdict(list)
    skipped = []
    for rec in records:
        rtype = (rec.get('type') or '').upper()
        fqdn = (rec.get('name') or '').rstrip('.').lower()
        if not rtype or rtype in IGNORED:
            continue
        if rec.get('disabled'):
            skipped.append((rtype, 'disabled', fqdn))
            continue
        if rtype in DELEGATION:
            skipped.append((rtype, 'ns' if rtype == 'NS' else 'delegation', fqdn))
            continue
        if rec.get('auth') is False:
            skipped.append((rtype, 'non-auth', fqdn))
            continue
        if rtype not in SUPPORTED:
            skipped.append((rtype, 'unsupported', fqdn))
            continue
        if fqdn == zone:
            name = ''
        elif fqdn.endswith('.' + zone):
            name = fqdn[: -len(zone) - 1]
        else:
            skipped.append((rtype, 'out-of-zone', fqdn))
            continue
        try:
            value = _value(rtype, rec.get('content') or '', rec.get('priority'))
        except (ValueError, KeyError, TypeError):
            skipped.append((rtype, 'invalid', fqdn))
            continue
        grouped[(name, rtype)].append((int(rec.get('ttl') or 0), value))

    rrsets = {}
    for (name, rtype), items in grouped.items():
        ttls = {ttl for ttl, _ in items}
        values = []
        for _, value in items:
            if value not in values:
                values.append(value)
        if rtype == 'CNAME':
            if len(values) != 1:
                skipped.extend((rtype, 'invalid', name or zone) for _ in items)
                continue
            data = {'type': rtype, 'ttl': min(ttls), 'value': values[0]}
        else:
            data = {'type': rtype, 'ttl': min(ttls), 'values': values}
        if len(ttls) > 1:
            data['_mixed_ttl'] = sorted(ttls)
        rrsets[(name, rtype)] = data
    return rrsets, skipped


class PoweradminSource(BaseSource):
    SUPPORTS_GEO = False
    SUPPORTS_DYNAMIC = False
    SUPPORTS = set(SUPPORTED)

    def __init__(self, id, url, api_key, timeout=10.0, verify_tls=True, *args, **kwargs):
        self.log = logging.getLogger(f'PoweradminSource[{id}]')
        super().__init__(id, *args, **kwargs)
        self.client = Poweradmin(url, api_key, timeout=float(timeout), verify_tls=verify_tls)

    def populate(self, zone, target=False, lenient=False):
        if target:
            raise NotImplementedError('PoweradminSource is read-only')
        zone_id = self.client.find_zone_id(zone.name)
        records = self.client.records(zone_id)
        rrsets, skipped = convert(zone.name, records)

        added = lenient_count = 0
        for (name, rtype), data in sorted(rrsets.items()):
            mixed = data.pop('_mixed_ttl', None)
            if mixed:
                self.log.warning('populate: %s %s has mixed TTLs %s, using %d', name or '@', rtype, mixed, data['ttl'])
            try:
                record = Record.new(zone, name, data, source=self, lenient=lenient)
            except ValidationError as e:
                # Mirror what PowerDNS serves even when octoDNS finds it unusual (e.g. SRV named
                # "dc._msdcs"); skipping it would make the sync delete the live record in Route53
                reasons = '; '.join(e.reasons)
                self.log.warning('populate: %s %s is not strictly valid (%s), mirroring as-is', name or '@', rtype, reasons)
                lenient_count += 1
                record = Record.new(zone, name, data, source=self, lenient=True)
            zone.add_record(record, lenient=True)
            added += 1

        metrics.SOURCE_RECORDS.set(added)
        metrics.LENIENT_RECORDS.set(lenient_count)
        metrics.SKIPPED_RECORDS.clear()
        for (rtype, reason), count in Counter((t, r) for t, r, _ in skipped).items():
            metrics.SKIPPED_RECORDS.labels(rtype, reason).set(count)
        for rtype, reason, fqdn in sorted(set(skipped)):
            if reason != 'ns':
                self.log.info('populate: skipped %s %s (%s)', rtype, fqdn, reason)
        self.log.info('populate: zone=%s id=%d records=%d rrsets=%d skipped=%d', zone.name, zone_id, len(records), added, len(skipped))
        return False
