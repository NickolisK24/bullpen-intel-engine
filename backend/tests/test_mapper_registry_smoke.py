"""
Mapper-registry smoke test for the sync entrypoints.

On 2026-07-05 both overnight postgame refreshes and the daily sync crashed
before game discovery: SQLAlchemy raised
``Mapper[ComposedReadEvidenceCitation] ... 'EvidenceObject' failed to locate
a name`` because a model referenced by relationship string was never imported
along the sync entrypoints' import path. Every acquisition job died on the
first ``SyncRun.query`` and the July 4 slate was never ingested.

These tests configure the full mapper registry in a fresh interpreter along
each production import path, so any future registry regression fails CI
instead of the 2 AM production pass.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

_SMOKE_SNIPPETS = {
    'app_entrypoint': (
        'import app\n'
        'from sqlalchemy.orm import configure_mappers\n'
        'configure_mappers()\n'
        'print("MAPPERS_OK")\n'
    ),
    'sync_service_only': (
        'import services.sync\n'
        'from sqlalchemy.orm import configure_mappers\n'
        'configure_mappers()\n'
        'print("MAPPERS_OK")\n'
    ),
    'daily_sync_script_imports': (
        'import scripts.run_daily_sync\n'
        'import app\n'
        'from sqlalchemy.orm import configure_mappers\n'
        'configure_mappers()\n'
        'print("MAPPERS_OK")\n'
    ),
}


@pytest.mark.parametrize('name', sorted(_SMOKE_SNIPPETS))
def test_sync_entrypoint_mapper_registry_configures(name):
    env = dict(os.environ)
    env.update({
        'AUTO_SYNC': 'false',
        'APP_ENV': 'test',
        'DATABASE_URL': 'sqlite:///:memory:',
        'TEST_DATABASE_URL': 'sqlite:///:memory:',
        'SECRET_KEY': 'mapper-smoke-test',
    })
    result = subprocess.run(
        [sys.executable, '-c', _SMOKE_SNIPPETS[name]],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f'{name} mapper configuration failed:\n{result.stderr[-2000:]}'
    )
    assert 'MAPPERS_OK' in result.stdout
