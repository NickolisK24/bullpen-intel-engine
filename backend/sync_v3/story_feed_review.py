"""Review the league writer's choices against one immutable historical edition."""
from datetime import date
from functools import cache
from hashlib import sha256
from types import SimpleNamespace

from services.game_context import landscape_team_groups
from services.mlb_club_directory import MLB_CLUBS
from services.team_state_public_vocabulary import TEAM_STATE_SEASON_COMPLETE
from services.story_feed import build_canonical_story_feed, canonical_story_team_descriptors
from sync_v3.editorial_league_baseline import league_concentration
from sync_v3.editorial_reads import _club_story
from sync_v3.evidence import encode_json
from sync_v3.intelligence_history import DOMAINS
from sync_v3.product_reads import (
    _blocks, _dated_team_state, _empty_selection_status, _historical_availability, _public_arms, _read_transaction, _selected,
)


def read_story_feed_review(connection, *, revision):
    if type(revision) is not int or revision < 1:
        raise ValueError('Expected an exact historical revision')

    def read(cur):
        selected = _selected(cur, revision)
        result = dict(scope='historical_story_feed_review', selection_revision=revision,
                      generation=None, current_serving_eligible=False, clubs=[], items=[])
        if not selected or selected[1] is None:
            return dict(result, status=_empty_selection_status(selected, revision))
        _, digest, through, reference = selected
        result.update(generation=digest, data_through=through.isoformat(), availability_reference=reference)
        identities, _ = _public_arms(cur, digest)
        method = DOMAINS['readiness'][1]
        reference_day = date.fromisoformat(reference)
        records, unresolved = [], []
        result.update(season_complete_clubs=[], readiness_citations={})
        for club in MLB_CLUBS:
            block = _blocks(cur, digest, 'team', club.team_id, {method: 'readiness'})['readiness']
            result['readiness_citations'][club.team_id] = block['citation']
            facts = block['value']
            competition = facts['competition']
            if (competition['team_id'] == club.team_id and competition['reference_date'] == reference
                    and _dated_team_state(facts, through, reference)['outcome'] == TEAM_STATE_SEASON_COMPLETE
                    and facts['reason'] == competition['basis'] and not facts['arms'] and facts['team_state'] is None):
                result['season_complete_clubs'].append(club.team_id)
                continue
            if _historical_availability(facts, identities, through, reference_day) is None:
                unresolved.append(club.team_id)
                continue
            identity = SimpleNamespace(team_id=club.team_id, team_name=club.team_name, team_abbreviation=club.abbreviation)
            records.extend(dict(pitcher=identity, availability=arm['read']['availability']) for arm in facts['arms'].values())
        if unresolved:
            return dict(result, status='incomplete_league_availability', unresolved_clubs=sorted(unresolved))
        descriptors = canonical_story_team_descriptors(landscape_team_groups(records))
        read_baseline = cache(league_concentration)
        writers, receipts = {}, {}
        for descriptor in descriptors:
            team = descriptor['team_id']
            review, writers[team] = _club_story(cur, team, selected, revision, read_league_baseline=read_baseline)
            receipts[team] = review['story_selection'] or dict(status='withheld', reason=review['qualification'])
        feed = build_canonical_story_feed(descriptors, as_of_date=reference,
                                          story_builder=lambda team, as_of_date: writers[team])
        for item in feed['items']:
            team = item['team_id']
            if item['story_available']:
                if receipts[team]['status'] != 'selected' or not item['headline'] or not item['narrative']:
                    raise ValueError('League story lacks a qualified club selection')
                copy = dict(headline=item['headline'], narrative=item['narrative'])
                result['items'].append(dict(team_id=team, observation_type=receipts[team]['observation_type'],
                                            source_layers=receipts[team]['source_layers'],
                                            club_copy_sha256=receipts[team]['copy_sha256'],
                                            feed_copy_sha256=sha256(encode_json(copy)).hexdigest()))
        result['clubs'] = [dict(descriptor, selection=receipts[descriptor['team_id']]) for descriptor in descriptors]
        return dict(result, status='reviewed')

    return _read_transaction(connection, read)
