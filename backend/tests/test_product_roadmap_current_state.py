"""The Product Roadmap's current-state contract.

The Roadmap is the canonical execution authority, and its failure mode is not a
wrong sentence: it is a stale true-yesterday sentence. Version 3.7 said #594 was
awaiting production verification for a day after that verification happened, and
nothing in the repository noticed. Version 3.8 then said VOC-001 was an unmerged
in-flight branch for a day after it merged and was production-verified — and
this file is what noticed. This contract pins the statements that go stale —
what is complete, what is active, what exits the phase, and in what order the
remaining work runs.

Re-pinned to Version 5.16 (D-058 per-team public-read authority decision). What it guards:

  * A closeout is evidence, not a status word. The #594 section must carry the
    run, the job, the counts, the represented date, the trusted snapshot, the
    routing repair, and both the valid and the fail-closed production route —
    and it must not name 398 as the trusted snapshot, which an earlier working
    note did. That assertion is scoped to the closeout section rather than
    banning the number document-wide, because 398 is a legitimate value
    elsewhere, including as VOC-001's own trusted snapshot.

  * A closed issue is not production proof. CI-003 (#598) remains complete only
    because its recorded run, tree, deployment, and routed-page evidence exist.

  * Order and package state are contracts. PRE-02B, PRE-02, TODAY-01 through
    TODAY-06, PIT-01 through PIT-07, and CMP-01 through CMP-02 are complete;
    SD-01, PI-01 through PI-02, and HIST-01 through HIST-04 are complete;
    History/Memory and the platform core loop are core-complete; no feature
    package is active; blocked, dated, and backlogged work may not silently advance.

  * Team Board package status is explicit. A completed user-facing package may
    not become future work, and a partial package may not be called complete.

  * An acceptance that expires must keep its date visible.

Narrow on purpose. Protected assets, risks, stop conditions, and the founder
operating system are not snapshotted here. D-051's trigger and league-trust
boundaries and D-052 remain invariant, while D-058 explicitly authorizes only
the staged per-team public-read architecture and records implementation pending.
"""

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
ROADMAP_PATH = (
    REPO_ROOT / 'docs' / 'canonical' / '05_PRODUCT_ROADMAP_DECISION_LEDGER.md'
)
TODAY_SURFACE_PATH = (
    REPO_ROOT / 'frontend' / 'src' / 'components' / 'home' / 'IntelligenceSurface.jsx'
)
FRONTEND_API_PATH = REPO_ROOT / 'frontend' / 'src' / 'utils' / 'api.js'
BULLPEN_API_PATH = REPO_ROOT / 'backend' / 'api' / 'bullpen.py'

EXPECTED_VERSION = '5.16'
EXPECTED_EFFECTIVE_DATE = 'September 4, 2026'
EXPECTED_MAIN = '8450485c7166c99ae65872a3d2aa2dcea41248b4'
PRE_02B_COMMIT = '399692904e6abbf462b31dd9db92512e726bb045'
TODAY_01_COMMIT = '77d77c56238844228bb07fcef9d173d3e1993e67'
TODAY_02_COMMIT = '3adb502f724362bc3612f3bf2a799a1560938a53'
TODAY_03_COMMIT = '08cf1c6a3267d3c7e5b93af4c2fa6a17dfe5e8d2'
TODAY_04_COMMIT = '655be73cd52b012a8cce904d7b808af54d51fc3f'
TODAY_05_COMMIT = '5b0668c4455161606a913b3300e1f9733f03b093'
TODAY_06_COMMIT = '4f513395216984c1e7332ad071f063c2de04dd6e'
PIT_01_COMMIT = 'edf1209b453ccaa3461c1c3ea19cd18bf5735657'

# The gated generated-content publication commit and the scheduled run that
# produced it. Version 3.9 asserted no such commit existed; that was true when
# written and false a day later, which is exactly the failure mode this file
# exists to catch.
CI_003_PUBLICATION_COMMIT = '2e83fa0'
CI_003_PUBLICATION_RUN = '31794183367'
CI_003_SNAPSHOT = '411'
CI_003_SYNC_RUN = '721'
CI_003_DATA_THROUGH = '2026-08-13'
CI_003_LIVE_ROUTE = 'https://baseballos.app/team/ATH'

# The DEP-001 edition, whose revision entry this file has pinned since #647.
# Later editions append beside it; they do not replace what it recorded.
DEP_VERSION = '3.9'
DEP_EFFECTIVE_DATE = 'August 13, 2026'

CLOSEOUT_HEADING = 'DIST-003 (#594) Production Closeout Evidence'

# The trusted export snapshot the verified #594 production pages were generated
# from, and the earlier mistaken value that must never take its place *in that
# closeout*. 398 is legitimate elsewhere — it is VOC-001's trusted snapshot.
CLOSEOUT_SNAPSHOT = '393'
REJECTED_CLOSEOUT_SNAPSHOT = '398'

# Version 5.16's post-core sequence. State is part of the contract: operational,
# strategic, blocked, dated, complete, and backlogged work must not silently
# become an active feature package.
APPROVED_EXECUTION = (
    (1, 'HIGH OPERATIONAL FOLLOW-UP', 'Since Yesterday natural production proof / share reliability'),
    (2, 'HIGH STRATEGIC', 'Retained data coverage and authority gaps'),
    (3, 'HIGH STRATEGIC', '2027 readiness'),
    (4, 'MEDIUM EXPANSION', 'UX, distribution, cross-season, and governed intelligence depth'),
    (5, 'LOW POLISH', 'History visualization, broad filters, and History-specific performance infrastructure'),
    (6, 'BLOCKED', 'TB-08 source-completeness follow-up'),
    (7, 'DATE-BOUND OBLIGATION', 'React Router migration (#645)'),
    (8, 'BACKLOGGED', 'Runtime work reduction'),
    (9, 'BACKLOGGED', 'Additional Team Board depth'),
    (10, 'COMPLETE PHASE', 'Platform core loop'),
)

TEAM_BOARD_PACKAGE_STATUSES = {
    'PRE-01': 'PARTIAL',
    'PRE-02': 'COMPLETE',
    'PRE-02B': 'COMPLETE',
    'TB-01': 'COMPLETE',
    'TB-02': 'COMPLETE',
    'TB-03': 'COMPLETE',
    'TB-04': 'COMPLETE',
    'TB-05': 'PARTIAL',
    'TB-06': 'COMPLETE',
    'TB-07': 'COMPLETE',
    'TB-08': 'PARTIAL',
    'TB-09': 'COMPLETE',
    'TB-10': 'COMPLETE',
    'TB-11': 'COMPLETE',
}

# Completed packages must not reappear as ordered future work.
COMPLETED_PACKAGES = (
    'VOC-001', '#638', '#601', 'DEP-001', 'CI-003', '#598', 'PRE-02B',
    'TODAY-01', 'TODAY-02', 'TODAY-03', 'TODAY-04', 'TODAY-05', 'TODAY-06',
    'PIT-01', 'HIST-01', 'HIST-02', 'HIST-03', 'HIST-04',
)

# The residual dependency acceptance is dated. If the date stops being visible,
# the expiry stops being reviewable.
ACCEPTANCE_EXPIRY = '2026-11-13'

# D-051 and D-052 carry the current authority posture. Their meaning is pinned
# by phrase, not by whole-row equality, so unrelated formatting cannot fail
# this while a weakened clause slips through.
D051_REQUIRED_PHRASES = (
    'Production full-daily execution is scheduled and first-attempt only',
    'generic manual daily execution',
    'local production daily invocation',
    'the legacy admin daily writer route',
    'GitHub reruns are non-authoritative/refused',
    'remaining trust and trigger boundaries stand',
)
D052_REQUIRED_PHRASES = (
    'Phase 1A Game-Driven Ingestion Authority Qualification is complete',
    'zero baseball-data mutation',
    'It grants no automated/scheduled write authority, no game-driven '
    'publication authority, no backfill authority, and no legacy-writer '
    'retirement.',
    'Permanent phase-exit decision',
)

# The shadow/backfill/legacy-writer posture a documentation pass must never move.
AUTHORITY_POSTURE_ROWS = (
    '| Daily game-driven lane | Shadow |',
    '| Postgame game-driven lane | Shadow |',
    '| Backfill lane | Off |',
    '| Production writer | Legacy sync/postgame path |',
    '| Automated write mode | Unapproved |',
    '| Game-driven publication authority | Unapproved |',
)


def _roadmap_text():
    return ROADMAP_PATH.read_text(encoding='utf-8')


def _section(text, heading, level=2):
    """Return the body of one heading's section, up to the next heading."""
    marker = '#' * level
    pattern = re.compile(
        rf'^{marker} {re.escape(heading)}\s*$(?P<body>.*?)(?=^\#{{1,{level}}} |\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    assert match, f'section {heading!r} not found in the Roadmap'
    return match.group('body')


def _ledger_row(text, decision_id):
    rows = [line for line in text.splitlines() if line.startswith(f'| {decision_id} |')]
    assert len(rows) == 1, f'exactly one {decision_id} ledger row'
    return rows[0]


def _next_approved_execution(text):
    """Return rank, state, and package from the Next Approved Work table."""
    body = _section(text, '6. Next Approved Work')
    execution = []
    for line in body.splitlines():
        line = line.strip()
        match = re.match(
            r'^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|',
            line,
        )
        if match:
            execution.append((
                int(match.group(1)),
                match.group(2).strip(),
                match.group(3).strip(),
            ))
    assert execution, 'no ordered work packages found'
    assert [rank for rank, _, _ in execution] == list(
        range(1, len(execution) + 1)
    ), 'work-package ranks must be contiguous and ascending'
    return execution


def _team_board_package_statuses(text):
    """Return the exact PRE/TB status map from the current reconciliation."""
    body = _section(text, 'Team Board 2.0 Current Status')
    statuses = {}
    for line in body.splitlines():
        match = re.match(
            r'^\|\s*((?:PRE|TB)-\d{2}B?)\s+—\s+[^|]+\|\s*([^|]+?)\s*\|',
            line.strip(),
        )
        if match:
            package, status = match.groups()
            assert package not in statuses, f'duplicate package status for {package}'
            statuses[package] = status.strip()
    return statuses


def test_roadmap_declares_current_version():
    text = _roadmap_text()

    assert f'| Version | {EXPECTED_VERSION} |' in text
    assert f'VERSION {EXPECTED_VERSION}' in text
    assert '| Version | 3.9 |' not in text
    assert 'VERSION 3.9' not in text


def test_effective_date_is_august_25_2026():
    text = _roadmap_text()

    assert f'| Effective date | {EXPECTED_EFFECTIVE_DATE} |' in text
    assert f'Effective {EXPECTED_EFFECTIVE_DATE}' in text


def test_repository_basis_is_audited_main_with_the_scoped_audit_branch():
    text = _roadmap_text()

    assert EXPECTED_MAIN in text
    assert (
        f'| Repository main | `{EXPECTED_MAIN}` | Audited `origin/main` after HIST-04 merged and deployed; '
        'includes the production-proven retained Team State timeline, repaired comparison carrier, '
        'backend-authored change markers, qualified transaction context, and all prior core-complete product surfaces. |'
        in text
    )
    assert (
        '| Audit branch | `docs/platform-core-loop-closeout` | '
        'Canonical status-only reconciliation after deployed History/Memory production proof. |'
        in text
    )

    # A superseded baseline must not still be claimed as current. The prior
    # basis may be named as history; it may not sit in the current-state row.
    assert '| Repository main | 18dd6914a933928254e969c85ecb19cf75b6a9f2 |' not in text
    assert '| Repository main | e3ad8bdf47a0bf6209917051df2070fba8eff417 |' not in text
    assert '| Repository main | `c63877a5b3d835b7190030d28ff143bedcafe099` |' not in text


def test_dist_003_is_recorded_complete_and_production_verified():
    text = _roadmap_text()
    body = _section(text, CLOSEOUT_HEADING)

    assert 'is **Complete**, production-verified August 11, 2026.' in body

    # And the state table agrees with the closeout section.
    assert '| DIST-003 (#594) | Complete |' in text
    assert 'production verification pending' not in text


def test_dist_003_closeout_records_its_production_evidence():
    body = _section(_roadmap_text(), CLOSEOUT_HEADING)

    for fragment in (
        '31483859116',                     # authorized scheduled export run
        '93760656523',                     # static team-preview export job
        '30 of 30 dated team previews',
        '| Previews withheld | 0 |',
        '2026-08-10',                      # represented baseball data
        '2026-08-11T11:15:00+00:00',       # export generated-at
        'PR #637',
        'Serve dated team preview pages at public team routes',
        '/team/COL',
        'dated_team_read',
        'Vulnerable',
        'trusted_dashboard_publication_v1',
        '684',                             # sync-run-id
        '2026-08-11T11:07:55.967061',      # published-at
        '/bullpen?view=board&team=COL&source=share',
        '/team/INVALID',
        'invalid_team',
    ):
        assert fragment in body, fragment

    assert f'| Trusted export snapshot | {CLOSEOUT_SNAPSHOT} |' in body

    # The fail-closed route publishes no claim and no receipt.
    assert 'no Team State, no data-through, no snapshot-id, no sync-run-id' in body

    # A social unfurl is explicitly not part of the recorded closeout.
    assert 'is not part of this recorded closeout' in body


def test_closeout_does_not_name_398_as_the_trusted_snapshot():
    """Scoped to the #594 closeout, not a document-wide ban on the number."""
    body = _section(_roadmap_text(), CLOSEOUT_HEADING)

    assert f'| Trusted export snapshot | {REJECTED_CLOSEOUT_SNAPSHOT} |' not in body
    assert f'trusted export snapshot for this closeout is **{CLOSEOUT_SNAPSHOT}**' in body

    # Where 398 appears at all, it appears as the rejected value.
    for line in body.splitlines():
        if REJECTED_CLOSEOUT_SNAPSHOT not in line:
            continue
        assert 'is not the snapshot' in line, line


def test_platform_core_loop_is_complete_with_no_active_feature_package():
    """The reconciliation closes the loop without manufacturing HIST-05."""
    text = _roadmap_text()

    assert '| PLATFORM CORE LOOP | COMPLETE |' in text
    assert 'PLATFORM CORE LOOP — COMPLETE' in text
    assert 'HIST-01 through HIST-04 are COMPLETE' in text
    assert 'No HIST package or replacement feature package is active.' in text
    assert 'There is no active HIST package and no replacement feature package is selected' in text
    assert '| ACTIVE | HIST-05' not in text

    # No current-state table may declare an active feature objective.
    assert '| ACTIVE OBJECTIVE |' not in text
    assert all(state != 'ACTIVE' for _, state, _ in _next_approved_execution(text))


def test_history_closeout_pins_deployed_proof_and_expansion_boundary():
    text = _roadmap_text()
    closeout = _section(text, '3. Platform Core Loop Closeout')
    completion_log = _section(text, 'Appendix A - Completion Log', level=1)

    for claimed in (
        '30 Team History endpoints',
        '1,019\ncanonical Team State rows',
        '180 comparable pairs',
        '95 changed pairs',
        '85 comparable unchanged',
        '808 `comparison_authority_missing`',
        'one\ncoverage gap',
        'Qualified transaction\noverlays remain operational',
        'one bounded History request',
    ):
        assert claimed in closeout, claimed

    for package in (
        'HIST-01 Team State Timeline Foundation',
        'HIST-02 Team State Change Markers',
        'HIST-03 Qualified Transaction Overlay',
        'HIST-04 Team State Comparison Carrier Repair',
    ):
        assert package in completion_log, package

    assert '| Phase 2 - Portable Intelligence | Core complete |' in text
    assert 'Natural production artifact generation remains unproven and unpopulated' in text
    assert 'observed zero natural `since_yesterday_change` rows' in closeout
    assert 'does not reopen Portable Intelligence or\nHistory/Memory and does not create PI-03' in closeout
    assert (
        'Short starts, Since Yesterday annotations, Pitcher History, visualization, '
        'filters, global discovery, and cross-season History remain expansion or polish'
        in text
    )


def test_today_01_completion_integrates_the_existing_lead_owner_once():
    """The completed package consumes its existing owner without request fan-out."""
    today_surface = TODAY_SURFACE_PATH.read_text(encoding='utf-8')
    frontend_api = FRONTEND_API_PATH.read_text(encoding='utf-8')
    bullpen_api = BULLPEN_API_PATH.read_text(encoding='utf-8')

    assert "@bullpen_bp.route('/intelligence/today', methods=['GET'])" in bullpen_api
    assert 'serve_today_lead_story(reference_date=reference_date)' in bullpen_api
    assert 'export const getTodayIntelligence' in frontend_api
    today_owner = 'useFetch(options => getTodayIntelligence({}, options))'
    assert today_surface.count(today_owner) == 1
    assert 'getTeamBoardV2' not in today_surface
    assert 'getTeamBullpen' not in today_surface

    # TODAY-01 composes the lead into a functioning Daily Edition; it is not a
    # replacement for the already-adopted Tonight and league sections. F-007
    # makes the trusted publication the Home Landscape authority, while F-004
    # projects that same governed value without the comprehensive carrier.
    for existing_owner in (
        'getTonightIntelligence',
        'getHomeProjection',
        'getTeams',
    ):
        assert existing_owner in today_surface, existing_owner
    assert 'getBullpenLandscape' not in today_surface
    assert 'getBullpenDashboard' not in today_surface
    assert 'const landscape = home.data?.landscape || null' in today_surface


def test_core_loop_closeout_preserves_every_authority_boundary():
    """Closing the sequence must not quietly relax its authority boundaries."""
    body = _section(_roadmap_text(), '3. Platform Core Loop Closeout')

    for preserved in (
        'D-051',
        'prohibits an\nauthoritative manual daily execution',
        'legacy sync/postgame writer remains\nthe baseball-data mutation authority',
        '`shadow`',
        'backfill remains `off`',
        'no game-driven write authority\nor game-driven publication authority is granted',
    ):
        assert preserved in body, preserved

    for boundary in (
        'There is no active HIST package and no replacement feature package is selected',
        'backend-owned HIST-01 comparison and emits a Team State\nchange marker only for',
        'an adjacent canonical pair whose comparison is both\nproven comparable and changed',
        'qualified pitcher transactions attributed through their\nstored historical source/destination teams',
        'exact transaction date',
        'canonical Team State 1.2 nested public code and label into scalar comparison-carrier values',
        'exact known retained malformed nested carrier shape through a side-effect-free compatibility projection',
        'rejects missing, contradictory, unsupported, or untrusted values',
        'preserves immutable ShareArtifacts, retained sidecars, publication seals, query bounds',
        'adds no event type, short start, Since Yesterday annotation, Pitcher History',
        'historical recomputation',
        '30 Team History endpoints',
        '180 comparable pairs',
        '95 changed pairs',
        '85 comparable unchanged',
        '`value_missing` defect\nis zero',
        '808 `comparison_authority_missing`',
        'does not create PI-03',
    ):
        assert boundary in body, boundary


def test_ci_003_completion_rests_on_evidence_not_on_the_closed_issue():
    """A closed issue and recorded evidence are still different claims.

    This is the successor to the PR #639 guard, and it survives the package
    closing. CI-003 is complete — but the Roadmap must record it complete
    because the run, the tree, the deployment, and the served page say so, not
    because the issue is closed. The distinction is what stops the next
    package from being marked complete on an issue state alone.
    """
    body = _section(_roadmap_text(), '3. Platform Core Loop Closeout')

    assert 'closed as **completed**' in body

    # The distinction itself must survive the package closing. If it is dropped
    # the moment it stops being inconvenient, it was never a contract.
    assert 'closed issue is still not by itself production proof' in body

    # Completion was not manufactured.
    assert (
        'No manual rerun, forced dispatch, or production mutation was used'
        in body
    )


def test_ci_003_publication_evidence_is_recorded_with_its_provenance():
    """The recorded negative went stale, so the positive carries its receipt.

    A bare "the commit exists" would rot the same way. The run, the attempt,
    the machine identity, the validated tree, and the snapshot are what make
    the claim checkable against the repository itself.
    """
    body = _section(_roadmap_text(), '3. Platform Core Loop Closeout')

    assert CI_003_PUBLICATION_COMMIT in body
    assert CI_003_PUBLICATION_RUN in body
    assert 'BaseballOS Automation <baseballoshq@gmail.com>' in body
    assert CI_003_SNAPSHOT in body
    assert CI_003_SYNC_RUN in body
    assert CI_003_DATA_THROUGH in body

    # Deployment and the live routed page are half the closeout. A Roadmap
    # that records only the commit records only half of what was required.
    assert 'deployment status on the generated commit is success' in body
    assert CI_003_LIVE_ROUTE in body
    assert 'trusted_dashboard_publication_v1' in body

    # Both retired false negatives. Each was true when written and false a day
    # later, which is the exact failure mode this file exists to catch.
    for retired in (
        'no gated, tree-exact, machine-attributed generated commit exists on main',
        'has not been taken',
        'The remaining closeout evidence',
        'deployment proof outstanding',
        'half the evidence',
    ):
        assert retired not in body, retired

    # A documentation pass does not move this package.
    assert (
        'Nothing in this edition changes the generated-content publication '
        'contract, its\nworkflow, D-053, or any authority it governs.'
    ) in body


def test_voc_001_and_dep_001_are_recorded_complete():
    text = _roadmap_text()

    assert '| VOC-001 (#638) | Complete |' in text
    assert '| DEP-001 (#601) | Complete |' in text

    # The stale in-flight language must be gone in all its forms.
    assert '| VOC-001 (#638) | Active;' not in text
    assert 'PR #639 is OPEN and NOT MERGED.' not in text
    assert 'Issue #638 remains OPEN.' not in text
    assert 'Open, unmerged, not deployed; this is not production truth.' not in text


def test_dep_001_records_its_residual_acceptance_and_expiry():
    text = _roadmap_text()

    assert ACCEPTANCE_EXPIRY in text
    assert '#645' in text

    # Recorded as time-boxed, not as a clean audit.
    body = _section(text, '3A. Preceding Package Outcomes')
    assert 'time-boxed' in body
    assert ACCEPTANCE_EXPIRY in body
    assert 'This is supply-chain hygiene.' in body
    assert (
        'No baseball semantics, publication gate, source authority, runtime '
        'configuration, or write authority changed.'
    ) in body


def test_voc_001_package_outcome_is_preserved_at_roadmap_altitude():
    """The vocabulary contract survives the package closing."""
    body = _section(_roadmap_text(), '3A. Preceding Package Outcomes')

    for label in (
        'Fresh / Stretched / Vulnerable',
        'Available / On Watch / Limited / Unavailable',
        'Trusted Arm / Setup Arm / Coverage Arm / Middle Relief Arm / Role Unclear',
        'Clean Option / Watch Arm / Limited Rest / Unavailable / Limited Read',
        'High / Medium / Low / Unavailable',
        '`Late-Inning Options`',
        '`Stable Rested Options`',
    ):
        assert label in body, label

    assert 'No model, threshold, classification, source authority, publication ' \
           'gate, or prediction behavior changed.' in body


def test_phase_1b_is_complete_in_both_phase_tables():
    text = _roadmap_text()

    phase_rows = [
        line for line in text.splitlines() if line.startswith('| Phase 1B')
    ]
    assert len(phase_rows) == 2, 'Phase 1B appears in both phase tables'

    for row in phase_rows:
        assert 'Complete' in row, row
        assert 'In progress' not in row, row
        # The exit is dated and attributed to production proof.
        assert 'Aug' in row and '12, 2026' in row, row

    # Phase 1A's exit is untouched by a later reconciliation.
    assert '| Phase 1A - Authority Qualification | Complete - August 10, 2026 |' in text


def test_approved_execution_order_and_states_are_preserved_exactly():
    execution = _next_approved_execution(_roadmap_text())

    assert execution == list(APPROVED_EXECUTION)


def test_team_board_package_statuses_are_exact_and_unique():
    statuses = _team_board_package_statuses(_roadmap_text())

    assert statuses == TEAM_BOARD_PACKAGE_STATUSES


def test_pre_02b_pre_02_and_be_gap_09_close_on_exact_transport_evidence():
    text = _roadmap_text()
    team_board = _section(text, 'Team Board 2.0 Current Status')
    backend_gaps = _section(text, 'Backend Gap Reconciliation')

    for fragment in (
        '| PRE-02 — Team Board Read Model v2 | COMPLETE |',
        '| PRE-02B — Team Board read-path consolidation | COMPLETE |',
        'Initial eager requests are 5 → 2',
        'team switching is 4 → 1',
        'Legacy `/board` remains available',
    ):
        assert fragment in team_board, fragment

    assert '| BE-GAP-09 — Team Board composition/query duplication | CLOSED |' in backend_gaps
    for fragment in (
        'one canonical board build',
        'calls the canonical Team Changes owner once',
        'isolates optional failures',
        'share-card work is lazy',
    ):
        assert fragment in backend_gaps, fragment


def test_recent_operations_reconciliation_is_current_without_moving_authority():
    text = _roadmap_text()

    assert '| Scheduled intraday repair | Retired for remainder of 2026 |' in text
    assert '| Postgame public-state preparation | Complete |' in text
    assert 'PR #729 / commit `2d91a1b2`' in text
    assert 'PR #730 / commit `e86a220d`' in text
    assert 'Daily plus postgame remain the active scheduled cadence' in text
    assert 'no product objective was created' in text


def test_completed_packages_are_not_listed_as_future_work():
    packages = [package for _, _, package in _next_approved_execution(_roadmap_text())]
    joined = '\n'.join(packages)

    for completed in COMPLETED_PACKAGES:
        assert completed not in joined, completed


def test_post_core_categories_do_not_select_an_active_feature_package():
    execution = _next_approved_execution(_roadmap_text())

    assert execution[0] == APPROVED_EXECUTION[0]
    assert all(state != 'ACTIVE' for _, state, _ in execution)
    assert (6, 'BLOCKED', 'TB-08 source-completeness follow-up') in execution
    assert (
        7,
        'DATE-BOUND OBLIGATION',
        'React Router migration (#645)',
    ) in execution
    assert (8, 'BACKLOGGED', 'Runtime work reduction') in execution
    assert (10, 'COMPLETE PHASE', 'Platform core loop') in execution


def test_authority_posture_is_unmoved():
    """A documentation reconciliation must never move the write posture."""
    text = _roadmap_text()

    for row in AUTHORITY_POSTURE_ROWS:
        assert row in text, row


def test_d051_preserves_its_trust_boundary_and_records_d058_amendment():
    row = _ledger_row(_roadmap_text(), 'D-051')

    for phrase in D051_REQUIRED_PHRASES:
        assert phrase in row, phrase
    for phrase in (
        'Amended by D-058',
        'one complete immutable per-team publication',
        'Compare remains common-boundary-only',
        'league surfaces remain complete-slate-only',
    ):
        assert phrase in row, phrase


def test_d052_is_unchanged_in_meaning():
    row = _ledger_row(_roadmap_text(), 'D-052')

    for phrase in D052_REQUIRED_PHRASES:
        assert phrase in row, phrase


def test_decision_ledger_is_contiguous_through_d058():
    """D-058 is the sole new durable authority decision in Version 5.16."""
    text = _roadmap_text()

    ids = re.findall(r'^\| (D-\d{3}) \|', text, re.MULTILINE)
    assert ids == [f'D-{number:03d}' for number in range(1, len(ids) + 1)], (
        'the Decision Ledger must stay contiguous and never renumber'
    )
    assert ids[-1] == 'D-058'

    assert 'Decision Ledger through D-058' in text
    assert 'Version 5.16 adds D-058.' in text

    # D-053 still names the package that decided it.
    assert 'D-053, added by CI-003 (#598)' in text
    assert 'D-054, added by UX-2B' in text
    assert 'D-055, added by Team Board Phase 2 Package 1' in text
    assert '| D-056 | Aug 18, 2026 |' in text

    d057 = _ledger_row(text, 'D-057')
    for phrase in (
        'PRE-02B read-path consolidation as the single active objective',
        'consolidate transport and duplicate population only',
        'may not change baseball semantics',
        'frontend interpretation authority',
        'thresholds, writers, publication gates',
        'governance/substrate-blocked depth',
        'Standing execution decision',
    ):
        assert phrase in d057, phrase

    d058 = _ledger_row(text, 'D-058')
    for phrase in (
        'immutable per-team public-read publication family',
        'backend-owned per-team current pointer',
        'no rendered package may mix authorities',
        'Compare remains common-boundary-only',
        'league-wide changes',
        'implementation pending',
    ):
        assert phrase in d058, phrase

    # A decision designed to expire is deliberately not a durable authority ID.
    assert 'DEP-001 (#601) created no Decision Ledger ID.' in text


def test_completion_log_records_the_closed_packages_with_evidence():
    text = _roadmap_text()
    body = _section(text, 'Appendix A - Completion Log', level=1)

    log_rows = [
        line for line in body.splitlines()
        if line.startswith('| Aug') or line.startswith('| Jul')
    ]
    joined = '\n'.join(log_rows)

    # Earlier evidence is preserved, not displaced.
    assert 'DIST-003 production closeout (#594)' in joined
    assert 'Routed team preview delivery correction' in joined
    assert 'PR #637' in joined

    # VOC-001 is now completed work, with its production evidence.
    assert 'VOC-001 public vocabulary and glossary parity (#638)' in joined
    assert '31589796614' in joined
    assert 'snapshot 398' in joined

    # DEP-001 is logged per slice, with the PRs and the verifying CI run.
    for fragment in ('PR #643', 'PR #644', 'PR #646', 'PR #647', '31729458591'):
        assert fragment in joined, fragment
    assert ACCEPTANCE_EXPIRY in joined

    for fragment in (
        'PR #729 / commit `2d91a1b2`',
        'PR #730 / commit `e86a220d`',
        'PR #731 / commit `39969290` / merge `4a39802c`',
        'Initial eager requests reduced 5 to 2',
        'PR #733 / commit `77d77c56` / merge `6f91c4d4`',
        'Public Today makes exactly one `/bullpen/intelligence/today` request',
        'PR #734 / commit `3adb502f` / merge `326e4da2`',
        'One `/bullpen/intelligence/tonight` response carries every game',
        'PR #735 / commit `08cf1c6a` / merge `14cdadb1`',
        'Every eligible Tonight game side carries the exact published Team State block',
        'PR #736 / commit `655be73c` / merge `773d3793`',
        'Every eligible Tonight game side carries the exact frozen seven-day workload carrier',
        'Scoped guard repairs `02b4d208` and `a19d19ae`',
        'PR #737 / commit `5b0668c4` / merge `46eb19a5`',
        'Every eligible Tonight game side carries exact short-start and bullpen-innings facts',
        'PR #738 / commit `d8611aea` / merge `6360a4b5`',
        'Initial 390px section height fell approximately 78.5%',
        'PR #739 / commit `4f513395` / merge `f545eb70`',
        'This closes the current governed Today/Tonight phase.',
        'PR #740 / commit `edf1209b` / guard repair `aca8e184` / merge `8036a27b`',
        'One eager `/bullpen/fatigue/:id` response carries pitcher/team identity',
        'PRs #741-#747 / merges `a10e29e4`, `cc128d07`, `21c0eab5`, `e8d3af8f`, `60824b97`, `3a8c9bb7`, `0722de60`',
        'PIT-02 through PIT-07 core closeout',
        'PRs #748-#749 / merges `17cfc862`, `16f72766`',
        'CMP-01 and CMP-02 core closeout',
        'PR #750 / commits `5b632ba2`, `288f5545` / merge `87bf735b`',
        'SD-01 Unified Entity Search',
        'PI-01 Team State Portable Citation',
        'PI-02 Since Yesterday Portable Change',
    ):
        assert fragment in joined, fragment


def test_revision_history_records_the_version_5_16_entry():
    """The current edition records D-058 as architecture, not implementation."""
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith(f'| {EXPECTED_VERSION} | {EXPECTED_EFFECTIVE_DATE} |')
    ]
    assert len(rows) == 1, 'exactly one Version 5.16 revision-history row'
    entry = rows[0]

    assert 'Nickolis Kacludis' in entry
    for claimed in (
        'game 824424 / SyncRun 4127',
        'complete-slate Dashboard correctly remains ineligible',
        'immutable per-team public-read authority family',
        'backend current pointer per team',
        'common-boundary-only Compare',
        'Implementation remains pending',
        'no model, migration, service, API, frontend, or production authority changed',
    ):
        assert claimed in entry, claimed


def test_revision_history_preserves_the_version_5_15_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith('| 5.15 | August 26, 2026 |')
    ]
    assert len(rows) == 1, 'exactly one historical Version 5.15 row'
    for claimed in (
        'deployed `origin/main` `8450485c`',
        'Closed HIST-04',
        'platform core loop complete',
        'D-001 through D-057 remain unchanged',
    ):
        assert claimed in rows[0], claimed


def test_revision_history_preserves_the_version_5_3_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith('| 5.3 | August 24, 2026 |')
    ]
    assert len(rows) == 1, 'exactly one historical Version 5.3 row'
    for claimed in ('`origin/main` `326e4da2`', 'TODAY-03', 'already-published public Team State'):
        assert claimed in rows[0], claimed


def test_revision_history_preserves_the_version_5_4_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith('| 5.4 | August 24, 2026 |')
    ]
    assert len(rows) == 1, 'exactly one historical Version 5.4 row'
    for claimed in ('`origin/main` `14cdadb1`', 'TODAY-04', 'seven-day workload carrier'):
        assert claimed in rows[0], claimed


def test_revision_history_preserves_the_version_5_2_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith('| 5.2 | August 24, 2026 |')
    ]
    assert len(rows) == 1, 'exactly one historical Version 5.2 row'
    for claimed in ('`origin/main` `6f91c4d4`', 'TODAY-02', 'Team State and role facts out'):
        assert claimed in rows[0], claimed


def test_revision_history_preserves_the_version_5_1_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith('| 5.1 | August 24, 2026 |')
    ]
    assert len(rows) == 1, 'exactly one historical Version 5.1 row'
    for claimed in ('`origin/main` `4a39802c`', 'TODAY-01', 'D-001 through D-057'):
        assert claimed in rows[0], claimed


def test_revision_history_preserves_the_version_5_0_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith('| 5.0 | August 23, 2026 |')
    ]
    assert len(rows) == 1, 'exactly one historical Version 5.0 row'
    for claimed in ('`origin/main` `c63877a5`', 'added D-057', 'PRE-02B'):
        assert claimed in rows[0], claimed


def test_revision_history_preserves_the_version_4_2_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith('| 4.2 | August 15, 2026 |')
    ]
    assert len(rows) == 1, 'exactly one historical Version 4.2 revision-history row'
    for claimed in ('D-055', 'Team Board Phase 2 Package 1', 'fail-closed Rest Status'):
        assert claimed in rows[0], claimed


def test_revision_history_preserves_the_version_4_1_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith('| 4.1 | August 15, 2026 |')
    ]
    assert len(rows) == 1, 'exactly one historical Version 4.1 revision-history row'
    for claimed in ('D-054', 'UX-2B', '30-club'):
        assert claimed in rows[0], claimed


def test_revision_history_records_the_version_3_9_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith(f'| {DEP_VERSION} | {DEP_EFFECTIVE_DATE} |')
    ]
    assert len(rows) == 1, 'exactly one Version 3.9 revision-history row'
    entry = rows[0]

    assert 'Nickolis Kacludis' in entry
    for claimed in (
        'e3ad8bd',
        '31729458591',
        'trusted snapshot 398',
        'PRs #643, #644, #646, and #647',
        'requirements-dev.txt',
        '6.30.4',
        ACCEPTANCE_EXPIRY,
        '#645',
        'CI-003 (#598)',
        'production-proof evidence this Roadmap requires is still outstanding',
    ):
        assert claimed in entry, claimed

    assert (
        'No durable authority decision was added, weakened, or renumbered; '
        'D-051, D-052, and D-053 stand unchanged; no new Decision Ledger ID was '
        'created; and the shadow/backfill/legacy-writer authority posture is '
        'untouched.'
    ) in entry


def test_prior_revision_history_is_preserved():
    """History is appended, never rewritten."""
    text = _roadmap_text()

    for prior in ('| 3.7 | August 11, 2026 |', '| 3.8 | August 11, 2026 |'):
        assert prior in text, prior
