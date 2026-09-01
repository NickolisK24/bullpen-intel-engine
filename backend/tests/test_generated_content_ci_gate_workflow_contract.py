"""The generated-content CI gate (CI-003 / #598).

WHAT WENT WRONG
---------------
The daily sync generated the routed `/team/{ABBR}` preview pages and committed
them straight to `main` with the default `GITHUB_TOKEN`. GitHub suppresses
workflow runs for pushes made with that token, so no CI run ever existed for the
generated commit — eleven of them, and for roughly sixty hours across August 8-10
every state of `main` was a commit no validation process had seen. The job ran no
frontend validation of its own either: no `npm test`, no `npm run build`, not
even Node. The commit was authored AND committed as Nickolis Kacludis, so
automated history was indistinguishable from human history. `contents: write`
was granted to the whole workflow. And the change check, `git diff --quiet`, is
blind to untracked files, so a newly generated page would have looked like "no
changes" and never been published at all.

WHAT THESE TESTS OWN
--------------------
Option C: the generated-content job gates itself, before the commit exists. The
guarantee is TREE-EXACT, and it is deliberately narrower than "the generated
commit SHA was tested" — a SHA cannot be tested before it exists. What is
provable is stronger than it sounds:

    the filesystem tree that passed the delivery gate, the frontend test suite,
    and the production build is byte-for-byte the tree the generated commit
    carries, proven by comparing `git write-tree` taken before the commit with
    `HEAD^{tree}` taken after it, before anything is pushed.

These tests assert that chain by ORDER and by CONTRACT, never by line number, so
the workflow stays free to be reformatted but cannot quietly lose a link. They
also own the delivery gate's fail-closed behaviour, because a gate that passes on
malformed input is not a gate.
"""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github/workflows/baseballos-sync.yml'
CI_WORKFLOW_PATH = REPO_ROOT / '.github/workflows/ci.yml'

PUBLICATION_JOB = 'static-team-story-preview'
GENERATED_PATH_PREFIX = 'frontend/public/team'
GENERATED_PATH_PREFIXES = ('frontend/public/team', 'frontend/public/share')
EXPORT_RESULT_FILE = '$GENERATED_EVIDENCE_DIR/export-result.json'

EXPORTER_PATH = REPO_ROOT / 'backend/scripts/export_team_story_pages.py'
# The exact line production run 31693516516 put on stdout ahead of the JSON.
SCHEDULER_BANNER = '[scheduler] AUTO_SYNC disabled'

AUTOMATION_NAME = 'BaseballOS Automation'
AUTOMATION_EMAIL = 'baseballoshq@gmail.com'
HUMAN_NAME = 'Nickolis Kacludis'
HUMAN_EMAIL = 'nickoliskacludis@gmail.com'

if str(REPO_ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / 'backend'))

from scripts.verify_generated_team_previews import (  # noqa: E402
    EXIT_CANNOT_VERIFY,
    EXIT_DELIVERY_VIOLATION,
    EXIT_OK,
    main as verify_main,
    verify,
)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def publication_job(workflow):
    return workflow['jobs'][PUBLICATION_JOB]


@pytest.fixture(scope='module')
def steps(publication_job):
    return publication_job.get('steps') or []


def _script(step):
    return step.get('run') or ''


def _commands(step):
    """The step's script with comment lines removed.

    These tests assert what the workflow DOES. The job is heavily commented —
    several comments quote the very constructs being forbidden, explaining why
    they are absent — so matching raw text would let prose satisfy or break a
    contract. Only executable lines count.
    """
    return '\n'.join(
        line for line in _script(step).splitlines()
        if not line.lstrip().startswith('#')
    )


def _all_commands(workflow):
    """Every executable shell line in the workflow, across every job."""
    return '\n'.join(
        _commands(step)
        for job in workflow['jobs'].values()
        for step in (job.get('steps') or [])
    )


def _label(step):
    return step.get('name') or step.get('uses') or ''


def _index_of(steps, predicate, description):
    """Position of the first step matching ``predicate``.

    Ordering is the contract these tests exist to protect, so a missing step is
    a failure with a name rather than an IndexError.
    """
    for position, step in enumerate(steps):
        if predicate(step):
            return position
    raise AssertionError(f'no step in {PUBLICATION_JOB} {description}')


def _script_index(steps, fragment):
    return _index_of(
        steps,
        lambda step: fragment in _script(step),
        f'runs {fragment!r}',
    )


# ── 1. The job, and who may write to the repository ──────────────────────────
def test_generated_content_publication_job_exists(workflow):
    assert PUBLICATION_JOB in workflow['jobs']


def test_workflow_default_permission_is_read_only(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


def test_only_the_publication_job_may_write_to_the_repository(workflow):
    """Write authority is a grant to one job, not a property of the workflow."""
    writers = sorted(
        name for name, job in workflow['jobs'].items()
        if (job.get('permissions') or {}).get('contents') == 'write'
    )
    assert writers == [PUBLICATION_JOB]

    for name, job in workflow['jobs'].items():
        if name == PUBLICATION_JOB:
            continue
        assert (job.get('permissions') or {}).get('contents') != 'write', (
            f'{name} must not carry repository write authority'
        )


def test_publication_job_requests_no_privilege_beyond_contents_write(publication_job):
    """No pull-request, actions, deployments, packages, or id-token scope."""
    assert publication_job['permissions'] == {'contents': 'write'}


# ── 2. Gate ordering: generate, verify delivery, validate, only then commit ──
def test_delivery_gate_runs_after_generation(steps):
    export = _script_index(steps, 'export_team_story_pages.py')
    delivery = _script_index(steps, 'verify_generated_team_previews.py')
    assert export < delivery


def test_frontend_gate_runs_after_generation(steps):
    """The point of Option C: validate the generated tree, not an earlier one."""
    export = _script_index(steps, 'export_team_story_pages.py')
    assert export < _script_index(steps, 'npm ci')
    assert export < _script_index(steps, 'npm test')
    assert export < _script_index(steps, 'npm run build')


def test_frontend_tests_run_before_the_automated_commit(steps):
    assert _script_index(steps, 'npm test') < _script_index(steps, 'git commit')


def test_production_build_runs_before_the_automated_commit(steps):
    assert _script_index(steps, 'npm run build') < _script_index(steps, 'git commit')


def test_no_push_can_happen_before_every_validation(steps):
    push = _script_index(steps, 'git push')
    for fragment in (
        'verify_generated_team_previews.py',
        'npm ci',
        'npm test',
        'npm run build',
        'git write-tree',
        'git commit',
    ):
        assert _script_index(steps, fragment) < push, (
            f'{fragment!r} must run before the push'
        )


def test_no_required_gate_is_soft_failed(steps):
    """A gate with continue-on-error is decoration, not a gate."""
    for step in steps:
        script = _script(step)
        gate = any(
            fragment in script
            for fragment in (
                'verify_generated_team_previews.py',
                'npm ci',
                'npm test',
                'npm run build',
                'git write-tree',
                'git commit',
                'git push',
            )
        )
        if gate:
            assert not step.get('continue-on-error'), (
                f'{_label(step)!r} is a required gate and must not be soft-failed'
            )


def test_frontend_gate_mirrors_canonical_ci_commands():
    """The gate and canonical CI must not drift into validating different things."""
    ci = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding='utf-8'))
    ci_scripts = [
        (step.get('run') or '').strip()
        for step in ci['jobs']['frontend-tests']['steps']
    ]
    ci_node = next(
        step for step in ci['jobs']['frontend-tests']['steps']
        if str(step.get('uses', '')).startswith('actions/setup-node')
    )

    gate = yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))
    gate_steps = gate['jobs'][PUBLICATION_JOB]['steps']
    gate_scripts = [(step.get('run') or '').strip() for step in gate_steps]
    gate_node = next(
        step for step in gate_steps
        if str(step.get('uses', '')).startswith('actions/setup-node')
    )

    assert gate_node['with']['node-version'] == ci_node['with']['node-version']
    assert gate_node['with']['cache-dependency-path'] == 'frontend/package-lock.json'
    for command in ('npm ci --no-audit --no-fund', 'npm test', 'npm run build'):
        assert command in ci_scripts, f'canonical CI no longer runs {command!r}'
        assert command in gate_scripts, f'the generated-content gate must run {command!r}'


# ── 3. Tree-exact validation ─────────────────────────────────────────────────
def test_validated_tree_is_captured_before_any_commit(steps):
    assert _script_index(steps, 'git write-tree') < _script_index(steps, 'git commit')


def test_committed_tree_is_compared_against_the_validated_tree_before_push(steps):
    compare = _index_of(
        steps,
        lambda step: (
            'HEAD^{tree}' in _script(step)
            and 'VALIDATED_TREE_SHA' in _script(step)
        ),
        'compares the generated commit tree with the validated tree',
    )
    assert _script_index(steps, 'git commit') <= compare
    assert compare < _script_index(steps, 'git push')


def test_tree_mismatch_refuses_to_publish(steps):
    """A mismatch must exit non-zero, not warn."""
    step = steps[
        _index_of(
            steps,
            lambda item: 'HEAD^{tree}' in _script(item),
            'compares trees',
        )
    ]
    script = _script(step)
    assert 'exit 1' in script
    assert re.search(r'!=\s*"\$VALIDATED_TREE_SHA"', script)


def test_generated_bytes_are_reverified_between_the_gate_and_staging(steps):
    """The digest comparison is what closes validated-bytes to staged-bytes."""
    stage = steps[
        _index_of(
            steps,
            lambda step: 'git write-tree' in _script(step),
            'stages the validated tree',
        )
    ]
    script = _script(stage)
    assert 'generated-digest.json' in script
    assert 'generated-digest-postbuild.json' in script
    assert 'diff -u' in script


# ── 4. Automation identity ───────────────────────────────────────────────────
def test_automated_commit_uses_the_governed_machine_identity(steps):
    commit = steps[_script_index(steps, 'git commit')]
    script = _script(commit)
    assert f'git config user.name "{AUTOMATION_NAME}"' in script
    assert f'git config user.email "{AUTOMATION_EMAIL}"' in script


def test_automated_commit_never_impersonates_a_human(workflow_text):
    """#598's provenance criterion, asserted over the whole workflow source."""
    assert HUMAN_NAME not in workflow_text
    assert HUMAN_EMAIL not in workflow_text


def test_automation_identity_carries_no_vendor_or_ai_attribution(workflow_text):
    forbidden = ('claude', 'anthropic', 'copilot', 'openai', 'co-authored-by')
    lowered = workflow_text.lower()
    for token in forbidden:
        assert token not in lowered, f'{token!r} must not appear in the workflow'


def test_generated_commit_carries_workflow_run_provenance(steps):
    commit = steps[_script_index(steps, 'git commit')]
    script = _script(commit)
    for trailer in ('Workflow-Run:', 'Source-SHA:', 'Validated-Tree:'):
        assert trailer in script, f'the generated commit must record {trailer}'
    assert commit['env']['WORKFLOW_RUN_ID'] == '${{ github.run_id }}'
    assert commit['env']['WORKFLOW_SOURCE_SHA'] == '${{ github.sha }}'


def test_commit_provenance_reads_the_structured_result_not_the_rendered_html(steps):
    """Snapshot and data-through come from the exporter, never from scraping."""
    commit = steps[_script_index(steps, 'git commit')]
    script = _script(commit)
    assert 'delivery-verification.json' in script
    assert '.html' not in script


# ── 5. Staging scope and change detection ────────────────────────────────────
def test_only_the_generated_delivery_paths_are_staged(steps):
    stage = steps[_script_index(steps, 'git add')]
    commands = _commands(stage)
    assert f'git add -- {" ".join(GENERATED_PATH_PREFIXES)}' in commands
    assert 'git add .' not in commands
    assert 'git add -A' not in commands


def test_staging_refuses_paths_outside_the_generated_scope(steps):
    stage = steps[_script_index(steps, 'git add')]
    script = _script(stage)
    assert 'git diff --cached --name-only' in script
    assert "grep -Ev '^frontend/public/(team|share)/'" in script


def test_share_preview_export_and_delivery_gate_precede_frontend_validation(steps):
    export = _script_index(steps, 'export_share_artifact_pages.py')
    verify = _script_index(steps, 'verify_generated_share_previews.py')
    frontend = next(
        index for index, step in enumerate(steps)
        if step.get('name') == 'Run frontend tests'
    )
    assert export < verify < frontend
    assert '--result-out "$GENERATED_EVIDENCE_DIR/share-export-result.json"' in _commands(steps[export])
    assert '--export-result "$GENERATED_EVIDENCE_DIR/share-export-result.json"' in _commands(steps[verify])


def test_share_preview_bytes_are_reverified_before_staging(steps):
    stage = steps[_script_index(steps, 'git add')]
    script = _script(stage)
    assert 'verify_generated_share_previews.py' in script
    assert 'share-generated-digest-postbuild.json' in script
    assert 'diff -u' in script


def test_the_static_og_asset_is_no_longer_swept_into_the_generated_commit(steps):
    """The generator never writes it; staging it only widened the blast radius."""
    for step in steps:
        assert 'baseballos-card.svg' not in _commands(step)


def test_change_detection_compares_the_index_not_the_worktree(steps):
    """The untracked-file blind spot must not be able to come back.

    `git diff --quiet -- <paths>` cannot see a newly generated page, so a new
    club would have read as "no changes" and never published. Detection has to
    happen against the index, after staging.
    """
    stage = steps[_script_index(steps, 'git add')]
    script = _script(stage)
    assert 'git diff --cached --quiet' in script
    assert not re.search(r'git diff --quiet\s+--\s', script), (
        'worktree-only change detection reintroduces the untracked-file blind spot'
    )
    assert script.index('git add') < script.index('git diff --cached --quiet')


def test_a_run_with_no_generated_change_creates_no_commit(steps):
    """No empty commits, and no push on an unchanged day."""
    stage_position = _script_index(steps, 'git add')
    stage = steps[stage_position]
    assert 'publish=false' in _script(stage)

    for fragment in ('git commit', 'git push'):
        step = steps[_script_index(steps, fragment)]
        assert "steps.stage.outputs.publish == 'true'" in step['if'], (
            f'{fragment!r} must be gated on there actually being a change'
        )


def test_publication_is_restricted_to_main(steps):
    for fragment in ('git commit', 'git push'):
        step = steps[_script_index(steps, fragment)]
        assert "github.ref == 'refs/heads/main'" in step['if']


# ── 6. Push safety ───────────────────────────────────────────────────────────
def test_push_is_fast_forward_only(workflow):
    """A non-fast-forward push must fail loudly, never overwrite human work."""
    commands = _all_commands(workflow)
    for forbidden in (
        '--force',
        '--force-with-lease',
        'push -f',
        'reset --hard',
        'git rebase',
        'git pull',
    ):
        assert forbidden not in commands, (
            f'{forbidden!r} must never run on the generated publication path'
        )


def test_no_recursive_or_elevated_credential_mechanism_is_introduced(workflow_text):
    """Option C gates itself; it does not try to make the push trigger CI."""
    for forbidden in (
        'repository_dispatch',
        'workflow_call',
        'personal_access_token',
        'PAT_TOKEN',
        'VERCEL_TOKEN',
        'app-token',
    ):
        assert forbidden not in workflow_text


def test_checkout_uses_the_default_token(steps):
    checkout = steps[
        _index_of(
            steps,
            lambda step: str(step.get('uses', '')).startswith('actions/checkout'),
            'checks out the repository',
        )
    ]
    assert 'token' not in (checkout.get('with') or {})


# ── 7. Provenance evidence artifact ──────────────────────────────────────────
def test_validation_evidence_is_uploaded_with_bounded_retention(steps):
    upload = steps[
        _index_of(
            steps,
            lambda step: 'generated-team-preview-validation' in str(
                (step.get('with') or {}).get('name', '')
            ),
            'uploads the validation evidence artifact',
        )
    ]
    assert upload['with']['name'] == (
        'generated-team-preview-validation-${{ github.run_id }}'
    )
    assert upload['with']['retention-days'] == 30
    assert upload['if'] == '${{ always() }}'


def test_evidence_is_secret_scanned_before_upload(steps):
    scan = _script_index(steps, 'scan_forbidden_artifact_content.py')
    upload = _index_of(
        steps,
        lambda step: 'generated-team-preview-validation' in str(
            (step.get('with') or {}).get('name', '')
        ),
        'uploads the validation evidence artifact',
    )
    assert scan < upload


def test_the_commit_message_file_never_leaves_the_runner(steps):
    """It is an intermediate, not evidence, and it is removed before upload."""
    scan = steps[_script_index(steps, 'scan_forbidden_artifact_content.py')]
    assert 'rm -f' in _script(scan)
    assert 'commit-message.txt' in _script(scan)


# ── 8. The delivery gate itself must fail closed ─────────────────────────────
def _export_result(tmp_path, **overrides):
    """A minimal, well-formed exporter declaration over two generated pages."""
    root = tmp_path / 'public'
    team_root = root / 'team'
    for abbr in ('AAA', 'BBB'):
        page = team_root / abbr
        page.mkdir(parents=True, exist_ok=True)
        (page / 'index.html').write_text(
            '<meta name="baseballos:representation" content="dated_team_read" />\n'
            '<meta name="baseballos:generated-at" content="2026-08-12T11:00:00+00:00" />\n'
            '<meta name="baseballos:data-through" content="2026-08-11" />\n'
            '<meta name="baseballos:snapshot-id" content="398" />\n'
            '<meta name="baseballos:authority-contract" '
            'content="trusted_dashboard_publication_v1" />\n'
            '<meta name="baseballos:team-state" content="Stretched" />\n'
            '<meta name="baseballos:unfurl-team-state" content="Stretched" />\n'
            '<meta property="og:title" content="Team Bullpen: Stretched" />\n'
            '<meta property="og:description" content="Team bullpen state: '
            'Stretched. Data through 2026-08-11." />\n'
            '<p data-baseballos-team-state="Stretched">BaseballOS Team State: '
            'Stretched.</p>\n',
            encoding='utf-8',
        )
    (team_root / 'index.html').write_text(
        '<meta name="baseballos:representation" content="invalid_team" />\n',
        encoding='utf-8',
    )
    result = {
        'status': 'ok',
        'teams': 2,
        'previews': 2,
        'publication_snapshot_id': 398,
        'publication_data_through': '2026-08-11',
        'generated_at': '2026-08-12T11:00:00+00:00',
        'withheld_teams': [],
        'output': {
            'count': 2,
            'files': [
                str(team_root / 'AAA' / 'index.html'),
                str(team_root / 'BBB' / 'index.html'),
            ],
            'fallback': str(team_root / 'index.html'),
        },
    }
    result.update(overrides)
    return result, root


def test_delivery_gate_passes_a_coherent_publication(tmp_path):
    result, root = _export_result(tmp_path)
    violations, facts = verify(result, str(root), REPO_ROOT)
    assert violations == []
    assert facts['dated_pages'] == 2


def test_delivery_gate_refuses_when_the_exporter_did_not_succeed(tmp_path):
    result, root = _export_result(tmp_path, status='no_trusted_publication')
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('did not declare success' in violation for violation in violations)


def test_delivery_gate_refuses_a_missing_declared_page(tmp_path):
    result, root = _export_result(tmp_path)
    Path(result['output']['files'][0]).unlink()
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('is missing' in violation for violation in violations)


def test_delivery_gate_refuses_a_stale_page_left_behind(tmp_path):
    """An old club directory would keep serving an old claim at a live route."""
    result, root = _export_result(tmp_path)
    stale = root / 'team' / 'OLD'
    stale.mkdir()
    (stale / 'index.html').write_text('<html></html>', encoding='utf-8')
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('unexpected generated file' in violation for violation in violations)


def test_delivery_gate_refuses_two_publication_clocks_in_one_run(tmp_path):
    """One trusted publication per run — the #594 contract, proven on disk."""
    result, root = _export_result(tmp_path)
    page = Path(result['output']['files'][0])
    page.write_text(
        page.read_text(encoding='utf-8').replace('content="398"', 'content="397"'),
        encoding='utf-8',
    )
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('more than one publication snapshot' in v for v in violations)


def test_delivery_gate_refuses_a_dated_claim_without_receipts(tmp_path):
    result, root = _export_result(tmp_path)
    page = Path(result['output']['files'][0])
    page.write_text(
        '<meta name="baseballos:representation" content="dated_team_read" />\n',
        encoding='utf-8',
    )
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('data-through' in violation for violation in violations)


def test_delivery_gate_passes_a_page_whose_unfurl_names_no_team_state(tmp_path):
    """Canonical story wording often names no state. Silence is not a conflict."""
    result, root = _export_result(tmp_path)
    page = Path(result['output']['files'][0])
    text = page.read_text(encoding='utf-8')
    text = text.replace(
        '<meta name="baseballos:unfurl-team-state" content="Stretched" />\n', ''
    )
    text = text.replace('Team Bullpen: Stretched', 'Yankees leaned on their late arms')
    text = text.replace(
        'Team bullpen state: Stretched. Data through 2026-08-11.',
        'Three relievers worked a third straight day. Data through 2026-08-11.',
    )
    page.write_text(text, encoding='utf-8')
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert violations == []


def test_delivery_gate_refuses_a_body_that_contradicts_the_published_state(tmp_path):
    """The H-8 defect from the reader's side: body says one state, page another."""
    result, root = _export_result(tmp_path)
    page = Path(result['output']['files'][0])
    page.write_text(
        page.read_text(encoding='utf-8').replace(
            '<p data-baseballos-team-state="Stretched">BaseballOS Team State: Stretched.</p>',
            '<p data-baseballos-team-state="Fresh">BaseballOS Team State: Fresh.</p>',
        ),
        encoding='utf-8',
    )
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('crawler-visible body renders Team State' in v for v in violations)


def test_delivery_gate_refuses_an_unfurl_that_contradicts_the_published_state(tmp_path):
    """The H-8 defect from the crawler's side: the share card claims another state."""
    result, root = _export_result(tmp_path)
    page = Path(result['output']['files'][0])
    page.write_text(
        page.read_text(encoding='utf-8')
        .replace(
            '<meta name="baseballos:unfurl-team-state" content="Stretched" />',
            '<meta name="baseballos:unfurl-team-state" content="Fresh" />',
        )
        .replace('Team Bullpen: Stretched', 'Team Bullpen: Fresh'),
        encoding='utf-8',
    )
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('would store different claims about this bullpen' in v for v in violations)


def test_delivery_gate_refuses_an_unfurl_receipt_the_shipped_bytes_do_not_support(tmp_path):
    """The receipt describes the artifact, so it may not outrun the artifact."""
    result, root = _export_result(tmp_path)
    page = Path(result['output']['files'][0])
    page.write_text(
        page.read_text(encoding='utf-8')
        .replace('Team Bullpen: Stretched', 'Team Bullpen Read')
        .replace('Team bullpen state: Stretched. ', ''),
        encoding='utf-8',
    )
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('no og:title/og:description on the page states it' in v for v in violations)


def test_delivery_gate_refuses_disagreeing_exporter_counts(tmp_path):
    result, root = _export_result(tmp_path, teams=3)
    violations, _ = verify(result, str(root), REPO_ROOT)
    assert any('counts disagree' in violation for violation in violations)


def test_delivery_gate_exit_codes_are_fail_closed(tmp_path):
    result, root = _export_result(tmp_path)
    ok_path = tmp_path / 'ok.json'
    ok_path.write_text(json.dumps(result), encoding='utf-8')
    assert verify_main(
        ['--export-result', str(ok_path), '--output-root', str(root)]
    ) == EXIT_OK

    result['status'] = 'no_trusted_publication'
    bad_path = tmp_path / 'bad.json'
    bad_path.write_text(json.dumps(result), encoding='utf-8')
    assert verify_main(
        ['--export-result', str(bad_path), '--output-root', str(root)]
    ) == EXIT_DELIVERY_VIOLATION

    malformed = tmp_path / 'malformed.json'
    malformed.write_text('not json', encoding='utf-8')
    assert verify_main(
        ['--export-result', str(malformed), '--output-root', str(root)]
    ) == EXIT_CANNOT_VERIFY


def test_delivery_gate_digest_is_deterministic_and_change_sensitive(tmp_path):
    """The digest is the evidence that validated bytes are the staged bytes."""
    result, root = _export_result(tmp_path)
    export_path = tmp_path / 'result.json'
    export_path.write_text(json.dumps(result), encoding='utf-8')

    first = tmp_path / 'a.json'
    second = tmp_path / 'b.json'
    args = ['--export-result', str(export_path), '--output-root', str(root)]
    verify_main(args + ['--digest-out', str(first)])
    verify_main(args + ['--digest-out', str(second)])
    assert first.read_text(encoding='utf-8') == second.read_text(encoding='utf-8')

    page = Path(result['output']['files'][0])
    page.write_text(page.read_text(encoding='utf-8') + '\n', encoding='utf-8')
    third = tmp_path / 'c.json'
    verify_main(args + ['--digest-out', str(third)])
    assert third.read_text(encoding='utf-8') != first.read_text(encoding='utf-8')


def test_delivery_gate_imports_no_baseball_authority():
    """The gate proves delivery. Baseball meaning stays with the generator.

    Asserted against the import graph rather than against words, so the module
    docstring is free to NAME the authorities it must not reach for. A gate that
    imported a service, a model, or the Flask app could resolve a snapshot,
    build a board, or map a Team State — a second publication authority, which
    is the outcome #598 exists to prevent.
    """
    source = (
        REPO_ROOT / 'backend/scripts/verify_generated_team_previews.py'
    ).read_text(encoding='utf-8')
    tree = ast.parse(source)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or '').split('.')[0])

    for forbidden in ('services', 'models', 'app', 'utils', 'flask', 'sqlalchemy'):
        assert forbidden not in imported, (
            f'the delivery gate must not import {forbidden!r} — that would move '
            'baseball authority into CI'
        )
    assert imported <= {'argparse', 'hashlib', 'html', 'json', 're', 'sys', 'pathlib',
                        '__future__'}, (
        f'the delivery gate grew an unexpected dependency: {sorted(imported)}'
    )


# ── 9. The structured result transport (production run 31693516516) ──────────
# The first naturally scheduled run of this gate generated all 30 previews from
# snapshot 404 and then refused to publish them, because the evidence file it
# was handed did not parse:
#
#     Could not read the exporter result (Expecting value: line 1 column 2
#     (char 1)). Delivery is UNPROVEN.
#
# The gate was right. The transport was wrong. The workflow captured the
# exporter's stdout with `| tee export-result.json`, and stdout is not a
# machine channel: importing the exporter pulls in the Flask app, which prints
# a scheduler banner before `main` is ever entered, so the file's first byte
# was `[`, not `{`.
#
# The repair is a channel, not a looser parser. These tests own that channel,
# and they exercise the REAL exporter in a REAL process — the banner in the
# captured stdout below is genuinely emitted by the import, not simulated —
# because a fixture that mocked the contamination away could not fail the way
# production failed. SQLite keeps it hermetic: nothing connects, and no
# production data is reachable.

_EMIT_RESULT_IN_A_REAL_PROCESS = '''
import json
import sys

from scripts.export_team_story_pages import emit_result

sys.exit(0 if emit_result(json.loads(sys.argv[1]), sys.argv[2] or None) else 7)
'''


def _run_exporter_emit(result, result_out):
    """Emit ``result`` through the exporter's own result channel, out of process."""
    return subprocess.run(
        [
            sys.executable,
            '-c',
            _EMIT_RESULT_IN_A_REAL_PROCESS,
            json.dumps(result),
            str(result_out or ''),
        ],
        cwd=str(REPO_ROOT),
        env={
            **os.environ,
            'APP_ENV': 'test',
            'DATABASE_URL': 'sqlite:///:memory:',
            'AUTO_SYNC': 'false',
            'PYTHONPATH': str(REPO_ROOT / 'backend'),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def _exporter_source():
    return EXPORTER_PATH.read_text(encoding='utf-8')


def test_the_exporter_still_contaminates_its_own_stdout(tmp_path):
    """The defect's precondition, asserted rather than assumed.

    If this ever stops being true the regression fixtures below stop proving
    anything, and the failure should say so out loud instead of passing
    vacuously. Note the assertion is on the FIRST line: nothing the exporter
    prints can be reached without stepping over this.
    """
    result_path = tmp_path / 'export-result.json'
    proc = _run_exporter_emit({'status': 'ok'}, result_path)

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[0].startswith(SCHEDULER_BANNER)


def test_the_old_stdout_transport_is_what_production_could_not_parse(tmp_path):
    """`| tee export-result.json`, reproduced end to end.

    This is run 31693516516 in miniature: the same stdout, captured the old
    way, rejected by the same strict loader with the same class of error.
    """
    result, _ = _export_result(tmp_path)
    proc = _run_exporter_emit(result, tmp_path / 'export-result.json')

    teed = tmp_path / 'teed-export-result.json'
    teed.write_text(proc.stdout, encoding='utf-8')

    with pytest.raises(json.JSONDecodeError):
        json.loads(teed.read_text(encoding='utf-8'))


def test_stdout_contamination_cannot_corrupt_the_structured_result_file(tmp_path):
    """The repair: same contaminated stdout, clean evidence file, gate passes.

    The whole chain in one assertion set — a diagnostic banner on stdout, one
    complete JSON document in the result file, and the unmodified delivery gate
    verifying a coherent publication from it.
    """
    result, root = _export_result(tmp_path)
    result_path = tmp_path / 'evidence' / 'export-result.json'
    proc = _run_exporter_emit(result, result_path)

    assert proc.returncode == 0, proc.stderr
    assert SCHEDULER_BANNER in proc.stdout

    # Exactly one JSON document, parsed strictly, with nothing in front of it.
    written = result_path.read_text(encoding='utf-8')
    assert SCHEDULER_BANNER not in written
    assert json.loads(written) == result

    assert verify_main([
        '--export-result', str(result_path),
        '--output-root', str(root),
    ]) == EXIT_OK


def test_the_result_file_and_stdout_carry_one_object_not_two(tmp_path):
    """No second representation: the file is the printed object, verbatim."""
    result, _ = _export_result(tmp_path)
    result_path = tmp_path / 'export-result.json'
    proc = _run_exporter_emit(result, result_path)

    printed = json.loads(proc.stdout.splitlines()[-1])
    assert printed == json.loads(result_path.read_text(encoding='utf-8')) == result


def test_a_nested_result_path_is_created_rather_than_silently_skipped(tmp_path):
    result_path = tmp_path / 'artifacts' / 'generated-team-preview' / 'export-result.json'
    proc = _run_exporter_emit({'status': 'ok', 'teams': 30}, result_path)

    assert proc.returncode == 0, proc.stderr
    assert json.loads(result_path.read_text(encoding='utf-8')) == {
        'status': 'ok', 'teams': 30,
    }


def test_an_unwritable_result_path_fails_instead_of_running_on(tmp_path):
    """Missing provenance and a clean run must never look the same."""
    blocker = tmp_path / 'blocker'
    blocker.write_text('not a directory', encoding='utf-8')

    proc = _run_exporter_emit({'status': 'ok'}, blocker / 'export-result.json')

    assert proc.returncode == 7
    assert 'reason=' in proc.stderr
    assert str(tmp_path) not in proc.stderr  # the reason is a class, not a path


def test_a_failed_result_write_can_never_leave_a_successful_export(tmp_path):
    """Source-level, because the zero-exit path is the one that must not exist."""
    source = _exporter_source()

    assert 'EXIT_RESULT_OUTPUT_FAILED = 3' in source
    assert 'return exit_code or EXIT_RESULT_OUTPUT_FAILED' in source


def test_no_trusted_publication_is_written_as_valid_json_and_still_refused(tmp_path):
    """A failure result is diagnostic evidence, never an authorization."""
    _, root = _export_result(tmp_path)
    result_path = tmp_path / 'export-result.json'
    failure = {
        'status': 'no_trusted_publication',
        'generated_at': '2026-08-12T11:00:00+00:00',
        'pages_written': 0,
    }
    proc = _run_exporter_emit(failure, result_path)

    assert proc.returncode == 0, proc.stderr
    assert json.loads(result_path.read_text(encoding='utf-8')) == failure

    # The gate reads it fine and refuses it anyway — parseable, not publishable.
    assert verify_main([
        '--export-result', str(result_path),
        '--output-root', str(root),
    ]) == EXIT_DELIVERY_VIOLATION


def test_the_trusted_publication_refusal_keeps_its_own_exit_code():
    """Writing diagnostic evidence must not renumber the refusal itself."""
    source = _exporter_source()
    tree = ast.parse(source)
    main_fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == 'main'
    )

    emits = [
        node for node in ast.walk(main_fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'emit_result'
    ]
    assert len(emits) == 2, 'both result outcomes go through the one result channel'

    returned = {
        node.value.id for node in ast.walk(main_fn)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name)
    }
    assert 'EXIT_NO_TRUSTED_PUBLICATION' in returned


def test_the_exporter_result_channel_reuses_the_durable_summary_writer():
    """One helper, atomically replaced: never a half-written authority file."""
    source = _exporter_source()

    assert 'from utils.summary_output import' in source
    assert 'write_summary' in source
    assert 'SummaryOutputError' in source
    # The stdout line and the file are the same serialization of one object.
    assert 'print(serialize_summary(result))' in source

    writer = (REPO_ROOT / 'backend/utils/summary_output.py').read_text(encoding='utf-8')
    assert 'os.replace(temporary, destination)' in writer


# ── 10. The workflow carries the result on that channel, not on stdout ───────
def test_the_workflow_asks_the_exporter_to_write_its_own_result_file(steps):
    export = steps[_script_index(steps, 'export_team_story_pages.py')]
    assert f'--result-out "{EXPORT_RESULT_FILE}"' in _commands(export)


def test_the_workflow_never_captures_stdout_as_the_authority_file(workflow):
    """The regression guard for run 31693516516.

    Asserted against executable lines only: the comments above the export step
    quote the old `tee` construct on purpose, to record what changed and why.
    """
    commands = _all_commands(workflow)

    for forbidden in (
        f'tee "{EXPORT_RESULT_FILE}"',
        f'tee {EXPORT_RESULT_FILE}',
        f'> "{EXPORT_RESULT_FILE}"',
        f'>"{EXPORT_RESULT_FILE}"',
    ):
        assert forbidden not in commands, (
            f'{forbidden!r} would rebuild the stdout capture that produced '
            'unparseable delivery evidence in production'
        )


def test_the_export_step_pipes_its_stdout_nowhere(steps):
    """stdout stays visible in the run log and feeds nothing."""
    export = _commands(steps[_script_index(steps, 'export_team_story_pages.py')])
    exporter_invocation = export.split('python backend/scripts/export_team_story_pages.py')[1]

    assert '|' not in exporter_invocation
    assert 'set -euo pipefail' in export


def test_every_delivery_proof_reads_the_explicit_result_file(steps):
    """Both the gate and the post-build re-proof read the file the exporter
    wrote — never a re-derivation, never a second capture."""
    verifications = [
        _commands(step) for step in steps
        if 'verify_generated_team_previews.py' in _script(step)
    ]
    assert len(verifications) == 2
    for script in verifications:
        assert f'--export-result "{EXPORT_RESULT_FILE}"' in script


def test_a_malformed_result_file_still_blocks_every_publication_step(tmp_path, steps):
    """Unchanged behaviour, re-asserted: the gate that stopped run 31693516516
    is the same gate, and it still stands ahead of everything."""
    _, root = _export_result(tmp_path)
    malformed = tmp_path / 'export-result.json'
    malformed.write_text(
        f'{SCHEDULER_BANNER} — daily scheduler not started.\n{{"status": "ok"}}\n',
        encoding='utf-8',
    )

    assert verify_main([
        '--export-result', str(malformed), '--output-root', str(root),
    ]) == EXIT_CANNOT_VERIFY

    gate = _script_index(steps, 'verify_generated_team_previews.py')
    for later in ('npm ci', 'npm test', 'npm run build', 'git add', 'git commit',
                  'git push'):
        assert gate < _script_index(steps, later)
