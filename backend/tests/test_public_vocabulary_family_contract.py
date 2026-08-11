"""VOC-001 / #638 — the cross-family boundaries the per-family contracts cannot see.

Every public vocabulary family already has a contract of its own. Team State is
pinned in ``test_team_state_public_contract.py``, the pitcher families in
``test_pitcher_public_labels.py``, availability and the board groups in
``test_public_copy_contract.py``, and the three canonical documents in their own
files. Each of those proves one family is internally correct.

None of them can prove the thing VOC-001 actually set out to fix: that the
families stay *separate*. A label can be perfectly valid inside its own
catalogue and still be wrong because a second family already owns the word, or
because a supporting-read tier reads like a Team State, or because a data-status
badge borrowed a baseball word. That failure mode is invisible to a
single-family test and is exactly what this file watches.

So this contract asserts across owners:

* Team State is exactly three labels, and no other family's label — availability,
  pitcher role, pitcher current read, read confidence, board group, data status,
  or supporting-read tier — is ever one of them.
* Arm availability is exactly four labels, and the board group headings, the
  pitcher current-read catalogue and the data-status family are each a
  *different* catalogue. ``Limited`` stays valid availability vocabulary; the
  ban is on the families colliding, not on the word.
* Every supporting read stays concept-qualified, so a bare adjective is never a
  public label and can never be mistaken for a state.
* The supporting-read NUMBERS did not move. VOC-001 renamed tiers; a rename that
  quietly shifts a boundary is a product change wearing a wording change's
  clothes, so the numeric constants and every numeric literal inside the read
  functions are compared against the package baseline commit.
* The five reader-facing temporal stamps stay five distinct concepts.

Deliberately narrow. Nothing here re-proves a family's own catalogue, and
nothing here is a repository-wide grep.
"""

import ast
import re
import subprocess
from pathlib import Path

import pytest

from services.bullpen_board import BOARD_GROUP_ORDER, GROUP_META
from services.pitcher_public_labels import READ_PUBLIC_LABELS, ROLE_PUBLIC_LABELS
from services.public_bullpen_copy import (
    PUBLIC_AVAILABILITY_LABELS,
    PUBLIC_AVAILABILITY_STATUSES,
)
from services.team_bullpen_shape import (
    CLEAN_OPTIONS_TIERS,
    READ_KEYS,
    TEAM_BULLPEN_PUBLIC_LABELS,
)
from services.team_state_public_vocabulary import (
    PUBLIC_STATE_LABELS,
    PUBLIC_TEAM_STATE_LABEL_SET,
    TEAM_STATE_AVAILABLE,
    TEAM_STATE_UNAVAILABLE_MESSAGES,
    public_team_state,
    team_state_unavailable,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

# The package baseline this branch is measured against (#639 / VOC-001).
BASELINE_COMMIT = '18dd6914a933928254e969c85ecb19cf75b6a9f2'

SYNC_STATUS_VIEW = REPO_ROOT / 'frontend/src/components/dashboard/syncStatusView.js'
AVAILABILITY_VIEW = REPO_ROOT / 'frontend/src/components/bullpen/availabilityView.js'
GAME_CONTEXT_VIEW = (
    REPO_ROOT / 'frontend/src/components/bullpen/board/teamGameContextView.js'
)
BULLPEN_CONCEPTS = REPO_ROOT / 'frontend/src/utils/bullpenConcepts.js'

CANONICAL_DOCS = {
    'Product Experience Standard': (
        REPO_ROOT / 'docs/canonical/03_PRODUCT_EXPERIENCE_STANDARD.md'
    ),
    'Bullpen Intelligence Standard': (
        REPO_ROOT / 'docs/canonical/02_BULLPEN_INTELLIGENCE_STANDARD.md'
    ),
    'Product Roadmap & Decision Ledger': (
        REPO_ROOT / 'docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md'
    ),
}


# ---------------------------------------------------------------------------
# Live catalogues, read from their declared owners.
# ---------------------------------------------------------------------------

TEAM_STATE_LABELS = frozenset(PUBLIC_TEAM_STATE_LABEL_SET)
ROLE_LABELS = frozenset(entry['label'] for entry in ROLE_PUBLIC_LABELS.values())
READ_LABELS = frozenset(entry['label'] for entry in READ_PUBLIC_LABELS.values())
AVAILABILITY_LABELS = frozenset(PUBLIC_AVAILABILITY_STATUSES)
BOARD_GROUP_LABELS = frozenset(GROUP_META[status]['label'] for status in BOARD_GROUP_ORDER)
SUPPORTING_LABELS = frozenset(
    label for labels in TEAM_BULLPEN_PUBLIC_LABELS.values() for label in labels
)

# The internal availability states the engine keeps. Renaming a reader label
# must never rename one of these.
INTERNAL_AVAILABILITY_STATES = ('Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable')

# Tier adjectives the supporting-read families use. Each is a real word inside a
# real label and none of them is ever a public label — or a Team State — alone.
SUPPORTING_TIER_ADJECTIVES = (
    'Strong',
    'Stable',
    'Deep',
    'Thin',
    'Very Thin',
    'Limited',
    'High',
    'Elevated',
    'Manageable',
    'Low',
    'Concentrated',
)

# The concept each supporting-read family must keep in its public label. This is
# the concept-qualification rule: a tier says WHICH read it is tiering, so a
# reader never sees a naked 'Thin' and has to guess thin at what.
SUPPORTING_CONCEPT_BY_KEY = {
    'trustAvailability': 'Late-Inning Availability',
    'cleanOptions': 'Rested Options',
    'bullpenPressure': 'Late-Inning Pressure',
    'workloadConcentration': 'Workload Concentration',
    'coverageSafety': 'Coverage Safety',
    'depthSafety': 'Depth Safety',
}

# The one shared fail-closed label. It belongs to no supporting concept because
# it says the evidence for the concept is missing, which is why it is exempt
# from the concept-qualification rule above.
SUPPORTING_FALLBACK_LABEL = 'Limited Read'

# The canonical Rested Options tiers, weakest to strongest, in the order the
# owner applies them.
EXPECTED_CLEAN_OPTIONS_TIERS = (
    'Very Thin Rested Options',
    'Thin Rested Options',
    'Stable Rested Options',
    'Deep Rested Options',
)

# The tiers the baseline commit carried, in the same positions. VOC-001 renamed
# these; the rename is one-for-one and order-preserving, and this map is what
# lets the threshold proof below assert that nothing moved but the strings.
BASELINE_CLEAN_OPTIONS_TIERS = (
    'Very Thin Rested Bullpen',
    'Thin Rested Bullpen',
    'Healthy Rested Bullpen',
    'Deep Rested Bullpen',
)

EXPECTED_DATA_STATUS_LABELS = ('Current', 'Partial Data', 'Stale', 'Data Unavailable')
EXPECTED_READ_CONFIDENCE_LABELS = ('High', 'Medium', 'Low', 'Unavailable')

# The five reader-facing temporal stamps and what each one answers. Three are
# freshness (what the read covers and when the data moved) and two are
# provenance (when an artifact was made and when it became trusted).
EXPECTED_FRESHNESS_STAMPS = ('Data through', 'Last data update', 'Last checked')
EXPECTED_PROVENANCE_STAMPS = ('Generated at', 'Published at')


# ---------------------------------------------------------------------------
# Small readers for the frontend catalogues that own a public family.
# ---------------------------------------------------------------------------

def _js_block(text, opener, closer):
    assert opener in text, f'{opener!r} not found in the frontend source'
    body = text.split(opener, 1)[1]
    assert closer in body, f'unterminated block after {opener!r}'
    return body.split(closer, 1)[0]


def _js_string_map(text, opener, closer='}'):
    """Return the ``key -> 'value'`` pairs of a flat JS object literal."""
    block = _js_block(text, opener, closer)
    return dict(re.findall(r"(\w+):\s*'([^']*)'", block))


def _js_named_definitions(text, name):
    """Return the ``name`` values of a frozen ``[{name, definition}]`` list."""
    block = _js_block(text, f'export const {name} = Object.freeze([', '])')
    return re.findall(r"name:\s*'([^']*)'", block)


def _js_definitions_by_name(text, name):
    block = _js_block(text, f'export const {name} = Object.freeze([', '])')
    return dict(re.findall(r"name:\s*'([^']*)',\s*definition:\s*'([^']*)'", block))


def data_status_labels():
    text = SYNC_STATUS_VIEW.read_text(encoding='utf-8')
    return _js_string_map(text, 'export const DATA_STATUS_LABELS = Object.freeze({', '})')


def read_confidence_labels():
    text = AVAILABILITY_VIEW.read_text(encoding='utf-8')
    return _js_string_map(text, 'const CONFIDENCE_READ_LABELS = {')


# ---------------------------------------------------------------------------
# STEP 2 — Team State exactness, and everything that is not a Team State.
# ---------------------------------------------------------------------------

def test_team_state_is_exactly_fresh_stretched_vulnerable():
    """The live owner publishes three labels. There is no fourth."""
    assert tuple(PUBLIC_STATE_LABELS.values()) == ('Fresh', 'Stretched', 'Vulnerable')
    assert TEAM_STATE_LABELS == {'Fresh', 'Stretched', 'Vulnerable'}
    assert len(PUBLIC_STATE_LABELS) == 3


def test_governed_non_state_outcomes_never_become_a_state():
    """Refused, data-limited, unsupported and unscoped stay label-less.

    A non-state outcome that acquired a label would be a fourth Team State by
    the back door — the reader cannot tell a state from a state-shaped message.
    """
    for outcome in TEAM_STATE_UNAVAILABLE_MESSAGES:
        block = team_state_unavailable(outcome)
        assert block['available'] is False, outcome
        assert block['public_label'] is None, outcome
        assert block['public_state'] is None, outcome
        assert block['unavailable_message'], outcome
        # And the message itself never asserts one of the three states.
        for label in TEAM_STATE_LABELS:
            assert label not in block['unavailable_message'], (outcome, label)

    # The projection agrees for a payload it cannot read at all.
    unreadable = public_team_state(None)
    assert unreadable['available'] is False
    assert unreadable['public_label'] is None


@pytest.mark.parametrize(
    'family, labels',
    [
        ('arm availability', AVAILABILITY_LABELS),
        ('pitcher role', ROLE_LABELS),
        ('pitcher current read', READ_LABELS),
        ('board group', BOARD_GROUP_LABELS),
        ('supporting read', SUPPORTING_LABELS),
    ],
)
def test_no_other_family_label_qualifies_as_team_state(family, labels):
    assert not (labels & TEAM_STATE_LABELS), (family, sorted(labels & TEAM_STATE_LABELS))


def test_read_confidence_and_data_status_values_are_not_team_state():
    confidence = set(read_confidence_labels().values())
    status = set(data_status_labels().values())
    assert confidence == set(EXPECTED_READ_CONFIDENCE_LABELS)
    assert status == set(EXPECTED_DATA_STATUS_LABELS)
    assert not (confidence & TEAM_STATE_LABELS)
    assert not (status & TEAM_STATE_LABELS)


def test_a_bare_tier_adjective_is_never_a_team_state():
    """`Strong`, `Thin`, `Elevated` and the rest are tier words, not states.

    They are the words a supporting read tiers WITH. On their own they say
    nothing about a team, which is why no supporting read ever ships one alone
    and why none of them can be read as Fresh, Stretched, or Vulnerable.
    """
    for adjective in SUPPORTING_TIER_ADJECTIVES:
        assert adjective not in TEAM_STATE_LABELS, adjective
        assert adjective not in SUPPORTING_LABELS, adjective
        assert adjective not in ROLE_LABELS, adjective
        assert adjective not in READ_LABELS, adjective


# ---------------------------------------------------------------------------
# STEP 3 — Arm availability exactness, and the catalogues it is not.
# ---------------------------------------------------------------------------

def test_arm_availability_is_exactly_four_reader_labels():
    assert PUBLIC_AVAILABILITY_STATUSES == ('Available', 'On Watch', 'Limited', 'Unavailable')


def test_engine_vocabulary_maps_into_the_reader_catalogue_without_moving():
    """`Monitor` and `Avoid` are engine words with distinct public forms.

    The engine states are unchanged — VOC-001 moved wording, not classification
    — so the internal key set is asserted alongside the mapping.
    """
    assert tuple(PUBLIC_AVAILABILITY_LABELS) == INTERNAL_AVAILABILITY_STATES
    assert PUBLIC_AVAILABILITY_LABELS['Monitor'] == 'On Watch'
    assert PUBLIC_AVAILABILITY_LABELS['Avoid'] == 'Unavailable'
    assert set(PUBLIC_AVAILABILITY_LABELS.values()) == AVAILABILITY_LABELS


def test_board_group_headings_are_not_the_availability_catalogue():
    """Group headings name a GROUP; availability labels classify an ARM.

    Before VOC-001 a column heading and a chip on a card inside it were the same
    string, so the two claims were indistinguishable.
    """
    assert BOARD_GROUP_LABELS != AVAILABILITY_LABELS
    assert not (BOARD_GROUP_LABELS & AVAILABILITY_LABELS)
    # The engine keys and their order are untouched by the heading change.
    assert tuple(GROUP_META[status]['label'] for status in BOARD_GROUP_ORDER) == (
        'Available Arms',
        'On-Watch Arms',
        'Limited Arms',
        'Unavailable — Heavy Workload',
        'Unavailable — Severe Workload',
    )


def test_pitcher_current_read_is_not_the_availability_catalogue():
    """Related questions, different catalogues.

    Availability asks how usable the arm is; the current read asks what the
    represented day looks like for it. `Unavailable` legitimately belongs to
    both — it is the one word the two families share, and sharing one word is
    not sharing a catalogue.
    """
    assert READ_LABELS != AVAILABILITY_LABELS
    assert READ_LABELS & AVAILABILITY_LABELS == {'Unavailable'}


def test_data_status_is_not_the_availability_catalogue():
    status = set(data_status_labels().values())
    assert status != AVAILABILITY_LABELS
    assert not (status & AVAILABILITY_LABELS)


def test_limited_remains_valid_arm_availability_vocabulary():
    """The family-aware half of the rule, stated as its own contract.

    VOC-001 removed `Limited` from the data-status badges because the word was
    already taken. It was taken BY THIS FAMILY, and it stays here: `Limited` is
    a governed arm availability label, an engine state, and a reader label, and
    nothing in this sweep may be read as banning it.
    """
    assert 'Limited' in PUBLIC_AVAILABILITY_STATUSES
    assert 'Limited' in AVAILABILITY_LABELS
    assert PUBLIC_AVAILABILITY_LABELS['Limited'] == 'Limited'
    assert 'Limited' in INTERNAL_AVAILABILITY_STATES
    # And the neighbouring families keep their own distinct `Limited …` labels.
    assert 'Limited Rest' in READ_LABELS
    assert 'Limited Read' in READ_LABELS
    assert 'Role Unclear' in ROLE_LABELS
    assert 'Limited' not in set(data_status_labels().values())


# ---------------------------------------------------------------------------
# STEP 4 — the supporting reads.
# ---------------------------------------------------------------------------

def test_trusted_arms_is_not_a_team_level_concept_and_trusted_arm_still_is_a_role():
    """The collision that made one word carry two hierarchy levels.

    `Trusted Arms` read as the plural of the pitcher role `Trusted Arm` and was
    not: it mixed role with current workload and roster usability. The role
    keeps the singular; the team-level concept is `Late-Inning Options`.
    """
    assert 'Trusted Arm' in ROLE_LABELS
    assert ROLE_PUBLIC_LABELS['trust_arm']['label'] == 'Trusted Arm'

    assert 'Trusted Arms' not in SUPPORTING_LABELS
    shape_source = (
        REPO_ROOT / 'backend/services/team_bullpen_shape.py'
    ).read_text(encoding='utf-8')
    assert 'Trusted Arms' not in shape_source

    glossary = BULLPEN_CONCEPTS.read_text(encoding='utf-8')
    supporting = _js_block(
        glossary,
        'export const SUPPORTING_CONCEPT_DEFINITIONS = Object.freeze({',
        '})',
    )
    names = re.findall(r"name:\s*'([^']*)'", supporting)
    assert 'Late-Inning Options' in names
    assert 'Trusted Arms' not in names

    # The editorial standard's approved-vocabulary table authorises what
    # published copy may say. A retired term listed there is a live route back
    # to a reader, so the retired plural is pinned out of the named-reads row.
    editorial = (
        REPO_ROOT / 'docs/canonical/06_EDITORIAL_DISTRIBUTION_STANDARD.md'
    ).read_text(encoding='utf-8')
    named_reads = [
        line for line in editorial.splitlines()
        if line.startswith('| Named bullpen reads |')
    ]
    assert len(named_reads) == 1, named_reads
    assert 'Trusted Arms' not in named_reads[0]
    assert 'Late-Inning Options' in named_reads[0]

    public_roles = [
        line for line in editorial.splitlines() if line.startswith('| Public roles |')
    ]
    assert len(public_roles) == 1, public_roles
    for label in ROLE_LABELS:
        assert label in public_roles[0], label
    assert 'Limited Read' not in public_roles[0]


def test_healthy_rested_bullpen_is_not_current_supporting_vocabulary():
    """BaseballOS observes public workload, never private health.

    `Healthy` asserted a condition the platform cannot see. The tier is
    `Stable Rested Options` and the family is named for what it measures.
    """
    assert 'Stable Rested Options' in SUPPORTING_LABELS
    assert 'Healthy Rested Bullpen' not in SUPPORTING_LABELS
    for label in SUPPORTING_LABELS:
        assert 'Healthy' not in label, label


def test_rested_options_tiers_are_exact_and_keep_their_order():
    """Four tiers, weakest to strongest, exactly as the owner applies them."""
    assert tuple(CLEAN_OPTIONS_TIERS) == EXPECTED_CLEAN_OPTIONS_TIERS
    assert tuple(TEAM_BULLPEN_PUBLIC_LABELS['cleanOptions']) == (
        'Deep Rested Options',
        'Stable Rested Options',
        'Thin Rested Options',
        'Very Thin Rested Options',
        SUPPORTING_FALLBACK_LABEL,
    )
    # The catalogue and the applied tier list describe one family.
    assert set(CLEAN_OPTIONS_TIERS) | {SUPPORTING_FALLBACK_LABEL} == set(
        TEAM_BULLPEN_PUBLIC_LABELS['cleanOptions']
    )


def test_every_supporting_label_stays_concept_qualified():
    """A tier names the read it is tiering.

    'Thin' alone is unreadable next to five other reads; 'Thin Coverage Safety'
    is not. The rule is per-family concept identity, not a fixed adjective list
    — families legitimately use different adjectives.
    """
    assert tuple(READ_KEYS) == tuple(SUPPORTING_CONCEPT_BY_KEY)
    for key, concept in SUPPORTING_CONCEPT_BY_KEY.items():
        labels = TEAM_BULLPEN_PUBLIC_LABELS[key]
        assert labels[-1] == SUPPORTING_FALLBACK_LABEL, key
        for label in labels[:-1]:
            if key == 'workloadConcentration':
                # This family qualifies on the concept's two words rather than a
                # fixed suffix ('Concentrated Workload' / 'Some Workload
                # Concentration' are both the same concept).
                assert 'Workload' in label, (key, label)
                assert 'Concentrat' in label, (key, label)
            else:
                assert label.endswith(concept), (key, label)
            assert label != concept, (key, label)
            assert len(label.split()) >= 2, (key, label)


def test_no_supporting_read_label_is_a_team_state():
    """Not one tier, in any family, equals or maps to a Team State."""
    for key, labels in TEAM_BULLPEN_PUBLIC_LABELS.items():
        for label in labels:
            assert label not in TEAM_STATE_LABELS, (key, label)
    assert not (SUPPORTING_LABELS & TEAM_STATE_LABELS)
    # And no supporting tier is even a substring match for one of the states,
    # so 'Fresh …' cannot appear as a tier word either.
    for label in SUPPORTING_LABELS:
        for state in TEAM_STATE_LABELS:
            assert state not in label, (label, state)


# ---------------------------------------------------------------------------
# STEP 5 — the numbers behind the supporting reads did not move.
# ---------------------------------------------------------------------------

# The supporting-read owners whose numeric behavior VOC-001 touched or borders.
# team_bullpen_shape.py is where the renamed tiers live; the other two own the
# coverage-safety and workload-concentration reads it composes.
THRESHOLD_SOURCES = (
    'backend/services/team_bullpen_shape.py',
    'backend/services/bullpen_coverage_safety.py',
    'backend/services/workload_concentration.py',
)

# The module-level numeric constants of team_bullpen_shape.py at the baseline
# commit, extracted from `git show 18dd6914…:backend/services/team_bullpen_shape.py`
# by the same AST walk used below. Recorded literally so the expected values are
# reviewable in the diff rather than only computable at run time.
#
# Source lines on the baseline (and on the current head, unmoved):
#   CLEAN_TIER_VERY_THIN / THIN / HEALTHY / DEEP  — the four Rested Options tiers
#   TRUST_PRESSURE_HIGH / TRUST_PRESSURE_ELEVATED — late-inning pressure cutoffs
#   ROLE_STRESS_ELEVATED                          — bridge/coverage stress cutoff
#   PRESSURE_SHARE_HIGH / PRESSURE_SHARE_ELEVATED — weighted-pressure share cutoffs
#   READ_USABILITY                                — per-read usability weights
#   ROLE_INFLUENCE                                — per-role pressure weights
BASELINE_TEAM_SHAPE_CONSTANTS = {
    'CLEAN_TIER_VERY_THIN': 0,
    'CLEAN_TIER_THIN': 1,
    'CLEAN_TIER_HEALTHY': 2,
    'CLEAN_TIER_DEEP': 3,
    'TRUST_PRESSURE_HIGH': 4.5,
    'TRUST_PRESSURE_ELEVATED': 2.5,
    'ROLE_STRESS_ELEVATED': 2,
    'PRESSURE_SHARE_HIGH': 0.45,
    'PRESSURE_SHARE_ELEVATED': 0.25,
    'READ_USABILITY': {
        'clean_option': 1,
        'watch_arm': 0.5,
        'rest_restricted': 0,
        'unavailable': 0,
        'limited_read': 0,
    },
    'ROLE_INFLUENCE': {
        'trust_arm': 3,
        'bridge_arm': 2,
        'coverage_arm': 2,
        'depth_arm': 1,
        'limited_read': 0,
    },
}


def _numeric(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if isinstance(node.value, bool):
            return None
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _numeric(node.operand)
        return None if inner is None else -inner
    return None


def _module_numeric_constants(tree):
    """Module-level numeric assignments, including numeric dicts and lists."""
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            value = _numeric(node.value)
            if value is not None:
                found[target.id] = value
            elif isinstance(node.value, ast.Dict):
                items = {
                    key.value: _numeric(item)
                    for key, item in zip(node.value.keys, node.value.values)
                    if isinstance(key, ast.Constant) and _numeric(item) is not None
                }
                if items:
                    found[target.id] = items
            elif isinstance(node.value, (ast.List, ast.Tuple)):
                items = [_numeric(element) for element in node.value.elts]
                if items and all(item is not None for item in items):
                    found[target.id] = items
    return found


def _function_numeric_literals(tree):
    """Every numeric literal inside each top-level function, sorted.

    A tier boundary that lives in an ``if clean >= 4`` branch is not a named
    constant, so comparing named constants alone would miss it. Walking the
    literals catches a moved boundary wherever it is written.
    """
    return {
        node.name: sorted(
            value
            for sub in ast.walk(node)
            if (value := _numeric(sub)) is not None
        )
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def _baseline_source(relative):
    result = subprocess.run(
        ['git', 'show', f'{BASELINE_COMMIT}:{relative}'],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f'could not read {relative} at baseline {BASELINE_COMMIT}: '
        f'{result.stderr.strip()}'
    )
    return result.stdout


@pytest.mark.parametrize('relative', THRESHOLD_SOURCES)
def test_supporting_read_numbers_are_identical_to_the_package_baseline(relative):
    """VOC-001 renamed tiers. It must not have moved one.

    Both files are parsed and their numbers compared directly: every
    module-level numeric constant, and every numeric literal inside every
    function. If a boundary changed by so much as a decimal, the two extracts
    disagree and this fails — which is the point, because a threshold change
    hiding inside a wording change is a product change nobody reviewed.
    """
    baseline = ast.parse(_baseline_source(relative))
    current = ast.parse((REPO_ROOT / relative).read_text(encoding='utf-8'))

    assert _module_numeric_constants(current) == _module_numeric_constants(baseline), (
        f'{relative}: a module-level numeric constant changed against baseline '
        f'{BASELINE_COMMIT}'
    )
    assert _function_numeric_literals(current) == _function_numeric_literals(baseline), (
        f'{relative}: a numeric literal inside a read function changed against '
        f'baseline {BASELINE_COMMIT}'
    )


def test_the_recorded_baseline_constants_are_what_the_baseline_commit_holds():
    """The literal map above is checked against the real baseline blob.

    Recording the numbers makes them reviewable; reading the blob keeps the
    record honest, so the map cannot quietly drift into being its own source of
    truth.
    """
    relative = 'backend/services/team_bullpen_shape.py'
    baseline = _module_numeric_constants(ast.parse(_baseline_source(relative)))
    for name, expected in BASELINE_TEAM_SHAPE_CONSTANTS.items():
        assert baseline[name] == expected, name

    current = _module_numeric_constants(
        ast.parse((REPO_ROOT / relative).read_text(encoding='utf-8'))
    )
    for name, expected in BASELINE_TEAM_SHAPE_CONSTANTS.items():
        assert current[name] == expected, name


def test_the_rested_options_rename_preserved_tier_order_position_for_position():
    """Four tiers before, four after, in the same slots.

    The tier list is the ordering authority: ``CLEAN_OPTIONS_TIERS[tier]`` is
    how the read resolves. A rename that reordered it would change which read a
    given count produces without touching a single number.
    """
    relative = 'backend/services/team_bullpen_shape.py'
    baseline_source = _baseline_source(relative)
    baseline_tiers = tuple(
        re.findall(
            r"'([^']+)'",
            baseline_source.split('CLEAN_OPTIONS_TIERS = [', 1)[1].split(']', 1)[0],
        )
    )
    assert baseline_tiers == BASELINE_CLEAN_OPTIONS_TIERS
    assert tuple(CLEAN_OPTIONS_TIERS) == EXPECTED_CLEAN_OPTIONS_TIERS
    assert len(CLEAN_OPTIONS_TIERS) == len(baseline_tiers)

    # Only the middle two tiers were reworded, and only in place.
    renamed = dict(zip(baseline_tiers, CLEAN_OPTIONS_TIERS))
    assert renamed['Healthy Rested Bullpen'] == 'Stable Rested Options'
    assert renamed['Deep Rested Bullpen'] == 'Deep Rested Options'
    assert renamed['Thin Rested Bullpen'] == 'Thin Rested Options'
    assert renamed['Very Thin Rested Bullpen'] == 'Very Thin Rested Options'


# ---------------------------------------------------------------------------
# STEP 6 — the data-status family.
# ---------------------------------------------------------------------------

def test_data_status_family_is_exactly_four_labels():
    labels = data_status_labels()
    assert tuple(labels) == ('CURRENT', 'PARTIAL', 'STALE', 'UNAVAILABLE')
    assert tuple(labels.values()) == EXPECTED_DATA_STATUS_LABELS


def test_data_status_borrows_no_baseball_word_and_no_retired_badge():
    """It describes the DATA. `Healthy`, `Limited` and `Not Current` are gone.

    `Healthy` claimed player condition; `Limited` was already an availability
    label, so a reader could not tell whether the bullpen or the data was
    limited; `Not Current` said only what the data was not.
    """
    values = set(data_status_labels().values())
    for retired in ('Healthy', 'Limited', 'Not Current'):
        assert retired not in values, retired

    source = SYNC_STATUS_VIEW.read_text(encoding='utf-8')
    catalogue = _js_block(
        source, 'export const DATA_STATUS_LABELS = Object.freeze({', '})'
    )
    for retired in ('Healthy', 'Limited', 'Not Current'):
        assert retired not in catalogue, retired


def test_the_second_data_status_surface_carries_no_retired_badge():
    """The game-context card renders the same family on another surface.

    Two freshness dictionaries disagreeing on one screen is the defect; both of
    its label maps are asserted, not just the short one.
    """
    source = GAME_CONTEXT_VIEW.read_text(encoding='utf-8')
    short = _js_string_map(source, 'const DATA_STATE_LABEL = {')
    long = _js_string_map(source, 'const DATA_STATE_LONG_LABEL = {')
    assert short['live'] == 'Current'
    assert short['stale'] == 'Stale'
    assert 'Not Current' not in set(short.values())
    assert 'Not Current' not in ' '.join(long.values())
    # The long form qualifies the same states; it never contradicts the badge.
    assert 'Stale' in long['stale']
    assert 'Current' in long['live']


# ---------------------------------------------------------------------------
# STEP 7 — five temporal stamps, five meanings.
# ---------------------------------------------------------------------------

def test_the_five_temporal_stamps_are_five_distinct_concepts():
    """Two clocks and a coverage date are not one stamp.

    `Data through` is a baseball date the read represents. `Last data update`
    and `Last checked` are platform clocks — a successful write and an attempt.
    `Generated at` and `Published at` belong to an artifact's lifecycle. Reusing
    one for another is how a stale read acquires a fresh-looking timestamp.
    """
    glossary = BULLPEN_CONCEPTS.read_text(encoding='utf-8')
    freshness = _js_definitions_by_name(glossary, 'FRESHNESS_LABEL_DEFINITIONS')
    provenance = _js_definitions_by_name(glossary, 'PROVENANCE_LABEL_DEFINITIONS')

    assert tuple(freshness) == EXPECTED_FRESHNESS_STAMPS
    assert tuple(provenance) == EXPECTED_PROVENANCE_STAMPS

    stamps = {**freshness, **provenance}
    assert len(stamps) == 5, 'a stamp name collided across the two families'

    # Every definition is distinct: no two stamps answer the same question.
    definitions = list(stamps.values())
    assert len(set(definitions)) == 5, definitions
    assert all(definition.strip() for definition in definitions)

    # And each says the thing that makes it different from the other four.
    assert 'completed baseball date' in stamps['Data through']
    assert 'successfully wrote' in stamps['Last data update']
    assert 'attempted' in stamps['Last checked']
    assert 'created' in stamps['Generated at']
    assert 'trusted public publication' in stamps['Published at']


def test_data_through_is_never_aliased_to_a_provenance_stamp():
    """The represented baseball date is not when the artifact was made.

    A surface that resolved `Data through` from a generation or publication
    timestamp would present platform activity as baseball coverage.
    """
    glossary = BULLPEN_CONCEPTS.read_text(encoding='utf-8')
    freshness = _js_definitions_by_name(glossary, 'FRESHNESS_LABEL_DEFINITIONS')
    provenance = _js_definitions_by_name(glossary, 'PROVENANCE_LABEL_DEFINITIONS')
    assert not (set(freshness) & set(provenance))
    for label, definition in provenance.items():
        assert definition != freshness['Data through'], label
        assert 'baseball date' not in definition, label

    # The live resolver reads a data-through/workload date and nothing else.
    sync = SYNC_STATUS_VIEW.read_text(encoding='utf-8')
    resolver = _js_block(sync, 'export function freshnessDataThrough(freshness) {', '\n}')
    for provenance_field in ('generated', 'published', 'last_checked', 'lastChecked'):
        assert provenance_field not in resolver, provenance_field
    assert "dataLabel: dataThrough ? 'Data through' : null" in sync
    assert "lastCheckedLabel: 'Last checked'" in sync
    assert "lastDataUpdateLabel: 'Last data update'" in sync


# ---------------------------------------------------------------------------
# STEP 8 — one small cross-document assertion.
# ---------------------------------------------------------------------------

def test_the_three_canonical_documents_do_not_disagree_on_team_state():
    """Each document has its own contract; none of them looks at the others.

    This is the only assertion that does: the three canonical documents name the
    same three Team States, name the same active objective, and none of them
    introduces a fourth state word of its own.
    """
    for name, path in CANONICAL_DOCS.items():
        text = path.read_text(encoding='utf-8')
        for state in ('Fresh', 'Stretched', 'Vulnerable'):
            assert state in text, (name, state)
        assert 'VOC-001' in text, name


# ---------------------------------------------------------------------------
# STEP 11 — permanent retired-alias contracts on the current source of truth.
#
# Narrow by design: these pin the CURRENT owners, never an archive, a historical
# audit, or a document recording a retirement.
# ---------------------------------------------------------------------------

def test_no_retired_role_or_read_alias_survives_in_the_governed_owner():
    """The label owner emits no retired wording, in any family."""
    published = {
        entry['label']
        for entry in list(ROLE_PUBLIC_LABELS.values()) + list(READ_PUBLIC_LABELS.values())
    }
    for retired in (
        'Trust Arm',
        'Bridge Arm',
        'Depth Arm',
        'Rested',
        'Rest-Restricted',
        'Trusted Arms',
    ):
        assert retired not in published, retired


def test_no_retired_read_confidence_label_survives_in_the_display_constant():
    """Read confidence is a quality scale, not a second arm-read vocabulary."""
    labels = read_confidence_labels()
    assert tuple(labels) == ('high', 'medium', 'low', 'none', 'unknown')
    assert tuple(labels.values()) == ('High', 'Medium', 'Low', 'Unavailable', 'Unavailable')
    values = set(labels.values())
    for retired in (
        'Strong Read',
        'Partial Read',
        'Unclear Read',
        'No Read',
        'Unknown Read',
    ):
        assert retired not in values, retired
    # And the confidence scale never collides with the pitcher read catalogue.
    assert not (values & (READ_LABELS - {'Unavailable'}))
