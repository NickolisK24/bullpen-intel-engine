"""Durable, structured outcome of one Dashboard publication attempt (WP-1).

A candidate withheld by the Team State publication proof is rolled back with
its publication transaction: the candidate row, its id and its evidence all
disappear, and the owning ``sync_runs`` row keeps only the one-line reason. The
incident then has to be reconstructed from logs or a special diagnostic.

This module shapes the PROOF OF FAILURE, never the candidate. The outcome is
written to ``sync_runs.publication_outcome`` by the sync-completion path after
the publication transaction has been rolled back (or committed), in its own
commit, so it survives the rollback and can never carry partial publication
state: it is a JSON document on the control-plane row, not a snapshot.

Contract (``schema_version`` 1)::

    status               published | withheld | failed
    stop_reason          publication_gate | exception class name | None
    withheld_reason      the run's reason string (bounded) | None
    failed_authority     team_state_eligibility | team_state_proof |
                         slate_coverage | appearance_ledger | publication | None
    candidate_snapshot_id  the id the candidate was allocated, when known
    candidate_persisted  False when the candidate was rolled back
    published_snapshot_id  the snapshot this attempt published | None
    serving_snapshot_id  the published snapshot after the attempt settled
    affected_team_ids    teams whose evidence blocked publication
    affected_game_pks    games whose evidence blocked publication, when known
    teams                per-team eligibility reasons, coverage counts and
                         active-bullpen arm causes (Team State failures only)
    reference_dates      membership / availability dates the proof used
    gate_evidence        the gate's own verdict, compact (slate coverage
                         reason codes and counts, ledger deficits), with the
                         per-game ``games`` that blocked it
    run_failures         this run's unresolved dead letters by entity type,
                         with compact roster-conflict entries
    publication_critical_complete  the run's publication-critical verdict
    recovery_attempted   whether a bounded repair ran before this outcome
    recovery_result      None, or the repair's class, actions and result
    recorded_at          UTC timestamp of the record

No source payloads, credentials or URLs are stored: reasons are the codes the
gates already emit, and failure labels are passed through the diagnostic's
artifact-safe label.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Optional

from utils.time import utc_now_naive


SCHEMA_VERSION = 1

STATUS_PUBLISHED = 'published'
STATUS_WITHHELD = 'withheld'
STATUS_FAILED = 'failed'

AUTHORITY_TEAM_STATE_ELIGIBILITY = 'team_state_eligibility'
AUTHORITY_TEAM_STATE_PROOF = 'team_state_proof'
AUTHORITY_SLATE_COVERAGE = 'slate_coverage'
AUTHORITY_APPEARANCE_LEDGER = 'appearance_ledger'
AUTHORITY_PUBLICATION = 'publication'

STOP_REASON_PUBLICATION_GATE = 'publication_gate'

MAX_REASON_LENGTH = 2000


def _bounded(text) -> Optional[str]:
    if text is None:
        return None
    text = str(text)
    return text if len(text) <= MAX_REASON_LENGTH else text[:MAX_REASON_LENGTH] + '...'


def json_safe(value):
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [json_safe(item) for item in value]
        return sorted(items, key=repr) if isinstance(value, (set, frozenset)) else items
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def failed_authority_for_reason(reason) -> Optional[str]:
    text = str(reason or '')
    if text.startswith('snapshot_team_state_ineligible'):
        return AUTHORITY_TEAM_STATE_ELIGIBILITY
    if text.startswith('team_state_publication_proof') or text.startswith(
        'snapshot_team_state'
    ):
        return AUTHORITY_TEAM_STATE_PROOF
    if 'appearance_ledger' in text:
        return AUTHORITY_APPEARANCE_LEDGER
    if 'slate' in text or 'coverage' in text:
        return AUTHORITY_SLATE_COVERAGE
    return AUTHORITY_PUBLICATION if text else None


def _serving_snapshot_id():
    """The published Bullpen Dashboard snapshot, read after the attempt settled."""
    try:
        from models.dashboard_snapshot import DashboardSnapshot
        from services.dashboard_snapshot import SNAPSHOT_TYPE_BULLPEN_DASHBOARD

        row = (
            DashboardSnapshot.query
            .with_entities(DashboardSnapshot.id)
            .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD)
            .filter(DashboardSnapshot.is_published.is_(True))
            .order_by(DashboardSnapshot.id.desc())
            .first()
        )
        return row[0] if row else None
    except Exception:
        return None


RUN_FAILURE_EXAMPLE_LIMIT = 20
ROSTER_CONFLICT_ENTITY_TYPE = 'roster_status_snapshot_conflict'


def run_failures(sync_run_id):
    """This run's unresolved dead letters: counts by entity type, and examples.

    Roster conflicts carry the pitcher, the two teams and the date, never the
    raw payload. Read only; empty when the run has no id.
    """
    if sync_run_id is None:
        return None
    try:
        from models.sync_failure import SyncFailure

        rows = (
            SyncFailure.query
            .filter(SyncFailure.sync_run_id == sync_run_id)
            .filter(SyncFailure.resolved.is_(False))
            .order_by(SyncFailure.id.asc())
            .all()
        )
    except Exception:
        return None
    counts = {}
    roster_conflicts = []
    for row in rows:
        counts[row.entity_type] = counts.get(row.entity_type, 0) + 1
        if (
            row.entity_type == ROSTER_CONFLICT_ENTITY_TYPE
            and len(roster_conflicts) < RUN_FAILURE_EXAMPLE_LIMIT
        ):
            payload = row.payload if isinstance(row.payload, Mapping) else {}
            roster_conflicts.append({
                'mlb_id': payload.get('mlb_id') or row.entity_ref,
                'pitcher_id': payload.get('pitcher_id'),
                'snapshot_date': payload.get('snapshot_date'),
                'existing_team_id': payload.get('existing_team_id'),
                'incoming_team_id': payload.get('incoming_team_id'),
            })
    return {
        'unresolved_by_entity_type': dict(sorted(counts.items())),
        'roster_conflicts': roster_conflicts,
    }


def _slate_gate_evidence(snapshot):
    from services.dashboard_snapshot import _payload_slate_coverage
    from services.slate_coverage import slate_game_evidence

    coverage = _payload_slate_coverage(getattr(snapshot, 'payload', None)) or {}
    slate_date = coverage.get('slate_date') or getattr(snapshot, 'data_through', None)
    games = slate_game_evidence(slate_date)
    return {
        'gate': AUTHORITY_SLATE_COVERAGE,
        'slate_date': slate_date,
        'data_through': getattr(snapshot, 'data_through', None),
        'reason_codes': list(coverage.get('reason_codes') or []),
        'counts': {
            key: coverage.get(key) for key in (
                'games_scheduled', 'games_final', 'games_fully_ingested',
                'games_incomplete', 'games_failed', 'games_postponed',
                'games_cancelled', 'games_suspended', 'games_unresolved',
                'games_included',
            )
        },
        'marker_counts': coverage.get('marker_counts'),
        'games': games,
    }


def _ledger_gate_evidence(snapshot):
    from services.appearance_ledger import build_appearance_ledger

    end_date = getattr(snapshot, 'data_through', None)
    ledger = build_appearance_ledger(end_date=end_date) if end_date else {}
    games = []
    for key, blocker in (
        ('missing_games', 'final_game_without_appearance_rows'),
        ('count_deficits', 'appearance_rows_below_ingested_lines'),
        ('incomplete_markers', 'final_game_marker_incomplete'),
    ):
        for item in (ledger.get(key) or [])[:RUN_FAILURE_EXAMPLE_LIMIT]:
            games.append({
                'game_pk': item.get('game_pk'),
                'game_date': item.get('game_date'),
                'marker_status': item.get('marker_status'),
                'blocker': blocker,
            })
    return {
        'gate': AUTHORITY_APPEARANCE_LEDGER,
        'window_start': ledger.get('window_start'),
        'window_end': ledger.get('window_end'),
        'reason_codes': list(ledger.get('reasons') or []),
        'games': games,
    }


def gate_evidence(snapshot, failed_authority):
    """The withholding gate's evidence, compact and safe to persist. Never raises."""
    try:
        if failed_authority == AUTHORITY_SLATE_COVERAGE:
            return _slate_gate_evidence(snapshot)
        if failed_authority == AUTHORITY_APPEARANCE_LEDGER:
            return _ledger_gate_evidence(snapshot)
    except Exception as exc:  # noqa: BLE001 - evidence must never mask the outcome
        return {'gate': failed_authority, 'evidence_error': type(exc).__name__}
    return None


def _game_pks(evidence):
    return [
        game['game_pk'] for game in (evidence or {}).get('games') or ()
        if game.get('game_pk') is not None
    ]


def _base(status, **fields) -> dict:
    document = {
        'schema_version': SCHEMA_VERSION,
        'status': status,
        'stop_reason': None,
        'withheld_reason': None,
        'failed_authority': None,
        'candidate_snapshot_id': None,
        'candidate_persisted': None,
        'published_snapshot_id': None,
        'serving_snapshot_id': _serving_snapshot_id(),
        'affected_team_ids': [],
        'affected_game_pks': [],
        'teams': [],
        'reference_dates': None,
        'gate_evidence': None,
        'run_failures': None,
        'publication_critical_complete': None,
        'recovery_attempted': False,
        'recovery_result': None,
        'recorded_at': utc_now_naive(),
    }
    document.update(fields)
    return json_safe(document)


def outcome_published(snapshot) -> dict:
    snapshot_id = getattr(snapshot, 'id', None)
    return _base(
        STATUS_PUBLISHED,
        candidate_snapshot_id=snapshot_id,
        candidate_persisted=True,
        published_snapshot_id=snapshot_id,
    )


def outcome_withheld(
    snapshot, withheld_reason, *, sync_run_id=None, publication_critical_complete=None,
) -> dict:
    """A gate kept the candidate pending; the candidate row itself survives."""
    authority = failed_authority_for_reason(withheld_reason)
    evidence = gate_evidence(snapshot, authority)
    return _base(
        STATUS_WITHHELD,
        stop_reason=STOP_REASON_PUBLICATION_GATE,
        withheld_reason=_bounded(withheld_reason),
        failed_authority=authority,
        candidate_snapshot_id=getattr(snapshot, 'id', None),
        candidate_persisted=True,
        affected_game_pks=_game_pks(evidence),
        gate_evidence=evidence,
        run_failures=run_failures(sync_run_id),
        publication_critical_complete=publication_critical_complete,
    )


def outcome_failed(exc, *, sync_run_id=None, publication_critical_complete=None) -> dict:
    """The publication transaction raised and was rolled back.

    Structured evidence carried by the exception (a Team State proof failure)
    is kept; the candidate it describes is reported as not persisted.
    """
    carried = dict(getattr(exc, 'publication_evidence', None) or {})
    reason = str(exc)
    return _base(
        STATUS_FAILED,
        stop_reason=type(exc).__name__,
        withheld_reason=_bounded(reason),
        failed_authority=carried.pop('failed_authority', None)
        or failed_authority_for_reason(reason),
        candidate_snapshot_id=carried.pop('candidate_snapshot_id', None),
        candidate_persisted=False,
        affected_team_ids=carried.pop('affected_team_ids', []),
        affected_game_pks=carried.pop('affected_game_pks', []),
        teams=carried.pop('teams', []),
        reference_dates=carried.pop('reference_dates', None),
        run_failures=run_failures(sync_run_id),
        publication_critical_complete=publication_critical_complete,
    )
