"""Offline comparisons against digest-pinned postcommit publication receipts."""

from services.team_state_public_vocabulary import public_team_state
from sync_v3.evidence import encode_json
from sync_v3.public_identities import ObservedIdentityExport


def _field_differences(state, observed):
    delta = {}
    for key in sorted(state.keys() | observed.keys()):
        if key not in state or key not in observed or encode_json(state[key]) != encode_json(observed[key]):
            delta[key] = {source: block[key] for source, block in [('candidate', state), ('archive', observed)]
                          if key in block}
    return delta


def compare_archived_league(listing, reference):
    """Compare one candidate's League Team State blocks with observed publication receipts."""
    if not isinstance(reference, ObservedIdentityExport) or listing['status'] not in ('represented', 'candidate_preview'):
        raise ValueError('Comparison requires an observed publication and a dated candidate League')
    archive_dates = dict(data_through=reference.provenance['data_through'], membership=reference.membership_reference,
                         availability=reference.availability_reference)
    candidate_dates = dict(data_through=listing['data_through'], membership=listing['data_through'],
                           availability=listing['availability_reference'])
    report = dict(scope='historical_league_team_state', generation=listing['generation'], candidate_status=listing['status'],
                  archive=reference.provenance, archive_dates=archive_dates, candidate_dates=candidate_dates,
                  clubs_compared=0, differences={}, current_serving_eligible=False)
    if archive_dates != candidate_dates:
        return dict(report, status='edition_dates_differ')
    teams = {str(item['team_id']): item['team_state'] for item in listing['teams']}
    if len(teams) != len(listing['teams']) or teams.keys() != reference.team_receipts.keys():
        return dict(report, status='club_population_differs')
    for team, state in teams.items():
        receipt = reference.team_receipts[team]
        observed = receipt['value']
        if (not isinstance(observed, dict) or observed.get('contract') != 'team_state_public_v1'
                or (receipt.get('season_context') or {}).get('reference_date') != archive_dates['availability']
                or observed.get('data_through') != archive_dates['data_through']):
            raise ValueError('Observed club receipt disagrees with the publication dates')
        delta = _field_differences(state, observed)
        if delta:
            report['differences'][team] = delta
    return dict(report, clubs_compared=len(teams),
                status='team_state_fields_differ' if report['differences'] else 'team_state_fields_match')


def compare_archived_competition(report, reference):
    """Compare competition evidence on its own date without advancing a candidate edition."""
    if not isinstance(reference, ObservedIdentityExport) or report['retrospective'] is not True:
        raise ValueError('Expected a retrospective competition read and an observed publication')
    result = dict(scope='historical_club_competition', archive=reference.provenance,
                  reference_date=report['reference_date'], archive_reference_date=reference.availability_reference,
                  verified_decisions=len(report['decision_sources']), missing_decisions=report['missing_decisions'],
                  clubs_compared=0, season_complete_projections_compared=0, differences={}, current_serving_eligible=False)
    if report['reference_date'] != reference.availability_reference:
        return dict(result, status='competition_dates_differ')
    clubs = {str(k): v for k, v in report['clubs'].items()}
    if report['calendar_source'] is None or report['missing_decisions'] or clubs.keys() != reference.team_receipts.keys():
        return dict(result, status='incomplete_competition_evidence')
    for club, context in clubs.items():
        if context.get('reference_date') != report['reference_date'] or context.get('team_id') != int(club):
            return dict(result, status='club_reference_mismatch')
    missing_context = sorted(int(club) for club in clubs if reference.team_receipts[club].get('season_context') is None)
    if missing_context:
        withheld = {}
        for team in missing_context:
            key = str(team)
            archived = reference.team_receipts[key]['value']
            context = clubs[key]
            if archived.get('available') is True and context['status'] == 'season_complete':
                projected = public_team_state(dict(season_context=context, freshness=dict(data_through=reference.provenance['data_through'])))
                withheld[key] = dict(archived_label=archived['public_label'], replayed_outcome=projected['outcome'],
                                     replayed_reason=projected['reason_code'])
        return dict(result, status='archived_competition_context_missing', clubs_missing_context=missing_context,
                    archived_claims_withheld_under_replayed_rules=withheld)
    for club in clubs:
        if reference.team_receipts[club]['season_context'].get('reference_date') != reference.availability_reference:
            return dict(result, status='club_reference_mismatch')
    for club, context in clubs.items():
        observed = reference.team_receipts[club]
        delta = _field_differences(context, observed['season_context'])
        if delta:
            result['differences'][club] = dict(season_context=delta)
        if context.get('status') == 'season_complete':
            block = public_team_state(dict(season_context=context,
                                           freshness=dict(data_through=reference.provenance['data_through'])))
            delta = _field_differences(block, observed['value'])
            result['season_complete_projections_compared'] += 1
            if delta:
                result['differences'].setdefault(club, {})['season_complete_projection'] = delta
    return dict(result, clubs_compared=len(clubs),
                status='competition_fields_differ' if result['differences'] else 'competition_fields_match')
