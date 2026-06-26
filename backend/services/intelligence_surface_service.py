"""Intelligence Surface service — League Today's Lead Story (COIN).

The first backend step for "What BaseballOS Sees." Given a reference date, this
service answers one question:

    "What is the one bullpen story BaseballOS sees first today?"

It does NO baseball reasoning and generates NO prose. It builds the existing COIN
StoryPackage for each candidate team (via the read-only inspection helper, which
runs the orchestrator and renders the existing writers), keeps only the
publishable packages, ranks them deterministically, and returns the single lead
story with its rendered drafts and the metadata that explains the choice.

Selection only — nothing here recomputes a story, fetches MLB data, mutates the
database, or introduces a new intelligence layer. Candidate context rows are read
from the existing ``completed_game_contexts`` table (or injected for tests); the
per-team bullpen snapshot is read through the same path the writers already use.

Ranking (deterministic, ascending priority — lower sorts first):

    1. story_priority        CRITICAL > HIGH > MEDIUM > LOW
    2. game_importance        HIGH > MEDIUM > LOW
    3. confidence             HIGH > MEDIUM > LOW
    4. primary_story weight   lost_game_shape > bullpen_kept_team_alive
                              > protected_game_shape > late_pressure_accumulated
                              > bullpen_overexposed > starter_covered_bullpen
    5. late_runs_allowed      descending (more late damage sorts first)
    6. lead/deficit swing     descending (bigger swing sorts first)
    7. team_id                ascending (final deterministic tiebreaker)
    8. game_pk                ascending (guards doubleheaders deterministically)

Fail closed: a candidate that fails to build is skipped and counted, never
fatal; if nothing is publishable the service returns an honest empty state.
"""

from __future__ import annotations

from services.coin_story_inspection import inspect_team_story

# ── Ranking vocabularies ──────────────────────────────────────────────────────
_UNKNOWN_RANK = 99

_PRIORITY_RANK = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
_IMPORTANCE_RANK = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
_CONFIDENCE_RANK = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
_PRIMARY_STORY_RANK = {
    'lost_game_shape': 0,
    'bullpen_kept_team_alive': 1,
    'protected_game_shape': 2,
    'late_pressure_accumulated': 3,
    'bullpen_overexposed': 4,
    'starter_covered_bullpen': 5,
}

# ── Status / empty reasons ────────────────────────────────────────────────────
STATUS_OK = 'ok'
STATUS_EMPTY = 'empty'
EMPTY_NO_CANDIDATES = 'no_completed_game_contexts'
EMPTY_NO_PUBLISHABLE = 'no_publishable_coin_story'

# The existing writers, in a stable order for the drafts mapping.
_DRAFT_ORDER = ('team_story', 'dashboard', 'morning_brief')


def build_today_lead_story(
    *,
    app=None,
    reference_date=None,
    candidate_contexts=None,
    inspect_fn=None,
):
    """Return the single most important publishable COIN story for a date.

    Read-only. ``reference_date`` is an ISO ``YYYY-MM-DD`` string or a ``date``;
    when omitted the latest available completed-game-context date is used. Pass
    ``candidate_contexts`` (a list of completed-game-context dicts) to inject the
    candidate set for tests/pure use and skip the database entirely. ``app`` (a
    Flask app) wraps the database reads in an app context for the real path; when
    the service is already called inside an app/request context, leave it ``None``.
    """
    inspect_fn = inspect_fn or inspect_team_story

    def _run():
        ref_iso, contexts = _resolve_candidates(reference_date, candidate_contexts)
        return _select_lead_story(ref_iso, contexts, inspect_fn)

    if app is not None and candidate_contexts is None:
        with app.app_context():
            return _run()
    return _run()


# ── Candidate enumeration ─────────────────────────────────────────────────────

def _resolve_candidates(reference_date, candidate_contexts):
    """Resolve (reference_date_iso, candidate completed-context dicts)."""
    if candidate_contexts is not None:
        return _iso(reference_date), [c for c in candidate_contexts if c]
    ref_date, rows = _load_candidate_contexts(reference_date)
    return _iso(ref_date), [r.to_dict() for r in rows]


def _load_candidate_contexts(reference_date):
    """Read completed-game-context rows for the reference date (single date).

    With no reference date, anchor on the most recent ``game_date`` present so
    the homepage shows the latest day BaseballOS actually has context for.
    """
    from models.completed_game_context import CompletedGameContext

    ref_date = _coerce_date(reference_date)
    if ref_date is None:
        latest = (
            CompletedGameContext.query
            .filter(CompletedGameContext.game_date.isnot(None))
            .order_by(CompletedGameContext.game_date.desc())
            .first()
        )
        if latest is None:
            return None, []
        ref_date = latest.game_date

    rows = (
        CompletedGameContext.query
        .filter_by(game_date=ref_date)
        .order_by(CompletedGameContext.team_id.asc(),
                  CompletedGameContext.game_pk.asc())
        .all()
    )
    return ref_date, rows


# ── Selection ─────────────────────────────────────────────────────────────────

def _select_lead_story(reference_date_iso, contexts, inspect_fn):
    considered = 0
    error_count = 0
    publishable = []

    for ctx in contexts:
        team_id = ctx.get('team_id')
        if team_id is None:
            continue
        considered += 1
        try:
            inspected = inspect_fn(
                team_id,
                app=None,  # already inside any needed app context
                reference_date=reference_date_iso,
                completed_game_context=ctx,
            )
        except Exception:
            # Fail closed per candidate: skip and count, never abort the slate.
            error_count += 1
            continue
        if inspected and inspected.get('publishable') is True:
            publishable.append(inspected)

    if not considered:
        return _empty_response(reference_date_iso, considered, 0, error_count,
                               EMPTY_NO_CANDIDATES)
    if not publishable:
        return _empty_response(reference_date_iso, considered, 0, error_count,
                               EMPTY_NO_PUBLISHABLE)

    ranked = sorted(publishable, key=_sort_key)
    lead = ranked[0]
    return {
        'status': STATUS_OK,
        'reference_date': reference_date_iso,
        'lead_story': _lead_story_payload(lead, rank=1),
        'candidates_considered': considered,
        'publishable_candidates': len(publishable),
        'errors': error_count,
        'empty_reason': None,
    }


def _sort_key(inspected):
    pkg = inspected.get('package') or {}
    completed = pkg.get('completed_game_context') or {}

    priority = _PRIORITY_RANK.get(inspected.get('story_priority'), _UNKNOWN_RANK)
    importance = _IMPORTANCE_RANK.get(inspected.get('game_importance'), _UNKNOWN_RANK)
    confidence = _CONFIDENCE_RANK.get(inspected.get('confidence'), _UNKNOWN_RANK)
    primary = _PRIMARY_STORY_RANK.get(pkg.get('primary_story'), _UNKNOWN_RANK)

    late_runs = _int_or_zero(completed.get('late_runs_allowed'))
    swing = _swing(completed)
    team_id = _int_or_zero(inspected.get('team_id'))
    game_pk = _int_or_zero(inspected.get('game_pk'))

    # Negate the "more is more important" signals so ascending sort puts the
    # biggest late damage and largest swing first.
    return (priority, importance, confidence, primary,
            -late_runs, -swing, team_id, game_pk)


def _swing(completed):
    return max(_int_or_zero(completed.get('largest_lead')),
               _int_or_zero(completed.get('largest_deficit')))


# ── Response shaping ──────────────────────────────────────────────────────────

def _lead_story_payload(inspected, *, rank):
    pkg = inspected.get('package') or {}
    completed = pkg.get('completed_game_context') or {}
    return {
        'team_id': inspected.get('team_id'),
        'game_pk': inspected.get('game_pk'),
        'package': pkg,
        'drafts': _drafts_by_writer(inspected.get('drafts') or []),
        'selection': {
            'rank': rank,
            'reason': pkg.get('publish_reason') or inspected.get('publish_reason'),
            'story_priority': inspected.get('story_priority'),
            'game_importance': inspected.get('game_importance'),
            'confidence': inspected.get('confidence'),
            'primary_story': pkg.get('primary_story'),
            'late_runs_allowed': completed.get('late_runs_allowed'),
            'swing': _swing(completed),
        },
    }


def _drafts_by_writer(drafts):
    """Map the inspection's draft list to {writer_name: draft}, stable order."""
    by_writer = {d.get('writer'): d for d in drafts if d.get('writer')}
    ordered = {name: by_writer[name] for name in _DRAFT_ORDER if name in by_writer}
    # Surface any writer outside the known order without dropping it.
    for name, draft in by_writer.items():
        ordered.setdefault(name, draft)
    return ordered


def _empty_response(reference_date_iso, considered, publishable, errors, reason):
    return {
        'status': STATUS_EMPTY,
        'reference_date': reference_date_iso,
        'lead_story': None,
        'candidates_considered': considered,
        'publishable_candidates': publishable,
        'errors': errors,
        'empty_reason': reason,
    }


# ── Small helpers ─────────────────────────────────────────────────────────────

def _int_or_zero(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_date(value):
    """Accept a date, an ISO string, or None; return a date or None."""
    if value is None:
        return None
    if hasattr(value, 'isoformat') and not isinstance(value, str):
        return value
    from services.availability_reference_date import parse_reference_date
    return parse_reference_date(value)


def _iso(value):
    if value is None:
        return None
    isoformat = getattr(value, 'isoformat', None)
    if callable(isoformat) and not isinstance(value, str):
        return isoformat()
    return value
