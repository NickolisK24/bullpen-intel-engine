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
    missing_context = []
    for team, state in teams.items():
        receipt = reference.team_receipts[team]
        observed = receipt['value']
        if (not isinstance(observed, dict) or observed.get('contract') != 'team_state_public_v1'
                or observed.get('data_through') != archive_dates['data_through']):
            raise ValueError('Observed club receipt disagrees with the publication dates')
        context = receipt.get('season_context')
        if context is None:
            missing_context.append(int(team))
            continue
        if (not isinstance(context, dict) or context.get('reference_date') != archive_dates['availability']
                or context.get('team_id') != int(team)):
            raise ValueError('Observed club context disagrees with the publication')
        delta = _field_differences(state, observed)
        if delta:
            report['differences'][team] = delta
    if missing_context:
        return dict(report, status='archived_competition_context_missing', clubs_missing_context=sorted(missing_context),
                    clubs_compared=len(teams) - len(missing_context))
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
    missing_context = []
    withheld = {}
    for club, context in clubs.items():
        archived = reference.team_receipts[club].get('season_context')
        if (context.get('reference_date') != report['reference_date'] or context.get('team_id') != int(club)
                or (archived is not None and (archived.get('reference_date') != reference.availability_reference
                                              or archived.get('team_id') != int(club)))):
            return dict(result, status='club_reference_mismatch')
    for club, context in clubs.items():
        observed = reference.team_receipts[club]
        if observed.get('season_context') is None:
            missing_context.append(int(club))
            if observed['value'].get('available') is True and context['status'] == 'season_complete':
                projected = public_team_state(dict(season_context=context, freshness=dict(data_through=reference.provenance['data_through'])))
                withheld[club] = dict(archived_label=observed['value']['public_label'], replayed_outcome=projected['outcome'],
                                      replayed_reason=projected['reason_code'])
            continue
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
    if missing_context:
        return dict(result, clubs_compared=len(clubs) - len(missing_context), status='archived_competition_context_missing',
                    clubs_missing_context=sorted(missing_context), archived_claims_withheld_under_replayed_rules=withheld)
    return dict(result, clubs_compared=len(clubs),
                status='competition_fields_differ' if result['differences'] else 'competition_fields_match')


def _compare_arm_population(facts, group):
    """Compare observed arm claims only after proving both samples contain the same MLB players."""
    records = group['records']
    public_ids = [row['pitcher_id'] for row in records]
    archived = {row['mlb_id']: row['public_read'] for row in records}
    if (not records or len(archived) != len(records) or len(set(public_ids)) != len(records)
            or group.get('missing_record_pitcher_ids') != []
            or sorted(group['member_pitcher_ids']) != sorted(public_ids)):
        return dict(status='incomplete_archived_population')
    candidate = {int(player): arm for player, arm in facts['arms'].items()}
    if candidate.keys() != archived.keys():
        return dict(status='population_differs', candidate_only=sorted(candidate.keys() - archived.keys()),
                    archive_only=sorted(archived.keys() - candidate.keys()))
    differences, missing, matched = {}, [], []
    for player, arm in sorted(candidate.items()):
        observed = archived[player]
        read = (arm['read'] or {}).get('arm_read')
        if arm['reason'] or not isinstance(read, dict) or not isinstance(observed, dict) or not read or not observed:
            missing.append(player)
            continue
        delta = _field_differences(read, observed)
        if delta:
            differences[player] = delta
        else:
            matched.append(player)
    status = 'arm_fields_differ' if differences else 'arm_fields_match'
    return dict(status='partial_arm_evidence' if missing else status,
                matching_players=matched, differences=differences, missing_players=missing)


def compare_archived_arm_reads(cur, generation, reference):
    """Account for every club's pinned readiness population against one postcommit archive."""
    from sync_v3.cohort import compare_membership
    from sync_v3.intelligence_history import DOMAINS

    cur.execute("SELECT represented,manifest->>'availability_reference' FROM candidate.generations WHERE digest=%s",
                (generation,))
    day, availability = cur.fetchone()
    report = dict(scope='historical_pitcher_arm_reads', generation=generation, archive=reference.provenance,
                  clubs={}, current_serving_eligible=False)
    if (str(day) != reference.provenance['data_through'] or str(day) != reference.membership_reference
            or availability != reference.availability_reference):
        return dict(report, status='edition_dates_differ')
    populations = compare_membership(cur, generation, day.isoformat())['clubs']
    cur.execute("""SELECT h.mlb_id,h.facts FROM candidate.generation_inputs i
                   JOIN candidate.workload_history h ON h.id=i.snapshot
                   WHERE i.generation=%s AND h.subject='team' AND h.methodology=%s""",
                (generation, DOMAINS['readiness'][1]))
    readiness = dict(cur.fetchall())
    for team, population in sorted(populations.items()):
        inputs = reference.available_inputs.get(str(team))
        facts = readiness.get(team, {})
        if facts.get('competition', {}).get('status') == 'season_complete' and not facts.get('arms'):
            result = dict(status='candidate_season_complete', reason=facts.get('reason'))
        elif not inputs:
            result = dict(status='archived_available_inputs_absent')
        elif population != 'matched':
            result = dict(status='candidate_population_unverified', reason=population)
        else:
            if facts['reference_date'] != availability:
                raise ValueError('Frozen readiness reference differs from the generation')
            result = _compare_arm_population(facts, inputs['arm_reads'])
            method = facts.get('availability_method')
            archived_method = reference.team_receipts[str(team)].get('availability_method_version')
            result.update(candidate_method=method, archive_method=archived_method,
                          same_method_verified=bool(method and method == archived_method))
        report['clubs'][team] = result
    return dict(report, status='accounted')
