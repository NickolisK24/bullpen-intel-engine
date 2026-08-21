"""Registered metrics under the Current Active-Pen Performance contract.

A metric contributes only its formula, numerator, denominator, formatter and
approved metadata. Group resolution, qualifying appearances, sample
validation, evidence, freshness, limitations and fail-closed publication all
belong to :mod:`services.performance_intelligence`.

Adding K%, BB%, K-BB%, HR/9, FIP, xFIP or SIERA later means adding a
``MetricDefinition`` here and registering it — including its own sample
measure, so publication logic never grows a metric-specific branch. No
framework change and, by design, almost no framework test.

M-001 ERA and M-002 WHIP are registered for the Team Board only.

M-001's parameters are approved by D-023 through D-030 and are set here. The
Team Board is its sole approved public surface; SC-05, Team State, Share Card,
and every other surface remain blocked.
"""

from __future__ import annotations

from services.performance_intelligence import (
    AppearanceComponents,
    MetricDefinition,
    registry,
)


METRIC_CURRENT_ACTIVE_PEN_ERA = 'M-001'
METRIC_CURRENT_ACTIVE_PEN_WHIP = 'M-002'

# ERA over integer recorded outs. The canonical convention already in
# production-internal use (season_bullpen_aggregation_2026._era_components) is
# earned_runs * 27 / outs — nine innings expressed in the outs authority of
# D-008 — refusing at a zero denominator. It is reused verbatim rather than
# restated, so the two cannot drift.
ERA_INNINGS_MULTIPLIER = 27
ERA_DENOMINATOR_ZERO = 'era_denominator_zero'

# APPROVED MINIMUM SAMPLE — D-023.
#
# 108 recorded outs, which is exactly 36.0 innings. Derived, not chosen: one
# earned run moves the value by exactly 27/outs, and 108 is the smallest
# whole-out sample at which a single earned run cannot move the published
# number by more than 0.25 — the smallest difference between two bullpens a
# baseball reader would treat as meaningful.
#
# The threshold is counted in RECORDED OUTS, the metric's own denominator unit,
# never in appearances. Ten one-out appearances is ten outs; an appearance gate
# would admit a sample the rate cannot support and would hold back a bullpen
# that has thrown real innings in fewer outings.
#
# The value never travels alone. Its unit and its authorizing decision are
# carried with it so no surface ever renders an unexplained threshold, and the
# registry refuses a threshold missing either one.
ERA_MINIMUM_SAMPLE = 108
ERA_MINIMUM_SAMPLE_UNIT = 'recorded_outs'
ERA_MINIMUM_SAMPLE_AUTHORITY = 'D-023'

ERA_DENOMINATOR_AUTHORITY = 'D-024'
ERA_ROUNDING_AUTHORITY = 'D-025'
ERA_BELOW_SAMPLE_LANGUAGE_AUTHORITY = 'D-026'
ERA_EVIDENCE_AUTHORITY = 'D-029'

# D-026. Never rendered without the group's current innings and the required
# innings beside it — a bare label is an unexplained threshold. `Limited Read`
# and `Unavailable` are governed arm-read labels about a single pitcher and are
# not reused here; `Monitor` is an internal state carrying an implied
# instruction.
ERA_BELOW_SAMPLE_WORDING = 'Not Enough Innings Yet'

# D-028. Backend keys own semantic identity; the public catalog owns rendered
# language. The registry identity and the internal name do not change.
ERA_PUBLIC_NAME = 'Active Bullpen ERA'
ERA_INTERNAL_NAME = 'Current Active-Pen ERA'

ERA_METHOD_VERSION = '1.1.0'
ERA_EFFECTIVE_DATE = '2026-07-30'

# D-025. Two decimal places, always, including trailing zeros.
ERA_DISPLAY_PRECISION = 2

# Independently approved for M-002 by the August 21 WHIP decision. It equals
# M-001's 108-out floor because both rates observe the same group, window, and
# innings denominator, not because ERA qualification automatically transfers.
# At 108 outs one additional hit or walk moves WHIP by 3/108 (0.0278 before
# display rounding), bounding single-event sensitivity to less than 0.03.
WHIP_INNINGS_MULTIPLIER = 3
WHIP_DENOMINATOR_ZERO = 'whip_denominator_zero'
WHIP_MINIMUM_SAMPLE = 108
WHIP_MINIMUM_SAMPLE_UNIT = 'recorded_outs'
WHIP_MINIMUM_SAMPLE_AUTHORITY = (
    '2026-08-21-team-board-active-bullpen-whip'
)
WHIP_DENOMINATOR_AUTHORITY = WHIP_MINIMUM_SAMPLE_AUTHORITY
WHIP_ROUNDING_AUTHORITY = WHIP_MINIMUM_SAMPLE_AUTHORITY
WHIP_BELOW_SAMPLE_LANGUAGE_AUTHORITY = WHIP_MINIMUM_SAMPLE_AUTHORITY
WHIP_EVIDENCE_AUTHORITY = WHIP_MINIMUM_SAMPLE_AUTHORITY
WHIP_BELOW_SAMPLE_WORDING = 'Not Enough Innings Yet'
WHIP_PUBLIC_NAME = 'Active Bullpen WHIP'
WHIP_INTERNAL_NAME = 'Current Active-Pen WHIP'
WHIP_METHOD_VERSION = '1.0.0'
WHIP_EFFECTIVE_DATE = '2026-08-21'
WHIP_DISPLAY_PRECISION = 2


def _era_numerator(components: AppearanceComponents) -> int:
    return int(components.earned_runs) * ERA_INNINGS_MULTIPLIER


def _era_denominator(components: AppearanceComponents) -> int:
    return int(components.outs)


def _era_sample_measure(components: AppearanceComponents) -> int:
    """ERA's sample is counted in the same unit as its denominator (D-023)."""
    return int(components.outs)


def _era_formatter(value):
    """The fixed-precision string, unchanged. Never a placeholder.

    The single rounding already happened in the framework. This returns what it
    produced verbatim so trailing zeros survive and no second rounding can
    occur. A real ``'0.00'`` passes through as a value.
    """
    return None if value is None else str(value)


def _whip_numerator(components: AppearanceComponents) -> int:
    return int(components.hits + components.walks) * WHIP_INNINGS_MULTIPLIER


def _whip_denominator(components: AppearanceComponents) -> int:
    return int(components.outs)


def _whip_sample_measure(components: AppearanceComponents) -> int:
    return int(components.outs)


def _whip_formatter(value):
    return None if value is None else str(value)


CURRENT_ACTIVE_PEN_ERA = MetricDefinition(
    metric_id=METRIC_CURRENT_ACTIVE_PEN_ERA,
    public_name=ERA_PUBLIC_NAME,
    internal_name=ERA_INTERNAL_NAME,
    version=ERA_METHOD_VERSION,
    effective_date=ERA_EFFECTIVE_DATE,
    formula='earned_runs * 27 / recorded_outs',
    numerator=_era_numerator,
    denominator=_era_denominator,
    formatter=_era_formatter,
    denominator_zero_reason=ERA_DENOMINATOR_ZERO,
    evidence_requirements=(
        'official_completed_pitching_line',
        'appearance_team_authority',
        'governed_bullpen_population',
        'canonical_completed_game_authority',
    ),
    # ERA cannot be computed without these. A missing or malformed value in
    # either refuses the read rather than becoming a zero.
    required_row_components=('innings_pitched_outs', 'earned_runs'),
    minimum_sample=ERA_MINIMUM_SAMPLE,
    minimum_sample_unit=ERA_MINIMUM_SAMPLE_UNIT,
    minimum_sample_authority=ERA_MINIMUM_SAMPLE_AUTHORITY,
    sample_measure=_era_sample_measure,
    display_precision=ERA_DISPLAY_PRECISION,
    denominator_authority=ERA_DENOMINATOR_AUTHORITY,
    rounding_authority=ERA_ROUNDING_AUTHORITY,
    below_sample_language_authority=ERA_BELOW_SAMPLE_LANGUAGE_AUTHORITY,
    below_sample_public_wording=ERA_BELOW_SAMPLE_WORDING,
    evidence_authority=ERA_EVIDENCE_AUTHORITY,
    approved_surfaces=('team_board',),
)


CURRENT_ACTIVE_PEN_WHIP = MetricDefinition(
    metric_id=METRIC_CURRENT_ACTIVE_PEN_WHIP,
    public_name=WHIP_PUBLIC_NAME,
    internal_name=WHIP_INTERNAL_NAME,
    version=WHIP_METHOD_VERSION,
    effective_date=WHIP_EFFECTIVE_DATE,
    formula='(walks + hits_allowed) * 3 / recorded_outs',
    numerator=_whip_numerator,
    denominator=_whip_denominator,
    formatter=_whip_formatter,
    denominator_zero_reason=WHIP_DENOMINATOR_ZERO,
    evidence_requirements=(
        'official_completed_pitching_line',
        'official_hits_allowed',
        'official_base_on_balls',
        'appearance_team_authority',
        'governed_bullpen_population',
        'canonical_completed_game_authority',
    ),
    required_row_components=(
        'innings_pitched_outs',
        'hits_allowed',
        'walks',
    ),
    minimum_sample=WHIP_MINIMUM_SAMPLE,
    minimum_sample_unit=WHIP_MINIMUM_SAMPLE_UNIT,
    minimum_sample_authority=WHIP_MINIMUM_SAMPLE_AUTHORITY,
    sample_measure=_whip_sample_measure,
    display_precision=WHIP_DISPLAY_PRECISION,
    denominator_authority=WHIP_DENOMINATOR_AUTHORITY,
    rounding_authority=WHIP_ROUNDING_AUTHORITY,
    below_sample_language_authority=WHIP_BELOW_SAMPLE_LANGUAGE_AUTHORITY,
    below_sample_public_wording=WHIP_BELOW_SAMPLE_WORDING,
    evidence_authority=WHIP_EVIDENCE_AUTHORITY,
    approved_surfaces=('team_board',),
)


def register_approved_metrics():
    """Idempotent registration of every approved metric."""
    if registry.get(METRIC_CURRENT_ACTIVE_PEN_ERA) is None:
        registry.register(CURRENT_ACTIVE_PEN_ERA)
    if registry.get(METRIC_CURRENT_ACTIVE_PEN_WHIP) is None:
        registry.register(CURRENT_ACTIVE_PEN_WHIP)
    return registry


register_approved_metrics()
