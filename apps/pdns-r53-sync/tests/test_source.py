from conftest import DKIM, PUBLISHED, ZONE

from pa_sync.source import convert


def rec(name, rtype, content, ttl=300, priority=0, **kw):
    return {'name': name, 'type': rtype, 'content': content, 'ttl': ttl, 'priority': priority, **kw}


def test_full_zone(pa):
    rrsets, skipped = convert(ZONE, pa.zones[pa.zone_id]['records'])
    assert set(rrsets) - {('internal', 'A'), ('mixed', 'A'), ('cgnat', 'A'), ('ula', 'AAAA')} == PUBLISHED
    reasons = {(t, r) for t, r, _ in skipped}
    assert reasons == {
        ('NS', 'ns'),
        ('DS', 'delegation'),
        ('A', 'non-auth'),
        ('LUA', 'unsupported'),
        ('A', 'disabled'),
    }


def test_names_are_relative_and_lowercase():
    rrsets, _ = convert('Example.com.', [rec('WWW.example.com', 'A', '192.0.2.1'), rec('example.com', 'A', '192.0.2.2')])
    assert set(rrsets) == {('www', 'A'), ('', 'A')}


def test_out_of_zone_is_skipped():
    rrsets, skipped = convert(ZONE, [rec('example.org', 'A', '192.0.2.1'), rec('badexample.com', 'A', '192.0.2.1')])
    assert rrsets == {}
    assert [r for _, r, _ in skipped] == ['out-of-zone', 'out-of-zone']


def test_mx_priority_field_and_embedded():
    rrsets, _ = convert(
        ZONE,
        [
            rec(ZONE, 'MX', 'mail.example.com', priority=10),
            rec(ZONE, 'MX', '20 mail2.example.com.', priority=0),
        ],
    )
    assert rrsets[('', 'MX')]['values'] == [
        {'preference': 10, 'exchange': 'mail.example.com.'},
        {'preference': 20, 'exchange': 'mail2.example.com.'},
    ]


def test_srv_priority_field_and_null_target():
    rrsets, _ = convert(
        ZONE,
        [
            rec(f'_sip._tcp.{ZONE}', 'SRV', '5 5060 sip.example.com', priority=10),
            rec(f'_sip._tcp.{ZONE}', 'SRV', '30 0 0 .', priority=None),
        ],
    )
    assert rrsets[('_sip._tcp', 'SRV')]['values'] == [
        {'priority': 10, 'weight': 5, 'port': 5060, 'target': 'sip.example.com.'},
        {'priority': 30, 'weight': 0, 'port': 0, 'target': '.'},
    ]


def test_txt_single_and_multi_string():
    rrsets, _ = convert(
        ZONE,
        [
            # Poweradmin strips the outer quotes of single-string values
            rec(ZONE, 'TXT', 'v=DMARC1; p=reject'),
            rec(ZONE, 'TXT', DKIM),
            rec(ZONE, 'TXT', 'say \\"hi\\"'),
        ],
    )
    values = rrsets[('', 'TXT')]['values']
    assert values[0] == '"v=DMARC1\\; p=reject"'
    assert values[1].startswith('"v=DKIM1\\; k=rsa\\; p=AAAA') and '" "BBBB' in values[1]
    assert values[2] == '"say \\"hi\\""'


def test_cname_to_fqdn_and_duplicates_collapse():
    rrsets, _ = convert(ZONE, [rec(f'a.{ZONE}', 'CNAME', 'b.example.net'), rec(f'a.{ZONE}', 'CNAME', 'b.example.net')])
    assert rrsets[('a', 'CNAME')] == {'type': 'CNAME', 'ttl': 300, 'value': 'b.example.net.'}


def test_conflicting_cname_is_skipped():
    rrsets, skipped = convert(ZONE, [rec(f'a.{ZONE}', 'CNAME', 'b.example.net'), rec(f'a.{ZONE}', 'CNAME', 'c.example.net')])
    assert rrsets == {}
    assert {r for _, r, _ in skipped} == {'invalid'}


def test_mixed_ttl_uses_minimum():
    rrsets, _ = convert(ZONE, [rec(ZONE, 'A', '192.0.2.1', ttl=600), rec(ZONE, 'A', '192.0.2.2', ttl=60)])
    assert rrsets[('', 'A')]['ttl'] == 60
    assert rrsets[('', 'A')]['_mixed_ttl'] == [60, 600]


def test_caa_naptr():
    rrsets, _ = convert(
        ZONE,
        [
            rec(ZONE, 'CAA', '0 issuewild ";"'),
            rec(ZONE, 'NAPTR', '100 10 "S" "SIP+D2U" "" _sip._udp.example.com'),
        ],
    )
    assert rrsets[('', 'CAA')]['values'] == [{'flags': 0, 'tag': 'issuewild', 'value': ';'}]
    assert rrsets[('', 'NAPTR')]['values'][0]['replacement'] == '_sip._udp.example.com.'


def test_garbage_content_is_skipped_not_fatal():
    rrsets, skipped = convert(ZONE, [rec(ZONE, 'MX', '1 2 3'), rec(ZONE, 'SRV', 'nope')])
    assert rrsets == {}
    assert [r for _, r, _ in skipped] == ['invalid', 'invalid']
