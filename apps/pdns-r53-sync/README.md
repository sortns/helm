# pdns-r53-sync (app)

Source of the `ghcr.io/sortns/pdns-r53-sync` image used by [`charts/pdns-r53-sync`](../../charts/pdns-r53-sync),
which documents deployment, Poweradmin/IAM preparation and metrics.

| Path | |
|---|---|
| `pa_sync/poweradmin.py` | read-only Poweradmin API v2 client (formats verified against 4.2.6) |
| `pa_sync/source.py` | octoDNS source: Poweradmin records → octoDNS records, skip rules |
| `pa_sync/processors.py` | Route53-side normalisation (dot-less targets written by other tools count as FQDNs) |
| `pa_sync/plan.py` | plan output: one `plan: Create/Update/Delete` log line per change + metrics |
| `pa_sync/guard.py` | refuses to sync unless the pinned hosted zone is the only public one with that name |
| `pa_sync/settings.py` | env settings, `<NAME>__FILE` secrets, invariant checks on the octoDNS config |
| `pa_sync/daemon.py` | serial polling loop, `/metrics` and `/healthz` on :9100 |
| `pa_sync/__main__.py` | `python -m pa_sync run|plan|check` |
| `tests/` | unit tests, Poweradmin mock, moto e2e, chart rendering checks |

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install --no-deps -r requirements.txt && .venv/bin/pip check
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q        # chart tests need helm on PATH
```

`requirements.txt` is the complete pinned set for CPython 3.12 and is installed with `--no-deps`.

## Releasing

Version tags are immutable. For app changes bump `__version__` in `pa_sync/__init__.py` together with
`appVersion` (and `version`) in `charts/pdns-r53-sync/Chart.yaml`; CI checks they match. On merge to
`master` the workflow pushes `ghcr.io/sortns/pdns-r53-sync:<version>` (skipped if that tag exists) and
chart-releaser publishes the chart.
