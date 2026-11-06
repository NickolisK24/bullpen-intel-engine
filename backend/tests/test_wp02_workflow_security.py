"""WP-0.2 (EOS-010): least-privilege workflow access and no tracked secrets.

These guards freeze today's credential surface so it can only shrink:

* every workflow declares its GITHUB_TOKEN permissions;
* no pull-request-triggered workflow can read a repository secret;
* only the existing, inventoried workflows may reference the production
  ``DATABASE_URL`` (WP02_CREDENTIAL_CONTAINMENT.md plans their reduction);
* only the two generated-distribution jobs may write repository contents,
  and they push only fast-forward to ``main``;
* no tracked file contains a credential-shaped value.

Removing a workflow from an allowlist is always allowed; adding one needs a
reviewed change to this file.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / '.github' / 'workflows'

# Inventoried 2026-11-05 (docs/audits/2026-end-of-season/wp02/WP02_SECURITY_FINDINGS.md).
DATABASE_SECRET_WORKFLOWS = frozenset({
    'appearance_team_backfill_2026.yml',
    'baseballos-generated-distribution.yml',
    'baseballos-intraday-repair.yml',
    'baseballos-production-maintenance.yml',
    'baseballos-scheduler-health.yml',
    'baseballos-sync.yml',
    'canonical_season_bullpen_aggregation.yml',
    'inherited-runners-authority-diagnostic.yml',
    'manual-game-driven-noop-qualification.yml',
    'manual-noop-qualification-candidate-audit.yml',
    'manual-postgame-publication-incident-audit.yml',
    'manual-publication-truth-certification.yml',
    'manual-team-state-coverage-diagnostic.yml',
    'official-starter-alignment-audit.yml',
    'official_pitching_line_completeness.yml',
    'official_pitching_line_matt_festa_apply.yml',
    'official_pitching_line_repair_apply.yml',
    'official_pitching_line_repair_closeout.yml',
    'official_pitching_line_repair_plan.yml',
    'official_pitching_line_transition_diagnostic.yml',
    'phantom_game_log_reconciliation.yml',
    'team-state-history-export.yml',
    'team-state-population-compare.yml',
    'unresolved_appearance_team_diagnostic_2026.yml',
    'unresolved_appearance_team_repair_2026.yml',
})
CONTENTS_WRITE_JOBS = frozenset({
    ('baseballos-sync.yml', 'static-team-story-preview'),
    ('baseballos-generated-distribution.yml', 'deliver-generated-content'),
})

# Credential shapes. Matches are reported by file and line only.
SECRET_PATTERNS = (
    re.compile(r'ghp_[A-Za-z0-9]{30,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(r'(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    re.compile(r'sk_live_[A-Za-z0-9]{10,}'),
    re.compile(r'xox[bpa]-[A-Za-z0-9-]{10,}'),
    re.compile(r'eyJ[A-Za-z0-9_-]{30,}\.eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{20,}'),
    # A database URL with an inline password on a non-placeholder host.
    re.compile(
        r'postgres(?:ql)?://[^:@/\s\'"]+:[^@/\s\'"]{6,}@'
        r'(?!localhost|127\.0\.0\.1|postgres[:/]|db\.example|[a-z.-]*\.invalid|[a-z.-]*\.internal[:/]'
        r'|[a-z.-]*example\.)'
        r'[a-z0-9.-]+\.[a-z]{2,}'
    ),
)
# Files that intentionally contain fake credential-shaped strings to prove
# redaction and detection (the AWS-style key there is AKIAABCDEF... ).
SECRET_FIXTURE_FILES = frozenset({
    'backend/tests/test_traffic_measurement.py',
    'frontend/tests/trafficMeasurement.test.mjs',
    'backend/tests/test_wp02_workflow_security.py',
})


def _workflows():
    return sorted(WORKFLOWS.glob('*.yml'))


def _load(path):
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}


def _triggers(parsed):
    triggers = parsed.get(True) or parsed.get('on') or {}
    if isinstance(triggers, str):
        return {triggers: None}
    if isinstance(triggers, list):
        return {item: None for item in triggers}
    return triggers


def test_every_workflow_declares_its_token_permissions():
    missing = [path.name for path in _workflows() if 'permissions' not in _load(path)]
    assert missing == []


def test_no_workflow_runs_untrusted_pull_request_code_with_secrets():
    for path in _workflows():
        parsed = _load(path)
        triggers = _triggers(parsed)
        assert 'pull_request_target' not in triggers, path.name
        if 'pull_request' in triggers:
            text = path.read_text(encoding='utf-8')
            assert 'secrets.' not in text, f'{path.name} exposes secrets to pull requests'


def test_production_database_secret_surface_can_only_shrink():
    holders = {
        path.name for path in _workflows()
        if 'secrets.DATABASE_URL' in path.read_text(encoding='utf-8')
    }
    added = holders - DATABASE_SECRET_WORKFLOWS
    assert added == set(), f'new workflows reference the production DATABASE_URL: {sorted(added)}'


def test_only_generated_distribution_jobs_can_write_repository_contents():
    writers = set()
    for path in _workflows():
        parsed = _load(path)
        top = parsed.get('permissions')
        assert not (isinstance(top, dict) and top.get('contents') == 'write'), path.name
        assert top != 'write-all', path.name
        for job_id, job in (parsed.get('jobs') or {}).items():
            permissions = (job or {}).get('permissions')
            if isinstance(permissions, dict) and permissions.get('contents') == 'write':
                writers.add((path.name, job_id))
            assert permissions != 'write-all', (path.name, job_id)
    assert writers <= CONTENTS_WRITE_JOBS
    for path in WORKFLOWS.glob('*.yml'):
        for line in path.read_text(encoding='utf-8').splitlines():
            if 'git push' in line:
                assert 'HEAD:refs/heads/main' in line and '--force' not in line and ' -f' not in line, (
                    path.name, line.strip(),
                )


def _tracked_files():
    completed = subprocess.run(
        ['git', 'ls-files', '-z'], cwd=REPO_ROOT, capture_output=True, check=False,
    )
    if completed.returncode != 0:
        pytest.skip('git is unavailable')
    return [item for item in completed.stdout.decode().split('\0') if item]


def test_no_tracked_file_contains_a_credential():
    hits = []
    for relative in _tracked_files():
        if relative in SECRET_FIXTURE_FILES or relative.startswith(('frontend/public/', 'docs/')):
            # Generated pages carry no secrets by the distribution scan;
            # docs are covered by test_docs_do_not_contain_credentials.
            continue
        path = REPO_ROOT / relative
        if path.suffix in {'.png', '.jpg', '.ico', '.woff', '.woff2', '.pyc', '.gz', '.zip'}:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                hits.append(f'{relative}:{number}')
    assert hits == []


def test_docs_do_not_contain_credentials():
    hits = []
    for relative in _tracked_files():
        if not (relative.startswith('docs/') and relative.endswith('.md')):
            continue
        text = (REPO_ROOT / relative).read_text(encoding='utf-8', errors='ignore')
        for number, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                hits.append(f'{relative}:{number}')
    assert hits == []


def test_tracked_env_files_are_examples_only():
    env_files = [
        item for item in _tracked_files()
        if re.search(r'(^|/)\.env($|\.)', item)
    ]
    assert all(item.endswith('.example') for item in env_files), env_files


def test_patterns_detect_real_shapes_and_skip_placeholders():
    assert any(p.search('postgresql://svc:Zx9kQ2mLp7@aws-0-us-east-1.pooler.supabase.com:6543/postgres')
               for p in SECRET_PATTERNS)
    for placeholder in (
        'postgresql://postgres:postgres@localhost:5432/baseballos_ci_tests',
        'postgresql://user:password@db.example.com:5432/baseballos',
        'postgresql://u:secretvalue@example.invalid/db',
        'postgres://user:hunter2pass@db.internal/prod',
    ):
        assert not any(p.search(placeholder) for p in SECRET_PATTERNS), placeholder
