"""VOC-001 / #638 — the Bullpen Intelligence Standard's public-language contract.

The Product Experience Standard says how a governed label reaches a reader. This
one says who owns the word and what it means. That is the half that rots
quietly: a document naming `backend/services/pitcher_public_labels.py` as the
role owner is only useful while that file still emits the labels the document
lists, and nothing but a test notices when the two drift.

So this contract binds the document to the live owners rather than to a second
hand-maintained list. Team State, arm availability, pitcher role, pitcher
current read, and the supporting-read tiers are all asserted against the modules
Section 8 names as their semantic owners. If a label moves in code and not in
the Standard, this fails; if it moves in the Standard and not in code, this
fails too.

Deliberately narrow. Nothing here snapshots the document. The observation
ladder, the four-class model, source authority, the data domains, the M-001
contract, publication gates, and the capability registry may all be revised
without touching this file — only the public-language architecture is pinned.
"""

from pathlib import Path
import re

from services.pitcher_public_labels import (
    READ_PUBLIC_LABELS,
    ROLE_PUBLIC_LABELS,
)
from services.public_bullpen_copy import PUBLIC_AVAILABILITY_STATUSES
from services.team_bullpen_shape import TEAM_BULLPEN_PUBLIC_LABELS
from services.team_state_public_vocabulary import PUBLIC_TEAM_STATE_LABEL_SET


REPO_ROOT = Path(__file__).resolve().parents[2]
STANDARD_PATH = (
    REPO_ROOT / 'docs' / 'canonical' / '02_BULLPEN_INTELLIGENCE_STANDARD.md'
)

EXPECTED_VERSION = '1.4'
EXPECTED_EFFECTIVE_DATE = 'August 14, 2026'

# The VOC-001 edition, whose revision entry this file has pinned since #638.
VOC_VERSION = '1.3'
VOC_EFFECTIVE_DATE = 'August 11, 2026'

# The four modules Section 8 names as semantic owners. Each is a real import
# above, so a rename that leaves the document behind breaks collection here
# rather than silently orphaning the owner map.
EXPECTED_OWNER_PATHS = (
    'backend/services/team_state_public_vocabulary.py',
    'backend/services/public_bullpen_copy.py',
    'backend/services/pitcher_public_labels.py',
    'backend/services/team_bullpen_shape.py',
)

# The six supporting dimensions owned by team_bullpen_shape.py, plus the
# team-level concept that replaced 'Trusted Arms'.
EXPECTED_SUPPORTING_DIMENSIONS = (
    'Late-Inning Availability',
    'Rested Options',
    'Late-Inning Pressure',
    'Workload Concentration',
    'Coverage Safety',
    'Depth Safety',
)
LATE_INNING_OPTIONS = 'Late-Inning Options'

# Tier examples the document cites. Every one must be a real label the owner
# emits — a Standard that invents a plausible-looking tier is worse than one
# that lists none.
CITED_TIERS = (
    'Strong Late-Inning Availability',
    'Stable Rested Options',
    'High Late-Inning Pressure',
    'Concentrated Workload',
    'Thin Coverage Safety',
    'Limited Depth Safety',
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
    assert match, f'section {heading!r} not found in the Bullpen Intelligence Standard'
    return match.group('body')


def _clean(cell):
    return cell.replace('**', '').replace('`', '').strip()


def _terms(body):
    """Return the bullet terms of a section, without any trailing definition."""
    terms = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('- '):
            continue
        terms.append(_clean(line[2:].split(' - ', 1)[0]))
    return tuple(terms)


def _table_rows(body):
    """Return the data rows of the first markdown table in ``body``."""
    rows = []
    header_seen = False
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('|'):
            if rows:
                break
            continue
        cells = [_clean(cell) for cell in line.strip('|').split('|')]
        if set(''.join(cells)) <= {'-'}:
            header_seen = True
            continue
        if not header_seen:
            continue
        rows.append(cells)
    return rows


def _first_column(body):
    return tuple(row[0] for row in _table_rows(body))


def _revision_row(text, version=None, effective=None):
    version = version or EXPECTED_VERSION
    effective = effective or EXPECTED_EFFECTIVE_DATE
    rows = [
        line for line in text.splitlines()
        if line.startswith(f'| {version} | {effective} |')
    ]
    assert len(rows) == 1, f'exactly one Version {version} revision-history row'
    return rows[0]


def test_document_control_declares_version_1_4():
    text = _standard_text()

    assert f'| Version | {EXPECTED_VERSION} |' in text
    assert f'| Effective date | {EXPECTED_EFFECTIVE_DATE} |' in text
    assert '| Version | 1.3 |' not in text
    # Ownership of the document itself is unchanged.
    assert '| Owner | Nickolis Kacludis |' in text


def test_public_language_owner_map_names_every_semantic_owner():
    body = _section(_standard_text(), 'Semantic families and their owners')

    families = {row[0]: row[2] for row in _table_rows(body)}
    assert families == {
        'Team State': 'backend/services/team_state_public_vocabulary.py',
        'Arm availability': 'backend/services/public_bullpen_copy.py',
        'Pitcher role': 'backend/services/pitcher_public_labels.py',
        'Pitcher current read': 'backend/services/pitcher_public_labels.py',
        'Bullpen supporting reads': 'backend/services/team_bullpen_shape.py',
        # Workload Data is the one family whose label catalogue does not live in
        # a backend module. The backend still decides the state; the owner cell
        # says so, and says where the catalogue currently is, rather than
        # pretending a backend owner exists.
        'Workload Data': (
            'Backend availability.data_state; public label catalogue in '
            'frontend/src/components/bullpen/availabilityView.js'
        ),
    }

    for path in EXPECTED_OWNER_PATHS:
        assert path in body, path
        assert (REPO_ROOT / path).is_file(), f'{path} named as owner but absent'

    assert 'one semantic owner in code' in body
    assert 'Nothing downstream may hold a second dictionary for the same family.' in body


def test_semantic_family_separation_is_explicit():
    body = _section(_standard_text(), 'Semantic families and their owners')

    assert (
        'Team State is not arm availability, is not pitcher role, is not pitcher '
        'current read, is not read confidence, and is not a bullpen supporting read.'
    ) in body
    assert 'These are not synonyms.' in body
    assert 'No family may serve as a fallback or a substitute for another' in body

    # Each family carries a definition, and each one states what it is not.
    definitions = _terms(body)
    assert definitions == (
        'Team State',
        'Arm availability',
        'Pitcher role',
        'Pitcher current read',
        'Read confidence',
        'Bullpen supporting read',
    )
    assert 'It is not current availability, talent, quality, manager intent, or a recommendation.' in body
    assert 'does not replace pitcher role' in body


def test_team_state_catalogue_matches_its_owner_and_stays_the_only_authority():
    text = _standard_text()
    body = _section(text, 'Team State')

    assert set(_first_column(body)) == set(PUBLIC_TEAM_STATE_LABEL_SET)
    assert _first_column(body) == ('Fresh', 'Stretched', 'Vulnerable')
    assert 'not a fourth Team State' in body

    # Only the named authority may publish one, and nothing may be translated
    # into one.
    assert 'Only that authority may publish a Team State.' in body
    for excluded in (
        'supporting-read tier',
        'tier adjective',
        'group count',
        'availability label',
        'pitcher current read',
        'read-confidence value',
    ):
        assert excluded in body, excluded


def test_arm_availability_catalogue_matches_its_owner():
    body = _section(_standard_text(), 'Arm availability')

    assert _first_column(body) == PUBLIC_AVAILABILITY_STATUSES
    assert _first_column(body) == ('Available', 'On Watch', 'Limited', 'Unavailable')

    # Engine vocabulary stays internal, and the document says which words those are.
    assert 'Monitor' in body and 'Avoid' in body
    assert 'neither internal word reaches a reader' in body


def test_pitcher_current_read_catalogue_matches_its_backend_owner():
    body = _section(_standard_text(), 'Pitcher current read - public arm read labels')

    documented = set(_first_column(body))
    assert documented == {entry['label'] for entry in READ_PUBLIC_LABELS.values()}
    assert _first_column(body) == (
        'Clean Option',
        'Watch Arm',
        'Limited Rest',
        'Unavailable',
        'Limited Read',
    )

    # The owner named here is the owner named in the family map.
    assert 'backend/services/pitcher_public_labels.py` owns the final rendered language' in body

    # Availability and current read: related, never interchangeable.
    assert 'Availability and current read are related and not interchangeable.' in body
    assert 'Neither may be substituted for the other' in body
    assert '`Unavailable` legitimately appears in both catalogues' in body
    assert 'which question is being answered' in body


def test_pitcher_role_catalogue_matches_its_backend_owner():
    body = _section(_standard_text(), 'Pitcher role - public role labels')

    assert _terms(body) == (
        'Trusted Arm',
        'Setup Arm',
        'Coverage Arm',
        'Middle Relief Arm',
        'Role Unclear',
    )
    assert set(_terms(body)) == {
        entry['label'] for entry in ROLE_PUBLIC_LABELS.values()
    }


def test_role_unclear_and_limited_read_remain_different_family_fallbacks():
    text = _standard_text()
    role = _section(text, 'Pitcher role - public role labels')
    read = _section(text, 'Pitcher current read - public arm read labels')

    # The collision VOC-001 removed, recorded in the document and in code.
    assert 'Limited Read' not in _terms(role)
    assert 'Role Unclear' not in _first_column(read)
    assert ROLE_PUBLIC_LABELS['limited_read']['label'] == 'Role Unclear'
    assert READ_PUBLIC_LABELS['limited_read']['label'] == 'Limited Read'

    assert 'The two families fail closed separately.' in role
    assert '`Role Unclear` means observed usage evidence is insufficient' in role
    assert '`Limited Read` means current evidence is insufficient' in role
    assert 'they may not share one public label' in role
    assert "The role family's earlier use of `Limited Read` is retired." in role


def test_trusted_arms_is_retired_and_late_inning_options_replaces_it():
    text = _standard_text()
    role = _section(text, 'Pitcher role - public role labels')
    supporting = _section(text, 'Bullpen supporting reads - named bullpen reads')

    assert '`Trusted Arm` belongs to this family alone.' in role
    assert 'The former team-level concept `Trusted Arms` is retired' in role
    assert f'**{LATE_INNING_OPTIONS}**' in role
    assert 'workload and roster context leave them usable in the represented read' in role
    assert 'It never says a manager will use them.' in role

    # And the replacement is carried in the supporting-read family.
    assert LATE_INNING_OPTIONS in supporting

    # The retired plural is never presented as a live team-level read.
    assert 'Trusted Arms' not in _terms(supporting)


def test_supporting_reads_are_documented_and_never_constitute_team_state():
    body = _section(
        _standard_text(), 'Bullpen supporting reads - named bullpen reads'
    )

    assert _terms(body) == EXPECTED_SUPPORTING_DIMENSIONS

    # Every tier the document cites is a label the owner actually emits.
    owned = {label for tiers in TEAM_BULLPEN_PUBLIC_LABELS.values() for label in tiers}
    for tier in CITED_TIERS:
        assert tier in body, tier
        assert tier in owned, f'{tier} cited by the Standard but not emitted by the owner'

    assert 'carry no Team State meaning by themselves' in body
    assert 'Only the Team State authority may publish Fresh, Stretched, or Vulnerable.' in body
    assert 'No surface may translate a supporting-read tier into a Team State' in body
    assert 'may not independently derive a competing public tier system' in body


def test_healthy_rested_bullpen_is_retired_on_the_unobservable_boundary():
    text = _standard_text()
    body = _section(text, 'Bullpen supporting reads - named bullpen reads')

    assert '`Healthy Rested Bullpen` is retired' in body
    assert '**Stable Rested Options**' in body

    # Tied to the private-health boundary, not to taste.
    assert 'medical status, soreness, injury absence' in body
    assert 'Section 2 classes as Unobservable' in body

    # And Section 2 carries the rule the retirement is an instance of.
    unobservable = _section(text, '2. Four-Class Data Model', level=2)
    assert 'Public vocabulary is bound by this class.' in unobservable
    assert 'private physical condition' in unobservable
    assert 'even when the value behind it is computed purely from observed workload' in unobservable

    # Wording only: the replacement is a live tier and the retired string is gone.
    assert 'Stable Rested Options' in TEAM_BULLPEN_PUBLIC_LABELS['cleanOptions']
    owned = {label for tiers in TEAM_BULLPEN_PUBLIC_LABELS.values() for label in tiers}
    assert 'Healthy Rested Bullpen' not in owned
    assert 'tier count, tier order, and every clean-options, workload, availability, ' \
           'and supporting-read boundary are unchanged' in body


def test_backend_governed_labels_are_final_and_frontend_may_not_translate():
    body = _section(
        _standard_text(), 'Backend-governed labels and the frontend boundary'
    )

    assert 'the backend decides the semantic label, and the frontend renders the label it was supplied' in body

    for owned in ('layout', 'tone', 'style', 'iconography', 'accessibility treatment'):
        assert owned in body, owned
    for forbidden in ('translate', 'paraphrase', 'substitute', 'reclassify'):
        assert forbidden in body, forbidden
    assert 'invent a fallback semantic label' in body
    assert 'semantic-substitution path' in body and 'is retired' in body

    # Scoped, not a blanket claim over all frontend copy.
    assert 'This rule is scoped to governed semantic vocabulary.' in body


def test_read_confidence_is_an_evidence_quality_family():
    body = _section(_standard_text(), 'Read confidence')

    assert 'exactly High, Medium, Low, and Unavailable' in body
    assert 'not another baseball-state or read classification' in body
    assert 'rendered under its own field label' in body
    assert 'The raw internal confidence values are unchanged' in body
    assert 'not a recommendation score' in body
    assert 'not a confidence grade about a future outcome' in body


def test_reader_facing_temporal_stamps_stay_separate_clocks():
    body = _section(_standard_text(), 'Reader-facing temporal vocabulary')

    assert _first_column(body) == (
        'Data through',
        'Last data update',
        'Last checked',
        'Generated at',
        'Published at',
    )
    assert 'These are different clocks.' in body
    assert 'No surface collapses them into one value' in body
    assert 'it establishes no new temporal model' in body

    # The data-status family borrows no baseball word.
    assert 'Current, Partial Data, Stale, Data Unavailable' in body
    assert '`Limited` remains arm-availability vocabulary.' in body


def test_revision_history_records_the_version_1_3_entry():
    # The VOC-001 entry is durable history. Later editions append beside it;
    # they do not replace what it recorded.
    entry = _revision_row(_standard_text(), VOC_VERSION, VOC_EFFECTIVE_DATE)

    assert 'Nickolis Kacludis' in entry
    for claimed in (
        'team_state_public_vocabulary.py',
        'public_bullpen_copy.py',
        'pitcher_public_labels.py',
        'team_bullpen_shape.py',
        'may never substitute for one another',
        'the frontend renders it',
        'no supporting-read tier or adjective becomes a Team State',
        'Role Unclear',
        'Limited Read',
        'Trusted Arms',
        'Late-Inning Options',
        'Healthy Rested Bullpen',
        'Stable Rested Options',
        'Unobservable class in Section 2',
    ):
        assert claimed in entry, claimed


def test_the_new_revision_claims_no_threshold_model_or_authority_change():
    entry = _revision_row(_standard_text(), VOC_VERSION, VOC_EFFECTIVE_DATE)

    assert (
        'No model, threshold, source authority, classification, publication, '
        'sync/write, recommendation, or prediction behavior changed.'
    ) in entry

    # A wording reconciliation may not read as a capability announcement.
    lowered = entry.lower()
    for forbidden in (
        'new threshold',
        'new model',
        'new authority',
        'new capability',
        'threshold changed',
        'gate is opened',
        'now predicts',
    ):
        assert forbidden not in lowered, forbidden
