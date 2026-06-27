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

from services.availability_reference_date import product_current_date
from services.schedule_context import build_schedule_contexts_for_date
from services.tonight_candidate_selection import build_tonight_candidates

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
                  schedule_contexts=None, bullpen_context_builder=None):
    """Build the public Tonight response for a reference date.

    ``reference_date`` is a ``date``/ISO string, or ``None`` to use the product
    current day (``current_date`` overrides that default for tests). Read-only.
    ``schedule_contexts`` and ``bullpen_context_builder`` are injectable for
    tests/pure use. Returns the public envelope dict. This is the live builder;
    the cache-aware entry point (timing / served_from logging) lives in
    ``tonight_intelligence_snapshot.serve_tonight_cached``.
    """
    ref = _resolve_reference_date(reference_date, current_date)

    if schedule_contexts is None:
        schedule_contexts = build_schedule_contexts_for_date(ref)

    return _build_response(ref, schedule_contexts, limit, bullpen_context_builder)


def _build_response(ref, schedule_contexts, limit, bullpen_context_builder):
    schedule_contexts = [s for s in (schedule_contexts or []) if s]

    if not schedule_contexts:
        return _empty(ref, EMPTY_NO_SCHEDULE_CONTEXT)
    if not any(s.get('is_playing_today') for s in schedule_contexts):
        return _empty(ref, EMPTY_NO_TEAMS_PLAYING)

    candidates = build_tonight_candidates(
        ref, limit=limit, schedule_contexts=schedule_contexts,
        bullpen_context_builder=bullpen_context_builder)
    if not candidates:
        return _empty(ref, EMPTY_NO_SIGNALS)

    cards = [_public_card(c) for c in candidates]
    return {
        'status': STATUS_OK,
        'reference_date': _iso(ref),
        'cards': cards,
        'card_count': len(cards),
        'empty_reason': None,
        'limitations': _aggregate_limitations(cards),
    }


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


def _empty(ref, reason):
    return {
        'status': STATUS_EMPTY,
        'reference_date': _iso(ref),
        'cards': [],
        'card_count': 0,
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
