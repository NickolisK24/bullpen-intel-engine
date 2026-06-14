"""
Visibility contract for public bullpen surfaces.

This module keeps the display universe aligned across the default team board
and public story intelligence. It does not score, rank, select, recommend, or
change availability. It only answers whether a pitcher belongs to the default
visible bullpen pool or expanded unavailable/stale context.
"""

from datetime import timedelta

from services.availability import ACTIVE_WINDOW_DAYS
from services.role_authority import ROLE_UNKNOWN, STATUS_ROLE_UNKNOWN
from services.roster_status import allows_default_board


def _iso_or_none(value):
    return value.isoformat() if value else None


def _latest_log_date(logs):
    dates = [
        getattr(log, 'game_date', None)
        for log in (logs or [])
        if getattr(log, 'game_date', None) is not None
    ]
    return max(dates) if dates else None


def _eligibility_unknown(eligibility):
    eligibility = eligibility or {}
    return (
        eligibility.get('status') == STATUS_ROLE_UNKNOWN
        or eligibility.get('role') == ROLE_UNKNOWN
    )


def build_visibility_contract(eligibility, roster_status, logs, reference_date):
    """
    Return the board/story visibility contract for one pitcher.

    Default-visible public bullpen options must have current workload evidence,
    default-board roster permission, and bullpen eligibility. Expanded context
    can still show inactive/stale records when requested, but those records are
    not public story-count options.
    """
    eligibility = eligibility or {}
    roster_status = roster_status or {}
    latest_game_date = _latest_log_date(logs)
    active_cutoff = reference_date - timedelta(days=ACTIVE_WINDOW_DAYS)
    has_current_workload = latest_game_date is not None and latest_game_date >= active_cutoff
    roster_allows_default = allows_default_board(roster_status)
    eligible = bool(eligibility.get('eligible'))
    role_unknown = _eligibility_unknown(eligibility)

    is_visible_by_default = (
        has_current_workload
        and roster_allows_default
        and eligible
        and not role_unknown
    )

    hidden_reasons = []
    if not has_current_workload:
        hidden_reasons.append('outside_active_workload_window')
    if not roster_allows_default:
        hidden_reasons.append('roster_status_unavailable')
    if not eligible:
        hidden_reasons.append('not_bullpen_eligible')
    if role_unknown:
        hidden_reasons.append('role_unknown')

    return {
        'is_visible_by_default': is_visible_by_default,
        'is_public_bullpen_option': is_visible_by_default,
        'is_unavailable_roster_status': bool(roster_status.get('is_inactive_context')),
        'hidden_until_show_unavailable': not is_visible_by_default,
        'hidden_reasons': hidden_reasons,
        'latest_game_date': _iso_or_none(latest_game_date),
        'active_cutoff_date': _iso_or_none(active_cutoff),
    }


def default_visible_contract():
    """Fallback for pure board payload tests that pass already-visible records."""
    return {
        'is_visible_by_default': True,
        'is_public_bullpen_option': True,
        'is_unavailable_roster_status': False,
        'hidden_until_show_unavailable': False,
        'hidden_reasons': [],
        'latest_game_date': None,
        'active_cutoff_date': None,
    }


def summarize_visibility(cards):
    cards = list(cards or [])
    hidden = [
        card for card in cards
        if not (card.get('visibility') or {}).get('is_visible_by_default')
    ]
    hidden_but_available = [
        card for card in hidden
        if (card.get('visibility') or {}).get('is_public_bullpen_option')
    ]
    hidden_unavailable = [
        card for card in hidden
        if not (card.get('visibility') or {}).get('is_public_bullpen_option')
    ]
    return {
        'active_count': sum(
            1 for card in cards
            if (card.get('visibility') or {}).get('is_public_bullpen_option')
        ),
        'default_visible_count': sum(
            1 for card in cards
            if (card.get('visibility') or {}).get('is_visible_by_default')
        ),
        'hidden_unavailable_count': len(hidden_unavailable),
        'hidden_but_available_count': len(hidden_but_available),
    }
