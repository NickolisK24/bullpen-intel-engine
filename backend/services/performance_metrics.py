"""Registered metrics under the Current Active-Pen Performance contract.

A metric contributes only its formula, numerator, denominator, formatter and
approved metadata. Group resolution, qualifying appearances, sample
validation, evidence, freshness, limitations and fail-closed publication all
belong to :mod:`services.performance_intelligence`.

Adding WHIP, K%, BB%, K-BB%, HR/9, FIP, xFIP or SIERA later means adding a
``MetricDefinition`` here and registering it. No framework change and, by
design, almost no framework test.

Only M-001 is registered. No other metric is approved.
"""

from __future__ import annotations

from services.performance_intelligence import (
    AppearanceComponents,
    MetricDefinition,
    registry,
)


METRIC_CURRENT_ACTIVE_PEN_ERA = 'M-001'

# ERA over integer recorded outs. The canonical convention already in
# production-internal use (season_bullpen_aggregation_2026._era_components) is
# earned_runs * 27 / outs — nine innings expressed in the outs authority of
# D-008 — refusing at a zero denominator. It is reused verbatim rather than
# restated, so the two cannot drift.
ERA_INNINGS_MULTIPLIER = 27
ERA_DENOMINATOR_ZERO = 'era_denominator_zero'

# NO APPROVED MINIMUM SAMPLE EXISTS.
#
# The Current Active-Pen Performance Contract explicitly leaves M-001's
# minimum sample undecided, and records that inventing one would create the
# kind of unexplained number the Constitution prohibits. baseline_engine's
# MIN_SAMPLE_COUNT governs baseline-distribution interpretation and the
# bullpen_eligibility constants govern roster eligibility; neither authorizes a
# performance threshold.
#
# None is therefore an explicit absence, not a default of zero. The framework
# refuses to publish while it holds. Approving a threshold is a governed
# decision that sets this value and its authority together.
ERA_MINIMUM_SAMPLE = None
ERA_MINIMUM_SAMPLE_AUTHORITY = None


def _era_numerator(components: AppearanceComponents) -> int:
    return int(components.earned_runs) * ERA_INNINGS_MULTIPLIER


def _era_denominator(components: AppearanceComponents) -> int:
    return int(components.outs)


def _era_formatter(value):
    """Two decimal places, or nothing at all. Never a placeholder."""
    return None if value is None else str(value)


CURRENT_ACTIVE_PEN_ERA = MetricDefinition(
    metric_id=METRIC_CURRENT_ACTIVE_PEN_ERA,
    public_name='Current Active-Pen ERA',
    version='1.0.0',
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
    minimum_sample_authority=ERA_MINIMUM_SAMPLE_AUTHORITY,
)


def register_approved_metrics():
    """Idempotent registration of every approved metric."""
    if registry.get(METRIC_CURRENT_ACTIVE_PEN_ERA) is None:
        registry.register(CURRENT_ACTIVE_PEN_ERA)
    return registry


register_approved_metrics()
