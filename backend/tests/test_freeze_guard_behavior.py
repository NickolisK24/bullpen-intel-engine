"""Behavior proof for the four branch-diff freeze guards themselves.

``test_freeze_policy.py`` pins the catalogue and the matcher. This module pins
the guards that consume them, by substituting a fabricated changed-path set for
the real ``git diff`` and asserting what each guard does with it. No product
file is touched to provoke a guard.

Both directions are asserted for every guard, because narrowing is only correct
if it moved exactly one way:

- an unrelated frontend file, an unrelated migration, and an archived document
  whose *name* collides with a protected module are all accepted;
- a genuinely frozen path is still refused.

Before H-1 the first three were refused by these same guards, which is what
forced ordinary changes into per-change allowlists in four test modules.
"""

import os
import subprocess
from pathlib import Path

import pytest

import branch_diff
import test_appearance_team_authority as appearance_guard
import test_public_team_relief_work as public_routes_guard
import test_qa_reconciliation_scenarios as phase0e_guard
import test_snapshot_trust_freeze as what_changed_guard


UNRELATED_FRONTEND = 'frontend/src/components/UI/ExampleUnusedComponent.jsx'
UNRELATED_MIGRATION = 'backend/migrations/versions/example_future_migration.py'
ARCHIVED_NAME_COLLISION = 'docs/archive/example_public_team_relief_work_history.md'

HARMLESS = (UNRELATED_FRONTEND, UNRELATED_MIGRATION, ARCHIVED_NAME_COLLISION)
TB04_FILES = (
    'backend/services/team_board_v2.py',
    'frontend/src/components/bullpen/board/TeamBoardWorkloadOverview.jsx',
)
TB09A_APPROVED_PATH = 'backend/services/share_artifact_generation.py'
UNAPPROVED_SHARE_ARTIFACT_NEIGHBOR = 'backend/models/share_artifact.py'


def _git(repo, *args):
    environment = dict(os.environ)
    environment.update({
        'GIT_AUTHOR_NAME': 'Test Author',
        'GIT_AUTHOR_EMAIL': 'test@example.com',
        'GIT_COMMITTER_NAME': 'Test Author',
        'GIT_COMMITTER_EMAIL': 'test@example.com',
    })
    return subprocess.run(
        ['git', *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )


def _commit_files(repo, message, files):
    for relative, contents in files.items():
        path = Path(repo) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding='utf-8')
    _git(repo, 'add', '--all')
    _git(repo, 'commit', '-m', message)


def _set_remote_ref(repo, name):
    _git(repo, 'update-ref', f'refs/remotes/origin/{name}', 'HEAD')


def _integration_feature_repo(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-b', 'main')
    _commit_files(repo, 'initial', {
        'backend/services/share_artifact_generation.py': 'main\n',
        'backend/services/team_board_v2.py': 'main\n',
    })
    _set_remote_ref(repo, 'main')

    _git(repo, 'checkout', '-b', 'integration')
    _commit_files(repo, 'approved integration change', {
        'backend/services/share_artifact_generation.py': 'integration\n',
    })
    _set_remote_ref(repo, 'integration')

    _git(repo, 'checkout', '-b', 'feature')
    _commit_files(repo, 'ordinary feature change', {
        'backend/services/team_board_v2.py': 'feature\n',
    })
    _set_remote_ref(repo, 'feature')
    return repo


def _run_what_changed(monkeypatch, changed):
    # This guard's helper returns a set.
    monkeypatch.setattr(
        what_changed_guard, '_changed_files_vs_main', lambda: set(changed)
    )
    what_changed_guard.test_frozen_legacy_what_changed_files_untouched()


def _run_public_routes(monkeypatch, changed):
    monkeypatch.setattr(
        public_routes_guard, '_changed_files_vs_main', lambda: list(changed)
    )
    public_routes_guard.test_existing_public_routes_behavior_freeze(monkeypatch)


def _run_phase0e(monkeypatch, changed):
    monkeypatch.setattr(
        phase0e_guard, '_changed_files_vs_main', lambda: list(changed)
    )
    phase0e_guard.test_phase0e_switches_and_legacy_public_files_not_modified()


def _run_appearance(monkeypatch, changed):
    monkeypatch.setattr(
        branch_diff, 'changed_files_for_current_change', lambda *_a, **_k: changed
    )
    appearance_guard.test_branch_touches_no_team_state_or_public_surface_files()


GUARDS = (
    ('frozen legacy What Changed', _run_what_changed),
    ('frozen public routes', _run_public_routes),
    ('phase 0E legacy public', _run_phase0e),
    ('appearance-team runtime surfaces', _run_appearance),
)

# One genuinely frozen path per guard.
FROZEN_EXAMPLES = (
    (
        'frozen legacy What Changed',
        _run_what_changed,
        'backend/services/what_changed_since_yesterday.py',
    ),
    ('frozen public routes', _run_public_routes, 'backend/api/pitchers.py'),
    # what_changed_since_yesterday_public rather than bullpen_board,
    # dashboard_snapshot, or tonight_intelligence_snapshot: those files hold
    # reviewed branch-scoped exceptions for H-6/H-7, D-054, and the current
    # TODAY snapshot-contract package respectively. Any other genuinely frozen
    # path in the same catalogue
    # proves the guard still refuses unapproved changes.
    (
        'phase 0E legacy public',
        _run_phase0e,
        'backend/services/what_changed_since_yesterday_public.py',
    ),
    (
        'appearance-team runtime surfaces',
        _run_appearance,
        'backend/services/team_state_payload.py',
    ),
)


def test_integration_base_history_is_not_attributed_to_feature_branch(tmp_path):
    repo = _integration_feature_repo(tmp_path)

    local_changed = branch_diff.changed_files_for_current_change(repo, environ={})
    ci_changed = branch_diff.changed_files_for_current_change(
        repo, environ={'GITHUB_BASE_REF': 'integration'}
    )

    assert local_changed == ['backend/services/team_board_v2.py']
    assert ci_changed == local_changed
    assert 'backend/services/share_artifact_generation.py' not in local_changed


@pytest.mark.parametrize(
    'environ',
    ({}, {'GITHUB_BASE_REF': 'integration'}),
    ids=('local-nearest-ancestor', 'github-explicit-base'),
)
def test_actual_protected_feature_change_still_fails_guard(
    tmp_path, monkeypatch, environ
):
    repo = _integration_feature_repo(tmp_path)
    _commit_files(repo, 'protected feature change', {
        UNAPPROVED_SHARE_ARTIFACT_NEIGHBOR: 'feature\n',
    })

    changed = branch_diff.changed_files_for_current_change(repo, environ=environ)

    assert UNAPPROVED_SHARE_ARTIFACT_NEIGHBOR in changed
    with pytest.raises(AssertionError):
        _run_appearance(monkeypatch, changed)


def test_exact_tb09a_exception_remains_allowed_for_feature_change(
    tmp_path, monkeypatch
):
    repo = _integration_feature_repo(tmp_path)
    _commit_files(repo, 'approved protected feature change', {
        TB09A_APPROVED_PATH: 'feature\n',
    })

    changed = branch_diff.changed_files_for_current_change(
        repo, environ={'GITHUB_BASE_REF': 'integration'}
    )

    assert TB09A_APPROVED_PATH in changed
    _run_appearance(monkeypatch, changed)


def test_main_based_feature_uses_main_as_actual_base(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-b', 'main')
    _commit_files(repo, 'initial', {'allowed.txt': 'main\n'})
    _set_remote_ref(repo, 'main')
    _git(repo, 'checkout', '-b', 'feature')
    _commit_files(repo, 'feature', {'allowed.txt': 'feature\n'})
    _set_remote_ref(repo, 'feature')

    assert branch_diff.resolve_comparison_ref(repo, environ={}) == 'origin/main'
    assert branch_diff.changed_files_for_current_change(repo, environ={}) == [
        'allowed.txt'
    ]


def test_missing_explicit_comparison_ref_never_produces_false_pass(tmp_path):
    repo = _integration_feature_repo(tmp_path)

    with pytest.raises(branch_diff.ComparisonBaseUnavailable):
        branch_diff.changed_files_for_current_change(
            repo, environ={'GITHUB_BASE_REF': 'missing-base'}
        )


def test_appearance_guard_skips_when_comparison_base_is_unavailable(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise branch_diff.ComparisonBaseUnavailable('fixture missing base')

    monkeypatch.setattr(
        branch_diff, 'changed_files_for_current_change', unavailable
    )
    with pytest.raises(pytest.skip.Exception):
        appearance_guard.test_branch_touches_no_team_state_or_public_surface_files()


def test_appearance_guard_accepts_ordinary_tb04_paths(monkeypatch):
    _run_appearance(monkeypatch, list(TB04_FILES))


@pytest.mark.parametrize('label,runner', GUARDS)
def test_guard_accepts_an_unrelated_frontend_file(monkeypatch, label, runner):
    runner(monkeypatch, [UNRELATED_FRONTEND])


@pytest.mark.parametrize('label,runner', GUARDS)
def test_guard_accepts_an_unrelated_migration(monkeypatch, label, runner):
    runner(monkeypatch, [UNRELATED_MIGRATION])


def test_sd01_public_route_exception_is_exact(monkeypatch):
    approved = list(phase0e_guard.freeze_policy.SD01_UNIFIED_SEARCH_PATHS)
    _run_phase0e(monkeypatch, approved)
    _run_appearance(monkeypatch, approved)

    with pytest.raises(AssertionError):
        _run_phase0e(monkeypatch, ['backend/api/search_admin.py'])
    with pytest.raises(AssertionError):
        _run_appearance(monkeypatch, ['backend/api/search_admin.py'])


def test_hist01_history_route_exception_is_exact(monkeypatch):
    approved = list(phase0e_guard.freeze_policy.HIST01_TEAM_STATE_TIMELINE_PATHS)
    _run_phase0e(monkeypatch, approved)
    _run_appearance(monkeypatch, approved)

    with pytest.raises(AssertionError):
        _run_phase0e(monkeypatch, ['backend/api/team_history_admin.py'])
    with pytest.raises(AssertionError):
        _run_appearance(monkeypatch, ['backend/services/team_state_history_admin.py'])


def test_hist03_transaction_history_exception_is_exact(monkeypatch):
    approved = list(
        phase0e_guard.freeze_policy.HIST03_QUALIFIED_TRANSACTION_HISTORY_PATHS
    )
    _run_phase0e(monkeypatch, approved)
    _run_appearance(monkeypatch, approved)

    with pytest.raises(AssertionError):
        _run_phase0e(
            monkeypatch,
            ['backend/services/what_changed_since_yesterday_public.py'],
        )
    with pytest.raises(AssertionError):
        _run_appearance(monkeypatch, ['backend/services/team_state_payload.py'])


@pytest.mark.parametrize('label,runner', GUARDS)
def test_guard_accepts_an_archived_document_name_collision(monkeypatch, label, runner):
    runner(monkeypatch, [ARCHIVED_NAME_COLLISION])


@pytest.mark.parametrize('label,runner', GUARDS)
def test_guard_accepts_all_three_harmless_paths_together(monkeypatch, label, runner):
    runner(monkeypatch, list(HARMLESS))


@pytest.mark.parametrize('label,runner,frozen', FROZEN_EXAMPLES)
def test_guard_still_refuses_a_frozen_path(monkeypatch, label, runner, frozen):
    with pytest.raises(AssertionError):
        runner(monkeypatch, [frozen])


@pytest.mark.parametrize('label,runner,frozen', FROZEN_EXAMPLES)
def test_harmless_paths_do_not_mask_a_frozen_path(monkeypatch, label, runner, frozen):
    """A frozen path is still caught when it arrives alongside benign ones."""
    with pytest.raises(AssertionError):
        runner(monkeypatch, list(HARMLESS) + [frozen])


def test_the_frozen_frontend_file_is_still_refused(monkeypatch):
    """Exactly one frontend file is genuinely frozen. Dropping the blanket
    ``frontend/`` prefix must not have dropped it too."""
    with pytest.raises(AssertionError):
        _run_what_changed(
            monkeypatch, ['frontend/src/components/dashboard/WhatChangedCard.jsx']
        )
