"""Tonight intelligence service (public envelope for the Tonight endpoint).

Wraps the Phase 3 candidate selection in the stable public response the
``GET /api/bullpen/intelligence/tonight`` endpoint serves: it resolves the
reference date (the pregame current day by default), derives diverse candidates,
strips internal-only fields (the selection ``strength``), and shapes a calm
envelope with honest empty states.

This is pregame intelligence, deliberately separate from the COIN completed-game
story services and from ``/intelligence/today`` — it imports neither and changes
neither. Nothing here predicts, ranks publicly, or recommends a "best" team.

Caching note: V1 builds on demand and logs timing (``served_from=on_demand``,
``elapsed_ms``). A persistent snapshot is intentionally deferred — the response is
small (<=3 cards), the public shape is still settling ahead of the Phase 5
frontend swap, and this wrapper is structured so a snapshot layer can wrap
``serve_tonight`` later (exactly as ``serve_today_lead_story`` wraps the lead
story builder) with no contract change.
"""

from __future__ import annotations

import logging

from models.slate_game import SlateGame
from services.availability_reference_date import product_current_date
from services.schedule_context import build_schedule_contexts_for_date
from services.tonight_candidate_selection import (
    build_tonight_candidates,
    public_tonight_bullpen_context,
)

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 3

STATUS_OK = 'ok'
STATUS_EMPTY = 'empty'

EMPTY_NO_SCHEDULE_CONTEXT = 'no_schedule_context'
EMPTY_NO_TEAMS_PLAYING = 'no_teams_playing_today'
EMPTY_NO_SIGNALS = 'no_tonight_signals'

# Fields carried on internal candidates that the public card must not expose.
_INTERNAL_CARD_FIELDS = ('strength', 'reference_date')


def serve_tonight(reference_date=None, *, limit=DEFAULT_LIMIT, current_date=None,
                  schedule_contexts=None, bullpen_context_builder=None,
                  slate_games=None):
    """Build the public Tonight response for a reference date.

    ``reference_date`` is a ``date``/ISO string, or ``None`` to use the product
    current day (``current_date`` overrides that default for tests). Read-only.
    ``schedule_contexts`` and ``bullpen_context_builder`` are injectable for
    tests/pure use. Returns the public envelope dict. This is the live builder;
    the cache-aware entry point (timing / served_from logging) lives in
    ``tonight_intelligence_snapshot.serve_tonight_cached``.
    """
    ref = _resolve_reference_date(reference_date, current_date)

    load_authoritative_slate = schedule_contexts is None
    if schedule_contexts is None:
        schedule_contexts = build_schedule_contexts_for_date(ref)
    if slate_games is None:
        slate_games = _load_slate_games(ref) if load_authoritative_slate else []

    return _build_response(
        ref,
        schedule_contexts,
        limit,
        bullpen_context_builder,
        slate_games,
    )


def _build_response(ref, schedule_contexts, limit, bullpen_context_builder,
                    slate_games):
    schedule_contexts = [s for s in (schedule_contexts or []) if s]

    if not schedule_contexts:
        return _empty(ref, EMPTY_NO_SCHEDULE_CONTEXT)
    if not any(s.get('is_playing_today') for s in schedule_contexts):
        games = _public_slate_games(slate_games, {}, [])
        return _empty(ref, EMPTY_NO_TEAMS_PLAYING, games=games)

    team_contexts = _build_team_contexts(
        ref,
        schedule_contexts,
        bullpen_context_builder,
    )
    candidates = build_tonight_candidates(
        ref, limit=limit, schedule_contexts=schedule_contexts,
        bullpen_context_builder=lambda team_id, _reference_date: team_contexts.get(team_id))

    cards = [_public_card(c) for c in candidates]
    games = _public_slate_games(slate_games, team_contexts, cards)
    if not candidates:
        return _empty(ref, EMPTY_NO_SIGNALS, games=games)
    return {
        'status': STATUS_OK,
        'reference_date': _iso(ref),
        'cards': cards,
        'card_count': len(cards),
        'games': games,
        'game_count': len(games),
        'empty_reason': None,
        'limitations': _aggregate_limitations(cards),
    }


def _build_team_contexts(ref, schedule_contexts, bullpen_context_builder):
    builder = bullpen_context_builder or _default_bullpen_context_builder
    contexts = {}
    for schedule in schedule_contexts:
        if not schedule.get('is_playing_today'):
            continue
        team_id = schedule.get('team_id')
        if team_id in contexts:
            continue
        try:
            contexts[team_id] = builder(team_id, ref)
        except Exception:  # noqa: BLE001 - one side never removes the slate
            logger.warning(
                'Tonight slate: bullpen context failed for team %s',
                team_id,
                exc_info=True,
            )
            contexts[team_id] = None
    return contexts


def _public_slate_games(slate_games, team_contexts, cards):
    cards_by_team = {
        card.get('team_id'): card
        for card in cards
        if card.get('team_id') is not None
    }
    games = []
    for source in slate_games or []:
        game = source.to_dict() if hasattr(source, 'to_dict') else dict(source or {})
        game_pk = game.get('game_pk')
        home_team_id = game.get('home_team_id')
        away_team_id = game.get('away_team_id')
        if game_pk is None or home_team_id is None or away_team_id is None:
            continue
        games.append({
            'game_pk': game_pk,
            'reference_date': game.get('game_date_et'),
            'game_time_utc': game.get('game_time_utc'),
            'status': dict(game.get('status') or {}),
            'doubleheader_flag': game.get('doubleheader_flag'),
            'game_number': game.get('game_number'),
            'away': _public_team_side(
                away_team_id,
                team_contexts.get(away_team_id),
                cards_by_team.get(away_team_id),
            ),
            'home': _public_team_side(
                home_team_id,
                team_contexts.get(home_team_id),
                cards_by_team.get(home_team_id),
            ),
        })
    return games


def _public_team_side(team_id, bullpen_context, card):
    identity = (bullpen_context or {}).get('team') or {}
    public_context = public_tonight_bullpen_context(bullpen_context)
    available = public_context.get('context_available') is True
    return {
        'status': 'available' if available else 'unavailable',
        'team_id': team_id,
        'team_name': identity.get('team_name'),
        'team_abbreviation': identity.get('team_abbreviation'),
        'bullpen_context': public_context,
        'watch': _public_watch(card),
        'limitations': [] if available else ['bullpen_context_unavailable'],
    }


def _public_watch(card):
    if not card:
        return None
    return {
        'headline': card.get('headline'),
        'summary': card.get('summary'),
        'pregame_story': card.get('pregame_story'),
        'evidence': list(card.get('evidence') or []),
    }


def _load_slate_games(ref):
    return (
        SlateGame.query
        .filter(SlateGame.game_date_et == ref)
        .order_by(SlateGame.game_time_utc.asc(), SlateGame.game_pk.asc())
        .all()
    )


def _default_bullpen_context_builder(team_id, reference_date):
    # Keep the candidate owner's existing loader as the one context authority.
    # The indirection also preserves the established test seam.
    from services import tonight_candidate_selection
    return tonight_candidate_selection._default_bullpen_context_builder(  # noqa: SLF001
        team_id,
        reference_date,
    )


def _public_card(candidate):
    """Strip internal-only fields; keep the public, evidence-backed card."""
    return {key: value for key, value in candidate.items()
            if key not in _INTERNAL_CARD_FIELDS}


def _aggregate_limitations(cards):
    seen = []
    for card in cards:
        for limitation in card.get('limitations') or []:
            if limitation not in seen:
                seen.append(limitation)
    return seen


def _empty(ref, reason, *, games=None):
    games = list(games or [])
    return {
        'status': STATUS_EMPTY,
        'reference_date': _iso(ref),
        'cards': [],
        'card_count': 0,
        'games': games,
        'game_count': len(games),
        'empty_reason': reason,
        'limitations': [],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_reference_date(reference_date, current_date):
    if reference_date is not None:
        return _as_date(reference_date)
    if current_date is not None:
        return _as_date(current_date)
    return product_current_date()


def _as_date(value):
    from datetime import date, datetime
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _iso(value):
    isoformat = getattr(value, 'isoformat', None)
    if callable(isoformat) and not isinstance(value, str):
        return isoformat()
    return value
