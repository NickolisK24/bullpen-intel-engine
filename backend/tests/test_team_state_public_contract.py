"""Canonical public Team State contract (UX-001).

Proves the one thing every reader-facing surface depends on: the backend owns
the internal-to-public Team State mapping, exposes it through a single
projection, and fails closed for every outcome that is not a Team State.

Three layers, no database required:

  * the canonical vocabulary itself (exact sets, exact mapping, fail-closed);
  * the public projection over a governed readiness payload;
  * a static check that no production module keeps a competing mapping.
"""

import ast
import os
import re

import pytest

from services import bullpen_comparison
from services.team_state_public_vocabulary import (
    INTERNAL_TO_PUBLIC_STATE,
    PUBLIC_STATE_CODES,
    PUBLIC_STATE_LABELS,
    PUBLIC_TEAM_STATE_CONTRACT,
    PUBLIC_TEAM_STATE_LABEL_SET,
    TEAM_STATE_AVAILABLE,
    TEAM_STATE_DATA_LIMITED,
    TEAM_STATE_NOT_TEAM_SCOPED,
    TEAM_STATE_READINESS_UNAVAILABLE,
    TEAM_STATE_REFUSED,
    TEAM_STATE_UNSUPPORTED,
    UnmappedTeamStateError,
    is_publishable_state,
    public_state_for,
    public_team_state,
    team_state_not_team_scoped,
    team_state_unavailable,
)


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_ROOT)

# The exact canonical public Team State vocabulary. Changing either constant is a
# reviewed product decision, never an implementation detail.
CANONICAL_PUBLIC_LABELS = {'Fresh', 'Stretched', 'Vulnerable'}
CANONICAL_PUBLIC_CODES = {'fresh', 'stretched', 'vulnerable'}
CANONICAL_MAPPING = {
    'operationally_stable': 'Fresh',
    'operationally_constrained': 'Stretched',
    'operationally_stressed': 'Vulnerable',
}


# ── Canonical vocabulary ─────────────────────────────────────────────────────

def test_public_label_set_is_exactly_fresh_stretched_vulnerable():
    assert set(PUBLIC_STATE_LABELS.values()) == CANONICAL_PUBLIC_LABELS
    assert PUBLIC_TEAM_STATE_LABEL_SET == frozenset(CANONICAL_PUBLIC_LABELS)


def test_public_code_set_is_exactly_the_canonical_codes():
    assert set(PUBLIC_STATE_LABELS) == CANONICAL_PUBLIC_CODES
    assert PUBLIC_STATE_CODES == frozenset(CANONICAL_PUBLIC_CODES)


def test_every_supported_internal_state_maps_to_its_canonical_label():
    assert {
        status: public_state_for(status)['public_label']
        for status in CANONICAL_MAPPING
    } == CANONICAL_MAPPING


def test_the_internal_to_public_map_holds_exactly_three_entries():
    # A fourth mapping — public or internal — fails here on purpose.
    assert set(INTERNAL_TO_PUBLIC_STATE) == set(CANONICAL_MAPPING)
    assert len(PUBLIC_STATE_LABELS) == 3


@pytest.mark.parametrize('status_code', [
    'data_limited',
    'refused',
    'unknown',
    'stale',
    'incomplete',
    'unsupported_method',
    'operationally_recovering',
    '',
    None,
])
def test_unsupported_internal_states_receive_no_public_team_state(status_code):
    assert is_publishable_state(status_code) is False
    with pytest.raises(UnmappedTeamStateError):
        public_state_for(status_code)


# ── Public projection ────────────────────────────────────────────────────────

def readiness(status_code, *, data_through='2026-08-04', **extra):
    payload = {
        'contract_state': 'available',
        'readiness': {'status_code': status_code},
        'freshness': {'data_through': data_through},
        'refusal': {'refused': False},
    }
    payload.update(extra)
    return payload


@pytest.mark.parametrize('status_code,public_state,public_label', [
    ('operationally_stable', 'fresh', 'Fresh'),
    ('operationally_constrained', 'stretched', 'Stretched'),
    ('operationally_stressed', 'vulnerable', 'Vulnerable'),
])
def test_supported_readiness_produces_backend_owned_public_fields(
    status_code, public_state, public_label,
):
    block = public_team_state(readiness(status_code))

    assert block['contract'] == PUBLIC_TEAM_STATE_CONTRACT
    assert block['available'] is True
    assert block['public_state'] == public_state
    assert block['public_label'] == public_label
    assert block['outcome'] == TEAM_STATE_AVAILABLE
    assert block['unavailable_message'] is None
    assert block['data_through'] == '2026-08-04'


def test_data_limited_readiness_produces_no_public_team_state():
    block = public_team_state(readiness('data_limited'))

    assert block['available'] is False
    assert block['public_state'] is None
    assert block['public_label'] is None
    assert block['outcome'] == TEAM_STATE_DATA_LIMITED
    # Fail-closed metadata stays inspectable, and the message is not a state.
    assert block['reason_code'] == 'data_limited'
    assert block['data_through'] == '2026-08-04'
    assert 'not available' in block['unavailable_message']


def test_refused_readiness_preserves_its_reason_and_publishes_no_state():
    block = public_team_state({
        'contract_state': 'refused',
        'refusal': {'refused': True, 'reason': 'source_inputs_missing'},
        'freshness': {'data_through': '2026-08-03'},
    })

    assert block['available'] is False
    assert block['public_label'] is None
    assert block['outcome'] == TEAM_STATE_REFUSED
    assert block['reason_code'] == 'source_inputs_missing'


@pytest.mark.parametrize('payload', [
    None,
    {},
    {'readiness': {}},
    {'readiness': {'status_code': None}},
    {'readiness': {'status_code': ''}},
    'not-a-mapping',
])
def test_missing_readiness_produces_no_public_team_state(payload):
    block = public_team_state(payload)

    assert block['available'] is False
    assert block['public_state'] is None
    assert block['public_label'] is None
    assert block['outcome'] == TEAM_STATE_READINESS_UNAVAILABLE


def test_an_unrecognized_internal_state_fails_closed_without_a_label():
    block = public_team_state(readiness('operationally_recovering'))

    assert block['available'] is False
    assert block['public_label'] is None
    assert block['outcome'] == TEAM_STATE_UNSUPPORTED


def test_a_league_scope_surface_receives_a_non_state_block():
    block = team_state_not_team_scoped()

    assert block['available'] is False
    assert block['public_label'] is None
    assert block['outcome'] == TEAM_STATE_NOT_TEAM_SCOPED
    assert 'team-level read' in block['unavailable_message']


def test_no_non_state_outcome_can_be_given_a_label():
    with pytest.raises(ValueError):
        team_state_unavailable(TEAM_STATE_AVAILABLE)
    with pytest.raises(ValueError):
        team_state_unavailable('thin')


def test_no_projection_ever_emits_a_label_outside_the_canonical_set():
    statuses = list(CANONICAL_MAPPING) + [
        'data_limited', 'refused', 'unknown', '', None,
    ]
    labels = {public_team_state(readiness(status))['public_label'] for status in statuses}

    assert labels <= CANONICAL_PUBLIC_LABELS | {None}


# ── The comparison contract passes both sides through unchanged ──────────────

def test_comparison_carries_each_side_team_state_without_combining_them():
    board_a = {
        'team': {'team_id': 1, 'team_name': 'Team A'},
        'team_state': public_team_state(readiness('operationally_stable')),
        'context': {'metrics': {}},
    }
    board_b = {
        'team': {'team_id': 2, 'team_name': 'Team B'},
        'team_state': public_team_state(readiness('data_limited')),
        'context': {'metrics': {}},
    }

    comparison = bullpen_comparison.build_team_comparison(board_a, board_b)

    assert comparison['teams']['team_a']['team_state'] == board_a['team_state']
    assert comparison['teams']['team_b']['team_state'] == board_b['team_state']
    # One unsupported side never becomes a state, and no winner is produced.
    assert comparison['teams']['team_b']['team_state']['public_label'] is None
    assert comparison['ranking_applied'] is False
    assert comparison['selection_made'] is False
    serialized = str(comparison).lower()
    for banned in ('winner', 'advantage', ' edge ', 'grade', 'ranking applied: true'):
        assert banned not in serialized


# ── No competing mapping anywhere in production code ─────────────────────────

VOCABULARY_MODULE = os.path.join(
    'backend', 'services', 'team_state_public_vocabulary.py',
).replace(os.sep, '/')

# Every internal status that has a public Team State. A production module other
# than the authority that names one of these next to a canonical public label is
# a second mapping.
INTERNAL_STATES = tuple(CANONICAL_MAPPING)


def _production_python_files():
    skip_dirs = {'tests', '__pycache__', 'migrations'}
    for root, dirs, files in os.walk(BACKEND_ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(root, name)
            yield os.path.relpath(path, REPO_ROOT).replace(os.sep, '/'), path


def test_only_the_vocabulary_module_maps_internal_states_to_public_labels():
    offenders = []
    for relative, path in _production_python_files():
        if relative == VOCABULARY_MODULE:
            continue
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        if not any(state in source for state in INTERNAL_STATES):
            continue
        # A duplicate mapping is an internal status and a canonical public label
        # appearing on the same line — the shape a second dictionary takes.
        for number, line in enumerate(source.splitlines(), start=1):
            if line.lstrip().startswith('#'):
                continue
            if any(state in line for state in INTERNAL_STATES) and any(
                re.search(rf'\b{label}\b', line) for label in CANONICAL_PUBLIC_LABELS
            ):
                offenders.append(f'{relative}:{number}: {line.strip()}')

    assert offenders == [], (
        'internal-to-public Team State mapping outside the canonical authority:\n'
        + '\n'.join(offenders)
    )


def test_the_api_layer_resolves_team_state_through_the_canonical_authority():
    path = os.path.join(BACKEND_ROOT, 'api', 'bullpen.py')
    with open(path, encoding='utf-8') as handle:
        tree = ast.parse(handle.read())

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == 'services.team_state_public_vocabulary'
        for alias in node.names
    }

    assert 'public_team_state' in imported
    assert 'team_state_not_team_scoped' in imported


def test_the_frontend_catalogue_declares_only_the_canonical_public_set():
    path = os.path.join(REPO_ROOT, 'frontend', 'src', 'adapters', 'publicTeamState.js')
    with open(path, encoding='utf-8') as handle:
        source = handle.read()

    codes = re.search(
        r"PUBLIC_TEAM_STATE_CODES = Object\.freeze\(\[([^\]]*)\]\)", source,
    )
    labels = re.search(
        r"PUBLIC_TEAM_STATE_LABELS = Object\.freeze\(\[([^\]]*)\]\)", source,
    )

    assert codes and labels
    assert set(re.findall(r"'([^']+)'", codes.group(1))) == CANONICAL_PUBLIC_CODES
    assert set(re.findall(r"'([^']+)'", labels.group(1))) == CANONICAL_PUBLIC_LABELS


def test_the_frontend_adapter_holds_no_team_state_dictionary():
    path = os.path.join(
        REPO_ROOT, 'frontend', 'src', 'adapters', 'operatingStateReadModel.js',
    )
    with open(path, encoding='utf-8') as handle:
        source = handle.read()

    # The retired frontend Team State dictionary and every label it produced.
    assert 'STATE_META' not in source
    for retired in (
        "'Stable'", "'Stable Overall'", "'Usable'", "'Worth Watching'",
        "'Thin'", "'Stressed'", "'Recovering'",
    ):
        assert retired not in source, f'retired Team State label still present: {retired}'
    # The state label is read from the backend block and never authored locally.
    assert 'const stateLabel = teamState.publicLabel' in source
    assert "stateLabel: '" not in source
    # The only canonical label text left in this file belongs to the public-copy
    # rewrite in safeText (internal prose wording, governed by #591), never to a
    # Team State assignment. Nothing here builds a label from an internal value.
    for number, line in enumerate(source.splitlines(), start=1):
        if not any(f"'{label}'" in line for label in CANONICAL_PUBLIC_LABELS):
            continue
        assert '.replace(' in line, (
            f'canonical Team State label authored outside a copy rewrite at line {number}: '
            f'{line.strip()}'
        )
