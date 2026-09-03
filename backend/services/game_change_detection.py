"""Persisted, non-authoritative MLB game change detection (CU-02).

This module observes and routes game identifiers only. It does not invoke game
ingestion, write canonical baseball facts, compute read models, or publish.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from time import perf_counter

from models.game_observation_state import GameObservationState
from services import continuous_game_work
from services import game_appearance_extraction
from services import game_finality
from services.mlb_api import MlbApiFetchError, mlb_client
from utils.db import db
from utils.time import utc_now_naive


NEW_GAME = 'new_game'
UNCHANGED = 'unchanged'
CHANGED = 'changed'
FINALIZED = 'finalized'
CORRECTED = 'corrected'
STALE_OBSERVATION = 'stale_observation'
AMBIGUOUS_OBSERVATION = 'ambiguous_observation'
SOURCE_FAILURE = 'source_failure'

SOURCE_AUTHORITY = 'mlb_statsapi_live_feed_v1_1'
SOURCE_ENDPOINT = '/api/v1.1/game/{game_pk}/feed/live'
SOURCE_AUTHORITY_RANKS = {SOURCE_AUTHORITY: 100}
EQUAL_REVISION_FINAL_VERIFIED = 'equal_revision_final_boxscore_verified'
FINAL_EVIDENCE_REGRESSION = 'final_evidence_regression'


@dataclass(frozen=True)
class GameChangeResult:
    game_pk: int | None
    classification: str
    changed: bool
    previous_observation_identity: str | None
    current_observation_identity: str | None
    finality_state: str | None
    source_authority: str
    source_observed_at: str | None
    detected_at: str
    differences: dict
    reason: str
    accepted: bool
    downstream_work_triggered: bool = False
    canonical_mutation_performed: bool = False
    affected_pitchers: tuple = ()
    affected_teams: tuple = ()
    approximate_payload_bytes: int | None = None
    elapsed_ms: float | None = None

    def to_dict(self):
        value = asdict(self)
        value['affected_pitchers'] = list(self.affected_pitchers)
        value['affected_teams'] = list(self.affected_teams)
        return value


def observe_game_change(
    game_pk,
    *,
    payload=None,
    client=None,
    source_authority=SOURCE_AUTHORITY,
    commit=True,
    create_work_obligation=False,
):
    """Fetch or accept one live-feed payload and compare it to durable state."""
    started = perf_counter()
    detected_at = utc_now_naive()
    client = client or mlb_client
    try:
        if payload is None:
            payload = client.get_game_live_feed(game_pk)
        observation = canonicalize_game_observation(payload, expected_game_pk=game_pk)
    except (MlbApiFetchError, ValueError, TypeError) as exc:
        return _result(
            game_pk=_positive_int(game_pk), classification=SOURCE_FAILURE,
            changed=False, detected_at=detected_at, source_authority=source_authority,
            reason=f'{type(exc).__name__}: {exc}', accepted=False,
            elapsed_ms=_elapsed(started),
        )

    fingerprint = observation_fingerprint(observation)
    source_observed_at = parse_source_timestamp(
        ((payload or {}).get('metaData') or {}).get('timeStamp')
    )
    payload_bytes = len(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode())
    row = GameObservationState.query.filter_by(
        mlb_game_pk=observation['game_pk']
    ).one_or_none()

    if row is None:
        row = GameObservationState(
            mlb_game_pk=observation['game_pk'],
            observation_fingerprint=fingerprint,
            observation=observation,
            source_authority=source_authority,
            source_endpoint=SOURCE_ENDPOINT.format(game_pk=observation['game_pk']),
            source_observed_at=source_observed_at,
            finality_state=observation['finality']['state'],
            previous_observation_fingerprint=None,
            last_classification=NEW_GAME,
            last_change_summary={},
            accepted_at=detected_at,
        )
        db.session.add(row)
        result = _result(
            game_pk=observation['game_pk'], classification=NEW_GAME, changed=True,
            current=fingerprint, finality=observation['finality']['state'],
            source_authority=source_authority, source_observed_at=source_observed_at,
            detected_at=detected_at, reason='first_accepted_observation', accepted=True,
            payload_bytes=payload_bytes, elapsed_ms=_elapsed(started),
        )
        if create_work_obligation:
            continuous_game_work.ensure_obligation(
                result, row=row, commit=False,
            )
        _finish(commit)
        return result

    if fingerprint == row.observation_fingerprint:
        # Exact material replay is a true no-op: not even observation-state
        # timestamps are rewritten.
        return _result(
            game_pk=observation['game_pk'], classification=UNCHANGED, changed=False,
            previous=row.observation_fingerprint, current=fingerprint,
            finality=row.finality_state, source_authority=source_authority,
            source_observed_at=source_observed_at, detected_at=detected_at,
            reason='material_fingerprint_match', accepted=False,
            payload_bytes=payload_bytes, elapsed_ms=_elapsed(started),
        )

    ordering, reason = _compare_order(
        accepted_authority=row.source_authority,
        accepted_observed_at=row.source_observed_at,
        incoming_authority=source_authority,
        incoming_observed_at=source_observed_at,
    )

    if (
        ordering not in {'older', 'weaker'}
        and _is_final_evidence_regression(row.observation, observation)
    ):
        ordering = 'ambiguous'
        reason = FINAL_EVIDENCE_REGRESSION

    if (
        ordering == 'ambiguous'
        and reason == 'equal_revision_with_different_material_content'
        and _equal_revision_final_is_verified(
            previous=row.observation,
            current=observation,
            payload=payload,
        )
    ):
        ordering = 'newer'
        reason = EQUAL_REVISION_FINAL_VERIFIED
    if ordering != 'newer':
        classification = (
            STALE_OBSERVATION if ordering in {'older', 'weaker'}
            else AMBIGUOUS_OBSERVATION
        )
        return _result(
            game_pk=observation['game_pk'], classification=classification,
            changed=False, previous=row.observation_fingerprint, current=fingerprint,
            finality=row.finality_state, source_authority=source_authority,
            source_observed_at=source_observed_at, detected_at=detected_at,
            reason=reason, accepted=False, payload_bytes=payload_bytes,
            elapsed_ms=_elapsed(started),
        )

    differences = observation_diff(row.observation, observation)
    classification = _accepted_change_classification(
        row.finality_state, observation['finality']['state']
    )
    previous = row.observation_fingerprint
    row.previous_observation_fingerprint = previous
    row.observation_fingerprint = fingerprint
    row.observation = observation
    row.source_authority = source_authority
    row.source_endpoint = SOURCE_ENDPOINT.format(game_pk=observation['game_pk'])
    row.source_observed_at = source_observed_at
    row.finality_state = observation['finality']['state']
    row.last_classification = classification
    row.last_change_summary = differences
    row.accepted_at = detected_at
    result = _result(
        game_pk=observation['game_pk'], classification=classification, changed=True,
        previous=previous, current=fingerprint,
        finality=observation['finality']['state'], source_authority=source_authority,
        source_observed_at=source_observed_at, detected_at=detected_at,
        differences=differences, reason=reason, accepted=True,
        payload_bytes=payload_bytes, elapsed_ms=_elapsed(started),
    )
    if create_work_obligation:
        continuous_game_work.ensure_obligation(
            result, row=row, commit=False,
        )
    _finish(commit)
    return result


def detect_active_slate_changes(
    *, reference_date=None, correction_days=2, client=None, commit=True,
    max_games=None, only_game_pks=None,
):
    """Observe a bounded active slate with one schedule request plus one feed/game.

    Candidate policy: reference-date games plus recent finals inside the bounded
    correction window. Suspended/postponed games remain candidates on their
    represented schedule date. There is no loop, sleep, or scheduler hook.
    """
    client = client or mlb_client
    ref = reference_date or datetime.now(timezone.utc).date()
    if isinstance(ref, str):
        ref = date.fromisoformat(ref)
    start = ref - timedelta(days=max(0, int(correction_days)))
    started = perf_counter()
    try:
        games = client.get_schedule(start_date=start.isoformat(), end_date=ref.isoformat())
    except MlbApiFetchError as exc:
        failure = _result(
            game_pk=None, classification=SOURCE_FAILURE, changed=False,
            source_authority=SOURCE_AUTHORITY, detected_at=utc_now_naive(),
            reason=f'{type(exc).__name__}: {exc}', accepted=False,
            elapsed_ms=_elapsed(started),
        )
        return _cycle([], [failure], started, schedule_requests=1)

    candidates = _candidate_game_pks(games, ref, start)
    if only_game_pks is not None:
        allowed = {
            value for value in (_positive_int(item) for item in only_game_pks)
            if value is not None
        }
        candidates = [game_pk for game_pk in candidates if game_pk in allowed]
    if max_games is not None:
        candidates = _prioritize_bounded_candidates(games, candidates, ref)
        candidates = candidates[:max(0, int(max_games))]
    results = [
        observe_game_change(
            pk,
            client=client,
            commit=False,
            create_work_obligation=True,
        )
        for pk in candidates
    ]
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return _cycle(candidates, results, started, schedule_requests=1)


def canonicalize_game_observation(payload, *, expected_game_pk=None):
    if not isinstance(payload, dict):
        raise ValueError('live feed payload must be an object')
    game_pk = _positive_int(payload.get('gamePk'))
    if game_pk is None or (
        expected_game_pk is not None and game_pk != _positive_int(expected_game_pk)
    ):
        raise ValueError('live feed gamePk is missing or mismatched')

    game_data = payload.get('gameData') or {}
    status = game_data.get('status') or {}
    live = payload.get('liveData') or {}
    boxscore = live.get('boxscore')
    # Finality is evaluated with the embedded official pitching boxscore. This
    # makes final_pending_data -> final_and_usable a real, monotonic evidence
    # upgrade that can safely resolve an equal MLB metadata timestamp.
    decision = game_finality.classify_game_finality(
        {'gamePk': game_pk, 'status': status},
        boxscore=boxscore,
        require_boxscore=True,
    )
    linescore = live.get('linescore') or {}
    plays = (live.get('plays') or {})
    all_plays = plays.get('allPlays') or []
    current = plays.get('currentPlay') or (all_plays[-1] if all_plays else {}) or {}
    play_events = current.get('playEvents') or []
    last_event = play_events[-1] if play_events else {}
    last_play = all_plays[-1] if all_plays else {}
    teams = game_data.get('teams') or {}
    dt = game_data.get('datetime') or {}
    game = game_data.get('game') or {}
    probable = game_data.get('probablePitchers') or {}
    pitching_fingerprint = (
        _official_pitching_fingerprint(
            game_pk=game_pk,
            official_date=dt.get('officialDate') or dt.get('originalDate'),
            home_team_id=_nested_id(teams.get('home')),
            away_team_id=_nested_id(teams.get('away')),
            boxscore=boxscore,
        )
        if decision.state == game_finality.FINAL_AND_USABLE
        else None
    )

    return {
        'schema_version': 1,
        'game_pk': game_pk,
        'identity': {
            'official_date': dt.get('officialDate') or dt.get('originalDate'),
            'game_datetime': dt.get('dateTime'),
            'game_type': game.get('type'),
            'double_header': game.get('doubleHeader'),
            'game_number': _int_or_none(game.get('gameNumber')),
            'home_team_id': _nested_id(teams.get('home')),
            'away_team_id': _nested_id(teams.get('away')),
            'home_probable_pitcher_id': _nested_id(probable.get('home')),
            'away_probable_pitcher_id': _nested_id(probable.get('away')),
        },
        'status': {
            'abstract': status.get('abstractGameState'),
            'coded': status.get('codedGameState'),
            'detailed': status.get('detailedState'),
            'status_code': status.get('statusCode'),
            'reason': status.get('reason'),
        },
        'finality': {
            'state': decision.state,
            'reason': decision.reason,
            'status_state': decision.status_state,
            'final_status': decision.final_status,
        },
        'pitching_evidence': {
            'source_authority': game_appearance_extraction.SOURCE_AUTHORITY,
            'appearance_set_fingerprint': pitching_fingerprint,
        },
        'linescore': {
            'inning': _int_or_none(linescore.get('currentInning')),
            'inning_ordinal': linescore.get('currentInningOrdinal'),
            'inning_state': linescore.get('inningState'),
            'inning_half': linescore.get('inningHalf'),
            'is_top': linescore.get('isTopInning'),
            'scheduled_innings': _int_or_none(linescore.get('scheduledInnings')),
            'balls': _int_or_none(linescore.get('balls')),
            'strikes': _int_or_none(linescore.get('strikes')),
            'outs': _int_or_none(linescore.get('outs')),
            'away': _team_totals((linescore.get('teams') or {}).get('away')),
            'home': _team_totals((linescore.get('teams') or {}).get('home')),
            'pitcher_id': _nested_id((linescore.get('defense') or {}).get('pitcher')),
            'batter_id': _nested_id((linescore.get('offense') or {}).get('batter')),
        },
        'play': {
            'all_play_count': len(all_plays),
            'pitch_event_count': sum(
                1 for play in all_plays for event in (play.get('playEvents') or [])
                if event.get('isPitch') is True or event.get('type') == 'pitch'
            ),
            'current_at_bat_index': _int_or_none(current.get('atBatIndex')),
            'current_pitcher_id': _nested_id((current.get('matchup') or {}).get('pitcher')),
            'current_batter_id': _nested_id((current.get('matchup') or {}).get('batter')),
            'current_is_complete': (current.get('about') or {}).get('isComplete'),
            'current_event_type': (current.get('result') or {}).get('eventType'),
            'last_play_at_bat_index': _int_or_none(last_play.get('atBatIndex')),
            'last_play_event_type': (last_play.get('result') or {}).get('eventType'),
            'last_event_identity': (
                last_event.get('playId')
                or _event_fallback_identity(current, last_event)
            ),
            'last_event_type': last_event.get('type'),
            'last_event_code': (last_event.get('details') or {}).get('eventType'),
        },
    }


def observation_fingerprint(observation):
    encoded = json.dumps(observation, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def observation_diff(previous, current):
    before = _flatten(previous)
    after = _flatten(current)
    return {
        key: {'previous': before.get(key), 'current': after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def parse_source_timestamp(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), '%Y%m%d_%H%M%S')
    except (TypeError, ValueError):
        return None


def _compare_order(*, accepted_authority, accepted_observed_at,
                   incoming_authority, incoming_observed_at):
    accepted_rank = SOURCE_AUTHORITY_RANKS.get(accepted_authority, 0)
    incoming_rank = SOURCE_AUTHORITY_RANKS.get(incoming_authority, 0)
    if incoming_rank < accepted_rank:
        return 'weaker', 'weaker_source_authority'
    if incoming_rank > accepted_rank:
        # Stronger authority still needs upstream order evidence before it may
        # destructively replace a known accepted observation.
        return 'ambiguous', 'stronger_source_without_comparable_revision'
    if accepted_authority != incoming_authority:
        return 'ambiguous', 'incomparable_source_authority'
    if accepted_observed_at is None or incoming_observed_at is None:
        return 'ambiguous', 'missing_upstream_observation_order'
    if incoming_observed_at > accepted_observed_at:
        return 'newer', 'newer_upstream_observation'
    if incoming_observed_at < accepted_observed_at:
        return 'older', 'older_upstream_observation'
    return 'ambiguous', 'equal_revision_with_different_material_content'


def _equal_revision_final_is_verified(*, previous, current, payload):
    """Admit one equal-timestamp final correction only on stronger evidence.

    An MLB timestamp tie is never enough by itself. The accepted observation
    must still be waiting on usable final data, while the incoming observation
    must advance to final_and_usable using the embedded official pitching
    boxscore. Once that terminal state is accepted, another same-timestamp
    variant cannot supersede it, preventing oscillation between replicas.
    """
    previous_finality = (previous or {}).get('finality') or {}
    current_finality = (current or {}).get('finality') or {}

    if previous_finality.get('state') != game_finality.FINAL_PENDING_DATA:
        return False
    if current_finality.get('state') != game_finality.FINAL_AND_USABLE:
        return False
    if not previous_finality.get('final_status') or not current_finality.get('final_status'):
        return False

    boxscore = ((payload or {}).get('liveData') or {}).get('boxscore')
    if not game_finality.classify_boxscore_usability(boxscore).is_final_and_usable:
        return False

    previous_result = _verified_final_result_identity(previous)
    current_result = _verified_final_result_identity(current)
    if previous_result is None or current_result is None:
        return False
    if previous_result != current_result:
        return False

    previous_evidence = (previous or {}).get('pitching_evidence') or {}
    current_evidence = (current or {}).get('pitching_evidence') or {}
    if (
        current_evidence.get('source_authority')
        != game_appearance_extraction.SOURCE_AUTHORITY
        or not current_evidence.get('appearance_set_fingerprint')
    ):
        return False
    if (
        previous_evidence
        and previous_evidence.get('source_authority')
        != game_appearance_extraction.SOURCE_AUTHORITY
    ):
        return False

    # The exception admits only the finality evidence upgrade. Any other
    # material observation difference remains ambiguous at an equal revision.
    # The source-authority key is allowed solely as a legacy-schema bootstrap;
    # its exact governed value was validated above.
    allowed_differences = {
        'finality.reason',
        'finality.state',
        'pitching_evidence.source_authority',
        'pitching_evidence.appearance_set_fingerprint',
    }
    if set(observation_diff(previous, current)) - allowed_differences:
        return False

    return True


def _is_final_evidence_regression(previous, current):
    previous_finality = (previous or {}).get('finality') or {}
    current_finality = (current or {}).get('finality') or {}
    return (
        previous_finality.get('state') == game_finality.FINAL_AND_USABLE
        and current_finality.get('state') == game_finality.FINAL_PENDING_DATA
        and previous_finality.get('final_status') is True
        and current_finality.get('final_status') is True
    )


def _official_pitching_fingerprint(
    *, game_pk, official_date, home_team_id, away_team_id, boxscore,
):
    """Hash canonical appearance fields from the already-fetched official feed."""
    try:
        from services import sync as sync_service

        appearances = game_appearance_extraction.extract_game_appearances(
            game={
                'gamePk': game_pk,
                'teams': {
                    'home': {'team': {'id': home_team_id}},
                    'away': {'team': {'id': away_team_id}},
                },
            },
            pitching_lines=sync_service._extract_pitching_lines_from_boxscore(
                boxscore
            ),
            pitcher_order=sync_service._pitcher_order_by_side(boxscore),
            game_date=official_date,
        )
    except (TypeError, ValueError, game_appearance_extraction.AppearanceExtractionError):
        return None
    if not appearances:
        return None
    return game_appearance_extraction.appearance_set_fingerprint(appearances)


def _verified_final_result_identity(observation):
    observation = observation or {}
    identity = observation.get('identity') or {}
    official_date = identity.get('official_date')
    try:
        parsed_date = date.fromisoformat(official_date)
    except (TypeError, ValueError):
        return None
    if not isinstance(official_date, str) or official_date != parsed_date.isoformat():
        return None

    home_team_id = identity.get('home_team_id')
    away_team_id = identity.get('away_team_id')
    if not _is_positive_integer(home_team_id) or not _is_positive_integer(away_team_id):
        return None
    if home_team_id == away_team_id:
        return None

    linescore = observation.get('linescore') or {}
    home_score = (linescore.get('home') or {}).get('runs')
    away_score = (linescore.get('away') or {}).get('runs')
    if not _is_nonnegative_integer(home_score):
        return None
    if not _is_nonnegative_integer(away_score):
        return None

    game_pk = observation.get('game_pk')
    if not _is_positive_integer(game_pk):
        return None
    return (
        game_pk,
        official_date,
        home_team_id,
        away_team_id,
        home_score,
        away_score,
    )


def _accepted_change_classification(previous_finality, current_finality):
    if current_finality in {game_finality.FINAL_AND_USABLE, game_finality.FINAL_PENDING_DATA}:
        if previous_finality not in {
            game_finality.FINAL_AND_USABLE, game_finality.FINAL_PENDING_DATA,
        }:
            return FINALIZED
        return CORRECTED
    return CHANGED


def _candidate_game_pks(games, reference_date, correction_start):
    candidates = set()
    for game in games or []:
        pk = _positive_int((game or {}).get('gamePk'))
        raw_date = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
        try:
            game_date = date.fromisoformat(raw_date)
        except (TypeError, ValueError):
            continue
        decision = game_finality.classify_game_finality(game)
        if game_date == reference_date:
            candidates.add(pk)
        elif correction_start <= game_date < reference_date and decision.has_safe_final_status:
            candidates.add(pk)
        elif decision.state == game_finality.SUSPENDED:
            candidates.add(pk)
    return sorted(pk for pk in candidates if pk is not None)


def _prioritize_bounded_candidates(games, candidate_game_pks, reference_date):
    """Keep active/current games ahead of correction-window finals when capped."""
    allowed = set(candidate_game_pks)
    ranked = []
    for game in games or []:
        pk = _positive_int((game or {}).get('gamePk'))
        if pk not in allowed:
            continue
        raw_date = (game or {}).get('officialDate') or str(
            (game or {}).get('gameDate') or ''
        )[:10]
        try:
            game_date = date.fromisoformat(raw_date)
        except (TypeError, ValueError):
            game_date = date.min
        decision = game_finality.classify_game_finality(game)
        status = (game or {}).get('status') or {}
        status_code = str(status.get('statusCode') or status.get('codedGameState') or '')
        if game_date == reference_date and status_code in game_finality.IN_PROGRESS_STATUS_CODES:
            tier = 0
        elif decision.state == game_finality.SUSPENDED:
            tier = 1
        elif game_date == reference_date and not decision.has_safe_final_status:
            tier = 2
        elif game_date == reference_date:
            tier = 3
        else:
            tier = 4
        ranked.append((tier, -game_date.toordinal(), pk))
    return [pk for _tier, _ordinal, pk in sorted(ranked)]


def _cycle(candidates, results, started, *, schedule_requests):
    values = [item.to_dict() for item in results]
    return {
        'candidate_game_pks': candidates,
        'games_checked': len([r for r in results if r.game_pk is not None]),
        'unchanged_games': sum(r.classification == UNCHANGED for r in results),
        'changed_games': sum(r.changed for r in results),
        'source_failures': sum(r.classification == SOURCE_FAILURE for r in results),
        'requests_expected': schedule_requests + len(candidates),
        'downstream_work_triggered': False,
        'elapsed_ms': _elapsed(started),
        'results': values,
    }


def _result(*, game_pk, classification, changed, source_authority,
            detected_at, reason, accepted, previous=None, current=None,
            finality=None, source_observed_at=None, differences=None,
            payload_bytes=None, elapsed_ms=None):
    return GameChangeResult(
        game_pk=game_pk, classification=classification, changed=changed,
        previous_observation_identity=previous,
        current_observation_identity=current,
        finality_state=finality, source_authority=source_authority,
        source_observed_at=(source_observed_at.isoformat() if source_observed_at else None),
        detected_at=detected_at.isoformat(), differences=differences or {},
        reason=reason, accepted=accepted,
        approximate_payload_bytes=payload_bytes, elapsed_ms=elapsed_ms,
    )


def _finish(commit):
    if commit:
        db.session.commit()
    else:
        db.session.flush()


def _flatten(value, prefix=''):
    result = {}
    if isinstance(value, dict):
        for key in sorted(value):
            path = f'{prefix}.{key}' if prefix else key
            result.update(_flatten(value[key], path))
    else:
        result[prefix] = value
    return result


def _team_totals(value):
    value = value or {}
    return {
        'runs': _score_or_none(value.get('runs')),
        'hits': _int_or_none(value.get('hits')),
        'errors': _int_or_none(value.get('errors')),
    }


def _nested_id(value):
    if not isinstance(value, dict):
        return None
    raw_value = value.get('id') or (value.get('team') or {}).get('id')
    return raw_value if _is_positive_integer(raw_value) else None


def _event_fallback_identity(play, event):
    if not event:
        return None
    return f"{play.get('atBatIndex')}:{event.get('index')}:{event.get('type')}"


def _positive_int(value):
    parsed = _int_or_none(value)
    return parsed if parsed is not None and parsed > 0 else None


def _score_or_none(value):
    return value if _is_nonnegative_integer(value) else None


def _is_positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _int_or_none(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _elapsed(started):
    return round((perf_counter() - started) * 1000, 2)
