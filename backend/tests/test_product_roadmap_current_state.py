"""VOC-001 / #638 — the Product Roadmap's current-state contract.

The Roadmap is the canonical execution authority, and its failure mode is not a
wrong sentence: it is a stale true-yesterday sentence. Version 3.7 said #594 was
awaiting production verification for a day after that verification happened, and
nothing in the repository noticed. This contract pins the statements that go
stale — what is complete, what is active, what is merely in flight, what exits
the phase, and in what order the remaining work runs.

Two things it guards specifically:

  * A closeout is evidence, not a status word. The #594 section must carry the
    run, the job, the counts, the represented date, the trusted snapshot, the
    routing repair, and both the valid and the fail-closed production route —
    and it must not name 398 as the trusted snapshot, which an earlier working
    note did. That assertion is scoped to the closeout section rather than
    banning the number document-wide, because 398 is a legitimate value
    elsewhere.

  * Branch work is not production truth. PR #639 is open and unmerged, #638 is
    open, and the canonical documents it carries are pending merge. A Roadmap
    that reads a green branch as a finished product is the exact error this
    file exists to catch.

Narrow on purpose. Phase structure, protected assets, risks, stop conditions,
the founder operating system, and the Decision Ledger's contents are not
snapshotted here — only that the ledger gained no ID and that D-051 and D-052
still say what they said.
"""

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
ROADMAP_PATH = (
    REPO_ROOT / 'docs' / 'canonical' / '05_PRODUCT_ROADMAP_DECISION_LEDGER.md'
)

EXPECTED_VERSION = '3.8'
EXPECTED_EFFECTIVE_DATE = 'August 11, 2026'

CLOSEOUT_HEADING = 'DIST-003 (#594) Production Closeout Evidence'

# The trusted export snapshot the verified production pages were generated
# from, and the earlier mistaken value that must never take its place.
CLOSEOUT_SNAPSHOT = '393'
REJECTED_CLOSEOUT_SNAPSHOT = '398'

# The approved order after VOC-001 closes. Order is the contract — a roadmap
# that quietly promotes Portable Intelligence ahead of the reliability work is
# the reordering this pins against.
POST_VOC_ORDER = (
    '#598',
    '#601',
    'Permanent daily-sync work reduction',
    'Portable Intelligence',
    'Resume M-001 and visible evidence',
    'Daily Habit and Consequence',
)

# D-051 and D-052 carry the current authority posture. Their meaning is pinned
# by phrase, not by whole-row equality, so unrelated formatting cannot fail
# this while a weakened clause slips through.
D051_REQUIRED_PHRASES = (
    'Production full-daily execution is scheduled and first-attempt only',
    'generic manual daily execution',
    'local production daily invocation',
    'the legacy admin daily writer route',
    'GitHub reruns are non-authoritative/refused',
    'Standing trust boundary',
)
D052_REQUIRED_PHRASES = (
    'Phase 1A Game-Driven Ingestion Authority Qualification is complete',
    'zero baseball-data mutation',
    'It grants no automated/scheduled write authority, no game-driven '
    'publication authority, no backfill authority, and no legacy-writer '
    'retirement.',
    'Permanent phase-exit decision',
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


def _next_approved_work_order(text):
    """Return the work packages of the Next Approved Work table, in order."""
    body = _section(text, '6. Next Approved Work')
    packages = []
    for line in body.splitlines():
        line = line.strip()
        match = re.match(r'^\|\s*(\d+)\s*\|([^|]+)\|', line)
        if match:
            packages.append((int(match.group(1)), match.group(2).strip()))
    assert packages, 'no ordered work packages found'
    assert [rank for rank, _ in packages] == list(
        range(1, len(packages) + 1)
    ), 'work-package ranks must be contiguous and ascending'
    return [package for _, package in packages]


def test_roadmap_declares_version_3_8():
    text = _roadmap_text()

    assert f'| Version | {EXPECTED_VERSION} |' in text
    assert f'VERSION {EXPECTED_VERSION}' in text
    assert '| Version | 3.7 |' not in text
    assert 'VERSION 3.7' not in text


def test_effective_date_is_august_11_2026():
    text = _roadmap_text()

    assert f'| Effective date | {EXPECTED_EFFECTIVE_DATE} |' in text
    assert f'Effective {EXPECTED_EFFECTIVE_DATE}' in text


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


def test_voc_001_is_the_active_objective():
    text = _roadmap_text()

    assert (
        '| ACTIVE OBJECTIVE | VOC-001 (#638) — public vocabulary / glossary '
        'parity closeout |'
    ) in text

    body = _section(text, '3. Active Objective')
    assert 'Phases 1 through 10B are implemented in PR #639.' in body
    assert 'Product Experience Standard v1.4 is in PR #639.' in body
    assert 'Bullpen Intelligence Standard v1.3 is in PR #639.' in body

    # Roadmap-altitude scope summary only, and no capability claim.
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


def test_voc_001_is_not_marked_complete():
    text = _roadmap_text()
    body = _section(text, '3. Active Objective')

    assert 'Issue #638 remains OPEN.' in body
    assert 'Production verification has NOT yet occurred for VOC-001.' in body
    assert 'Close #638 only after production proof' in body

    # The state table must not promote it.
    assert '| VOC-001 (#638) | Complete |' not in text
    assert '| VOC-001 (#638) | Active;' in text


def test_pr_639_is_recorded_as_in_flight_and_not_production_truth():
    text = _roadmap_text()

    assert 'PR #639 is OPEN and NOT MERGED.' in _section(text, '3. Active Objective')
    assert 'Open, unmerged, not deployed; this is not production truth.' in text

    basis = _section(text, 'Repository basis')
    assert 'PR #639, which is open and unmerged' in basis
    assert 'repository implementation pending merge' in basis
    assert 'are not production or main truth until PR #639 merges' in basis

    # Production main is the merged baseline, not the branch.
    assert '18dd6914a933928254e969c85ecb19cf75b6a9f2' in text


def test_phase_1b_remains_active_with_a_production_exit_condition():
    text = _roadmap_text()

    active_rows = [
        line for line in text.splitlines()
        if line.startswith('| Phase 1B') and 'In progress / active' in line
    ]
    assert len(active_rows) == 2, 'Phase 1B is active in both phase tables'

    for row in active_rows:
        assert 'PR #639' in row
        assert '#638' in row
        assert 'smoke' in row
        # Repository CI is never the phase exit, however each table words it.
        assert 'CI green' in row
        assert 'not sufficient' in row or 'does not exit the phase' in row


def test_post_voc_work_order_is_preserved_exactly():
    packages = _next_approved_work_order(_roadmap_text())

    # VOC-001 is first; everything after it keeps the approved order.
    assert packages[0].startswith('VOC-001 (#638)')
    remaining = packages[1:]
    assert len(remaining) == len(POST_VOC_ORDER)
    for actual, expected in zip(remaining, POST_VOC_ORDER):
        assert actual.startswith(expected), f'{actual!r} does not start with {expected!r}'


def test_portable_intelligence_does_not_precede_the_reliability_work():
    packages = _next_approved_work_order(_roadmap_text())
    index = {package: position for position, package in enumerate(packages)}

    def position_of(prefix):
        matches = [pos for package, pos in index.items() if package.startswith(prefix)]
        assert len(matches) == 1, prefix
        return matches[0]

    portable = position_of('Portable Intelligence')
    assert position_of('#598') < portable
    assert position_of('#601') < portable
    assert position_of('Permanent daily-sync work reduction') < portable
    assert portable < position_of('Resume M-001 and visible evidence')


def test_d051_is_unchanged_in_meaning():
    row = _ledger_row(_roadmap_text(), 'D-051')

    for phrase in D051_REQUIRED_PHRASES:
        assert phrase in row, phrase


def test_d052_is_unchanged_in_meaning():
    row = _ledger_row(_roadmap_text(), 'D-052')

    for phrase in D052_REQUIRED_PHRASES:
        assert phrase in row, phrase


def test_version_3_8_introduces_no_new_decision_ledger_id():
    text = _roadmap_text()

    ids = re.findall(r'^\| (D-\d{3}) \|', text, re.MULTILINE)
    assert ids == [f'D-{number:03d}' for number in range(1, 53)]
    assert ids[-1] == 'D-052'

    assert 'Decision Ledger through D-052' in text
    assert 'adds no Decision Ledger ID' in text
    assert (
        'The current-state reconciliation does not create a new durable '
        'semantic or authority decision.'
    ) in text


def test_completion_log_records_594_and_637_but_not_638():
    text = _roadmap_text()
    body = _section(text, 'Appendix A - Completion Log', level=1)

    log_rows = [
        line for line in body.splitlines()
        if line.startswith('| Aug') or line.startswith('| Jul')
    ]
    joined = '\n'.join(log_rows)

    assert 'DIST-003 production closeout (#594)' in joined
    assert 'Routed team preview delivery correction' in joined
    assert 'PR #637' in joined

    # An open package is never logged as completed work.
    assert '#638' not in joined
    assert 'VOC-001' not in joined


def test_revision_history_records_the_version_3_8_entry():
    text = _roadmap_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith(f'| {EXPECTED_VERSION} | {EXPECTED_EFFECTIVE_DATE} |')
    ]
    assert len(rows) == 1, 'exactly one Version 3.8 revision-history row'
    entry = rows[0]

    assert 'Nickolis Kacludis' in entry
    for claimed in (
        '31483859116',
        '93760656523',
        'trusted snapshot 393',
        '/team/COL',
        '/team/INVALID',
        'PR #637',
        'VOC-001 (#638)',
        'open and unmerged',
        '#638 remains open',
        'repository CI green is necessary and not sufficient',
        '#598, then #601, then permanent daily-sync work reduction, then '
        'Portable Intelligence, then M-001 and visible evidence, then Daily '
        'Habit and consequence',
    ):
        assert claimed in entry, claimed

    assert (
        'No durable authority decision was added, weakened, or renumbered, '
        'D-051 and D-052 stand unchanged, and no new Decision Ledger ID was '
        'created.'
    ) in entry
