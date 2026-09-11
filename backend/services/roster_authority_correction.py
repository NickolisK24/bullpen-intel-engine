"""SP-05 append-only correction of claims accepted under the pre-R1 boundary."""

from models.repair_request import RepairRequest
from models.roster_membership import RosterMembershipInterval
from models.source_observation import SourceObservation, SourceSubject, SourcePayloadArtifact
from services.mlb_club_directory import MLB_TEAM_IDS
from services.roster_authority_scope import MLB_MEMBERSHIP_TYPES, classify_roster_team
from utils.db import db


def observation_scope(observation):
    subject = db.session.get(SourceSubject, observation.source_subject_id)
    if subject.source_domain != 'roster' or subject.provider != 'mlb_stats_api':
        return None, None, []
    parameters = subject.request_parameters or {}
    team_id = parameters.get('teamId')
    roster_type = parameters.get('rosterType')
    if team_id is None or subject.subject_key != f'{int(team_id)}:{roster_type}':
        return None, None, []
    artifact = db.session.get(SourcePayloadArtifact, observation.payload_artifact_id)
    records = (artifact.payload_json or {}).get('records') if artifact else None
    if not isinstance(records, list) or len(records) != observation.record_count:
        return None, subject, []
    return classify_roster_team(team_id, records=records), subject, records


def correct_roster_authority(
    team_id, roster_date, *, observations, entries_by_type, repair_request_id,
    sync_run_id, timestamp,
):
    """Only an applied, bounded SP-13 roster request may correct prior history.

    Affiliate claims are voided, not reinterpreted as proven assignment history.
    A false MLB closure needs retained complete MLB inclusion on its boundary
    date. Later dated MLB absence remains authoritative; it is never reopened.
    """
    from services.roster_transaction_authority import supersede_membership_interval, _pitcher_entries

    request = db.session.get(RepairRequest, int(repair_request_id))
    scope = (request.scope_json or {}) if request else {}
    teams = set(scope.get('team_ids') or []) | ({scope['team_id']} if scope.get('team_id') else set())
    if (
        request is None or request.dry_run or request.source_domain != 'roster'
        or request.status != 'running' or team_id not in teams
        or not request.baseball_date_start <= roster_date <= request.baseball_date_end
        or team_id not in MLB_TEAM_IDS
    ):
        raise ValueError('Roster history correction requires a running applied SP-13 request for this club/date')

    reason = f'AUDIT-R1: affiliate source cannot own MLB membership; SP-13 request {request.id}'
    mutations = []
    rows = RosterMembershipInterval.query.filter(
        RosterMembershipInterval.is_current_version.is_(True),
        RosterMembershipInterval.is_void.is_(False),
        RosterMembershipInterval.membership_type.in_(MLB_MEMBERSHIP_TYPES),
        db.or_(RosterMembershipInterval.team_id == team_id,
               RosterMembershipInterval.team_id.notin_(MLB_TEAM_IDS)),
    ).order_by(RosterMembershipInterval.id).with_for_update().all()
    # Void erroneous affiliate claims before restoring the MLB intervals.
    for prior in rows:
        if prior.team_id in MLB_TEAM_IDS:
            continue
        opening = db.session.get(SourceObservation, prior.opened_by_observation_id)
        ownership, subject, records = observation_scope(opening)
        if not ownership or ownership['mlb_parent_id'] != team_id:
            continue
        if ownership['authority_conflict'] or ownership['requested_team_id'] != prior.team_id:
            raise ValueError(f'Unresolved affiliate ownership on interval {prior.id}')
        corrected, mutation = supersede_membership_interval(
            prior.id, source_observation_id=opening.id, correction_reason=reason,
            is_void=True, organization_id=team_id, sync_run_id=sync_run_id,
            timestamp=timestamp, commit=False,
        )
        # This correction removes a false claim about the parent organization.
        # It does not dispatch a new affiliate baseball-intelligence cohort.
        mutation.team_id = team_id
        mutation.baseball_date = roster_date
        mutations.append(mutation)
        pitcher = prior.pitcher
        if pitcher.team_id == prior.team_id:
            pitcher.team_id = team_id
            pitcher.team_assignment_status = 'assigned'
            pitcher.team_assignment_source = 'official_affiliate_parent_v1'
            pitcher.team_assignment_updated_at = timestamp
            pitcher.updated_at = timestamp

    for prior in rows:
        if prior.team_id != team_id or prior.closed_by_observation_id is None:
            continue
        closing = db.session.get(SourceObservation, prior.closed_by_observation_id)
        ownership, closing_subject, _ = observation_scope(closing)
        if not ownership or ownership['requested_team_id'] in MLB_TEAM_IDS:
            continue
        roster_type = 'active' if prior.membership_type == 'active_roster' else '40Man'
        history = (
            db.session.query(SourceObservation, SourceSubject)
            .join(SourceSubject, SourceSubject.id == SourceObservation.source_subject_id)
            .filter(SourceSubject.subject_key == f'{team_id}:{roster_type}',
                    SourceSubject.baseball_date >= prior.effective_end_date,
                    SourceSubject.baseball_date <= roster_date,
                    SourceObservation.is_authoritative.is_(True),
                    SourceObservation.completeness == 'complete')
            .order_by(SourceSubject.baseball_date, SourceObservation.id).all()
        )
        latest_by_date = {}
        for observation, subject in history:
            authority, _, records = observation_scope(observation)
            if authority and authority['mlb_membership_authority']:
                latest_by_date[subject.baseball_date] = (observation, _pitcher_entries(records))
        boundary = latest_by_date.get(prior.effective_end_date)
        if boundary is None or prior.player_mlb_id not in boundary[1]:
            raise ValueError(f'Cannot prove historical MLB inclusion at false closure of interval {prior.id}')
        removal = next((
            (day, observation) for day, (observation, members) in sorted(latest_by_date.items())
            if prior.player_mlb_id not in members
        ), None)
        # Do not bridge an independently reacquired stint without explicit review.
        overlaps = RosterMembershipInterval.query.filter(
            RosterMembershipInterval.id != prior.id,
            RosterMembershipInterval.pitcher_id == prior.pitcher_id,
            RosterMembershipInterval.team_id == team_id,
            RosterMembershipInterval.membership_type == prior.membership_type,
            RosterMembershipInterval.is_current_version.is_(True),
            RosterMembershipInterval.is_void.is_(False),
            RosterMembershipInterval.effective_start_date >= prior.effective_end_date,
        ).all()
        if overlaps:
            raise ValueError(f'Additional stint needs governed correction review for interval {prior.id}')
        corrected, mutation = supersede_membership_interval(
            prior.id, source_observation_id=(boundary[0].id if removal else observations[prior.membership_type].id),
            correction_reason=reason, reopen=removal is None,
            effective_end_date=removal[0] if removal else None,
            organization_id=team_id, sync_run_id=sync_run_id, timestamp=timestamp, commit=False,
        )
        if removal:
            corrected.closed_by_observation_id = removal[1].id
        mutation.baseball_date = roster_date
        mutations.append(mutation)
    return mutations
