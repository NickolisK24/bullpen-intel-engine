"""Read-only Team State calibration history export.

The exporter lifts frozen Team State evidence into an offline artifact. These
tests pin the two properties that make such an artifact trustworthy: it must
carry exactly what history preserved, and it must never quietly fill a gap.

Nothing here changes Team State semantics. No threshold, status meaning, public
mapping, or classifier behaviour is exercised or altered.
"""

import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.public_serving_authority import (
    TEAM_BOARD_PACKAGE_CONTRACT,
    TEAM_BOARD_PACKAGE_KEY,
)
from services.team_state_history_export import (
    UNPRESERVED_ARM_FIELDS,
    UNPRESERVED_TEAM_LEVEL_FIELDS,
    build_export,
    build_row,
    public_state_for,
)


def board_record(pitcher_id, status, *, raw_score=None, data_state='fresh'):
    return {
        'pitcher_id': pitcher_id,
        'name': f'Arm {pitcher_id}',
        'fatigue_score': raw_score,
        'availability': {'availability_status': status, 'data_state': data_state},
    }


def snapshot(*, records=None, default_ids=None, package=True, snapshot_id=424):
    payload = {}
    if package:
        payload[TEAM_BOARD_PACKAGE_KEY] = {
            'contract': TEAM_BOARD_PACKAGE_CONTRACT,
            'by_team_id': {
                '147': {
                    'records': records if records is not None else [],
                    'default_pitcher_ids': (
                        default_ids
                        if default_ids is not None
                        else [record['pitcher_id'] for record in (records or [])]
                    ),
                },
            },
        }
    return SimpleNamespace(
        id=snapshot_id,
        sync_run_id=748,
        published_at=datetime(2026, 8, 16, 10, 41, 9),
        data_through=date(2026, 8, 15),
        payload=payload,
    )


def artifact(*, status_code='operationally_stressed', summary='One reliever is Unavailable.',
             constraints=None, trust=None, team_abbr='NYY'):
    return SimpleNamespace(
        team_id=147,
        product_date=date(2026, 8, 15),
        render_version='1.0.0',
        payload={
            'team': {'team_id': 147, 'team_abbreviation': team_abbr},
            'team_state': {
                'status_code': status_code,
                'summary': summary,
                'constraints': constraints if constraints is not None else [
                    {'constraint_id': 'availability_constrained', 'category': 'availability'},
                ],
            },
            'trust': trust if trust is not None else {
                'confidence': 'high', 'data_state': 'fresh', 'freshness_state': 'current',
            },
        },
    )


# ── frozen authority is exported unchanged ───────────────────────────────────

def test_frozen_component_evidence_is_exported_unchanged():
    records = [board_record(i, 'available') for i in range(1, 7)]
    records.append(board_record(7, 'monitor'))
    records.append(board_record(8, 'unavailable'))

    row = build_row(snapshot(records=records), artifact())

    assert row['snapshot_id'] == 424
    assert row['sync_run_id'] == 748
    assert row['data_through'] == '2026-08-15'
    assert row['contract_version'] == '1.0.0'
    assert row['readiness_status_code'] == 'operationally_stressed'
    assert row['published_why_text'] == 'One reliever is Unavailable.'
    assert row['constraint_ids'] == ['availability_constrained']
    assert row['trust_confidence'] == 'high'
    assert row['freshness_state'] == 'current'

    partition = row['derived_partition']
    assert partition['clean_count'] == 6
    assert partition['moderate_count'] == 1
    assert partition['severe_count'] == 1
    assert partition['unknown_count'] == 0
    assert partition['population_count'] == 8
    assert partition['clean_share'] == pytest.approx(0.75)
    assert partition['derived'] is True


def test_partition_integrity_is_reported_and_never_repaired():
    records = [board_record(i, 'available') for i in range(1, 4)]
    # A declared population that the records cannot satisfy must be surfaced.
    row = build_row(snapshot(records=records, default_ids=[1, 2, 3, 99]), artifact())

    assert row['integrity']['ok'] is False
    assert 'population_count_mismatch' in row['integrity']['flags']
    # The row is still emitted, unrepaired.
    assert row['derived_partition']['clean_count'] == 3


def test_missing_frozen_board_package_is_flagged_not_filled():
    row = build_row(snapshot(package=False), artifact())

    assert row['frozen_board_present'] is False
    assert row['derived_partition'] is None
    assert row['arms'] == []
    assert 'frozen_board_package_missing' in row['integrity']['flags']


# ── null / zero / absent are three different things ──────────────────────────

def test_zero_stays_zero_and_null_stays_null():
    records = [board_record(1, 'available', raw_score=0), board_record(2, 'available', raw_score=None)]
    row = build_row(snapshot(records=records), artifact())

    assert row['arms'][0]['raw_score'] == 0
    assert row['arms'][1]['raw_score'] is None
    # A legitimately empty category is 0, not None.
    assert row['derived_partition']['severe_count'] == 0


def test_unpreserved_history_is_null_never_zero():
    row = build_row(snapshot(records=[board_record(1, 'available')]), artifact())

    for field in UNPRESERVED_TEAM_LEVEL_FIELDS:
        assert field in row, f'{field} must be present under one consistent contract'
        assert row[field] is None, f'{field} was not preserved by history and must be null'
    for field in UNPRESERVED_ARM_FIELDS:
        assert row['arms'][0][field] is None


def test_current_live_data_never_fills_a_frozen_gap():
    """A snapshot with no frozen arm evidence must not acquire any."""
    row = build_row(snapshot(records=[]), artifact())

    assert row['arms'] == []
    assert row['derived_partition']['population_count'] == 0
    assert row['derived_partition']['clean_share'] is None  # guarded, not 0.0
    assert row['active_pitcher_count'] is None


def test_arm_level_exported_only_when_historically_preserved():
    with_arms = build_row(snapshot(records=[board_record(1, 'monitor', raw_score=42)]), artifact())
    without_arms = build_row(snapshot(package=False), artifact())

    assert with_arms['arms'][0]['availability_status'] == 'monitor'
    assert with_arms['arms'][0]['raw_score'] == 42
    assert without_arms['arms'] == []


# ── public state mapping ─────────────────────────────────────────────────────

@pytest.mark.parametrize('status_code,expected', [
    ('operationally_stable', 'Fresh'),
    ('operationally_constrained', 'Stretched'),
    ('operationally_stressed', 'Vulnerable'),
])
def test_internal_status_maps_to_its_canonical_public_state(status_code, expected):
    assert public_state_for(status_code) == expected
    row = build_row(snapshot(records=[]), artifact(status_code=status_code))
    assert row['readiness_status_code'] == status_code
    assert row['public_team_state'] == expected


@pytest.mark.parametrize('status_code', ['data_limited', 'refused', 'something_new'])
def test_non_publishable_status_never_becomes_a_public_team_state(status_code):
    row = build_row(snapshot(records=[]), artifact(status_code=status_code))

    assert row['readiness_status_code'] == status_code
    assert row['public_team_state'] is None


# ── export envelope ──────────────────────────────────────────────────────────

def test_export_envelope_reports_counts_and_read_only():
    pairs = [(snapshot(records=[board_record(1, 'available')]), artifact())]
    export = build_export(
        pairs, generated_at='2026-08-17T00:00:00+00:00',
        repository_sha='abc123', filters={'snapshot_id': 424},
    )

    assert export['read_only'] is True
    assert export['snapshot_count'] == 1
    assert export['team_classification_count'] == 1
    assert export['filters'] == {'snapshot_id': 424}
    assert export['unpreserved_team_level_fields']


def test_export_is_deterministic_apart_from_generation_timestamp():
    pairs = [(snapshot(records=[board_record(1, 'available'), board_record(2, 'avoid')]), artifact())]
    first = build_export(pairs, generated_at='A', repository_sha='sha', filters={})
    second = build_export(pairs, generated_at='B', repository_sha='sha', filters={})

    first.pop('generated_at')
    second.pop('generated_at')
    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(
        second, sort_keys=True, default=str
    )


def test_export_carries_no_credentials_or_raw_rows():
    export = build_export(
        [(snapshot(records=[board_record(1, 'available')]), artifact())],
        generated_at='now', repository_sha=None, filters={},
    )
    text = json.dumps(export, default=str).lower()

    for secret in ('password', 'database_url', 'postgres://', 'admin_token', 'secret_key'):
        assert secret not in text


# ── the exporter performs no writes ──────────────────────────────────────────

def test_exporter_module_contains_no_mutation_calls():
    source = Path(__file__).resolve().parents[1] / 'services' / 'team_state_history_export.py'
    text = source.read_text()

    for forbidden in (
        'session.add(', 'session.delete(', 'session.commit(', 'session.merge(',
        '.update(', '.insert(', 'session.flush(',
    ):
        assert forbidden not in text, f'exporter must not contain {forbidden}'


def test_export_script_issues_no_mutations():
    source = Path(__file__).resolve().parents[1] / 'scripts' / 'export_team_state_history.py'
    text = source.read_text()

    # Match call syntax, so the read-only inspection attributes the script uses
    # to assert cleanliness (session.new / session.dirty / session.deleted) are
    # not mistaken for mutations.
    for forbidden in ('session.add(', 'session.delete(', 'session.commit(', 'session.merge('):
        assert forbidden not in text, f'export script must not contain {forbidden}'
    # A rollback is the only session state change the script is allowed to make.
    assert 'db.session.rollback()' in text


def test_build_row_does_not_mutate_its_inputs():
    records = [board_record(1, 'available')]
    snap = snapshot(records=records)
    art = artifact()
    before = json.dumps(snap.payload, sort_keys=True, default=str)
    art_before = json.dumps(art.payload, sort_keys=True, default=str)

    build_row(snap, art)

    assert json.dumps(snap.payload, sort_keys=True, default=str) == before
    assert json.dumps(art.payload, sort_keys=True, default=str) == art_before
