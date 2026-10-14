"""In-process HTTP server emulating the Poweradmin 4.2.6 API v2 endpoints used by pa_sync.

Mirrors the real quirks: data.zones vs bare data list, FQDN names without trailing dot,
priority in its own field, TXT stored quoted but single strings returned unquoted,
disabled records included, 403 with a different body shape when the API is disabled.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def _strip_txt_quotes(content):
    # Poweradmin RecordRepository::stripTxtQuotes: only single-string values are unquoted
    if len(content) >= 2 and content[0] == '"' and content[-1] == '"' and '" "' not in content:
        return content[1:-1]
    return content


class MockPoweradmin:
    def __init__(self, api_key='test-key'):
        self.api_key = api_key
        self.api_enabled = True
        self.zones = {}
        self.requests = []
        self._next_id = 1
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self._handler())
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def add_zone(self, name, serial=2026101401):
        zone_id = len(self.zones) + 10
        self.zones[zone_id] = {'name': name, 'records': []}
        self.add(zone_id, name, 'SOA', f'ns1.{name} hostmaster.{name} {serial} 10800 3600 604800 3600', 3600)
        return zone_id

    def add(self, zone_id, name, rtype, content, ttl=300, priority=0, disabled=False, auth=True):
        self.zones[zone_id]['records'].append(
            {
                'id': self._next_id,
                'name': name,
                'type': rtype,
                'content': content,
                'ttl': ttl,
                'priority': priority,
                'disabled': disabled,
                'auth': auth,
            }
        )
        self._next_id += 1

    def bump_serial(self, zone_id):
        for rec in self.zones[zone_id]['records']:
            if rec['type'] == 'SOA':
                parts = rec['content'].split()
                parts[2] = str(int(parts[2]) + 1)
                rec['content'] = ' '.join(parts)

    def _handler(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                mock.requests.append((url.path, query, self.headers.get('X-API-Key')))
                if not mock.api_enabled:
                    return self._send(403, {'error': True, 'message': 'The API feature is disabled in the system configuration.'})
                if self.headers.get('X-API-Key') != mock.api_key:
                    return self._send(401, {'success': False, 'data': None, 'message': 'Unauthorized: Invalid credentials'})
                if url.path == '/api/v2/zones':
                    zones = [
                        {'id': zid, 'name': z['name'], 'type': 'MASTER', 'created_at': None}
                        for zid, z in sorted(mock.zones.items(), key=lambda i: i[1]['name'])
                        if 'name' not in query or z['name'] == query['name']
                    ]
                    return self._send(200, {'success': True, 'data': {'zones': zones}, 'message': 'Zones retrieved successfully'})
                m = re.fullmatch(r'/api/v2/zones/(\d+)/records', url.path)
                if m:
                    zone = mock.zones.get(int(m.group(1)))
                    if zone is None:
                        return self._send(404, {'success': False, 'data': None, 'message': 'Zone not found'})
                    out = []
                    for rec in zone['records']:
                        if 'type' in query and rec['type'] != query['type']:
                            continue
                        item = dict(rec)
                        if rec['type'] == 'TXT':
                            item['content'] = _strip_txt_quotes(rec['content'])
                        out.append(item)
                    out.sort(key=lambda r: (r['type'], r['name']))
                    return self._send(200, {'success': True, 'data': out, 'message': 'Records retrieved successfully'})
                return self._send(404, {'error': True, 'message': 'Endpoint not found'})

            def log_message(self, *args):
                pass

        return Handler
