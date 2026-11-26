"""Single scheduled primary or controlled publication rollback for the pinned BaseballOS project."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
import subprocess
import sys

from sync_v3 import runtime_binding as binding

# One session-level lock covers the whole command, including independent projector/publisher processes.
LOCK = 'baseballos.sync_v3.production_writer'
SECRETS = {
    'STAGING_WORKER_PASSWORD': 'SYNC_V3_WORKER_PASSWORD',
    'STAGING_PROJECTOR_PASSWORD': 'SYNC_V3_PROJECTOR_PASSWORD',
    'STAGING_PRODUCT_PUBLISHER_PASSWORD': 'SYNC_V3_PUBLISHER_PASSWORD',
}


def warm_candidate(worker, password):
    from zoneinfo import ZoneInfo
    from services.mlb_api import MLBApiClient
    from sync_v3.current_worker import verify_target, process, acquisition_failed
    from sync_v3.primary_date import prepare
    from sync_v3.staging_postseason import retain, reconcile_current_decisions

    verify_target(worker)
    day = datetime.now(ZoneInfo('America/New_York')).date()
    archive = retain(worker)
    report = process(worker, day, max_jobs=256, profiles=True)
    if acquisition_failed(report):
        raise ValueError('Candidate acquisition has unresolved failures')
    client = MLBApiClient()
    with closing(client.session):
        reconcile_current_decisions(worker, client._get)
    result = prepare(worker, password, day, for_projection=True)
    print(
        json.dumps(
            dict(candidate_ready=result['ready'], generation=result['generation'], retained=archive),
            default=str,
        )
    )
    return 0 if result['ready'] else 75


def launch(action):
    if not binding.PRODUCTION:
        raise ValueError('Set SYNC_V3_DEPLOYMENT=production explicitly')
    if any(os.environ.get(k) for k in ('DATABASE_URL', 'DATABASE_MIGRATION_URL', 'STAGING_OWNER_DSN')):
        raise ValueError('Detach owner and legacy database bindings from the v3 runtime')
    role = binding.PUBLISHER if action == 'rollback' else binding.WORKER
    secret = 'SYNC_V3_PUBLISHER_PASSWORD' if action == 'rollback' else 'SYNC_V3_WORKER_PASSWORD'
    with closing(binding.connect_runtime(role, os.environ[secret])) as guard:
        with guard, guard.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))', (LOCK,))
            if not cur.fetchone()[0]:
                raise ValueError('Another writer handoff or primary cycle owns the database lock')
            cur.execute('SELECT mode,revision,predecessor FROM sync_v3_control.authority WHERE singleton')
            mode, revision, pin = cur.fetchone()
            expected_mode = {'warm': 'legacy', 'cycle': 'v3', 'rollback': 'rollback'}[action]
            if revision != os.environ.get('RENDER_GIT_COMMIT') or mode != expected_mode:
                raise ValueError('Deployed revision or publication authority differs from the approved handoff')
        if action == 'warm':
            return warm_candidate(guard, os.environ[secret])
        keys = (
            'PATH',
            'HOME',
            'LANG',
            'LC_ALL',
            'LD_LIBRARY_PATH',
            'PYTHONPATH',
            'VIRTUAL_ENV',
            'SYNC_V3_DEPLOYMENT',
            'SYNC_V3_SESSION_HOST',
            'SYNC_V3_SSL_ROOT_CERT',
        )
        env = {key: os.environ[key] for key in keys if key in os.environ}
        env.update(AUTO_SYNC='false', STAGING_LEGACY_PREDECESSOR=json.dumps(pin))
        if action == 'rollback':
            env.update(
                STAGING_PRODUCT_PUBLISHER_PASSWORD=os.environ[secret],
                STAGING_PRODUCT_GENERATION=os.environ['SYNC_V3_ROLLBACK_GENERATION'],
                STAGING_ROLLBACK_SNAPSHOT=str(int(os.environ['SYNC_V3_ROLLBACK_SNAPSHOT'])),
            )
            operation = 'rollback'
        else:
            env.update({key: os.environ[value] for key, value in SECRETS.items()})
            # The overnight UTC slots reconcile the preceding US baseball day's finals.
            hour = datetime.now(timezone.utc).hour
            env.update(
                STAGING_INSTALLER_TASK='run-current-primary',
                STAGING_PRIMARY_PHASE='postgame' if hour in (2, 3, 4, 5, 6, 7) else 'pregame',
            )
            operation = 'bootstrap'
        return subprocess.run([sys.executable, '-m', 'sync_v3.render_staging', operation], env=env).returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('warm', 'cycle', 'rollback'))
    try:
        sys.exit(launch(parser.parse_args().action))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f'Production writer refused to start ({type(exc).__name__}).\n')
    except Exception as exc:
        parser.exit(1, f'Production binding or control check failed ({type(exc).__name__}).\n')
