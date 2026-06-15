"""Governed current-availability population for public bullpen surfaces."""

from services.availability_snapshot import CURRENT_AVAILABILITY_MODE, classify_latest_fatigue_rows
from services.availability_reference_date import product_current_date
from services.bullpen_population import eligible_bullpen_pitcher_contexts
from services.bullpen_visibility import build_visibility_contract
from services.roster_status import apply_roster_status_to_availability


CURRENT_AVAILABILITY_SCOPE = 'bullpen_eligible'


def availability_with_eligibility(availability, eligibility, roster_status=None):
    merged = apply_roster_status_to_availability(availability, roster_status)
    limitations = list(merged.get('limitations') or [])
    for limitation in (eligibility or {}).get('limitations') or []:
        if limitation not in limitations:
            limitations.append(limitation)
    merged['limitations'] = limitations
    return merged


def current_availability_records(rows, reference_date=None):
    """
    Return the governed current-availability records for bullpen-eligible arms.
    """
    classified = classify_latest_fatigue_rows(
        rows,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    ref = reference_date or product_current_date()
    contexts, _roster_summary = eligible_bullpen_pitcher_contexts(
        [record['pitcher'] for record in classified],
        include_stale=True,
        include_inactive_context=False,
        reference_date=ref,
    )
    contexts_by_pitcher = {
        context['pitcher'].id: context
        for context in contexts
    }

    eligible = []
    for record in classified:
        pitcher = record['pitcher']
        context = contexts_by_pitcher.get(pitcher.id)
        if context is None:
            continue

        visibility = build_visibility_contract(
            context['eligibility'],
            context['roster_status'],
            context['logs'],
            ref,
        )
        if not visibility['is_visible_by_default']:
            continue

        updated = dict(record)
        updated['eligibility'] = context['eligibility']
        updated['roster_status'] = context['roster_status']
        updated['availability'] = availability_with_eligibility(
            updated.get('availability'),
            context['eligibility'],
            context['roster_status'],
        )
        updated['visibility'] = visibility
        eligible.append(updated)
    return eligible
