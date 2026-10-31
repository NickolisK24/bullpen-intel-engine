"""Baseball plausibility checks for a Team State publication (WP-0.1, EOS-004).

The existing publication gates prove structure and completeness. They did not
catch October 2026, when idle and eliminated clubs drifted to Vulnerable for
weeks: the only distribution check fired when *no* club was Fresh, and it was
advisory. These checks target that failure family and run inside the
mandatory pre-trust Team State proof, before the publication pointer moves.

Two severities:

``block``
    A deterministic contradiction. The candidate is not published; the
    previous trusted snapshot keeps serving. Raised as
    :class:`TeamStatePlausibilityBlocked`.

    * ``inactive_club_published_as_current`` - a club the competition status
      authority says is not in active competition carries a public state.
    * ``inactivity_counted_as_constraint`` - an arm whose only evidence is
      "no appearance inside the freshness window" reads Watch Arm or Limited
      Rest (the October failure mode at arm level).
    * ``represented_date_contradiction`` - a club's competition status was
      evaluated for a different date than the read it gates.

``warn``
    A statistical anomaly that can be legitimate. Recorded in the durable
    proof and surfaced as ``PASS_WITH_INCONCLUSIVE``; never blocks.

    * ``majority_vulnerable`` - more than half of at least
      ``MIN_PUBLISHED_FOR_DISTRIBUTION_CHECKS`` published clubs are Vulnerable.
    * ``vulnerable_shift`` - at least half of the clubs published in both this
      and the previous publication moved toward Vulnerable at once.
    * ``arm_read_team_state_mismatch`` - a club's clean partition count differs
      from its Clean Option arm reads.
    * ``season_context_missing`` - a published state carries no competition
      status (a resolver that predates WP-0.1).
    * ``competition_status_lookup_failed`` - one club's competition authority
      could not be read. That club is already withheld as unconfirmed (and if
      it carried a public state, ``inactive_club_published_as_current``
      blocks), so the other clubs still publish.
    * ``final_game_after_data_through`` - the schedule shows a club's final
      game after the publication's data-through date. This is normally
      ingestion lag (a game final before its appearances are ingested), so it
      is surfaced rather than blocking the previous-day read.

Distribution checks count only clubs that publish a current state, so the
postseason (when most clubs are correctly withheld) cannot trip them.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, Optional


CONTRACT = 'team_state_publication_plausibility_v1'

SEVERITY_BLOCK = 'block'
SEVERITY_WARN = 'warn'

CHECK_INACTIVE_CLUB_CURRENT = 'inactive_club_published_as_current'
CHECK_INACTIVITY_CONSTRAINT = 'inactivity_counted_as_constraint'
CHECK_LOOKUP_FAILED = 'competition_status_lookup_failed'
CHECK_DATE_CONTRADICTION = 'represented_date_contradiction'
CHECK_FINAL_AFTER_DATA_THROUGH = 'final_game_after_data_through'
CHECK_MAJORITY_VULNERABLE = 'majority_vulnerable'
CHECK_VULNERABLE_SHIFT = 'vulnerable_shift'
CHECK_ARM_TEAM_MISMATCH = 'arm_read_team_state_mismatch'
CHECK_SEASON_CONTEXT_MISSING = 'season_context_missing'

MIN_PUBLISHED_FOR_DISTRIBUTION_CHECKS = 8
CONSTRAINT_ARM_READ_KEYS = frozenset({'watch_arm', 'rest_restricted'})
CLEAN_ARM_READ_KEY = 'clean_option'
STATE_ORDER = {'fresh': 0, 'stretched': 1, 'vulnerable': 2}


class TeamStatePlausibilityBlocked(ValueError):
    """A candidate publication contradicts itself; carries every finding."""

    def __init__(self, message, *, evidence):
        super().__init__(message)
        self.publication_evidence = dict(evidence)


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _finding(check, severity, team_ids=(), detail=None, **extra):
    return {
        'check': check,
        'severity': severity,
        'team_ids': sorted(int(team_id) for team_id in team_ids),
        'detail': detail,
        **extra,
    }


def _parse_date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def evaluate_publication_plausibility(
    teams: Iterable[Mapping[str, Any]],
    *,
    data_through=None,
    previous_states: Optional[Mapping[int, Optional[str]]] = None,
) -> dict:
    """Evaluate one candidate publication.

    ``teams`` are per-club entries with ``team_id``, ``public_state`` (``None``
    when withheld), ``season_context`` (the competition status block or
    ``None``), ``availability_reference_date``, ``partition`` (the Team State
    partition counts) and ``arm_reads`` (frozen public arm reads with
    ``public_read.key`` and ``evidence_state.data_state``; may be empty when
    not captured). ``previous_states`` maps team id to the previous
    publication's public state for clubs that had one.
    """
    teams = [_mapping(team) for team in teams or ()]
    represented = _parse_date(data_through)
    findings = []

    inactive_current = []
    lookup_failed = []
    date_contradictions = []
    final_after_data_through = []
    missing_context = []
    inactivity_constraint = {}
    mismatched = []

    for team in teams:
        team_id = int(team['team_id'])
        public_state = team.get('public_state')
        context = team.get('season_context')
        if isinstance(context, Mapping):
            if context.get('basis') == 'competition_status_lookup_failed':
                lookup_failed.append(team_id)
            if context.get('status') != 'active' and public_state is not None:
                inactive_current.append(team_id)
            last_final = _parse_date(context.get('last_final_game_date'))
            if represented is not None and last_final is not None and last_final > represented:
                final_after_data_through.append(team_id)
            reference = context.get('reference_date')
            expected_reference = _iso(team.get('availability_reference_date'))
            if reference and expected_reference and reference != expected_reference:
                date_contradictions.append(team_id)
        elif public_state is not None:
            missing_context.append(team_id)

        arm_reads = [_mapping(arm) for arm in team.get('arm_reads') or ()]
        stale_constrained = [
            arm.get('pitcher_id') for arm in arm_reads
            if _mapping(arm.get('evidence_state')).get('data_state') == 'stale'
            and _mapping(arm.get('public_read')).get('key') in CONSTRAINT_ARM_READ_KEYS
        ]
        if stale_constrained:
            inactivity_constraint[team_id] = stale_constrained

        partition = _mapping(team.get('partition'))
        clean_count = partition.get('clean_count')
        if arm_reads and isinstance(clean_count, int) and public_state is not None:
            clean_reads = sum(
                1 for arm in arm_reads
                if _mapping(arm.get('public_read')).get('key') == CLEAN_ARM_READ_KEY
            )
            if clean_reads != clean_count:
                mismatched.append(team_id)

    if inactive_current:
        findings.append(_finding(
            CHECK_INACTIVE_CLUB_CURRENT, SEVERITY_BLOCK, inactive_current,
            'Clubs not in active competition carry a current Team State.',
        ))
    if inactivity_constraint:
        findings.append(_finding(
            CHECK_INACTIVITY_CONSTRAINT, SEVERITY_BLOCK, inactivity_constraint,
            'Arms with no appearance inside the freshness window read as constrained.',
            pitcher_ids_by_team={
                str(team_id): sorted(ids) for team_id, ids in inactivity_constraint.items()
            },
        ))
    if lookup_failed:
        findings.append(_finding(
            CHECK_LOOKUP_FAILED, SEVERITY_WARN, lookup_failed,
            'Club competition status could not be read from stored authority.',
        ))
    if date_contradictions:
        findings.append(_finding(
            CHECK_DATE_CONTRADICTION, SEVERITY_BLOCK, set(date_contradictions),
            'Competition context contradicts the represented baseball date.',
        ))
    if final_after_data_through:
        findings.append(_finding(
            CHECK_FINAL_AFTER_DATA_THROUGH, SEVERITY_WARN, final_after_data_through,
            'The schedule shows a final game after the represented data-through date.',
        ))
    if missing_context:
        findings.append(_finding(
            CHECK_SEASON_CONTEXT_MISSING, SEVERITY_WARN, missing_context,
            'Published states carry no club competition status.',
        ))
    if mismatched:
        findings.append(_finding(
            CHECK_ARM_TEAM_MISMATCH, SEVERITY_WARN, mismatched,
            'Clean partition count differs from Clean Option arm reads.',
        ))

    published = {
        int(team['team_id']): team.get('public_state')
        for team in teams
        if team.get('public_state') in STATE_ORDER
    }
    vulnerable = [team_id for team_id, state in published.items() if state == 'vulnerable']
    if (
        len(published) >= MIN_PUBLISHED_FOR_DISTRIBUTION_CHECKS
        and len(vulnerable) * 2 > len(published)
    ):
        findings.append(_finding(
            CHECK_MAJORITY_VULNERABLE, SEVERITY_WARN, vulnerable,
            f'{len(vulnerable)}/{len(published)} published clubs are Vulnerable.',
        ))

    previous = {
        int(team_id): state for team_id, state in (previous_states or {}).items()
        if state in STATE_ORDER
    }
    comparable = sorted(set(previous) & set(published))
    worsened = [
        team_id for team_id in comparable
        if STATE_ORDER[published[team_id]] > STATE_ORDER[previous[team_id]]
    ]
    if (
        len(comparable) >= MIN_PUBLISHED_FOR_DISTRIBUTION_CHECKS
        and len(worsened) * 2 >= len(comparable)
    ):
        findings.append(_finding(
            CHECK_VULNERABLE_SHIFT, SEVERITY_WARN, worsened,
            f'{len(worsened)}/{len(comparable)} comparable clubs moved toward Vulnerable.',
        ))

    blocking = [item for item in findings if item['severity'] == SEVERITY_BLOCK]
    warnings = [item for item in findings if item['severity'] == SEVERITY_WARN]
    return {
        'contract': CONTRACT,
        'data_through': _iso(represented),
        'published_team_count': len(published),
        'withheld_team_count': len(teams) - len(published),
        'blocked': bool(blocking),
        'blocking_checks': sorted({item['check'] for item in blocking}),
        'warning_checks': sorted({item['check'] for item in warnings}),
        'findings': findings,
    }


def require_publication_plausibility(result: Mapping[str, Any]) -> None:
    """Raise when any blocking check failed; the caller's transaction aborts."""
    if result.get('blocked'):
        raise TeamStatePlausibilityBlocked(
            'team_state_publication_implausible:' + ','.join(result.get('blocking_checks') or ()),
            evidence=result,
        )
