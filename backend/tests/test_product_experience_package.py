"""UX-003 (D-054) is a presentation authority, and this proves it stayed one.

The change guards let the Product Experience Foundation migration touch an
enumerated set of protected frontend files. An allowlist that is only a list is
a hole: it says which files may change and nothing about what they may become.
These tests own the two properties that make the exemption safe.

1. **Exactness.** The constant equals the set of protected files the branch
   actually changes. It cannot quietly grow a path nobody reviewed, and it
   cannot keep naming a file the package no longer touches.
2. **Semantic ownership.** The allowlisted files derive no baseball meaning.
   The backend remains the owner of what may be claimed; these files arrange and
   label values it already governs.

Neither test weakens a guard. They are the purpose proof the guards' own
convention asks every allowlist to carry.
"""

import subprocess
from pathlib import Path

import pytest

from tests.product_experience_files import (
    UX003_PRODUCT_EXPERIENCE_FRONTEND_FILES,
    UX003_PRODUCT_EXPERIENCE_RUNTIME_FILES,
    UX003_PRODUCT_EXPERIENCE_TEST_FILES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _changed_files_vs_main():
    try:
        out = subprocess.run(
            ['git', 'diff', '--name-only', 'origin/main...HEAD'],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except Exception:
        pytest.skip('git diff against origin/main unavailable')
    return [line.strip().replace('\\', '/') for line in out.splitlines() if line.strip()]


def _source_of(relative):
    path = REPO_ROOT / relative
    if not path.exists():
        return None
    return path.read_text(encoding='utf-8')


def test_ux003_allowlist_is_exactly_the_frontend_files_the_branch_changes():
    """The constant is a description of the package, not a budget for it.

    A drifting allowlist is the failure mode this whole mechanism exists to
    prevent: a package lands, its constant keeps a few extra paths "for later",
    and the next edit to one of them sails through a guard nobody re-read. So
    the list is pinned in both directions — every protected frontend file the
    branch changes must be named, and every name must correspond to a file the
    branch actually changes.
    """
    changed = _changed_files_vs_main()
    if not changed:
        pytest.skip('no diff resolved')

    changed_frontend = {path for path in changed if path.startswith('frontend/')}
    if not changed_frontend:
        pytest.skip('branch changes no frontend file')

    declared = set(UX003_PRODUCT_EXPERIENCE_FRONTEND_FILES)

    undeclared = sorted(changed_frontend - declared)
    assert undeclared == [], (
        'these frontend files change on the branch but are not declared by any '
        f'UX-003 list, so no guard reviewed them: {undeclared}'
    )

    stale = sorted(declared - changed_frontend)
    assert stale == [], (
        'UX-003 declares these files but the branch does not change them; a '
        f'stale allowlist pre-approves a future edit nobody reviewed: {stale}'
    )


def test_ux003_lists_are_disjoint_exact_paths_with_no_wildcard():
    """No directory exemption, no glob, no duplicate, no overlap."""
    runtime = list(UX003_PRODUCT_EXPERIENCE_RUNTIME_FILES)
    tests = list(UX003_PRODUCT_EXPERIENCE_TEST_FILES)

    for entry in runtime + tests:
        assert '*' not in entry, f'wildcard in allowlist: {entry}'
        assert not entry.endswith('/'), f'directory exemption in allowlist: {entry}'
        assert (REPO_ROOT / entry).is_file(), f'allowlisted path is not a file: {entry}'

    assert len(runtime) == len(set(runtime)), 'duplicate runtime path'
    assert len(tests) == len(set(tests)), 'duplicate test path'
    assert set(runtime).isdisjoint(set(tests)), 'a path is in both lists'

    for entry in tests:
        assert entry.startswith('frontend/tests/'), f'not a test path: {entry}'
    for entry in runtime:
        assert not entry.startswith('frontend/tests/'), f'test path in runtime list: {entry}'


def test_ux003_transfers_no_team_state_authority_to_the_browser():
    """Presentation may render a decided Team State; it may not decide one.

    The internal-to-public projection lives in
    ``backend/services/team_state_public_vocabulary.py``, and the only frontend
    module allowed to validate its output is
    ``frontend/src/adapters/publicTeamState.js`` — which is deliberately NOT a
    UX-003 file. If a presentation file ever names an internal readiness code,
    it has started mapping meaning in the browser.
    """
    assert 'frontend/src/adapters/publicTeamState.js' not in (
        UX003_PRODUCT_EXPERIENCE_FRONTEND_FILES
    ), 'the Team State adapter is not a presentation file and is not UX-003 scope'

    internal_state_codes = (
        'operationally_stable',
        'operationally_constrained',
        'operationally_stressed',
    )
    offenders = []
    for relative in UX003_PRODUCT_EXPERIENCE_RUNTIME_FILES:
        source = _source_of(relative)
        if source is None:
            continue
        for code in internal_state_codes:
            if code in source:
                offenders.append(f'{relative}: {code}')
    assert offenders == [], (
        'UX-003 files must not name internal Team State codes; the backend owns '
        f'the projection: {offenders}'
    )


def test_ux003_resurrects_no_deleted_semantic_engine():
    """The engines main deleted stay deleted, and UX-003 does not re-import them.

    SEC-001 removed the public fatigue model and VOC-001 removed the duplicate
    frontend bullpen tier engine. A visual migration is exactly the kind of
    change that could quietly reintroduce either one while "just rendering a
    value", so the import surface is pinned rather than trusted.
    """
    assert not (REPO_ROOT / 'frontend/src/utils/fatigueModel.js').exists(), (
        'the public fatigue model was deleted by SEC-001 and must stay deleted'
    )

    # Bullpen.jsx already hosts the unchanged Reliever Finder fetch. Pass 3
    # adds only page chrome to that route owner; it neither adds nor calls a
    # browser semantic engine. Pin the grandfathered API use exactly so this is
    # not a general exemption for fatigue-shaped presentation logic.
    bullpen_shell = _source_of('frontend/src/components/bullpen/Bullpen.jsx') or ''
    assert bullpen_shell.count('getFatigueScores') == 2
    assert "import { getFatigueScores, getTeams } from '../../utils/api'" in bullpen_shell

    offenders = []
    for relative in UX003_PRODUCT_EXPERIENCE_RUNTIME_FILES:
        source = _source_of(relative)
        if source is None:
            continue
        for token in ('fatigueModel', 'getFatigueScores', 'fatigue_score', 'fatigueScore'):
            if relative == 'frontend/src/components/bullpen/Bullpen.jsx' and token == 'getFatigueScores':
                continue
            if token in source:
                offenders.append(f'{relative}: {token}')
    assert offenders == [], (
        f'UX-003 files must not reach for internal fatigue scoring: {offenders}'
    )


def test_ux003_claims_no_today_lead_story_authority():
    """D-054 grants presentation authority, not a new claim family.

    Today renders no lead story: no public claim contract for it exists in the
    Bullpen Intelligence Standard and Phase 3 Today lead authority is unstarted.
    The reader for the governed endpoint may exist, but it must not invent copy
    or carry the engine's selection internals out of the module.
    """
    surface = _source_of('frontend/src/components/home/IntelligenceSurface.jsx')
    assert surface is not None

    assert 'BaseballOS is watching this bullpen story' not in surface, (
        'a fabricated lead headline is a frontend-invented baseball claim'
    )
    assert 'buildSelectionMetadata' not in surface, (
        'story_priority / confidence are engine selection internals and must not '
        'leave the module'
    )


def test_ux003_reads_no_clock_on_the_today_path():
    """A stale read must not be able to acquire a fresh-looking date.

    Every date Today shows is a value the application was served. The defence
    that survives refactoring is that the rendering path never reads the current
    time at all, so there is no code path in which a non-current edition can be
    dated today.
    """
    clock_path = (
        'frontend/src/components/home/IntelligenceSurface.jsx',
        'frontend/src/components/intel/EditionHeader.jsx',
        'frontend/src/components/intel/TrustStrip.jsx',
        'frontend/src/components/UI/Freshness.jsx',
        'frontend/src/utils/dateDisplay.js',
    )
    offenders = []
    for relative in clock_path:
        source = _source_of(relative)
        if source is None:
            continue
        if 'new Date()' in source.replace(' ', '') or 'Date.now()' in source.replace(' ', ''):
            offenders.append(relative)
    assert offenders == [], (
        f'the Today path must not read the reader clock: {offenders}'
    )
