"""Game 824487 source-revision audit — code-path drift contract.

Requirements 42-52.

Two identical source revisions cannot be told apart by their digests, so the
audit's second lever is the CODE that produced them. A whole-file comparison
answers the wrong question: a module can move for reasons that cannot reach
either digest, and this repository's own history contains exactly that case.
These tests own the property that makes the comparison usable — symbol-level
semantics, insensitive to formatting and comments, sensitive to behaviour, and
explicit whenever a symbol or a revision is simply not there.
"""

import subprocess
from pathlib import Path

import pytest

from scripts import run_game_source_revision_audit as runner
from services import game_source_revision_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[2]

PRIOR = runner.REVISION_PRIOR
LATER = runner.REVISION_LATER
AUDIT = runner.REVISION_AUDIT

BASE = '''
"""Module docstring."""

FINGERPRINT_FIELDS = (
    'pitcher_mlb_id',
    'outs_recorded',
)


def appearance_set_fingerprint(appearances):
    """Observed-content marker."""
    payload = [record for record in appearances]
    return hash(tuple(payload))


def parse_games_started(value):
    if value is None:
        return None
    return int(value)
'''


def _target(target_id, path, names, kind, affects=()):
    return {
        'target_id': target_id,
        'path': path,
        'names': tuple(names),
        'kind': kind,
        'affects': tuple(affects),
    }


FINGERPRINT_TARGET = _target(
    'x.appearance_set_fingerprint', 'm.py', ('appearance_set_fingerprint',),
    audit.SYMBOL_KIND_FUNCTION, (audit.AFFECTS_SOURCE_REVISION,),
)
CONSTANT_TARGET = _target(
    'x.FINGERPRINT_FIELDS', 'm.py', ('FINGERPRINT_FIELDS',),
    audit.SYMBOL_KIND_CONSTANT, (audit.AFFECTS_SOURCE_REVISION,),
)


def _compare(target, prior, later, audit_source=None):
    return audit.compare_symbol_across_revisions(target, {
        PRIOR: prior,
        LATER: later,
        AUDIT: prior if audit_source is None else audit_source,
    })


# ── 42-44. What must NOT be called drift ────────────────────────────────────

def test_identical_symbol_bodies_report_no_semantic_drift():
    result = _compare(FINGERPRINT_TARGET, BASE, BASE)
    assert result['state'] == audit.DRIFT_EQUAL
    assert result['semantic_drift'] is False
    assert result['comparable'] is True


def test_a_formatting_only_change_reports_no_semantic_drift():
    reflowed = BASE.replace(
        '    payload = [record for record in appearances]\n'
        '    return hash(tuple(payload))',
        '    payload = [\n'
        '        record\n'
        '        for record in appearances\n'
        '    ]\n'
        '    return hash(\n'
        '        tuple(payload)\n'
        '    )',
    )
    assert reflowed != BASE
    result = _compare(FINGERPRINT_TARGET, BASE, reflowed)
    assert result['state'] == audit.DRIFT_EQUAL
    assert result['semantic_drift'] is False
    # The file itself DID move, and that is reported alongside — never instead.
    assert result['full_file_identical_across_revisions'] is False


def test_a_comment_only_change_reports_no_semantic_drift():
    commented = BASE.replace(
        '    payload = [record for record in appearances]',
        '    # Deterministic order, independent of payload order.\n'
        '    payload = [record for record in appearances]',
    )
    assert commented != BASE
    result = _compare(FINGERPRINT_TARGET, BASE, commented)
    assert result['semantic_drift'] is False


def test_a_docstring_only_change_reports_no_semantic_drift():
    redocumented = BASE.replace(
        '"""Observed-content marker."""',
        '"""Observed-content marker for one game\'s appearance set."""',
    )
    result = _compare(FINGERPRINT_TARGET, BASE, redocumented)
    assert result['semantic_drift'] is False


# ── 45-50. What MUST be called drift ────────────────────────────────────────

def test_a_fingerprint_fields_change_is_detected():
    changed = BASE.replace(
        "    'outs_recorded',\n", "    'outs_recorded',\n    'strikeouts',\n",
    )
    result = _compare(CONSTANT_TARGET, BASE, changed)
    assert result['state'] == audit.DRIFT_CHANGED
    assert result['semantic_drift'] is True
    assert result['constants_identical'] is False
    assert result['can_affect_source_revision'] is True
    assert result['observations'][LATER]['constant_value'] == [
        'pitcher_mlb_id', 'outs_recorded', 'strikeouts',
    ]


def test_an_appearance_set_fingerprint_change_is_detected():
    changed = BASE.replace(
        '    return hash(tuple(payload))',
        '    return hash(tuple(sorted(payload)))',
    )
    result = _compare(FINGERPRINT_TARGET, BASE, changed)
    assert result['semantic_drift'] is True
    assert result['can_affect_source_revision'] is True


def test_an_extraction_normalization_change_is_detected():
    source = BASE + '''

def extract_game_appearances(game, lines):
    return [dict(line) for line in lines]
'''
    changed = source.replace(
        '    return [dict(line) for line in lines]',
        '    return [dict(line, normalized=True) for line in lines]',
    )
    target = _target(
        'x.extract_game_appearances', 'm.py', ('extract_game_appearances',),
        audit.SYMBOL_KIND_FUNCTION, (audit.AFFECTS_SOURCE_REVISION,),
    )
    assert _compare(target, source, changed)['semantic_drift'] is True


def test_a_games_started_normalization_change_is_detected():
    changed = BASE.replace('        return None', '        return 0')
    target = _target(
        'x.parse_games_started', 'm.py', ('parse_games_started',),
        audit.SYMBOL_KIND_FUNCTION, (audit.AFFECTS_SOURCE_REVISION,),
    )
    assert _compare(target, BASE, changed)['semantic_drift'] is True


def test_an_innings_normalization_change_is_detected():
    source = '''
def parse_mlb_innings_to_outs(value):
    whole, _, part = str(value).partition('.')
    return int(whole) * 3 + int(part or 0)
'''
    changed = source.replace('int(whole) * 3', 'round(float(whole) * 3)')
    target = _target(
        'x.parse_mlb_innings_to_outs', 'm.py',
        ('parse_mlb_innings_to_outs',), audit.SYMBOL_KIND_FUNCTION,
        (audit.AFFECTS_SOURCE_REVISION,),
    )
    assert _compare(target, source, changed)['semantic_drift'] is True


def test_a_reconciliation_plan_construction_change_is_detected():
    source = '''
def plan_row(values, stored):
    return {'action': 'unchanged' if values == stored else 'update'}
'''
    changed = source.replace("values == stored", "values is stored")
    target = _target(
        'x.plan_row', 'm.py', ('plan_row',), audit.SYMBOL_KIND_FUNCTION,
        (audit.AFFECTS_PLAN_FINGERPRINT,),
    )
    result = _compare(target, source, changed)
    assert result['semantic_drift'] is True
    assert result['can_affect_plan_fingerprint'] is True
    assert result['can_affect_source_revision'] is False


def test_a_signature_change_is_detected_even_with_an_identical_body():
    changed = BASE.replace(
        'def appearance_set_fingerprint(appearances):',
        'def appearance_set_fingerprint(appearances, *, strict=True):',
    )
    assert _compare(FINGERPRINT_TARGET, BASE, changed)['semantic_drift'] is True


# ── 51-52. Absent evidence is stated, never skipped ─────────────────────────

def test_a_missing_historical_symbol_is_reported_explicitly(tmp_path):
    without = BASE.replace('def appearance_set_fingerprint', 'def renamed_away')
    result = _compare(FINGERPRINT_TARGET, without, BASE)
    assert result['state'] == audit.DRIFT_SYMBOL_MISSING
    assert result['comparable'] is False
    assert result['observations'][PRIOR]['symbol_name'] is None


def test_a_historically_renamed_symbol_is_identified_not_skipped():
    """The historical symbol actually used is found through its alias."""
    historical = BASE.replace(
        'def parse_games_started', 'def _line_games_started',
    )
    target = _target(
        'x.games_started_helper', 'm.py',
        ('parse_games_started', '_line_games_started'),
        audit.SYMBOL_KIND_FUNCTION, (audit.AFFECTS_SOURCE_REVISION,),
    )
    result = _compare(target, historical, BASE)
    assert result['comparable'] is True
    assert result['symbol_names_by_revision'][PRIOR] == '_line_games_started'
    assert result['symbol_names_by_revision'][LATER] == 'parse_games_started'
    assert result['renamed_between_revisions'] is True
    # A rename alone is not behavioural drift.
    assert result['semantic_drift'] is False


def test_an_unavailable_historical_sha_is_unproven_not_equal():
    result = _compare(FINGERPRINT_TARGET, None, BASE)
    assert result['state'] == audit.DRIFT_UNAVAILABLE
    assert result['comparable'] is False
    assert result['semantic_drift'] is False


def test_a_file_absent_at_a_revision_is_distinct_from_an_absent_revision():
    result = _compare(FINGERPRINT_TARGET, '', BASE)
    assert result['state'] == audit.DRIFT_FILE_MISSING
    assert result['comparable'] is False


def test_an_unparseable_historical_file_is_reported_not_ignored():
    result = _compare(FINGERPRINT_TARGET, 'def broken(:', BASE)
    assert result['state'] == audit.DRIFT_UNPARSEABLE
    assert result['comparable'] is False


# ── Summary semantics ───────────────────────────────────────────────────────

def test_the_summary_separates_blob_movement_from_semantic_drift():
    reflowed = BASE.replace('    return hash(tuple(payload))',
                            '    return hash(\n        tuple(payload)\n    )')
    summary = audit.summarize_code_drift([
        _compare(FINGERPRINT_TARGET, BASE, reflowed),
    ])
    assert summary['semantic_drift_detected'] is False
    assert summary['files_whose_full_blob_changed'] == ['m.py']
    assert summary['files_changed_without_semantic_drift'] == ['m.py']
    assert summary['comparison_complete'] is True


def test_an_incomparable_target_makes_the_summary_incomplete():
    summary = audit.summarize_code_drift([
        _compare(FINGERPRINT_TARGET, None, BASE),
    ])
    assert summary['comparison_complete'] is False
    assert summary['incomparable_targets'] == ['x.appearance_set_fingerprint']


# ── The orchestration path, driven against real repository history ──────────

def _head_sha():
    return subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    ).stdout.strip()


def _history_available():
    for sha in audit.HISTORICAL_SHAS.values():
        if not runner.revision_available(sha):
            return False
    return bool(_head_sha())


needs_history = pytest.mark.skipif(
    not _history_available(),
    reason='requires full repository history for both incident SHAs',
)


@needs_history
def test_every_declared_target_resolves_at_both_incident_shas():
    result = runner.observe_code_drift(_head_sha())
    assert result['all_revisions_reachable'] is True
    assert result['comparison_complete'] is True
    assert result['incomparable_targets'] == []
    assert result['targets_compared'] == len(audit.CODE_DRIFT_TARGETS)


@needs_history
def test_the_real_comparison_names_the_symbol_it_found_at_each_sha():
    result = runner.observe_code_drift(_head_sha())
    by_id = {entry['target_id']: entry for entry in result['comparisons']}
    entry = by_id['sync.games_started_helper']
    assert set(entry['symbol_names_by_revision'].values()) <= set(
        entry['candidate_names']
    )
    assert None not in entry['symbol_names_by_revision'].values()


@needs_history
def test_the_real_fingerprint_field_list_is_read_from_each_revision():
    result = runner.observe_code_drift(_head_sha())
    by_id = {entry['target_id']: entry for entry in result['comparisons']}
    entry = by_id['extraction.FINGERPRINT_FIELDS']
    for label in (PRIOR, LATER, AUDIT):
        value = entry['observations'][label]['constant_value']
        assert isinstance(value, list) and value


@needs_history
def test_an_unreachable_revision_is_reported_rather_than_assumed_equal():
    result = runner.observe_code_drift('0' * 40)
    assert result['all_revisions_reachable'] is False
    assert AUDIT in result['unreachable_revisions']
    assert result['comparison_complete'] is False
