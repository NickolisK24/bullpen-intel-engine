"""CU-06 bounded, non-publishing read-model rebuilds.

The service overlays accepted CU-04/CU-05 facts on a copied trusted snapshot,
then delegates to the existing serving builders.  The copy is never persisted,
published, cached, or installed as serving authority.
"""

from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date
from time import perf_counter
from types import SimpleNamespace

from models.pitcher import Pitcher
from models.slate_game import SlateGame
from services import public_serving_authority
from services.bullpen_board import author_rest_status
from services.incremental_workload_rest import (
    PARITY_MATCH,
    PARITY_MISMATCH,
    PARITY_NOT_COMPARABLE,
    STATUS_COMPLETE,
)
from services.league_team_state_listing import (
    build_league_team_state_listing,
    build_league_team_state_row,
)
from services.trusted_compare_authority import build_scheduled_game_matchup_payload
from utils.db import db


STATUS_NO_ACTION = 'no_action'
STATUS_PARTIAL = 'partial'
NON_SEMANTIC_FIELDS = frozenset({'generated_at', 'elapsed_ms', 'served_from'})


@dataclass(frozen=True)
class SurfaceParity:
    surface: str
    entity_id: int
    status: str
    incremental_value: object
    authoritative_value: object


@dataclass(frozen=True)
class IncrementalReadModelResult:
    game_pk: int | None
    represented_date: str | None
    status: str
    reason_code: str
    requested_pitcher_ids: tuple = ()
    requested_team_ids: tuple = ()
    team_boards_rebuilt: tuple = ()
    league_rows_rebuilt: tuple = ()
    matchups_rebuilt: tuple = ()
    tonight_entries_rebuilt: tuple = ()
    pitcher_models_rebuilt: tuple = ()
    team_board_results: dict = field(default_factory=dict)
    team_package_results: dict = field(default_factory=dict)
    league_row_results: dict = field(default_factory=dict)
    matchup_results: dict = field(default_factory=dict)
    tonight_results: dict = field(default_factory=dict)
    parity_status: str = PARITY_NOT_COMPARABLE
    parity_entries: tuple = ()
    parity_mismatches: tuple = ()
    failures: tuple = ()
    rebuild_performed: bool = False
    rebuild_ms: float = 0.0
    publication_affected: bool = False
    cache_invalidation_triggered: bool = False
    scheduling_affected: bool = False
    frontend_affected: bool = False
    what_changed_generated: bool = False
    downstream_triggered: bool = False

    def to_dict(self):
        value = asdict(self)
        for key in (
            'requested_pitcher_ids', 'requested_team_ids',
            'team_boards_rebuilt', 'league_rows_rebuilt',
            'matchups_rebuilt', 'tonight_entries_rebuilt',
            'pitcher_models_rebuilt', 'parity_entries',
            'parity_mismatches', 'failures',
        ):
            value[key] = list(value[key])
        return value


def rebuild_read_model_impact(
    cu05_result,
    *,
    source_snapshot=None,
    compare_authoritative=True,
    team_board_builder=None,
    league_listing_builder=None,
    matchup_builder=None,
    tonight_builder=None,
):
    """Rebuild only read models invalidated by a trusted CU-05 result."""
    pitcher_ids = tuple(sorted(set(_get(cu05_result, 'arm_reads_recomputed') or ())))
    team_ids = tuple(sorted(set(_get(cu05_result, 'teams_recomputed') or ())))
    game_pk = _get(cu05_result, 'game_pk')
    represented_date = _parse_date(_get(cu05_result, 'data_through'))
    trusted = (
        _get(cu05_result, 'status') == STATUS_COMPLETE
        and _get(cu05_result, 'parity_status') == PARITY_MATCH
        and bool(_get(cu05_result, 'recomputation_performed'))
    )
    if not trusted or not team_ids:
        return IncrementalReadModelResult(
            game_pk=game_pk,
            represented_date=_iso(represented_date),
            status=STATUS_NO_ACTION,
            reason_code='cu05_no_action_or_untrusted',
            requested_pitcher_ids=pitcher_ids,
            requested_team_ids=team_ids,
        )
    if represented_date is None:
        raise ValueError('CU-06 requires CU-05 explicit represented date')

    snapshot = source_snapshot or (
        public_serving_authority.dashboard_snapshot_service
        .get_latest_valid_dashboard_snapshot()
    )
    if snapshot is None:
        return _partial(
            game_pk, represented_date, pitcher_ids, team_ids,
            failure={'scope': 'snapshot', 'error': 'TrustedSnapshotUnavailable'},
        )

    shadow_snapshot = build_shadow_snapshot(snapshot, cu05_result)
    state_overrides = _public_state_overrides(cu05_result)
    classified_overrides = _classified_overrides(cu05_result)
    board_builder = team_board_builder or _default_team_board_builder
    listing_builder = league_listing_builder or _default_league_listing_builder
    game = SlateGame.query.filter_by(game_pk=game_pk).one_or_none() if game_pk else None

    started = perf_counter()
    failures = []
    boards = {}
    league_rows = {}
    matchups = {}
    tonight = {}
    parity = []

    try:
        league_listing = listing_builder(shadow_snapshot, state_overrides)
    except Exception as exc:
        league_listing = None
        failures.append(_failure('league', None, exc))

    for team_id in team_ids:
        try:
            board = board_builder(
                team_id, shadow_snapshot, state_overrides.get(team_id),
            )
            boards[team_id] = board
            if compare_authoritative:
                authoritative = board_builder(
                    team_id, shadow_snapshot, state_overrides.get(team_id),
                )
                parity.append(_parity('team_board', team_id, board, authoritative))
        except Exception as exc:
            failures.append(_failure('team_board', team_id, exc))

        if isinstance(league_listing, dict):
            row = _listing_row(league_listing, team_id)
            if row is not None:
                identity = {
                    key: row.get(key)
                    for key in ('team_id', 'team_abbreviation', 'team_name')
                }
                rebuilt = build_league_team_state_row(
                    identity, state_overrides.get(team_id) or row.get('team_state'),
                )
                league_rows[team_id] = rebuilt
                parity.append(_parity('league_row', team_id, rebuilt, row))
            else:
                failures.append({
                    'scope': 'league_row', 'entity_id': team_id,
                    'error': 'LeagueRowUnavailable',
                })

    if game is not None and ({game.home_team_id, game.away_team_id} & set(team_ids)):
        try:
            build_matchup = matchup_builder or _default_matchup_builder
            payload = build_matchup(game, shadow_snapshot, state_overrides)
            matchups[int(game.game_pk)] = payload
            if compare_authoritative:
                authoritative = build_matchup(game, shadow_snapshot, state_overrides)
                parity.append(_parity(
                    'matchup', int(game.game_pk), payload, authoritative,
                ))
        except Exception as exc:
            failures.append(_failure('matchup', game_pk, exc))

        try:
            build_tonight = tonight_builder or _default_tonight_builder
            payload = build_tonight(
                game, shadow_snapshot, state_overrides, classified_overrides,
                league_listing,
            )
            entry = _game_entry(payload, game_pk)
            if entry is not None:
                tonight[int(game_pk)] = entry
                if compare_authoritative:
                    authority_payload = build_tonight(
                        game, shadow_snapshot, state_overrides,
                        classified_overrides, league_listing,
                    )
                    parity.append(_parity(
                        'tonight', int(game_pk), entry,
                        _game_entry(authority_payload, game_pk),
                    ))
            else:
                failures.append({
                    'scope': 'tonight', 'entity_id': game_pk,
                    'error': 'TonightEntryUnavailable',
                })
        except Exception as exc:
            failures.append(_failure('tonight', game_pk, exc))

    mismatches = tuple(
        asdict(entry) for entry in parity if entry.status == PARITY_MISMATCH
    )
    if failures:
        status, reason, parity_status = (
            STATUS_PARTIAL, 'bounded_rebuild_failed', PARITY_NOT_COMPARABLE,
        )
    elif mismatches:
        status, reason, parity_status = (
            STATUS_PARTIAL, 'parity_mismatch', PARITY_MISMATCH,
        )
    else:
        status = STATUS_COMPLETE
        reason = 'parity_match' if compare_authoritative else 'rebuilt_without_parity'
        parity_status = PARITY_MATCH if compare_authoritative else PARITY_NOT_COMPARABLE

    return IncrementalReadModelResult(
        game_pk=game_pk,
        represented_date=represented_date.isoformat(),
        status=status,
        reason_code=reason,
        requested_pitcher_ids=pitcher_ids,
        requested_team_ids=team_ids,
        team_boards_rebuilt=tuple(sorted(boards)),
        league_rows_rebuilt=tuple(sorted(league_rows)),
        matchups_rebuilt=tuple(sorted(matchups)),
        tonight_entries_rebuilt=tuple(sorted(tonight)),
        team_board_results=boards,
        team_package_results={
            team_id: deepcopy(
                (
                    (shadow_snapshot.payload or {})
                    .get(public_serving_authority.TEAM_BOARD_PACKAGE_KEY, {})
                    .get('by_team_id', {})
                    .get(str(team_id), {})
                )
            )
            for team_id in team_ids
        },
        league_row_results=league_rows,
        matchup_results=matchups,
        tonight_results=tonight,
        parity_status=parity_status,
        parity_entries=tuple(asdict(entry) for entry in parity),
        parity_mismatches=mismatches,
        failures=tuple(failures),
        rebuild_performed=bool(boards or league_rows or matchups or tonight),
        rebuild_ms=round((perf_counter() - started) * 1000.0, 3),
    )


def build_shadow_snapshot(snapshot, cu05_result):
    """Return an in-memory trusted-snapshot copy with affected inputs overlaid."""
    shadow = copy(snapshot)
    payload = deepcopy(getattr(snapshot, 'payload', None) or {})
    package = payload.get(public_serving_authority.TEAM_BOARD_PACKAGE_KEY) or {}
    by_team = package.get('by_team_id') or {}
    availability = dict(_get(cu05_result, 'availability_results') or {})
    pitcher_workload = dict(
        _get(cu05_result, 'workload_rest_pitcher_results') or {}
    )
    team_workload = dict(_get(cu05_result, 'workload_rest_team_results') or {})

    for team_id in set(_get(cu05_result, 'teams_recomputed') or ()):
        team_package = by_team.get(str(team_id))
        if not isinstance(team_package, dict):
            continue
        for record in team_package.get('records') or ():
            pitcher_id = record.get('pitcher_id')
            if pitcher_id in availability:
                record['availability'] = deepcopy(availability[pitcher_id])
            workload = pitcher_workload.get(pitcher_id) or {}
            fatigue = workload.get('fatigue_workload') or {}
            rest_inputs = workload.get('rest_workload_inputs') or {}
            if fatigue:
                previous = record.get('workload_facts') or {}
                record['workload_facts'] = {
                    'calculated_at': previous.get('calculated_at'),
                    **deepcopy(fatigue),
                }
                record['fatigue_score'] = rest_inputs.get('fatigue_score')
        if team_id in team_workload:
            team_package['workload_windows'] = deepcopy(team_workload[team_id])
            authority = team_package.get('workload_windows_authority') or {}
            authority['data_through'] = team_workload[team_id].get('data_through')
            team_package['workload_windows_authority'] = authority
        default_ids = set(team_package.get('default_pitcher_ids') or ())
        selected = [
            record for record in team_package.get('records') or ()
            if record.get('pitcher_id') in default_ids
        ]
        team_package['rest_status'] = author_rest_status(
            selected,
            freshness=payload.get('freshness') or {},
            roster_authority=team_package.get('roster_authority') or {},
        )
    shadow.payload = payload
    return shadow


def _classified_overrides(cu05_result):
    availability = dict(_get(cu05_result, 'availability_results') or {})
    workload = dict(_get(cu05_result, 'workload_rest_pitcher_results') or {})
    result = {}
    for pitcher_id, read in availability.items():
        pitcher = db.session.get(Pitcher, pitcher_id)
        if pitcher is None:
            continue
        inputs = (workload.get(pitcher_id) or {}).get('rest_workload_inputs') or {}
        result[pitcher_id] = {
            'pitcher_id': pitcher_id,
            'pitcher': pitcher,
            'score': SimpleNamespace(
                raw_score=inputs.get('fatigue_score'),
                risk_level=inputs.get('fatigue_risk_level'),
            ),
            'availability': deepcopy(read),
        }
    return result


def _public_state_overrides(cu05_result):
    result = {}
    for team_id, projection in dict(
        _get(cu05_result, 'team_state_results') or {}
    ).items():
        projection = projection or {}
        state = projection.get('public_team_state')
        if isinstance(state, dict):
            result[int(team_id)] = deepcopy(state)
    return result


def _default_team_board_builder(team_id, snapshot, team_state):
    return public_serving_authority.build_published_team_board(
        team_id,
        snapshot_override=snapshot,
        team_state_override=team_state,
        include_delivery_identity=True,
    )


def _default_league_listing_builder(snapshot, state_overrides):
    listing = build_league_team_state_listing(
        snapshot_resolver=lambda: (snapshot, None),
    )
    rows = []
    for row in listing.get('teams') or ():
        team_id = row.get('team_id')
        rows.append(build_league_team_state_row(
            row, state_overrides.get(team_id) or row.get('team_state'),
        ))
    return {**listing, 'teams': rows}


def _default_matchup_builder(game, snapshot, state_overrides):
    return build_scheduled_game_matchup_payload(
        game, snapshot, team_state_overrides=state_overrides,
    )


def _default_tonight_builder(
    game, snapshot, state_overrides, classified_overrides, league_listing,
):
    from services.bullpen_context import build_team_bullpen_context
    from services.published_team_rest_status_listing import (
        build_published_team_rest_status_listing,
    )
    from services.published_team_workload_listing import (
        build_published_team_workload_listing,
    )
    from services.schedule_context import build_schedule_contexts_for_date
    from services.tonight_intelligence_service import serve_tonight

    ref = game.game_date_et
    teams = {game.home_team_id, game.away_team_id}
    schedules = [
        row for row in build_schedule_contexts_for_date(ref)
        if row.get('team_id') in teams
    ]
    resolver = lambda: (snapshot, None)
    return serve_tonight(
        ref,
        schedule_contexts=schedules,
        slate_games=[game],
        bullpen_context_builder=lambda team_id, reference_date: (
            build_team_bullpen_context(
                team_id,
                reference_date,
                classified_record_overrides=classified_overrides,
            )
        ),
        team_state_listing_builder=lambda: league_listing,
        workload_listing_builder=lambda: build_published_team_workload_listing(
            snapshot_resolver=resolver,
        ),
        rest_status_listing_builder=lambda: build_published_team_rest_status_listing(
            snapshot_resolver=resolver,
        ),
    )


def _listing_row(listing, team_id):
    return next(
        (row for row in listing.get('teams') or () if row.get('team_id') == team_id),
        None,
    )


def _game_entry(payload, game_pk):
    return next(
        (row for row in (payload or {}).get('games') or () if row.get('game_pk') == game_pk),
        None,
    )


def _semantic(value):
    if isinstance(value, dict):
        return {
            key: _semantic(item)
            for key, item in value.items()
            if key not in NON_SEMANTIC_FIELDS
        }
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return value


def _parity(surface, entity_id, incremental, authoritative):
    left = _semantic(incremental)
    right = _semantic(authoritative)
    return SurfaceParity(
        surface=surface,
        entity_id=int(entity_id),
        status=PARITY_MATCH if left == right else PARITY_MISMATCH,
        incremental_value=left,
        authoritative_value=right,
    )


def _failure(scope, entity_id, exc):
    return {
        'scope': scope,
        'entity_id': entity_id,
        'error': type(exc).__name__,
    }


def _partial(game_pk, represented_date, pitcher_ids, team_ids, *, failure):
    return IncrementalReadModelResult(
        game_pk=game_pk,
        represented_date=_iso(represented_date),
        status=STATUS_PARTIAL,
        reason_code='bounded_rebuild_failed',
        requested_pitcher_ids=pitcher_ids,
        requested_team_ids=team_ids,
        failures=(failure,),
    )


def _parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _iso(value):
    return value.isoformat() if isinstance(value, date) else None


def _get(value, field):
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)
