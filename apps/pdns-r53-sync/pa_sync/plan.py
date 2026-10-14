"""octoDNS plan output: one greppable log line per change plus plan metrics."""

import json
import logging

from octodns.provider.plan import _PlanOutput
from octodns.record.change import Create, Delete, Update

from . import metrics

log = logging.getLogger('pa_sync.plan')

# Summary of the most recent plan, read by the daemon after Manager.sync()
LAST = {'create': 0, 'update': 0, 'delete': 0}


def _fmt(record):
    data = {k: v for k, v in record.data.items() if k != 'octodns'}
    return json.dumps(data, sort_keys=True, default=str)


class PlanReporter(_PlanOutput):
    def run(self, plans, *args, **kwargs):
        counts = {'create': 0, 'update': 0, 'delete': 0}
        for target, plan in plans:
            for change in plan.changes:
                rec = change.record
                if isinstance(change, Create):
                    counts['create'] += 1
                    log.info('plan: Create %s %s %s', rec._type, rec.fqdn, _fmt(change.new))
                elif isinstance(change, Update):
                    counts['update'] += 1
                    log.info(
                        'plan: Update %s %s %s -> %s', rec._type, rec.fqdn, _fmt(change.existing), _fmt(change.new)
                    )
                elif isinstance(change, Delete):
                    counts['delete'] += 1
                    log.info('plan: Delete %s %s %s', rec._type, rec.fqdn, _fmt(change.existing))
        LAST.update(counts)
        for action, count in counts.items():
            metrics.PLANNED_CHANGES.labels(action).set(count)
        log.info('plan: create=%d update=%d delete=%d', counts['create'], counts['update'], counts['delete'])
