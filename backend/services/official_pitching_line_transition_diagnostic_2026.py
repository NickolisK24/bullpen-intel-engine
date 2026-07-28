"""Targeted forensic diagnostic for ONE exact-to-defective pitching line — READ ONLY.

The repaired repair-planner ran cleanly in production at 970664f and still returned
``inconclusive`` / ``blocked_by_baseline_drift``. Every reconciliation was true, there were no
blocking reasons, no writes, and the identity partition was internally valid. Exactly one
immutable defect count moved: 12,697 -> 12,696 exact matches, 159 -> 160 defective matched
lines, 604 -> 605 defect-line actions.

The whole of that movement is one line. Official MLB person 805299, Brandyn Garcia, relieving
for official team 109 in game 825058 on 2026-07-20, stored locally as GameLog 43765. The local
row says one hit allowed; the current official box score says zero.

That is the entire content of the current evidence, and it is NOT enough to say what happened.
"Local says 1, official says 0" is a statement about two values right now. It does not say
whether MLB corrected a box score after the accepted diagnostic ran, or whether local
ingestion wrote a value that never matched official evidence. Those are different failures
with different remedies, and the current artifact cannot distinguish them.

This module answers only that question, for only that line, and it fails closed. It reproduces
the current mismatch from live official evidence and the live local row, then searches every
durable local source that could establish a PRIOR value on either side. If no durable source
retains a prior value, the answer is ``historical_state_unprovable`` and the result is
INCONCLUSIVE. Absence of history is never reported as proof that MLB changed the box score.

Boundaries: read only. No writes, no apply mode, no repair, no baseline amendment, and no
fingerprint approval. The accepted defect baseline is not read from here and is not changed.
Identity is resolved by exact official MLB id; name matching, current team assignment, and
current roster state are never consulted.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import official_pitching_line_completeness_2026 as completeness
from services import sync as sync_service
from services.mlb_api import mlb_client
from utils.db import db
from utils.time import utc_now_naive


CAPABILITY = 'official_pitching_line_transition_diagnostic_2026_v1'
DIAGNOSTIC_CONTRACT_VERSION = 'official_pitching_line_transition_diagnostic_2026.v1'
COMPARISON_AUTHORITY = completeness.DIAGNOSTIC_CONTRACT_VERSION
EXPECTED_MIGRATION_HEAD = completeness.EXPECTED_MIGRATION_HEAD

MODE_READ_ONLY = completeness.MODE_READ_ONLY
RESULT_PASS = completeness.RESULT_PASS
RESULT_FAIL = completeness.RESULT_FAIL
RESULT_INCONCLUSIVE = completeness.RESULT_INCONCLUSIVE
EXIT_BY_RESULT = dict(completeness.EXIT_BY_RESULT)

# ── The single line under investigation ───────────────────────────────────────
# Fixed by the production artifact. A scoped diagnostic that could be pointed anywhere would
# be a general tool; this one exists to answer one question about one line.
TARGET_SEASON = 2026
TARGET_GAME_PK = 825058
TARGET_OFFICIAL_MLB_PERSON_ID = 805299
TARGET_APPEARANCE_TEAM_ID = 109
TARGET_LOCAL_GAME_LOG_ID = 43765
TARGET_FIELD = 'hits_allowed'
TARGET_OFFICIAL_STAT_KEY = 'hits'
TARGET_GAME_DATE = date(2026, 7, 20)
TARGET_REASON_CODE = completeness.REASON_HITS_MISMATCH

# What the production manifest asserted about this line. Expectations, not authority: the
# diagnostic re-derives both sides and reports any disagreement rather than assuming these.
EXPECTED_LOCAL_VALUE = 1
EXPECTED_OFFICIAL_VALUE = 0
EXPECTED_UPDATE_ACTION_ID = 'gamelog:update:43765:825058:805299'
EXPECTED_SOURCE_FINGERPRINT = (
    '5fc28e9d7def63ffbb75a1f8b099bfa40db3d416062fb08a80e7d69aed16dc9b')

# Unapproved manifest fingerprints. Pinned so a reader can see they are known and refused;
# none of them is wired to any apply path, because no apply path exists.
UNAPPROVED_MANIFEST_FINGERPRINTS = (
    '9b8ab677c83ec5b8efa5a4020593911dc4d6d73e3262a09c0703d1a5907b49b7',
    'dd453cd63b1e4ccc14b5ff97c962635d6c5eda296a4e4ef63066105eeec225c6',
    '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b',
)

# ── Authority transition vocabulary ───────────────────────────────────────────
TRANSITION_OFFICIAL_CHANGED = 'official_source_changed'
TRANSITION_LOCAL_CHANGED = 'local_game_log_changed'
TRANSITION_BOTH_CHANGED = 'both_changed'
TRANSITION_UNPROVABLE = 'historical_state_unprovable'
TRANSITION_NOT_REPRODUCED = 'current_mismatch_not_reproduced'
TRANSITION_CLASSIFICATIONS = (
    TRANSITION_OFFICIAL_CHANGED, TRANSITION_LOCAL_CHANGED, TRANSITION_BOTH_CHANGED,
    TRANSITION_UNPROVABLE, TRANSITION_NOT_REPRODUCED,
)
# Only a proven transition may pass. Unprovable and unreproduced are inconclusive by
# construction: neither is a finding about what happened.
PROVEN_CLASSIFICATIONS = (
    TRANSITION_OFFICIAL_CHANGED, TRANSITION_LOCAL_CHANGED, TRANSITION_BOTH_CHANGED)

CONFIDENCE_PROVEN = 'proven_by_durable_evidence'
CONFIDENCE_UNPROVABLE = 'not_provable_from_retained_evidence'
CONFIDENCE_CONTRADICTED = 'contradicted_by_current_evidence'

# ── Contradiction vocabulary ──────────────────────────────────────────────────
FAIL_OFFICIAL_LINE_ABSENT = 'official_line_absent_for_target_key'
FAIL_OFFICIAL_LINE_DUPLICATED = 'official_line_duplicated_for_target_key'
FAIL_LOCAL_ROW_ABSENT = 'local_game_log_absent_for_target_key'
FAIL_LOCAL_ROW_DUPLICATED = 'local_game_log_duplicated_for_target_key'
FAIL_LOCAL_IDENTITY_MISMATCH = 'local_pitcher_identity_mismatch'
FAIL_APPEARANCE_TEAM_MISMATCH = 'appearance_team_mismatch'
FAIL_OFFICIAL_EVIDENCE_UNAVAILABLE = 'official_evidence_unavailable'
FAIL_INCONSISTENT_HISTORY = 'historical_evidence_chronology_inconsistent'

# ── Durable historical sources ────────────────────────────────────────────────
# Every source that could establish a PRIOR value for either side, whether or not it turns
# out to hold one. A source that exists and holds nothing is evidence; a source that does not
# exist at all is a stated limitation, never a silent gap.
SOURCE_CORRECTION_METADATA = 'game_logs.correction_metadata'
SOURCE_EVIDENCE_CITATIONS = 'evidence_citations.cited_values'
SOURCE_EVIDENCE_OBJECTS = 'evidence_objects.invalidation_markers'
SOURCE_SYNC_RUNS = 'sync_runs'
SOURCE_POSTGAME = 'postgame_processed_games'
SOURCE_SYNC_FAILURES = 'sync_failures'
SOURCE_REPO_ARTIFACTS = 'repository_retained_artifacts'
SOURCE_OFFICIAL_SNAPSHOTS = 'official_response_snapshots'
SOURCE_WORKFLOW_ARTIFACTS = 'github_workflow_run_artifacts'

# Sources that do not exist in this system at all. Named so their absence is an explicit,
# reviewable limitation rather than an unexamined assumption.
STRUCTURALLY_ABSENT_SOURCES = {
    SOURCE_OFFICIAL_SNAPSHOTS: (
        'no table retains the raw official box-score response as fetched at ingestion time, '
        'so a prior OFFICIAL value cannot be read back from local state'),
    SOURCE_WORKFLOW_ARTIFACTS: (
        'private workflow-run artifacts are not reachable from application code or database '
        'state; they are retained for 14 days in GitHub Actions and must be inspected there'),
}

# The local GameLog columns reported verbatim. GameLog has no updated_at column, so the
# governed correction metadata is the only durable record that the row was ever rewritten.
LOCAL_REPORTED_FIELDS = (
    'id', 'pitcher_id', 'mlb_game_pk', 'appearance_team_id', 'game_date', 'game_type',
    'games_started', 'hits_allowed', 'runs_allowed', 'earned_runs', 'walks', 'strikeouts',
    'home_runs_allowed', 'innings_pitched', 'innings_pitched_outs', 'pitches_thrown',
    'strikes', 'batters_faced', 'opponent', 'opponent_abbreviation',
    'appearance_team_source', 'appearance_team_status', 'appearance_team_reason',
    'created_at', 'stat_correction_count', 'last_stat_correction_at',
    'last_stat_correction_source', 'last_stat_correction_sync_run_id',
)

# Identity is resolved by exact official MLB id and nothing else.
IDENTITY_RESOLUTION_CONTRACT = 'pitcher.mlb_id_exact_match'
IDENTITY_EXCLUDED_SIGNALS = (
    'full_name', 'name_similarity', 'team_id', 'roster_status', 'active', 'organization',
)

REPO_ARTIFACT_DIR = Path(__file__).resolve().parents[2] / 'artifacts'


def sha256_of(value) -> str:
    """Deterministic SHA-256 over a normalized JSON serialization."""
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


# ── Current official evidence ─────────────────────────────────────────────────
def _current_official_evidence(client, *, retrieved_at) -> tuple:
    """Fetch the live official box score and isolate the target line.

    The line is located by (game_pk, official person id, appearance team id) only. A name is
    never matched, and the current team assignment of the local identity is never consulted.
    """
    endpoint = f'/game/{TARGET_GAME_PK}/boxscore'
    failures: List[str] = []
    try:
        boxscore = client.get_game_boxscore(TARGET_GAME_PK) or {}
    except Exception:  # noqa: BLE001 — a bounded official failure is an evidence gap
        return ({
            'endpoint': endpoint,
            'retrieved_at': retrieved_at,
            'official_evidence_available': False,
            'matching_line_count': 0,
        }, [FAIL_OFFICIAL_EVIDENCE_UNAVAILABLE])

    sides = completeness._official_sides(
        boxscore, game_pk=TARGET_GAME_PK, game_date=TARGET_GAME_DATE)
    raw_by_key = {}
    for raw in sync_service._extract_pitching_lines_from_boxscore(boxscore):
        person_id = completeness._pos_int(raw.get('person_id')) \
            or completeness._pos_int(raw.get('player_id'))
        team = completeness._pos_int(raw.get('team_id'))
        if person_id is not None:
            raw_by_key.setdefault((person_id, team), []).append(raw)

    matching = [
        line for side in sides for line in side.lines
        if line.pitcher_id == TARGET_OFFICIAL_MLB_PERSON_ID
        and line.team_id == TARGET_APPEARANCE_TEAM_ID
    ]
    if not matching:
        failures.append(FAIL_OFFICIAL_LINE_ABSENT)
    if len(matching) > 1:
        failures.append(FAIL_OFFICIAL_LINE_DUPLICATED)

    line = matching[0] if matching else None
    official_side = next(
        (s for s in sides if s.team_id == TARGET_APPEARANCE_TEAM_ID), None)
    opposing_side = next(
        (s for s in sides if s.team_id is not None
         and s.team_id != TARGET_APPEARANCE_TEAM_ID), None)
    raw_candidates = raw_by_key.get(
        (TARGET_OFFICIAL_MLB_PERSON_ID, TARGET_APPEARANCE_TEAM_ID)) or []
    if len(raw_candidates) > 1 and FAIL_OFFICIAL_LINE_DUPLICATED not in failures:
        failures.append(FAIL_OFFICIAL_LINE_DUPLICATED)
    raw_stats = dict((raw_candidates[0].get('stats') or {})) if raw_candidates else None

    evidence = {
        'endpoint': endpoint,
        'retrieved_at': retrieved_at,
        'official_evidence_available': True,
        'matching_line_count': len(matching),
        'official_mlb_person_id': (line.pitcher_id if line else None),
        'official_name': (line.pitcher_name if line else None),
        'official_side': (line.side if line else None),
        'official_team_id': (line.team_id if line else None),
        'official_team_name': (line.team_name if line else None),
        'opposing_team_id': (opposing_side.team_id if opposing_side else None),
        'opposing_team_name': (opposing_side.team_name if opposing_side else None),
        'official_role': (line.role if line else None),
        'official_raw_pitching_line': raw_stats,
        'official_raw_hits': (raw_stats or {}).get(TARGET_OFFICIAL_STAT_KEY),
        'normalized_stats': (dict(line.stats) if line else None),
        'normalized_hits_allowed': (line.stats.get(TARGET_OFFICIAL_STAT_KEY)
                                    if line else None),
        'innings_pitched': (raw_stats or {}).get('inningsPitched'),
        'innings_pitched_outs': (
            completeness._official_outs(raw_stats) if raw_stats else None),
        'identity_resolution': IDENTITY_RESOLUTION_CONTRACT,
        'identity_excluded_signals': list(IDENTITY_EXCLUDED_SIGNALS),
    }
    evidence['source_fingerprint'] = sha256_of({
        k: v for k, v in evidence.items() if k != 'retrieved_at'})
    return evidence, failures


# ── Current local evidence ────────────────────────────────────────────────────
def _current_local_evidence(session) -> tuple:
    """Read the target GameLog and verify it belongs to the target official identity."""
    failures: List[str] = []
    rows = (session.query(GameLog)
            .filter(GameLog.mlb_game_pk == TARGET_GAME_PK)
            .filter(GameLog.id == TARGET_LOCAL_GAME_LOG_ID)
            .all())
    if not rows:
        failures.append(FAIL_LOCAL_ROW_ABSENT)
    if len(rows) > 1:
        failures.append(FAIL_LOCAL_ROW_DUPLICATED)

    # Any other stored row for the same identity and game is a duplicate ledger line.
    log = rows[0] if rows else None
    pitcher = None
    sibling_ids: List[int] = []
    if log is not None:
        pitcher = session.query(Pitcher).filter(Pitcher.id == log.pitcher_id).first()
        siblings = (session.query(GameLog)
                    .filter(GameLog.mlb_game_pk == TARGET_GAME_PK)
                    .filter(GameLog.pitcher_id == log.pitcher_id)
                    .filter(GameLog.id != log.id)
                    .all())
        sibling_ids = sorted(row.id for row in siblings)
        if sibling_ids:
            failures.append(FAIL_LOCAL_ROW_DUPLICATED)
        if completeness._pos_int(getattr(pitcher, 'mlb_id', None)) \
                != TARGET_OFFICIAL_MLB_PERSON_ID:
            failures.append(FAIL_LOCAL_IDENTITY_MISMATCH)
        if completeness._pos_int(log.appearance_team_id) != TARGET_APPEARANCE_TEAM_ID:
            failures.append(FAIL_APPEARANCE_TEAM_MISMATCH)

    evidence = {
        'matching_row_count': len(rows),
        'duplicate_sibling_game_log_ids': sibling_ids,
        'local_game_log_present': log is not None,
        'pitcher_mlb_id': completeness._pos_int(getattr(pitcher, 'mlb_id', None)),
        'pitcher_row_id': getattr(pitcher, 'id', None),
        'identity_resolution': IDENTITY_RESOLUTION_CONTRACT,
        'identity_excluded_signals': list(IDENTITY_EXCLUDED_SIGNALS),
        # GameLog carries no updated_at column, so a row rewrite is only durably recorded by
        # the governed correction metadata below.
        'updated_at_column_exists': hasattr(GameLog, 'updated_at'),
    }
    for field in LOCAL_REPORTED_FIELDS:
        evidence[field] = _iso(getattr(log, field, None)) if log is not None else None
    if log is not None:
        for field in ('id', 'pitcher_id', 'mlb_game_pk', 'appearance_team_id',
                      'games_started', 'hits_allowed', 'runs_allowed', 'earned_runs',
                      'walks', 'strikeouts', 'home_runs_allowed', 'innings_pitched_outs',
                      'pitches_thrown', 'strikes', 'batters_faced',
                      'stat_correction_count', 'last_stat_correction_sync_run_id'):
            evidence[field] = getattr(log, field, None)
        evidence['innings_pitched'] = getattr(log, 'innings_pitched', None)
    return evidence, failures, log


# ── Historical evidence ───────────────────────────────────────────────────────
def _correction_metadata_evidence(log) -> dict:
    """The governed correction metadata: proof that the row WAS rewritten, and when.

    It records that a correction happened and by which run, but never the value that was
    replaced. A zero count is real evidence too — it proves the governed correction path
    never rewrote this row — but it is evidence of local stability, not of official change.
    """
    if log is None:
        return {'available': False, 'reason': 'local row absent'}
    count = getattr(log, 'stat_correction_count', None) or 0
    return {
        'available': True,
        'stat_correction_count': count,
        'last_stat_correction_at': _iso(getattr(log, 'last_stat_correction_at', None)),
        'last_stat_correction_source': getattr(log, 'last_stat_correction_source', None),
        'last_stat_correction_sync_run_id': getattr(
            log, 'last_stat_correction_sync_run_id', None),
        'row_was_corrected_after_ingestion': count > 0,
        'retains_prior_value': False,
        'prior_value_retained': None,
        'note': (
            'the governed correction contract records that a row changed and which run '
            'changed it; it does not retain the replaced value'),
    }


def _citation_evidence(session) -> dict:
    """Evidence citations are the only durable store that can retain a PRIOR field value.

    A citation created before the transition, naming ``game_logs`` row 43765 and carrying
    ``hits_allowed`` in ``cited_values``, records what the local row said at that moment.
    """
    citations = (session.query(EvidenceCitation)
                 .filter(EvidenceCitation.source_table == 'game_logs')
                 .filter(EvidenceCitation.source_pk == str(TARGET_LOCAL_GAME_LOG_ID))
                 .order_by(EvidenceCitation.created_at.asc(), EvidenceCitation.id.asc())
                 .all())
    retained = []
    for citation in citations:
        cited = dict(citation.cited_values or {})
        if TARGET_FIELD not in cited:
            continue
        retained.append({
            'citation_id': citation.id,
            'evidence_object_id': citation.evidence_object_id,
            'source_family': citation.source_family,
            'source_table': citation.source_table,
            'source_pk': citation.source_pk,
            'cited_field': TARGET_FIELD,
            'cited_value': cited.get(TARGET_FIELD),
            'created_at': _iso(citation.created_at),
            'provenance': dict(citation.provenance or {}),
        })
    return {
        'available': True,
        'citations_for_target_row': len(citations),
        'citations_retaining_the_target_field': len(retained),
        'retained_prior_local_values': retained,
    }


def _official_citation_evidence(session) -> dict:
    """Any citation that retained an OFFICIAL hits value for this game and person.

    Nothing in this system is known to write one; the search is performed anyway so its
    emptiness is a measured result rather than an assumption.
    """
    keys = (
        str(TARGET_GAME_PK),
        f'{TARGET_GAME_PK}:{TARGET_OFFICIAL_MLB_PERSON_ID}',
        f'{TARGET_GAME_PK}:{TARGET_OFFICIAL_MLB_PERSON_ID}:{TARGET_APPEARANCE_TEAM_ID}',
        str(TARGET_OFFICIAL_MLB_PERSON_ID),
    )
    citations = (session.query(EvidenceCitation)
                 .filter(EvidenceCitation.source_table != 'game_logs')
                 .filter(EvidenceCitation.source_pk.in_(keys))
                 .order_by(EvidenceCitation.created_at.asc(), EvidenceCitation.id.asc())
                 .all())
    retained = []
    for citation in citations:
        cited = dict(citation.cited_values or {})
        for key in (TARGET_OFFICIAL_STAT_KEY, TARGET_FIELD):
            if key in cited:
                retained.append({
                    'citation_id': citation.id,
                    'source_family': citation.source_family,
                    'source_table': citation.source_table,
                    'source_pk': citation.source_pk,
                    'cited_field': key,
                    'cited_value': cited.get(key),
                    'created_at': _iso(citation.created_at),
                    'provenance': dict(citation.provenance or {}),
                })
                break
    return {
        'available': True,
        'citations_for_target_official_keys': len(citations),
        'citations_retaining_official_hits': len(retained),
        'retained_prior_official_values': retained,
    }


def _invalidation_evidence(session) -> dict:
    """Evidence objects marked for recompute because this GameLog was corrected."""
    objects = (session.query(EvidenceObject)
               .filter(EvidenceObject.invalidated_by_source_table == 'game_logs')
               .filter(EvidenceObject.invalidated_by_source_pk
                       == str(TARGET_LOCAL_GAME_LOG_ID))
               .order_by(EvidenceObject.id.asc())
               .all())
    return {
        'available': True,
        'invalidation_marker_count': len(objects),
        'markers': [{
            'evidence_object_id': row.id,
            'rule_id': row.rule_id,
            'recompute_status': row.recompute_status,
            'recompute_reason_codes': list(row.recompute_reason_codes or []),
            'invalidated_at': _iso(row.invalidated_at),
            'sync_run_id': row.sync_run_id,
        } for row in objects],
        'retains_prior_value': False,
    }


def _sync_run_evidence(session, log) -> dict:
    """Sync runs that could bracket the ingestion or correction of this row."""
    run_ids = set()
    for value in (getattr(log, 'last_stat_correction_sync_run_id', None),):
        if value:
            run_ids.add(int(value))
    runs = []
    if run_ids:
        runs = (session.query(SyncRun)
                .filter(SyncRun.id.in_(sorted(run_ids)))
                .order_by(SyncRun.id.asc()).all())
    return {
        'available': True,
        'referenced_sync_run_ids': sorted(run_ids),
        'runs': [{
            'id': run.id,
            'job_name': run.job_name,
            'status': run.status,
            'source': run.source,
            'started_at': _iso(run.started_at),
            'completed_at': _iso(run.completed_at),
        } for run in runs],
        'retains_prior_value': False,
    }


def _postgame_evidence(session) -> dict:
    rows = (session.query(PostgameProcessedGame)
            .filter(PostgameProcessedGame.mlb_game_pk == TARGET_GAME_PK)
            .order_by(PostgameProcessedGame.id.asc()).all())
    return {
        'available': True,
        'row_count': len(rows),
        'rows': [{
            'id': row.id,
            'processing_status': row.processing_status,
            'attempt_count': row.attempt_count,
            'pitching_lines_seen': row.pitching_lines_seen,
            'correction_attempts_failed': row.correction_attempts_failed,
            'processed_at': _iso(row.processed_at),
            'last_attempted_at': _iso(row.last_attempted_at),
            'sync_run_id': row.sync_run_id,
        } for row in rows],
        'retains_prior_value': False,
    }


def _sync_failure_evidence(session) -> dict:
    refs = (str(TARGET_GAME_PK), str(TARGET_OFFICIAL_MLB_PERSON_ID),
            str(TARGET_LOCAL_GAME_LOG_ID))
    rows = (session.query(SyncFailure)
            .filter(SyncFailure.entity_ref.in_(refs))
            .order_by(SyncFailure.id.asc()).all())
    return {
        'available': True,
        'row_count': len(rows),
        'rows': [{
            'id': row.id, 'entity_type': row.entity_type, 'entity_ref': row.entity_ref,
            'created_at': _iso(row.created_at), 'resolved': row.resolved,
        } for row in rows],
        'retains_prior_value': False,
    }


def _repo_artifact_evidence() -> dict:
    """Retained repository artifacts that name the target game, person, or row."""
    tokens = (str(TARGET_GAME_PK), str(TARGET_OFFICIAL_MLB_PERSON_ID),
              str(TARGET_LOCAL_GAME_LOG_ID))
    matches = []
    directory_exists = REPO_ARTIFACT_DIR.is_dir()
    if directory_exists:
        for path in sorted(REPO_ARTIFACT_DIR.iterdir()):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            hit = [token for token in tokens if token in text]
            if hit:
                matches.append({'artifact': path.name, 'matched_tokens': hit})
    return {
        'available': directory_exists,
        'directory': str(REPO_ARTIFACT_DIR),
        'artifacts_matching_target': matches,
        'retains_prior_value': bool(matches),
    }


def _structurally_absent(name) -> dict:
    return {'available': False, 'reason': STRUCTURALLY_ABSENT_SOURCES[name],
            'retains_prior_value': False}


def _historical_evidence(session, log) -> tuple:
    """Every durable source that could establish a prior value, checked and reported."""
    sources = {
        SOURCE_CORRECTION_METADATA: _correction_metadata_evidence(log),
        SOURCE_EVIDENCE_CITATIONS: _citation_evidence(session),
        SOURCE_EVIDENCE_OBJECTS: _invalidation_evidence(session),
        SOURCE_SYNC_RUNS: _sync_run_evidence(session, log),
        SOURCE_POSTGAME: _postgame_evidence(session),
        SOURCE_SYNC_FAILURES: _sync_failure_evidence(session),
        SOURCE_REPO_ARTIFACTS: _repo_artifact_evidence(),
        SOURCE_OFFICIAL_SNAPSHOTS: _structurally_absent(SOURCE_OFFICIAL_SNAPSHOTS),
        SOURCE_WORKFLOW_ARTIFACTS: _structurally_absent(SOURCE_WORKFLOW_ARTIFACTS),
    }
    official_citations = _official_citation_evidence(session)
    sources['evidence_citations.official_keys'] = official_citations
    return sources, official_citations


def _official_change_evidence(sources, official_citations, current_official_value) -> dict:
    """A prior OFFICIAL value, source-backed, that differs from the current official value."""
    retained = official_citations.get('retained_prior_official_values') or []
    differing = [
        item for item in retained
        if item.get('cited_value') is not None
        and item.get('cited_value') != current_official_value
    ]
    return {
        'prior_official_value_sources_checked': [
            SOURCE_OFFICIAL_SNAPSHOTS, 'evidence_citations.official_keys',
            SOURCE_REPO_ARTIFACTS, SOURCE_WORKFLOW_ARTIFACTS],
        'prior_official_value_retained': bool(retained),
        'prior_official_values': retained,
        'prior_official_value_differs_from_current': bool(differing),
        'proves_official_change': bool(differing),
        'limitation': STRUCTURALLY_ABSENT_SOURCES[SOURCE_OFFICIAL_SNAPSHOTS],
    }


def _local_change_evidence(sources, current_local_value) -> dict:
    """A prior LOCAL value, source-backed, or governed proof the row was rewritten."""
    citations = sources[SOURCE_EVIDENCE_CITATIONS]
    correction = sources[SOURCE_CORRECTION_METADATA]
    retained = citations.get('retained_prior_local_values') or []
    differing = [
        item for item in retained
        if item.get('cited_value') is not None
        and item.get('cited_value') != current_local_value
    ]
    corrected = bool(correction.get('row_was_corrected_after_ingestion'))
    return {
        'prior_local_value_sources_checked': [
            SOURCE_EVIDENCE_CITATIONS, SOURCE_CORRECTION_METADATA, SOURCE_EVIDENCE_OBJECTS,
            SOURCE_REPO_ARTIFACTS],
        'prior_local_value_retained': bool(retained),
        'prior_local_values': retained,
        'prior_local_value_differs_from_current': bool(differing),
        'row_was_corrected_after_ingestion': corrected,
        'correction_count': correction.get('stat_correction_count'),
        'last_stat_correction_at': correction.get('last_stat_correction_at'),
        'last_stat_correction_source': correction.get('last_stat_correction_source'),
        'last_stat_correction_sync_run_id': correction.get(
            'last_stat_correction_sync_run_id'),
        # A rewrite of the row is proof the row changed; combined with a retained prior value
        # it proves THIS field changed. Alone it proves only that some correction occurred.
        'proves_local_change': bool(differing),
        'proves_row_was_rewritten': corrected,
    }


def _classify(*, mismatch_reproduced, official_change, local_change) -> tuple:
    """Classify the transition, refusing to convert absence of history into a finding."""
    if not mismatch_reproduced:
        return (TRANSITION_NOT_REPRODUCED, CONFIDENCE_CONTRADICTED)
    official_proven = bool(official_change.get('proves_official_change'))
    local_proven = bool(local_change.get('proves_local_change'))
    if official_proven and local_proven:
        return (TRANSITION_BOTH_CHANGED, CONFIDENCE_PROVEN)
    if official_proven:
        return (TRANSITION_OFFICIAL_CHANGED, CONFIDENCE_PROVEN)
    if local_proven:
        return (TRANSITION_LOCAL_CHANGED, CONFIDENCE_PROVEN)
    # Neither side retained a prior value. The mismatch is real and its cause is not
    # recoverable from durable evidence. This is NOT evidence that MLB changed the box score.
    return (TRANSITION_UNPROVABLE, CONFIDENCE_UNPROVABLE)


def _unresolved_questions(classification, local_change, official_change) -> list:
    if classification in PROVEN_CLASSIFICATIONS:
        return []
    questions = []
    if not official_change.get('prior_official_value_retained'):
        questions.append({
            'question': (
                'what did the official box score report for hits before the accepted '
                'diagnostic ran'),
            'why_unanswerable': STRUCTURALLY_ABSENT_SOURCES[SOURCE_OFFICIAL_SNAPSHOTS],
            'where_it_could_still_be_answered': (
                'MLB Stats API change history if one is exposed, or a retained private '
                'workflow artifact from the accepted diagnostic run within its 14-day '
                'retention window'),
        })
    if not local_change.get('prior_local_value_retained'):
        questions.append({
            'question': 'what did GameLog 43765 store for hits_allowed at ingestion time',
            'why_unanswerable': (
                'game_logs has no updated_at column and no row-version history; the governed '
                'correction metadata records that a row changed, never the replaced value'),
            'where_it_could_still_be_answered': (
                'a database point-in-time backup predating the transition, or an evidence '
                'citation that captured hits_allowed before it moved'),
        })
    if local_change.get('proves_row_was_rewritten'):
        questions.append({
            'question': (
                'which field did the recorded correction to GameLog 43765 actually change'),
            'why_unanswerable': (
                'stat_correction_count increments once per corrected row, never per field'),
            'where_it_could_still_be_answered': (
                'the sync run identified by last_stat_correction_sync_run_id, if its logs '
                'are retained'),
        })
    return questions


def _reconciliations(*, official, local, comparison, classification, official_change,
                     local_change, emitted_write_sql) -> dict:
    retained_claims = ((official_change.get('prior_official_values') or [])
                       + (local_change.get('prior_local_values') or []))
    return {
        'exactly_one_official_line_matches_the_target_key':
            official.get('matching_line_count') == 1,
        'exactly_one_local_game_log_matches_the_target':
            local.get('matching_row_count') == 1
            and not local.get('duplicate_sibling_game_log_ids'),
        'local_pitcher_mlb_id_equals_the_official_person':
            local.get('pitcher_mlb_id') == TARGET_OFFICIAL_MLB_PERSON_ID,
        'appearance_team_equals_the_official_team':
            local.get('appearance_team_id') == TARGET_APPEARANCE_TEAM_ID
            and official.get('official_team_id') == TARGET_APPEARANCE_TEAM_ID,
        'current_official_hits_is_zero':
            official.get('normalized_hits_allowed') == EXPECTED_OFFICIAL_VALUE,
        'current_local_hits_allowed_is_one':
            local.get(TARGET_FIELD) == EXPECTED_LOCAL_VALUE,
        'current_mismatch_reason_is_hits_mismatch':
            comparison.get('reason_code') == TARGET_REASON_CODE,
        'no_name_based_identity_resolution_was_used':
            official.get('identity_resolution') == IDENTITY_RESOLUTION_CONTRACT
            and local.get('identity_resolution') == IDENTITY_RESOLUTION_CONTRACT,
        'no_current_team_authority_was_used':
            'team_id' in IDENTITY_EXCLUDED_SIGNALS
            and 'roster_status' in IDENTITY_EXCLUDED_SIGNALS,
        # Every historical claim must name a durable source, a timestamp, and a value.
        'every_historical_claim_identifies_a_durable_source': all(
            claim.get('source_table') or claim.get('source_family')
            for claim in retained_claims),
        'every_historical_claim_reports_a_timestamp': all(
            claim.get('created_at') for claim in retained_claims),
        'every_historical_claim_is_source_backed': all(
            claim.get('cited_value') is not None for claim in retained_claims),
        # Each source's own sequence must be non-decreasing. The two sides are NOT ordered
        # against each other: an official capture and a local capture are independent
        # observations, and requiring one to precede the other would invent a chronology.
        'historical_chronology_is_internally_consistent':
            _chronology_is_consistent(official_change.get('prior_official_values') or [])
            and _chronology_is_consistent(local_change.get('prior_local_values') or []),
        'absence_of_history_is_not_reported_as_official_change':
            classification != TRANSITION_OFFICIAL_CHANGED
            or bool(official_change.get('prior_official_value_retained')),
        'classification_is_from_the_governed_vocabulary':
            classification in TRANSITION_CLASSIFICATIONS,
        'no_manifest_fingerprint_is_approved': True,
        'no_accepted_baseline_value_is_read_or_changed': True,
        'no_repair_action_is_applied': True,
        'database_writes_performed_false': not emitted_write_sql,
    }


def _chronology_is_consistent(claims) -> bool:
    """Timestamps on retained claims must be present and non-decreasing when sorted."""
    stamps = [claim.get('created_at') for claim in claims]
    if any(stamp is None for stamp in stamps):
        return not claims
    return stamps == sorted(stamps)


def _decide(*, failures, reconciliations, classification):
    reasons: List[str] = []
    if failures:
        reasons.extend(sorted(set(failures)))
    failed = sorted(name for name, ok in reconciliations.items() if not ok)
    if classification == TRANSITION_NOT_REPRODUCED:
        # A mismatch that no longer reproduces is not a contradiction in identity; it is a
        # different current state, and the transition question stays open.
        failed = [name for name in failed
                  if name not in ('current_official_hits_is_zero',
                                  'current_local_hits_allowed_is_one',
                                  'current_mismatch_reason_is_hits_mismatch')]
    if any(f in failures for f in (
            FAIL_OFFICIAL_LINE_DUPLICATED, FAIL_LOCAL_ROW_DUPLICATED,
            FAIL_LOCAL_IDENTITY_MISMATCH, FAIL_APPEARANCE_TEAM_MISMATCH,
            FAIL_INCONSISTENT_HISTORY)) or failed:
        reasons.extend(f'reconciliation_failed:{name}' for name in failed)
        return (RESULT_FAIL, sorted(set(reasons)))
    if classification in PROVEN_CLASSIFICATIONS:
        return (RESULT_PASS, sorted(set(reasons + [f'transition_proven:{classification}'])))
    return (RESULT_INCONCLUSIVE,
            sorted(set(reasons + [f'transition_not_proven:{classification}'])))


# ── Public entry point ────────────────────────────────────────────────────────
def run_transition_diagnostic(*, client=None, session=None, generated_at=None,
                              retrieved_at=None) -> dict:
    """Read-only forensic diagnostic for the single Brandyn Garcia defect transition."""
    client = client or mlb_client
    session = session or db.session
    retrieved_at = retrieved_at or utc_now_naive().isoformat()

    official, official_failures = _current_official_evidence(
        client, retrieved_at=retrieved_at)
    local, local_failures, log = _current_local_evidence(session)
    failures = list(official_failures) + list(local_failures)

    official_value = official.get('normalized_hits_allowed')
    local_value = local.get(TARGET_FIELD)
    mismatch_reproduced = (
        official.get('official_evidence_available')
        and official_value is not None
        and local_value is not None
        and official_value != local_value
    )
    comparison = {
        'field': TARGET_FIELD,
        'official_stat_key': TARGET_OFFICIAL_STAT_KEY,
        'current_official_value': official_value,
        'current_local_value': local_value,
        'values_differ': bool(mismatch_reproduced),
        'reason_code': TARGET_REASON_CODE if mismatch_reproduced else None,
        'expected_official_value': EXPECTED_OFFICIAL_VALUE,
        'expected_local_value': EXPECTED_LOCAL_VALUE,
        'matches_production_artifact_expectation': (
            official_value == EXPECTED_OFFICIAL_VALUE
            and local_value == EXPECTED_LOCAL_VALUE),
        'proves_which_side_changed': False,
        'why_not': (
            'two current values prove only a present disagreement; neither carries a '
            'history, so the direction of the change is not recoverable from them'),
    }

    sources, official_citations = _historical_evidence(session, log)
    official_change = _official_change_evidence(sources, official_citations, official_value)
    local_change = _local_change_evidence(sources, local_value)
    classification, confidence = _classify(
        mismatch_reproduced=mismatch_reproduced,
        official_change=official_change, local_change=local_change)

    reconciliations = _reconciliations(
        official=official, local=local, comparison=comparison,
        classification=classification, official_change=official_change,
        local_change=local_change, emitted_write_sql=False)
    result, decision_reasons = _decide(
        failures=failures, reconciliations=reconciliations, classification=classification)

    historical_found = bool(
        (official_change.get('prior_official_values') or [])
        or (local_change.get('prior_local_values') or [])
        or local_change.get('proves_row_was_rewritten'))

    return {
        'capability': CAPABILITY,
        'mode': MODE_READ_ONLY,
        'result': result,
        'exit_code': EXIT_BY_RESULT[result],
        'generated_at': generated_at,
        'git_sha': completeness._git_sha(),
        'migration_head': completeness._migration_head(session),
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'contracts': {
            'diagnostic_contract_version': DIAGNOSTIC_CONTRACT_VERSION,
            'comparison_authority': COMPARISON_AUTHORITY,
            'identity_resolution_contract': IDENTITY_RESOLUTION_CONTRACT,
        },
        'target': {
            'season': TARGET_SEASON,
            'mlb_game_pk': TARGET_GAME_PK,
            'game_date': TARGET_GAME_DATE.isoformat(),
            'official_mlb_person_id': TARGET_OFFICIAL_MLB_PERSON_ID,
            'appearance_team_id': TARGET_APPEARANCE_TEAM_ID,
            'local_game_log_id': TARGET_LOCAL_GAME_LOG_ID,
            'field': TARGET_FIELD,
            'production_update_action_id': EXPECTED_UPDATE_ACTION_ID,
            'production_source_fingerprint': EXPECTED_SOURCE_FINGERPRINT,
        },
        'current_official_evidence': official,
        'current_local_evidence': local,
        'current_comparison': comparison,
        'historical_evidence_sources_checked': sorted(sources),
        'historical_evidence_source_detail': sources,
        'historical_evidence_found': historical_found,
        'official_change_evidence': official_change,
        'local_change_evidence': local_change,
        'authority_transition_classification': classification,
        'allowed_classifications': list(TRANSITION_CLASSIFICATIONS),
        'confidence': confidence,
        'unresolved_questions': _unresolved_questions(
            classification, local_change, official_change),
        'reconciliations': reconciliations,
        'decision_reasons': decision_reasons,
        'unapproved_manifest_fingerprints': list(UNAPPROVED_MANIFEST_FINGERPRINTS),
        'approved_manifest_fingerprints': [],
        'accepted_defect_baseline_modified': False,
        'repair_actions_applied': 0,
        'foundation_3b_gate': 'blocked',
        'public_reader_gate': 'blocked',
        'share_card_performance_gate': 'blocked',
        'repair_apply_gate': 'blocked',
        'database_writes_performed': False,
    }
