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

import subprocess

import pytest

import test_appearance_team_authority as appearance_guard
import test_public_team_relief_work as public_routes_guard
import test_qa_reconciliation_scenarios as phase0e_guard
import test_snapshot_trust_freeze as what_changed_guard


UNRELATED_FRONTEND = 'frontend/src/components/UI/ExampleUnusedComponent.jsx'
UNRELATED_MIGRATION = 'backend/migrations/versions/example_future_migration.py'
ARCHIVED_NAME_COLLISION = 'docs/archive/example_public_team_relief_work_history.md'

HARMLESS = (UNRELATED_FRONTEND, UNRELATED_MIGRATION, ARCHIVED_NAME_COLLISION)


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
    # This guard shells out to git itself rather than using a module helper.
    class _Result:
        stdout = '\n'.join(changed)

    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: _Result())
    appearance_guard.test_branch_touches_no_team_state_or_public_surface_files()


GUARDS = (
    ('frozen legacy What Changed', _run_what_changed),
    ('frozen public routes', _run_public_routes),
    ('phase 0E legacy public', _run_phase0e),
    ('appearance-team runtime surfaces', _run_appearance),
)

# One genuinely frozen path per guard.
FROZEN_EXAMPLES = (
    ('frozen legacy What Changed', _run_what_changed, 'backend/services/team_changes.py'),
    ('frozen public routes', _run_public_routes, 'backend/api/pitchers.py'),
    # tonight_intelligence_snapshot rather than bullpen_board or
    # dashboard_snapshot: those files hold reviewed branch-scoped exceptions
    # for H-6/H-7 and D-054 respectively. Any other genuinely frozen path in the
    # same catalogue proves the guard still refuses unapproved changes.
    (
        'phase 0E legacy public',
        _run_phase0e,
        'backend/services/tonight_intelligence_snapshot.py',
    ),
    (
        'appearance-team runtime surfaces',
        _run_appearance,
        'backend/services/team_state_payload.py',
    ),
)


@pytest.mark.parametrize('label,runner', GUARDS)
def test_guard_accepts_an_unrelated_frontend_file(monkeypatch, label, runner):
    runner(monkeypatch, [UNRELATED_FRONTEND])


@pytest.mark.parametrize('label,runner', GUARDS)
def test_guard_accepts_an_unrelated_migration(monkeypatch, label, runner):
    runner(monkeypatch, [UNRELATED_MIGRATION])


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
