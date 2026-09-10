"""Read-only evidence report for continuous-update SyncRuns.

The command intentionally performs no writes. It is safe to run against the
production database from the existing manual shadow workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ['AUTO_SYNC'] = 'false'

from app import app  # noqa: E402
from models.source_observation import SourceFetchAttempt, SourceObservation  # noqa: E402
from models.sync_failure import SyncFailure  # noqa: E402
from models.sync_job import SyncJob  # noqa: E402
from models.sync_run import SyncRun  # noqa: E402


def _json_object(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {'unparsed': str(value)}
    return parsed if isinstance(parsed, dict) else {'value': parsed}


def inspect_runs(run_ids):
    values = []
    for run_id in run_ids:
        run = SyncRun.query.filter_by(id=run_id).one_or_none()
        if run is None:
            values.append({'sync_run_id': run_id, 'found': False})
            continue
        failures = SyncFailure.query.filter_by(sync_run_id=run_id).order_by(
            SyncFailure.id.asc()
        ).all()
        jobs = SyncJob.query.filter_by(sync_run_id=run_id).order_by(
            SyncJob.id.asc()
        ).all()
        observations = SourceObservation.query.filter_by(
            sync_run_id=run_id
        ).order_by(SourceObservation.id.asc()).all()
        attempts = SourceFetchAttempt.query.filter_by(
            sync_run_id=run_id
        ).order_by(SourceFetchAttempt.id.asc()).all()
        error_summary = _json_object(run.error_message)
        referenced_job_ids = sorted({
            item.get('work_job_id')
            for item in (error_summary.get('failures') or ())
            if isinstance(item, dict) and isinstance(item.get('work_job_id'), int)
        })
        referenced_jobs = (
            SyncJob.query.filter(SyncJob.id.in_(referenced_job_ids)).order_by(
                SyncJob.id.asc()
            ).all()
            if referenced_job_ids else []
        )
        values.append({
            'sync_run_id': run_id,
            'found': True,
            'status': run.status,
            'stage': run.stage,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'completed_at': run.completed_at.isoformat() if run.completed_at else None,
            'records_processed': run.records_processed or 0,
            'records_failed': run.records_failed or 0,
            'warnings_count': run.warnings_count or 0,
            'source_reads': run.source_reads or 0,
            'source_changes': run.source_changes or 0,
            'canonical_mutations': run.canonical_mutations or 0,
            'outcome': run.outcome_json or {},
            'error_summary': error_summary,
            'sync_failures': [item.to_dict() for item in failures],
            'jobs': [{
                'id': item.id,
                'job_name': item.job_name,
                'status': item.status,
                'attempts': item.attempts,
                'error_type': item.error_type,
                'error_message': item.error_message,
            } for item in jobs],
            'referenced_jobs': [{
                'id': item.id,
                'job_name': item.job_name,
                'status': item.status,
                'attempts': item.attempts,
                'max_attempts': item.max_attempts,
                'product_date': (
                    item.product_date.isoformat() if item.product_date else None
                ),
                'scope_key': item.scope_key,
                'error_type': item.error_type,
                'error_message': item.error_message,
                'details': item.details_json,
            } for item in referenced_jobs],
            'source_observations': [{
                'id': item.id,
                'subject_id': item.source_subject_id,
                'version': item.version_number,
                'outcome': item.outcome,
                'completeness': item.completeness,
                'is_authoritative': bool(item.is_authoritative),
                'fingerprint': item.fingerprint,
            } for item in observations],
            'source_attempts': [{
                'id': item.id,
                'subject_id': item.source_subject_id,
                'observation_id': item.source_observation_id,
                'status': item.status,
                'outcome': item.outcome,
                'completeness': item.completeness,
                'error_class': item.error_class,
            } for item in attempts],
        })
    return {
        'capability': 'continuous_observation_run_audit_v1',
        'read_only': True,
        'runs': values,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_ids', nargs='+', type=int)
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    with app.app_context():
        report = inspect_runs(args.run_ids)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as output:
            output.write(rendered + '\n')
    print(rendered)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
