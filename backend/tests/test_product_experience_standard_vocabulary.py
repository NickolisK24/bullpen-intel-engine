"""VOC-001 / #638 — the Product Experience Standard's public vocabulary contract.

Phases 1-9 gave every public vocabulary family one owner in code. This contract
holds the canonical document to the same result: the Standard is where a reader
of the repository learns which families exist, which labels belong to each, and
what presentation is allowed to do with them. A document that drifts from the
shipped vocabulary is worse than no document, because it is quotable.

Deliberately narrow. These tests assert the semantic content the vocabulary
reconciliation established — the family rosters, the ownership and pass-through
rules, the four labels that read like one ladder and are not, and the temporal
stamps that must stay apart. They are not a whole-document snapshot: page
missions, surface hierarchy, accessibility rules, and every other section may be
revised without touching this file.

Where a family has a code owner that is safe to import, the document is checked
against that owner rather than against a second hand-maintained list. The point
of VOC-001 is one owner per family; a doc test that keeps its own copy of the
role labels would quietly become a second one.
"""

from pathlib import Path
import re

from services.pitcher_public_labels import (
    READ_PUBLIC_LABELS,
    ROLE_PUBLIC_LABELS,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STANDARD_PATH = REPO_ROOT / 'docs' / 'canonical' / '03_PRODUCT_EXPERIENCE_STANDARD.md'

EXPECTED_VERSION = '1.4'
EXPECTED_EFFECTIVE_DATE = 'August 11, 2026'

# The board's reader-facing group headings. Held here as literals on purpose:
# services/bullpen_board.py cannot be imported without the database stack, and
# test_public_copy_contract.py already pins the same five strings against the
# live payload. If these two ever disagree, one of them is wrong and both fail.
EXPECTED_BOARD_GROUP_HEADINGS = (
    'Available Arms',
    'On-Watch Arms',
    'Limited Arms',
    'Unavailable — Heavy Workload',
    'Unavailable — Severe Workload',
)

# The engine statuses underneath those headings. Unchanged by VOC-001, and the
# document says so — a presentation label that quietly renamed a classification
# would be a behavior change wearing a wording change's clothes.
EXPECTED_ENGINE_STATUSES = (
    'Available',
    'Monitor',
    'Limited',
    'Avoid',
    'Unavailable',
)


def _standard_text():
    return STANDARD_PATH.read_text(encoding='utf-8')


def _section(text, heading, level=3):
    """Return the body of one heading's section, up to the next heading."""
    marker = '#' * level
    pattern = re.compile(
        rf'^{marker} {re.escape(heading)}\s*$(?P<body>.*?)(?=^\#{{1,{level}}} |\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    assert match, f'section {heading!r} not found in the Product Experience Standard'
    return match.group('body')


def _terms(body):
    """Return the bullet terms of a section, without any trailing definition."""
    terms = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('- '):
            continue
        term = line[2:].split(' - ', 1)[0]
        terms.append(term.replace('**', '').replace('`', '').strip())
    return tuple(terms)


def _limited_family_rows(text):
    """Return {label: family} from the Limited-family disambiguation table."""
    body = _section(text, 'The Limited family')
    rows = {}
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('|') or line.startswith('|---'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) != 3 or cells[0] in ('Label', ''):
            continue
        rows[cells[0]] = cells[1]
    return rows


def test_document_control_declares_version_1_4():
    text = _standard_text()

    assert f'| Version | {EXPECTED_VERSION} |' in text
    assert f'| Effective date | {EXPECTED_EFFECTIVE_DATE} |' in text
    assert '| Version | 1.3 |' not in text


def test_team_state_family_is_exactly_the_three_canonical_states():
    body = _section(_standard_text(), 'Team State')

    assert _terms(body) == ('Fresh', 'Stretched', 'Vulnerable')

    # No fourth state, by any of the names a surface has reached for before.
    for forbidden in ('Unknown', 'Neutral', 'Healthy'):
        assert f'- {forbidden}' not in body


def test_arm_availability_family_is_exact():
    body = _section(_standard_text(), 'Arm Availability')

    assert _terms(body) == ('Available', 'On Watch', 'Limited', 'Unavailable')


def test_pitcher_role_family_matches_its_backend_owner():
    body = _section(_standard_text(), 'Pitcher Role')

    assert _terms(body) == (
        'Trusted Arm',
        'Setup Arm',
        'Coverage Arm',
        'Middle Relief Arm',
        'Role Unclear',
    )
    # The document names exactly the labels the declared owner emits.
    assert set(_terms(body)) == {
        entry['label'] for entry in ROLE_PUBLIC_LABELS.values()
    }

    # Role is usage shape. It is not availability and it is not quality — the
    # two readings this family kept collecting.
    assert 'observed bullpen usage shape' in body
    assert 'not current availability' in body
    assert 'not pitcher quality' in body


def test_pitcher_current_read_family_matches_its_backend_owner():
    text = _standard_text()
    body = _section(text, 'Pitcher Current Read')

    assert _terms(body) == (
        'Clean Option',
        'Watch Arm',
        'Limited Rest',
        'Unavailable',
        'Limited Read',
    )
    assert set(_terms(body)) == {
        entry['label'] for entry in READ_PUBLIC_LABELS.values()
    }

    # Role and read answer different questions, and neither derives the other.
    assert 'Pitcher Role and Pitcher Current Read answer different questions.' in body
    assert 'neither is derived from the other' in body

    # Availability and current read are related, never interchangeable.
    assert 'never interchangeable' in body


def test_role_and_read_families_share_no_fallback_label():
    text = _standard_text()
    role_terms = set(_terms(_section(text, 'Pitcher Role')))
    read_terms = set(_terms(_section(text, 'Pitcher Current Read')))

    # The collision VOC-001 removed: both families used to end in 'Limited Read'.
    assert 'Limited Read' not in role_terms
    assert 'Role Unclear' not in read_terms

    # And 'Trusted Arm' is a pitcher role and nothing else.
    assert 'Trusted Arm' in role_terms
    assert '`Trusted Arm` belongs to this family alone.' in _section(text, 'Pitcher Role')


def test_read_confidence_is_an_evidence_family_not_a_baseball_conclusion():
    body = _section(_standard_text(), 'Read Confidence')

    assert _terms(body) == ('High', 'Medium', 'Low', 'Unavailable')

    assert 'how clear or complete the evidence behind a read is' in body
    assert 'not a baseball conclusion' in body
    for excluded in (
        'not Team State',
        'not Arm Availability',
        'not Pitcher Role',
        'not pitcher quality',
        'not a ranking',
        'not a prediction',
    ):
        assert excluded in body, excluded


def test_board_group_headings_are_presentation_labels_over_unchanged_statuses():
    body = _section(_standard_text(), 'Board group presentation')

    assert _terms(body) == EXPECTED_BOARD_GROUP_HEADINGS

    for status in EXPECTED_ENGINE_STATUSES:
        assert status in body, status

    assert 'are unchanged' in body
    assert 'no classification, membership, count, or ordering behavior' in body
    assert 'is not a pitcher' in body


def test_supporting_reads_are_documented_and_do_not_constitute_team_state():
    text = _standard_text()
    body = _section(text, 'Bullpen supporting reads')

    assert _terms(body) == (
        'Late-Inning Availability',
        'Rested Options',
        'Late-Inning Pressure',
        'Workload Concentration',
        'Coverage Safety',
        'Depth Safety',
        'Late-Inning Options',
    )

    for tier in (
        'Deep Rested Options',
        'Stable Rested Options',
        'Thin Rested Options',
        'Very Thin Rested Options',
    ):
        assert tier in body, tier

    # The rule this section exists for.
    assert 'Supporting reads are not Team State.' in body
    assert 'constitutes, implies, or overrides a Team State' in body

    # Retired team-level vocabulary, named so it cannot quietly return.
    assert '`Trusted Arms` is retired as a team-level concept' in body
    assert '`Healthy Rested Bullpen` is retired' in body

    # Team State is never assembled from the dimensions below it.
    team_state = _section(text, 'Team State')
    assert 'never inferred from supporting reads' in team_state
    assert 'Read Confidence' in team_state


def test_limited_family_distinction_is_recorded_with_each_term_s_family():
    text = _standard_text()
    rows = _limited_family_rows(text)

    assert rows == {
        'Limited': 'Arm Availability',
        'Limited Rest': 'Pitcher Current Read',
        'Limited Read': 'Pitcher Current Read / evidence limitation',
        'Role Unclear': 'Pitcher Role',
    }

    body = _section(text, 'The Limited family')
    assert 'four different dimensions' in body
    assert 'not four severity levels of one concept' in body
    assert 'ladder, order, or style them as degrees of the same thing' in body


def test_freshness_data_status_and_provenance_stay_three_separate_families():
    text = _standard_text()

    freshness = _section(text, 'Freshness')
    assert _terms(freshness) == ('Data through', 'Last data update', 'Last checked')
    assert 'three separate reader-facing temporal concepts' in freshness
    assert 'No surface collapses them' in freshness

    data_status = _section(text, 'Data Status')
    assert _terms(data_status) == (
        'Current',
        'Partial Data',
        'Stale',
        'Data Unavailable',
    )
    # The badges that borrowed baseball words, retired by name.
    assert '`Healthy`, `Limited`, and `Not Current` are not Data Status labels.' in data_status
    assert '`Limited` remains valid Arm Availability vocabulary.' in data_status

    provenance = _section(text, 'Provenance')
    assert _terms(provenance) == ('Generated at', 'Published at')
    assert 'not synonyms for Data through or Last data update' in provenance


def test_one_semantic_owner_rule_is_recorded():
    body = _section(_standard_text(), 'One semantic owner per family')

    assert 'exactly one semantic owner' in body
    assert 'competing dictionary for the same family' in body
    assert 'no family may borrow a word that already belongs to another family' in body


def test_backend_governed_labels_render_verbatim_and_presentation_owns_no_meaning():
    body = _section(_standard_text(), 'Backend-governed labels render verbatim')

    assert 'renders the supplied string exactly as supplied' in body

    # What presentation does own.
    for owned in (
        'layout',
        'density',
        'tone',
        'icons',
        'color',
        'interaction',
        'accessibility treatment',
    ):
        assert owned in body, owned

    # And what it does not.
    assert 'Presentation does not own meaning' in body
    for forbidden in ('translate', 'paraphrase', 'abbreviate', 'substitute', 'derive'):
        assert forbidden in body, forbidden
    assert 'may not supply a fallback label' in body


def test_how_to_read_is_the_canonical_reader_facing_semantic_map():
    text = _standard_text()

    assert '| Reader-facing public vocabulary map | About and How to Read |' in text

    body = _section(text, '24. Start Here / About and How to Read', level=2)
    assert 'How to Read is the canonical reader-facing semantic map.' in body
    for family in (
        'Team State',
        'Arm Availability',
        'Pitcher Role',
        'Pitcher Current Read',
        'Read Confidence',
    ):
        assert family in body, family

    # It must disambiguate the four similar terms rather than leave it to a reader.
    for term in ('`Limited`', '`Limited Rest`', '`Limited Read`', '`Role Unclear`'):
        assert term in body, term
    assert 'rather than leave it to inference' in body


def test_revision_history_records_the_version_1_4_entry():
    text = _standard_text()
    rows = [
        line for line in text.splitlines()
        if line.startswith(f'| {EXPECTED_VERSION} | {EXPECTED_EFFECTIVE_DATE} |')
    ]
    assert len(rows) == 1, 'exactly one Version 1.4 revision-history row'
    entry = rows[0]

    assert 'Nickolis Kacludis' in entry
    for claimed in (
        'one semantic owner per public family',
        'rendered verbatim',
        'Pitcher Role and Pitcher Current Read answer different questions',
        'never constitute a Team State',
        'Limited / Limited Rest / Limited Read / Role Unclear',
    ):
        assert claimed in entry, claimed

    # A vocabulary reconciliation claims no new capability. VOC-001 moved
    # strings; the entry must not read as though it moved anything else.
    assert 'No model, threshold, classification, capability, authority, or ' \
           'prediction behavior changes.' in entry
