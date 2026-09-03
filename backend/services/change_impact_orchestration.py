"""CU-03 deterministic bridge from CU-02 detection to reviewed CU-01 writes.

The bridge is non-authoritative and non-scheduled. It stops after canonical
reconciliation and mutation-scoped affected-entity resolution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from models.game_observation_state import GameObservationState
from services import game_change_detection as detection
from services import game_driven_ingestion as cu01
from services import game_finality


NO_ACTION = 'no_action'
DEFER_LIVE_CANONICAL = 'defer_live_canonical'
INGEST_FINAL_GAME = 'ingest_final_game'
INSPECT_POST_FINAL_CORRECTION = 'inspect_post_final_correction'
REJECT_OBSERVATION = 'reject_observation'
SOURCE_FAILURE = 'source_failure'

STATUS_NO_ACTION = 'no_action'
STATUS_DEFERRED = 'deferred'
STATUS_AUTHORIZATION_REQUIRED = 'authorization_required'
STATUS_RECONCILED = 'reconciled'
STATUS_CANONICAL_FAILED = 'canonical_failed'

_FINALITY_STATES = {
    game_finality.FINAL_PENDING_DATA,
    game_finality.FINAL_AND_USABLE,
}
_LIVE_BULLPEN_PATHS = {
    'linescore.pitcher_id',
    'play.current_pitcher_id',
    'play.pitch_event_count',
    'play.all_play_count',
    'play.last_event_identity',
}


@dataclass(frozen=True)
class ChangeImpactResult:
    game_pk: int | None
    detection_classification: str
    decision: str
    orchestration_status: str
    reason_code: str
    canonical_action_attempted: bool
    canonical_ingestion_mode: str | None
    cu01_invocations: int
    finality_state: str | None
    game_log_inserted: int = 0
    game_log_updated: int = 0
    game_log_unchanged: int = 0
    pitch_inserted: int = 0
    pitch_updated: int = 0
    pitch_unchanged: int = 0
    pitch_superseded: int = 0
    canonical_mutation_performed: bool = False
    affected_pitcher_mlb_ids: tuple = ()
    affected_pitcher_ids: tuple = ()
    affected_team_ids: tuple = ()
    optional_pbp_status: str = 'not_requested'
    source_failure_state: str | None = None
    publication_affected: bool = False
    downstream_recomputation_triggered: bool = False

    def to_dict(self):
        value = asdict(self)
        for field in (
            'affected_pitcher_mlb_ids', 'affected_pitcher_ids',
            'affected_team_ids',
        ):
            value[field] = list(value[field])
        return value


def decide_game_change(change) -> tuple[str, str, str]:
    """Return (decision, orchestration_status, reason_code) without side effects."""
    classification = _get(change, 'classification')
    reason = _get(change, 'reason') or ''
    finality = _get(change, 'finality_state')
    differences = _get(change, 'differences') or {}

    if classification == detection.UNCHANGED:
        return NO_ACTION, STATUS_NO_ACTION, 'observation_unchanged'
    if classification in {
        detection.STALE_OBSERVATION, detection.AMBIGUOUS_OBSERVATION,
    }:
        suffix = 'weaker_authority' if 'weaker' in reason else classification
        return REJECT_OBSERVATION, STATUS_NO_ACTION, suffix
    if classification == detection.SOURCE_FAILURE:
        return SOURCE_FAILURE, STATUS_NO_ACTION, 'detection_source_failure'
    if _get(change, 'accepted') is False:
        return REJECT_OBSERVATION, STATUS_NO_ACTION, 'unaccepted_observation'
    if classification == detection.NEW_GAME:
        return NO_ACTION, STATUS_NO_ACTION, 'first_observation_only'
    if classification == detection.FINALIZED and finality in _FINALITY_STATES:
        return INGEST_FINAL_GAME, STATUS_AUTHORIZATION_REQUIRED, 'finality_transition'
    if classification == detection.CORRECTED and finality in _FINALITY_STATES:
        return (
            INSPECT_POST_FINAL_CORRECTION,
            STATUS_AUTHORIZATION_REQUIRED,
            'newer_post_final_observation',
        )
    if classification == detection.CHANGED:
        paths = set(differences)
        if paths & _LIVE_BULLPEN_PATHS:
            return (
                DEFER_LIVE_CANONICAL, STATUS_DEFERRED,
                'cu01_final_game_only_live_bullpen_change',
            )
        return NO_ACTION, STATUS_NO_ACTION, 'no_final_canonical_action'
    return REJECT_OBSERVATION, STATUS_NO_ACTION, 'unsupported_detection_classification'


def orchestrate_game_change(
    change,
    *,
    allow_canonical_write=False,
    expected_plan_fingerprint=None,
    canonical_ingestor=None,
    canonical_completion_callback=None,
    source_client=None,
):
    """Apply the CU-03 decision and optionally invoke one reviewed CU-01 write."""
    decision, status, reason = decide_game_change(change)
    base = {
        'game_pk': _get(change, 'game_pk'),
        'detection_classification': _get(change, 'classification') or 'unknown',
        'decision': decision,
        'orchestration_status': status,
        'reason_code': reason,
        'canonical_action_attempted': False,
        'canonical_ingestion_mode': None,
        'cu01_invocations': 0,
        'finality_state': _get(change, 'finality_state'),
    }
    if decision not in {INGEST_FINAL_GAME, INSPECT_POST_FINAL_CORRECTION}:
        return ChangeImpactResult(**base)
    if not allow_canonical_write:
        return ChangeImpactResult(**base)
    if not expected_plan_fingerprint:
        base['reason_code'] = 'reviewed_plan_fingerprint_required'
        return ChangeImpactResult(**base)

    ingestor = canonical_ingestor or _run_reviewed_cu01_write
    ingestor_kwargs = {
        'expected_plan_fingerprint': expected_plan_fingerprint,
    }
    if canonical_completion_callback is not None:
        ingestor_kwargs['canonical_completion_callback'] = (
            canonical_completion_callback
        )
    if canonical_ingestor is None and source_client is not None:
        ingestor_kwargs['source_client'] = source_client
    report = ingestor(change, **ingestor_kwargs)
    return _from_cu01_report(base, report)


def derive_current_plan_fingerprint(change, *, source_client=None):
    """Build the exact current CU-01 plan identity for an unattended final.

    The write path still recomputes and compares this fingerprint before its
    first mutation.  This removes the manual copy/paste authorization step for
    an explicitly activated continuous-production cycle without weakening the
    plan mismatch guard itself.
    """
    game_pk = _get(change, 'game_pk')
    state = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one_or_none()
    official_date = (
        ((state.observation or {}).get('identity') or {}).get('official_date')
        if state is not None else None
    )
    if not official_date:
        raise ValueError('accepted final observation is missing official_date')
    report = cu01.run_game_driven_ingestion(
        date.fromisoformat(official_date),
        mode=cu01.MODE_SHADOW,
        only_game_pks=[game_pk],
        source_client=source_client,
    )
    fingerprint = report.get('complete_reconciliation_fingerprint')
    if report.get('status') != 'complete' or not fingerprint:
        raise RuntimeError(
            f"current reconciliation plan unavailable: {report.get('status')}"
        )
    return fingerprint


def detect_and_orchestrate_game(
    game_pk,
    *,
    payload=None,
    client=None,
    allow_canonical_write=False,
    expected_plan_fingerprint=None,
    canonical_ingestor=None,
):
    """Standalone one-game proof seam: CU-02 observation then CU-03 decision."""
    change = detection.observe_game_change(
        game_pk, payload=payload, client=client,
    )
    return {
        'detection': change.to_dict(),
        'orchestration': orchestrate_game_change(
            change,
            allow_canonical_write=allow_canonical_write,
            expected_plan_fingerprint=expected_plan_fingerprint,
            canonical_ingestor=canonical_ingestor,
        ).to_dict(),
    }


def _run_reviewed_cu01_write(
    change,
    *,
    expected_plan_fingerprint,
    canonical_completion_callback=None,
    source_client=None,
):
    game_pk = _get(change, 'game_pk')
    state = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one_or_none()
    official_date = (
        ((state.observation or {}).get('identity') or {}).get('official_date')
        if state is not None else None
    )
    if not official_date:
        return {'status': 'invalid_observation_state', 'failure_classes': {
            'missing_official_date': 1,
        }}
    return cu01.run_game_driven_ingestion(
        date.fromisoformat(official_date),
        mode=cu01.MODE_WRITE,
        only_game_pks=[game_pk],
        expected_plan_fingerprint=expected_plan_fingerprint,
        completion_callback=canonical_completion_callback,
        source_client=source_client,
    )


def _from_cu01_report(base, report):
    values = dict(base)
    values.update({
        'canonical_action_attempted': True,
        'canonical_ingestion_mode': 'cu01_write_non_authoritative',
        'cu01_invocations': 1,
    })
    games = list(report.get('games') or ())
    target_games = [
        game for game in games
        if game.get('game_pk') == base.get('game_pk')
    ]
    canonical_game_completed = (
        int(report.get('games_failed') or 0) == 0
        and int(report.get('games_completed') or 0) == 1
        and len(target_games) == 1
        and target_games[0].get('status') in {
            'completed', 'completed_with_correction',
        }
    )
    if report.get('status') != 'complete' or not canonical_game_completed:
        values.update({
            'orchestration_status': STATUS_CANONICAL_FAILED,
            'reason_code': 'cu01_canonical_ingestion_failed',
            'source_failure_state': _failure_state(report),
        })
        return ChangeImpactResult(**values)

    pitch_counts = _pitch_counts(games)
    affected_local_ids = sorted({
        pitcher_id
        for game in games
        for pitcher_id in ((game.get('impact') or {}).get('affected_pitcher_ids') or ())
    })
    mutation_count = (
        int(report.get('rows_inserted') or 0)
        + int(report.get('rows_updated') or 0)
        + int(report.get('pitcher_identity_mutations') or 0)
        + pitch_counts['inserted'] + pitch_counts['updated'] + pitch_counts['superseded']
    )
    values.update({
        'orchestration_status': STATUS_RECONCILED,
        'reason_code': 'cu01_canonical_reconciliation_complete',
        'game_log_inserted': int(report.get('rows_inserted') or 0),
        'game_log_updated': int(report.get('rows_updated') or 0),
        'game_log_unchanged': int(report.get('rows_unchanged') or 0),
        'pitch_inserted': pitch_counts['inserted'],
        'pitch_updated': pitch_counts['updated'],
        'pitch_unchanged': pitch_counts['unchanged'],
        'pitch_superseded': pitch_counts['superseded'],
        'canonical_mutation_performed': mutation_count > 0,
        'affected_pitcher_mlb_ids': tuple(report.get('affected_pitcher_mlb_ids') or ()),
        'affected_pitcher_ids': tuple(affected_local_ids),
        'affected_team_ids': tuple(report.get('affected_team_ids') or ()),
        'optional_pbp_status': _optional_pbp_status(games),
    })
    return ChangeImpactResult(**values)


def _pitch_counts(games):
    totals = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'superseded': 0}
    for game in games:
        optional = (game.get('optional_source_domains') or {}).get(
            'final_play_by_play'
        ) or {}
        rows = optional.get('pitch_rows') or {}
        for field in totals:
            totals[field] += int(rows.get(field) or 0)
    return totals


def _optional_pbp_status(games):
    statuses = [
        ((game.get('optional_source_domains') or {}).get('final_play_by_play') or {}).get(
            'processing_status'
        )
        for game in games
    ]
    statuses = [value for value in statuses if value]
    return statuses[0] if len(set(statuses)) == 1 else ('mixed' if statuses else 'not_requested')


def _failure_state(report):
    failures = report.get('failure_classes') or {}
    if failures:
        return ','.join(sorted(failures))
    return str(report.get('status') or 'unknown_failure')


def _get(value, field):
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)
