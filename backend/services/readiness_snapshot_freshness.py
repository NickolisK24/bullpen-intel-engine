"""Serving-snapshot freshness authority for public Team Operations readiness reads.

Founder-approved readiness-freshness repair. When a public read is produced FROM a
specific serving trusted daily snapshot (the Share Artifact batch generates one
immutable artifact per team from one shared, validated snapshot), the freshness of
that read must reflect the SNAPSHOT it is built from — the immutable, authoritative
``data_through`` the snapshot published on — not a live, global recompute of
``max(GameLog.game_date)`` that can lag the snapshot whenever the per-pitcher
game-log lane trails the schedule/appearance authority the snapshot published on.

This module owns ONE deterministic decision: given a candidate serving snapshot and
a reference date, is the read anchored to a *current* serving trusted snapshot? It
introduces no second freshness engine and no second slate authority — it consumes
the SAME snapshot-trust verdict (``dashboard_snapshot.snapshot_unavailable_reason``)
and the SAME active window (``services.availability.ACTIVE_WINDOW_DAYS``) the rest of
the system uses. It fails closed: a missing / untrusted / unpublished / non-serving
snapshot, a missing ``data_through``, or a ``data_through`` outside the freshness
window all yield *no authority* (None), so the caller keeps its prior conservative
live freshness. It never invents currency from an untrusted or stale snapshot, and
it never touches per-team coverage — a team whose own active-bullpen inputs are
insufficient still degrades through the unchanged coverage classifier.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Optional

from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_reference_date import product_current_date


# Non-sensitive reason codes surfaced on the anchored freshness read. The two
# codes distinguish WHICH trusted source anchored a current read, so an operator
# can tell a league serving-snapshot read from a team-progressive one without
# inferring it from a numeric id.
REASON_CURRENT_SERVING_SNAPSHOT = 'current_publication_critical_serving_snapshot'
REASON_CURRENT_TEAM_PROGRESSIVE = 'current_trusted_team_progressive_source'

# Durable source-authority discriminator carried on a team-progressive authority
# object (``TeamStateSnapshotAuthority.subject_type``). Local literal to avoid a
# models import in this pure freshness module.
_TEAM_PROGRESSIVE_SUBJECT_TYPE = 'team_progressive'

# Live freshness reason codes that describe a stale/absent workload window. When a
# current serving snapshot supersedes the live recompute, these no longer describe
# the read and are dropped from the anchored copy (the snapshot IS the authority).
_SUPERSEDED_STALE_REASON_CODES = frozenset({
    'workload_data_outside_active_window',
    'workload_data_unavailable',
    'workload_data_missing',
    'successful_sync_missing',
})


def serving_snapshot_freshness_authority(
    snapshot,
    *,
    reference_date: Optional[date] = None,
    active_window_days: int = ACTIVE_WINDOW_DAYS,
    unavailable_reason: Optional[Callable] = None,
) -> Optional[dict]:
    """Resolve the serving-snapshot freshness authority, or ``None`` (fail closed).

    Returns a small JSON-safe authority dict ONLY when ``snapshot`` is a published,
    serving, trusted daily snapshot (``snapshot_unavailable_reason`` is ``None`` —
    the same verdict SC-02 eligibility and single-team gathering use) whose
    ``data_through`` is within ``active_window_days`` of ``reference_date`` (default
    the product-timezone current date). Every other case — no snapshot, an
    untrusted / unpublished / non-serving snapshot, a missing ``data_through``, or a
    ``data_through`` outside the window (a genuinely stale snapshot) — returns
    ``None`` so the caller keeps its prior conservative live freshness.
    """
    if snapshot is None:
        return None
    reason_fn = unavailable_reason or _default_unavailable_reason
    try:
        if reason_fn(snapshot) is not None:
            # Untrusted / unpublished / non-serving / version or date mismatch.
            return None
    except Exception:
        # An unreadable trust verdict must never manufacture currency: fail closed
        # to the caller's prior conservative live freshness.
        return None
    data_through = getattr(snapshot, 'data_through', None)
    if not isinstance(data_through, date):
        return None
    ref = reference_date or product_current_date()
    cutoff = ref - timedelta(days=int(active_window_days))
    if data_through < cutoff:
        # The serving snapshot itself is older than the freshness window: it is
        # genuinely stale and must NOT be presented as current (fail closed).
        return None
    is_team_progressive = (
        getattr(snapshot, 'subject_type', None) == _TEAM_PROGRESSIVE_SUBJECT_TYPE
    )
    return {
        'data_through': data_through,
        'availability_reference_date': data_through + timedelta(days=1),
        'reference_date': ref,
        'active_window_days': int(active_window_days),
        'reason_code': (
            REASON_CURRENT_TEAM_PROGRESSIVE if is_team_progressive
            else REASON_CURRENT_SERVING_SNAPSHOT
        ),
        'source_scope': _TEAM_PROGRESSIVE_SUBJECT_TYPE if is_team_progressive else 'league_snapshot',
    }


def anchor_sync_status_to_serving_snapshot(sync_status, authority) -> dict:
    """Return a copy of ``sync_status`` whose freshness is anchored to ``authority``.

    Only the freshness/data-through fields are rewritten to the serving snapshot's
    authoritative dates and a current verdict; every other sync-status field is
    preserved. When ``authority`` is ``None`` the input is returned unchanged, so a
    caller that resolved no authority keeps its exact prior conservative freshness.
    This does not touch per-team coverage — the coverage classifier still governs
    high / medium / low / unknown from the team's own active-bullpen inputs.
    """
    if authority is None:
        return sync_status
    anchored = dict(sync_status or {})
    freshness = dict(anchored.get('freshness') or {})
    reasons = [
        code for code in (freshness.get('reason_codes') or [])
        if code not in _SUPERSEDED_STALE_REASON_CODES
    ]
    if authority['reason_code'] not in reasons:
        reasons.append(authority['reason_code'])
    data_through_iso = authority['data_through'].isoformat()
    availability_ref_iso = authority['availability_reference_date'].isoformat()
    if authority.get('source_scope') == _TEAM_PROGRESSIVE_SUBJECT_TYPE:
        label = f'Current trusted team source through {data_through_iso}.'
    else:
        label = f'Current serving trusted snapshot through {data_through_iso}.'
    freshness.update({
        'is_current': True,
        'is_stale': False,
        'freshness_state': 'current',
        'availability_reference_date': availability_ref_iso,
        'reference_date': authority['reference_date'].isoformat(),
        'active_window_days': authority['active_window_days'],
        'reason_codes': reasons,
        'label': label,
        'stale_warning': None,
    })
    data = dict(anchored.get('data') or {})
    data['latest_workload_date'] = data_through_iso
    data['latest_game_date'] = data.get('latest_game_date') or data_through_iso
    anchored['freshness'] = freshness
    anchored['data'] = data
    anchored['availability_reference_date'] = availability_ref_iso
    return anchored


def _default_unavailable_reason(snapshot):
    # A team-scoped source authority (progressive publication checkpoint /
    # TeamStateSnapshotAuthority) carries its OWN fail-closed trust verdict computed
    # from that team's final-game evidence; a league DashboardSnapshot uses the
    # canonical league snapshot trust verdict. Duck-type so the same freshness anchor
    # serves both without a second freshness engine.
    if hasattr(snapshot, 'is_trusted') and hasattr(snapshot, 'unavailable_reason'):
        if getattr(snapshot, 'is_trusted', False):
            return None
        return getattr(snapshot, 'unavailable_reason', None) or 'source_untrusted'
    from services.dashboard_snapshot import snapshot_unavailable_reason

    return snapshot_unavailable_reason(snapshot)
