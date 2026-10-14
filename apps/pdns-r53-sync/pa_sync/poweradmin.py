"""Minimal read-only client for the Poweradmin API v2 (verified against 4.2.x).

Response shapes (Poweradmin 4.2.6):
  GET /api/v2/zones?name=<zone>         -> {"success": true, "data": {"zones": [{"id", "name", ...}]}}
  GET /api/v2/zones/{id}/records[?type] -> {"success": true, "data": [{"id", "name", "type", "content",
                                            "ttl", "priority", "disabled", ...}]}
Record names are FQDNs without the trailing dot; the records list is not paginated.
"""

import logging

import requests

from . import __version__

log = logging.getLogger('pa_sync.poweradmin')


class PoweradminError(Exception):
    pass


class ZoneNotFound(PoweradminError):
    pass


class Poweradmin:
    def __init__(self, url, api_key, timeout=10.0, verify_tls=True):
        if not api_key:
            raise PoweradminError('Poweradmin API key is empty')
        self.base = url.rstrip('/') + '/api/v2'
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = verify_tls
        # Header auth only: Poweradmin also accepts ?api_key=, which would leak into access logs
        self.session.headers.update(
            {
                'X-API-Key': api_key,
                'Accept': 'application/json',
                'User-Agent': f'pdns-r53-sync/{__version__}',
            }
        )

    def _get(self, path, params=None):
        try:
            resp = self.session.get(self.base + path, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            # The exception text carries the URL only, never headers
            raise PoweradminError(f'GET {path}: {e.__class__.__name__}: {e}') from None
        try:
            body = resp.json()
        except ValueError:
            raise PoweradminError(f'GET {path}: HTTP {resp.status_code}, non-JSON response') from None
        if resp.status_code == 404 and path.startswith('/zones/'):
            raise ZoneNotFound(f'GET {path}: {body.get("message", "not found")}')
        if resp.status_code != 200 or body.get('success') is not True:
            # Disabled API answers 403 {"error": true, "message": ...} without "success"
            raise PoweradminError(f'GET {path}: HTTP {resp.status_code}: {body.get("message", "unexpected response")}')
        return body['data']

    def find_zone_id(self, zone_name):
        name = zone_name.rstrip('.')
        zones = self._get('/zones', {'name': name})['zones']
        matches = [z for z in zones if z.get('name', '').lower() == name.lower()]
        if len(matches) != 1:
            raise PoweradminError(
                f"zone '{name}': expected exactly one match, got {len(matches)} "
                '(is the API key owner allowed to view this zone?)'
            )
        return int(matches[0]['id'])

    def records(self, zone_id, rtype=None):
        params = {'type': rtype} if rtype else None
        data = self._get(f'/zones/{zone_id}/records', params)
        if not isinstance(data, list):
            raise PoweradminError(f'zone {zone_id}: records response is not a list')
        return data

    def soa_serial(self, zone_id):
        soa = [r for r in self.records(zone_id, 'SOA') if r.get('type') == 'SOA']
        if len(soa) != 1:
            raise PoweradminError(f'zone {zone_id}: expected one SOA record, got {len(soa)}')
        # PowerDNS SOA content: "mname rname serial refresh retry expire minimum"
        parts = soa[0]['content'].split()
        try:
            return int(parts[2])
        except (IndexError, ValueError):
            raise PoweradminError(f'zone {zone_id}: cannot parse SOA serial') from None
