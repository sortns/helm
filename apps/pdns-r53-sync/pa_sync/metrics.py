from prometheus_client import Counter, Gauge, Histogram, Info

from . import __version__

BUILD_INFO = Info('pa_sync_build', 'pdns-r53-sync build information')
BUILD_INFO.info({'version': __version__})

DRY_RUN = Gauge('pa_sync_dry_run', '1 when the plan is only logged and never applied to Route53')
SOURCE_SERIAL = Gauge('pa_sync_source_serial', 'Last SOA serial read from Poweradmin')
SYNCED_SERIAL = Gauge('pa_sync_synced_serial', 'SOA serial of the last successful sync')
POLLS = Counter('pa_sync_polls_total', 'SOA serial polls')
POLL_ERRORS = Counter('pa_sync_poll_errors_total', 'Failed SOA serial polls')
SYNCS = Counter('pa_sync_syncs_total', 'Sync attempts', ['reason', 'result'])
SYNC_DURATION = Histogram(
    'pa_sync_sync_duration_seconds', 'Duration of a sync run', buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300)
)
LAST_SUCCESS = Gauge('pa_sync_last_success_timestamp_seconds', 'Unix time of the last successful sync')
LAST_ATTEMPT = Gauge('pa_sync_last_attempt_timestamp_seconds', 'Unix time of the last sync attempt')
UNSAFE_PLANS = Counter('pa_sync_unsafe_plans_total', 'Syncs refused by octoDNS safety thresholds (TooMuchChange etc.)')
HOSTED_ZONE_OK = Gauge('pa_sync_hosted_zone_check_ok', '1 when the Route53 hosted zone guard passed on the last sync')
PLANNED_CHANGES = Gauge('pa_sync_planned_changes', 'Changes in the most recent plan', ['action'])
APPLIED_CHANGES = Counter('pa_sync_applied_changes_total', 'Changes applied to Route53')
SOURCE_RECORDS = Gauge('pa_sync_source_records', 'Record sets read from Poweradmin and offered to octoDNS')
SKIPPED_RECORDS = Gauge(
    'pa_sync_skipped_records', 'Poweradmin records not published to Route53 on the last read', ['type', 'reason']
)

for _action in ('create', 'update', 'delete'):
    PLANNED_CHANGES.labels(_action).set(0)
