"""Current Active-Pen Performance intelligence framework (D-021).

One reusable family that answers a single baseball question: how have the
pitchers who make up a team's active bullpen *today* performed in official
completed games *for this team*?

The framework owns everything that is a FAMILY question — active-group
resolution, qualifying-appearance resolution, sample validation, evidence
construction, freshness, limitations, and fail-closed publication. A metric
contributes only what is genuinely per-metric: its formula, its numerator and
denominator over the shared components, its formatting, and its approved
metadata. Adding WHIP, K%, BB%, HR/9 or FIP later is a registry entry, not a
new service.

Two authorities are evaluated at two different times, and conflating them is
the failure mode this contract exists to prevent:

  * WHO IS IN THE GROUP is a current-roster question, resolved as of the
    represented baseball date from the governed bullpen population.
  * WHICH APPEARANCES QUALIFY is a historical question, owned by
    ``GameLog.appearance_team_id`` (Foundation 1). Current team is never an
    attribution source, so a pitcher acquired in July brings his appearances
    FOR THIS TEAM into the window and leaves his prior organization's
    appearances where they belong.

Nothing here is public. The contract keeps SC-05, ``public_reader_gate``,
``team_state_performance_gate`` and ``share_card_performance_gate`` blocked,
and this module publishes no metric until its definitional parameters are
approved by a governed decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from models.game_log import GameLog
from services import bullpen_population
# THE canonical completed-game authority. season_bullpen_aggregation_2026 owns
# schedule-authority classification for appearance aggregation, including the
# distinction between a legitimately non-final game and missing authority. It
# is reused here rather than reimplemented: a second finality classifier is
# exactly how two surfaces come to disagree about whether a game happened.
from services import season_bullpen_aggregation_2026 as schedule_authority
from utils.db import db
from utils.games_started import RELIEF, START, UNKNOWN, games_started_state


CAPABILITY = 'current_active_pen_performance'
FAMILY_ID = 'current_active_pen_performance'
CONTRACT_DECISION = 'D-021'

# Historical appearance ownership. Current Pitcher.team_id is forbidden as an
# attribution source; it is used only to resolve CURRENT group membership.
APPEARANCE_TEAM_RESOLVED = GameLog.APPEARANCE_TEAM_RESOLVED
REGULAR_SEASON_GAME_TYPE = 'R'

# ── Governed refusal reasons ────────────────────────────────────────────────
# The family fails closed. It never publishes zero, a previous value, an
# estimate, or a league substitute in place of a value it cannot support.
REFUSAL_UNKNOWN_METRIC = 'metric_not_registered'
REFUSAL_ACTIVE_GROUP_EMPTY = 'active_group_empty'
REFUSAL_NO_QUALIFYING_APPEARANCES = 'no_qualifying_appearances'
REFUSAL_MINIMUM_SAMPLE_UNAPPROVED = 'minimum_sample_not_approved'
REFUSAL_BELOW_MINIMUM_SAMPLE = 'below_minimum_sample'
REFUSAL_QUALIFYING_ROW_INVALID = 'qualifying_row_invalid'

# Row-level reason codes. The first four mirror the canonical dispositions in
# season_bullpen_aggregation_2026._classify_row so the two cannot diverge; the
# component codes carry the unknowns-stay-unknown rule for metric inputs.
ROW_SCHEDULE_AUTHORITY_MISSING = 'schedule_authority_missing'
ROW_CONTRADICTORY_GAME_AUTHORITY = 'contradictory_game_authority'
ROW_APPEARANCE_TEAM_NOT_IN_GAME = 'appearance_team_not_in_game'
ROW_STARTER_IDENTITY_UNKNOWN = 'starter_identity_unknown'
ROW_COMPONENT_MISSING = 'required_component_missing'
ROW_COMPONENT_MALFORMED = 'required_component_malformed'
ROW_IDENTITY_MISSING = 'required_identity_missing'

# Harmless exclusions: the row simply does not qualify. Deliberately distinct
# from the blocking codes above so the two can never be confused.
ROW_GAME_NOT_FINAL = 'game_not_final'
ROW_STARTER_EXCLUDED = 'starter_excluded'

# Every gate this family touches stays blocked. D-021 opens none of them.
BLOCKED_GATES = {
    'public_reader_gate': 'blocked',
    'team_state_performance_gate': 'blocked',
    'share_card_performance_gate': 'blocked',
}


# ── Shared components every metric reads from ───────────────────────────────
@dataclass(frozen=True)
class AppearanceComponents:
    """Official totals over the qualifying appearance set.

    Integer outs are the innings authority (D-008); decimal innings are
    display-only and never define a denominator.
    """

    appearances: int = 0
    pitchers: int = 0
    outs: int = 0
    earned_runs: int = 0
    runs: int = 0
    hits: int = 0
    walks: int = 0
    strikeouts: int = 0
    home_runs: int = 0
    batters_faced: int = 0


@dataclass(frozen=True)
class MetricDefinition:
    """What a metric contributes. The framework owns everything else.

    ``minimum_sample`` is ``None`` when no governed decision has approved a
    threshold. That is not a default of zero — it is an explicit absence, and
    the framework refuses to publish the metric while it holds.
    """

    metric_id: str
    public_name: str
    version: str
    formula: str
    numerator: Callable[[AppearanceComponents], int]
    denominator: Callable[[AppearanceComponents], int]
    formatter: Callable[[Optional[str]], Optional[str]]
    denominator_zero_reason: str
    evidence_requirements: tuple = ()
    # Per-row source fields this metric cannot be computed without. A missing
    # or malformed value in any of them refuses the read; it never becomes a
    # zero that quietly moves the published number.
    required_row_components: tuple = ()
    minimum_sample: Optional[int] = None
    minimum_sample_authority: Optional[str] = None
    family_id: str = FAMILY_ID


class MetricRegistry:
    """Registration is the whole integration surface for a future metric."""

    def __init__(self):
        self._metrics = {}

    def register(self, definition: MetricDefinition) -> MetricDefinition:
        if definition.metric_id in self._metrics:
            raise ValueError(f'Metric already registered: {definition.metric_id}')
        self._metrics[definition.metric_id] = definition
        return definition

    def get(self, metric_id: str) -> Optional[MetricDefinition]:
        return self._metrics.get(metric_id)

    def metric_ids(self) -> list:
        return sorted(self._metrics)

    def clear(self):
        self._metrics.clear()


registry = MetricRegistry()


# ── Active group: a CURRENT-roster question ─────────────────────────────────
def resolve_active_group(team_id, *, reference_date=None):
    """Today's active bullpen for one team, from the governed population.

    Delegates to the existing bullpen-population authority rather than
    reimplementing membership, so every surface resolves the same group. This
    is the one place ``Pitcher.team_id`` legitimately participates, because
    the question asked is current membership — never appearance ownership.
    """
    pitchers = bullpen_population.eligible_bullpen_pitchers(
        team_id,
        reference_date=reference_date,
    )
    members = [
        {
            'pitcher_id': p.id,
            'pitcher_mlb_id': getattr(p, 'mlb_id', None),
            'pitcher_full_name': getattr(p, 'full_name', None),
        }
        for p in pitchers
        if getattr(p, 'id', None) is not None
    ]
    return {
        'team_id': team_id,
        'reference_date': reference_date.isoformat() if reference_date else None,
        'membership_authority': 'governed_bullpen_population',
        'pitcher_ids': [m['pitcher_id'] for m in members],
        'members': members,
        'size': len(members),
    }


# ── Row validation: unknowns stay unknown ──────────────────────────────────
@dataclass(frozen=True)
class RowIssue:
    """Bounded identity for one unusable row. Never a raw payload.

    Carries only the identifiers needed to find the row again — game, pitcher,
    field, reason — so a refusal is diagnosable without leaking stored data.
    """

    mlb_game_pk: Optional[int]
    pitcher_id: Optional[int]
    field: Optional[str]
    reason: str

    def to_dict(self):
        return {
            'mlb_game_pk': self.mlb_game_pk,
            'pitcher_id': self.pitcher_id,
            'field': self.field,
            'reason': self.reason,
        }


@dataclass(frozen=True)
class QualifyingSelection:
    """The outcome of selecting qualifying appearances for one team-season.

    ``blocking`` is what makes this fail closed. A row that cannot be proved
    usable is never silently dropped and never zero-filled: it blocks the whole
    read, because a rate computed over a partially-unknown sample is not the
    rate it claims to be.
    """

    rows: tuple = ()
    excluded: tuple = ()
    blocking: tuple = ()

    @property
    def is_valid(self) -> bool:
        return not self.blocking


def _required_int(value):
    """Strict integer extraction. ``(ok, value)``.

    A real observed zero is valid. ``None``, a non-numeric value, a bool, or a
    negative count is not, and must not be coerced.
    """
    if value is None or isinstance(value, bool):
        return False, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return False, None
    if parsed < 0:
        return False, None
    return True, parsed


def _optional_int(value):
    """Non-required component. Absent contributes nothing and blocks nothing."""
    ok, parsed = _required_int(value)
    return parsed if ok else 0


# ── Qualifying appearances: a HISTORICAL, team-side-owned question ──────────
def qualifying_appearances(
    team_id, pitcher_ids, *, season, through_date=None,
    required_components=(), session=None,
):
    """Select official COMPLETED relief appearances made FOR this team.

    Finality is not asserted by this query; it is proved against the canonical
    schedule authority in ``season_bullpen_aggregation_2026``, and this function
    mirrors that module's dispositions exactly:

      * a legitimately non-final, postponed, suspended-without-final, or
        non-regular-season game is a HARMLESS EXCLUSION — it never qualified;
      * missing schedule authority, contradictory authority, an appearance team
        that did not play the game, and an unprovable starter/relief flag are
        BLOCKING — a canonical read must not omit an in-scope appearance for
        want of authority.
    """
    if not pitcher_ids:
        return QualifyingSelection()

    active_session = session or db.session
    final_games, sched_class = schedule_authority._schedule_authority(
        active_session,
        season=season,
        as_of_date=through_date or date(season, 12, 31),
    )

    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id.in_(sorted(set(pitcher_ids))),
            GameLog.appearance_team_status == APPEARANCE_TEAM_RESOLVED,
            GameLog.appearance_team_id == team_id,
            GameLog.game_date >= date(season, 1, 1),
            GameLog.game_date <= (through_date or date(season, 12, 31)),
        )
        .order_by(GameLog.game_date.asc(), GameLog.id.asc())
        .all()
    )

    rows, excluded, blocking = [], [], []
    for log in logs:
        game_pk = getattr(log, 'mlb_game_pk', None)
        pitcher_id = getattr(log, 'pitcher_id', None)

        def issue(reason, field=None):
            return RowIssue(game_pk, pitcher_id, field, reason)

        if game_pk is None or pitcher_id is None or getattr(log, 'game_date', None) is None:
            blocking.append(issue(ROW_IDENTITY_MISSING))
            continue

        cls = sched_class.get(game_pk)
        if cls is None:
            blocking.append(issue(ROW_SCHEDULE_AUTHORITY_MISSING))
            continue
        if cls == schedule_authority.SCHED_CONTRADICTORY:
            blocking.append(issue(ROW_CONTRADICTORY_GAME_AUTHORITY))
            continue
        if cls == schedule_authority.SCHED_NON_FINAL:
            # In progress, postponed, suspended-without-final, or not 'R'.
            excluded.append(issue(ROW_GAME_NOT_FINAL))
            continue
        if team_id not in final_games[game_pk].team_ids:
            blocking.append(issue(ROW_APPEARANCE_TEAM_NOT_IN_GAME))
            continue

        state = _start_relief_state(log)
        if state == UNKNOWN:
            blocking.append(issue(ROW_STARTER_IDENTITY_UNKNOWN, 'games_started'))
            continue
        if state == START:
            excluded.append(issue(ROW_STARTER_EXCLUDED))
            continue

        row_issue = _validate_required_components(log, required_components, issue)
        if row_issue is not None:
            blocking.append(row_issue)
            continue
        rows.append(log)

    return QualifyingSelection(
        rows=tuple(rows), excluded=tuple(excluded), blocking=tuple(blocking),
    )


def _validate_required_components(log, required_components, issue):
    """Every required source field must be a real, well-formed value."""
    for field_name in required_components:
        raw = getattr(log, field_name, None)
        if raw is None:
            return issue(ROW_COMPONENT_MISSING, field_name)
        ok, _parsed = _required_int(raw)
        if not ok:
            return issue(ROW_COMPONENT_MALFORMED, field_name)
    return None


def _start_relief_state(log):
    try:
        return games_started_state(getattr(log, 'games_started', None))
    except Exception:
        return UNKNOWN


def build_components(logs) -> AppearanceComponents:
    """Totals over rows already proved usable by ``qualifying_appearances``."""
    rows = list(logs or [])
    return AppearanceComponents(
        appearances=len(rows),
        pitchers=len({getattr(r, 'pitcher_id', None) for r in rows} - {None}),
        outs=sum(_optional_int(getattr(r, 'innings_pitched_outs', None)) for r in rows),
        earned_runs=sum(_optional_int(getattr(r, 'earned_runs', None)) for r in rows),
        runs=sum(_optional_int(getattr(r, 'runs_allowed', None)) for r in rows),
        hits=sum(_optional_int(getattr(r, 'hits_allowed', None)) for r in rows),
        walks=sum(_optional_int(getattr(r, 'walks', None)) for r in rows),
        strikeouts=sum(_optional_int(getattr(r, 'strikeouts', None)) for r in rows),
        home_runs=sum(_optional_int(getattr(r, 'home_runs_allowed', None)) for r in rows),
        batters_faced=sum(_optional_int(getattr(r, 'batters_faced', None)) for r in rows),
    )


# ── Execution: one path every metric and every surface shares ───────────────
def build_metric_read(
    metric_id,
    team_id,
    *,
    season,
    reference_date=None,
    through_date=None,
    freshness=None,
):
    """Compute one registered metric for one team's current active pen.

    Returns a structured read carrying the value (when supportable), the
    group, the sample, the represented date, the evidence chain down to
    official completed pitching lines, the limitation, and the publication
    decision. Surfaces render this; none of them recalculates.
    """
    definition = registry.get(metric_id)
    if definition is None:
        return _refusal(metric_id, team_id, REFUSAL_UNKNOWN_METRIC, season=season)

    group = resolve_active_group(team_id, reference_date=reference_date)
    if not group['pitcher_ids']:
        return _refusal(
            metric_id, team_id, REFUSAL_ACTIVE_GROUP_EMPTY,
            season=season, group=group, definition=definition, freshness=freshness,
        )

    selection = qualifying_appearances(
        team_id, group['pitcher_ids'], season=season, through_date=through_date,
        required_components=definition.required_row_components,
    )
    if not selection.is_valid:
        # A row that cannot be proved usable blocks the whole read. Ignoring it
        # or treating it as zero would publish a rate over a sample that is not
        # the sample it claims to be.
        return _refusal(
            metric_id, team_id, REFUSAL_QUALIFYING_ROW_INVALID,
            season=season, group=group, definition=definition,
            freshness=freshness,
            invalid_rows=[i.to_dict() for i in selection.blocking],
        )

    logs = selection.rows
    components = build_components(logs)
    if components.appearances == 0:
        return _refusal(
            metric_id, team_id, REFUSAL_NO_QUALIFYING_APPEARANCES,
            season=season, group=group, definition=definition,
            components=components, freshness=freshness,
        )

    numerator = definition.numerator(components)
    denominator = definition.denominator(components)
    value = None
    reason_code = None
    if denominator <= 0:
        reason_code = definition.denominator_zero_reason
    else:
        value = _exact_ratio(numerator, denominator)

    read = {
        'capability': CAPABILITY,
        'family_id': definition.family_id,
        'contract': CONTRACT_DECISION,
        'metric_id': definition.metric_id,
        'metric_name': definition.public_name,
        'metric_version': definition.version,
        'formula': definition.formula,
        'team_id': team_id,
        'season': season,
        'represented_date': group['reference_date'],
        'value': value,
        'display_value': definition.formatter(value),
        'reason_code': reason_code,
        'exact_numerator': numerator,
        'exact_denominator': denominator,
        'group': group,
        'sample': {
            'appearances': components.appearances,
            'pitchers': components.pitchers,
            'outs': components.outs,
            'minimum_sample': definition.minimum_sample,
            'minimum_sample_authority': definition.minimum_sample_authority,
        },
        'evidence': _evidence(definition, group, components, logs),
        'freshness': freshness,
        'limitations': _limitations(definition, components),
        'gates': dict(BLOCKED_GATES),
    }
    read['publication'] = _publication_decision(definition, read, components)
    return read


def _exact_ratio(numerator, denominator):
    """Exact decimal ratio at two places, matching the canonical convention."""
    from decimal import Decimal, ROUND_HALF_UP

    return str(
        (Decimal(int(numerator)) / Decimal(int(denominator)))
        .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    )


def _evidence(definition, group, components, logs):
    """Summary -> Context -> Evidence -> Official Record, built once.

    Reusable verbatim by Team Board, Compare, Stories and Share Artifacts; none
    of them recalculates, and a frozen artifact keeps what it published.
    """
    return {
        'summary': {
            'metric_id': definition.metric_id,
            'metric_name': definition.public_name,
            'exact_numerator': definition.numerator(components),
            'exact_denominator': definition.denominator(components),
        },
        'context': {
            'group_size': group['size'],
            'membership_authority': group['membership_authority'],
            'appearance_ownership_authority': 'game_log_appearance_team_id',
            'window': 'official completed relief appearances for this team',
            'excluded': ['starts', 'other_organization_appearances',
                         'unresolved_appearance_team', 'non_regular_season'],
        },
        'evidence': [
            {
                'pitcher_id': getattr(log, 'pitcher_id', None),
                'mlb_game_pk': getattr(log, 'mlb_game_pk', None),
                'game_date': (
                    log.game_date.isoformat()
                    if getattr(log, 'game_date', None) else None
                ),
                'appearance_team_id': getattr(log, 'appearance_team_id', None),
                'outs': _optional_int(getattr(log, 'innings_pitched_outs', 0)),
                'earned_runs': _optional_int(getattr(log, 'earned_runs', 0)),
            }
            for log in logs
        ],
        'official_record': {
            'source': 'official_completed_pitching_line',
            'appearance_count': components.appearances,
            'outs': components.outs,
            'earned_runs': components.earned_runs,
        },
        'requirements': list(definition.evidence_requirements),
    }


def _limitations(definition, components):
    limitations = []
    if definition.minimum_sample is None:
        limitations.append(
            'No approved minimum sample exists for this metric, so no '
            'below-sample read is published.'
        )
    limitations.append(
        'Covers only appearances made for this team; a pitcher acquired '
        'mid-season keeps his prior club\'s appearances with that club.'
    )
    limitations.append(
        'Active-bullpen membership comes from the governed bullpen population '
        'as of the represented date and is not yet guaranteed complete for a '
        'newly active arm with no usage-based role evidence.'
    )
    return limitations


def _publication_decision(definition, read, components):
    """Fail closed. A computed value is not automatically a publishable one."""
    if read['value'] is None:
        return {'publishable': False, 'reason': read['reason_code']}
    if definition.minimum_sample is None:
        # The contract deliberately leaves M-001's minimum sample unapproved.
        # Inventing one here would publish an unexplained number.
        return {'publishable': False, 'reason': REFUSAL_MINIMUM_SAMPLE_UNAPPROVED}
    if components.appearances < definition.minimum_sample:
        return {'publishable': False, 'reason': REFUSAL_BELOW_MINIMUM_SAMPLE}
    return {'publishable': False, 'reason': 'public_reader_gate_blocked'}


def _refusal(metric_id, team_id, reason, *, season=None, group=None,
             definition=None, components=None, freshness=None,
             invalid_rows=None):
    payload = {
        'capability': CAPABILITY,
        'family_id': FAMILY_ID,
        'contract': CONTRACT_DECISION,
        'metric_id': metric_id,
        'metric_name': definition.public_name if definition else None,
        'metric_version': definition.version if definition else None,
        'team_id': team_id,
        'season': season,
        'represented_date': (group or {}).get('reference_date'),
        'value': None,
        'display_value': None,
        'reason_code': reason,
        'group': group,
        'sample': {
            'appearances': components.appearances if components else 0,
            'pitchers': components.pitchers if components else 0,
            'outs': components.outs if components else 0,
        },
        'evidence': None,
        'freshness': freshness,
        'limitations': ['No supportable value; nothing is published.'],
        'gates': dict(BLOCKED_GATES),
        'publication': {'publishable': False, 'reason': reason},
    }
    if invalid_rows:
        payload['invalid_rows'] = list(invalid_rows)
    return payload
