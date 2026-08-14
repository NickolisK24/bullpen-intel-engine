"""Structured explanation labels are owned by the backend (H-5 closeout).

Reasons and evidence items always carried a governed ``label``. Limitations did
not, so the browser was left to build a heading out of the internal key --
``insufficient_context`` reached readers as "Insufficient Context", and
``deterministic_sample_state`` as "Deterministic Sample State". The refusal path
had a *second* label table of its own in ``api/explanations``, so one limitation
type could read one way in a refused response and another way in a successful
explanation.

Both are fixed here rather than in the renderer: the type is validated against a
closed vocabulary, and the label is authored next to that vocabulary. The
matrix below is the regression contract -- it is driven off
ALLOWED_LIMITATION_TYPES, so a new type with no governed label fails this file
rather than reaching a reader through a title-cased key.
"""

import pytest

from explanations import (
    ALLOWED_LIMITATION_TYPES,
    ALLOWED_REASON_CODES,
    LIMITATION_TYPE_DEFINITIONS,
    REASON_CODE_DEFINITIONS,
    limitation_type_label,
)
from explanations.builders import build_limitation
from explanations.contracts import V4Limitation, V4Reason


# ── every reachable key has a governed label ────────────────────────────────

@pytest.mark.parametrize('limitation_type', sorted(ALLOWED_LIMITATION_TYPES))
def test_every_allowed_limitation_type_has_a_governed_label(limitation_type):
    label = limitation_type_label(limitation_type)
    assert isinstance(label, str) and label.strip()


@pytest.mark.parametrize('reason_code', sorted(ALLOWED_REASON_CODES))
def test_every_allowed_reason_code_has_a_governed_label(reason_code):
    assert REASON_CODE_DEFINITIONS[reason_code]['label'].strip()


def test_the_limitation_catalogue_covers_exactly_the_allowed_vocabulary():
    """No orphan label, and no allowed type without one."""
    assert set(LIMITATION_TYPE_DEFINITIONS) == set(ALLOWED_LIMITATION_TYPES)


@pytest.mark.parametrize('limitation_type', sorted(ALLOWED_LIMITATION_TYPES))
def test_a_governed_label_never_looks_like_an_internal_key(limitation_type):
    label = limitation_type_label(limitation_type)
    assert '_' not in label, label
    assert label != limitation_type
    assert label[:1] == label[:1].upper()


@pytest.mark.parametrize('limitation_type', sorted(ALLOWED_LIMITATION_TYPES))
def test_a_governed_label_carries_no_engine_vocabulary(limitation_type):
    lowered = limitation_type_label(limitation_type).lower()
    for banned in ('null', 'none', 'enum', 'payload', 'serializer', 'traceback',
                   'exception', 'sql', 'schema', 'snake_case'):
        assert banned not in lowered, (limitation_type, banned)


# ── the label reaches the serialized payload ────────────────────────────────

@pytest.mark.parametrize('limitation_type', sorted(ALLOWED_LIMITATION_TYPES))
def test_every_serialized_limitation_carries_its_label(limitation_type):
    payload = build_limitation(
        limitation_type=limitation_type, summary='Governed summary.'
    ).to_dict()
    assert payload['label'] == limitation_type_label(limitation_type)
    assert payload['limitation_type'] == limitation_type


def test_a_limitation_built_directly_also_carries_its_label():
    """The label is resolved by the contract, not by one convenience builder."""
    payload = V4Limitation(
        limitation_type='stale_data', summary='Governed summary.'
    ).to_dict()
    assert payload['label'] == limitation_type_label('stale_data')


def test_a_serialized_limitation_round_trips_without_losing_its_label():
    """_limitation_reference re-builds from a dict; every field must survive."""
    original = build_limitation(
        limitation_type='partial_coverage', summary='Governed summary.'
    ).to_dict()
    rebuilt = build_limitation(**original).to_dict()
    assert rebuilt == original


def test_reason_labels_still_come_from_their_own_definitions():
    reason = V4Reason.from_code('TRUST_LIMITED').to_dict()
    assert reason['label'] == REASON_CODE_DEFINITIONS['TRUST_LIMITED']['label']


# ── unknown keys fail closed ────────────────────────────────────────────────

@pytest.mark.parametrize('unknown', [
    'deterministic_sample_state',
    'live_observation_source_unavailable',
    'forbidden_request_parameter',
    'unsupported_request_parameter',
    'invalid_supplied_state',
    'some_internal_reason',
    '',
    None,
])
def test_an_unknown_key_has_no_governed_label(unknown):
    """None is the fail-closed answer; nothing derives a label from the key."""
    assert limitation_type_label(unknown) is None


@pytest.mark.parametrize('unknown', ['deterministic_sample_state', 'not_a_type'])
def test_an_unknown_limitation_type_cannot_be_constructed_at_all(unknown):
    with pytest.raises(ValueError):
        build_limitation(limitation_type=unknown, summary='Governed summary.')


# ── one authority, not two ──────────────────────────────────────────────────

def test_the_refusal_route_uses_the_canonical_catalogue():
    """api/explanations carried its own copy of all six labels."""
    from api.explanations import _limitation_label

    for limitation_type in sorted(ALLOWED_LIMITATION_TYPES):
        assert _limitation_label(limitation_type) == limitation_type_label(limitation_type)


def test_the_refusal_route_never_derives_a_label_from_an_unknown_key():
    from api.explanations import _limitation_label

    label = _limitation_label('deterministic_sample_state')
    assert label == 'Explanation unavailable'
    assert 'deterministic' not in label.lower()
    assert 'sample' not in label.lower()


def test_no_second_label_table_lives_outside_the_contract():
    """A grep-level guard: the six labels are authored in exactly one file."""
    from pathlib import Path

    import explanations.contracts as contracts

    canonical = Path(contracts.__file__).resolve()
    backend_root = canonical.parent.parent
    labels = {definition['label'] for definition in LIMITATION_TYPE_DEFINITIONS.values()}

    offenders = []
    for path in backend_root.rglob('*.py'):
        if path.resolve() == canonical or 'tests' in path.parts:
            continue
        try:
            source = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        for label in labels:
            if f"'{label}'" in source or f'"{label}"' in source:
                offenders.append((path.relative_to(backend_root).as_posix(), label))
    assert offenders == [], offenders


# ── determinism ─────────────────────────────────────────────────────────────

def test_label_resolution_is_deterministic():
    for limitation_type in sorted(ALLOWED_LIMITATION_TYPES):
        runs = [
            build_limitation(
                limitation_type=limitation_type, summary='Governed summary.'
            ).to_dict()
            for _ in range(3)
        ]
        assert runs[0] == runs[1] == runs[2], limitation_type


def test_the_catalogue_introduces_no_runtime_variability():
    import explanations.contracts as contracts

    source = open(contracts.__file__, encoding='utf-8').read()
    for banned in ('import random', 'random.choice', 'datetime.now', 'time.time',
                   'os.environ'):
        assert banned not in source, banned
