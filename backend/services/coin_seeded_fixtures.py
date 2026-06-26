"""Seeded fixture scenarios for COIN story-quality review (manual, review-only).

The live sandbox has no ingested MLB data, so the real corpus correctly fails
closed with ``no_completed_context``. This module provides deterministic,
hand-authored CompletedGameContext-shaped fixtures for the four review teams so
the story pipeline can be exercised and read without a populated database.

Only structured facts are seeded — no prose is hardcoded. Each fixture is a
CompletedGameContext dict (the real model/dict shape) plus a lightweight team
context for the bullpen snapshots. The seeded path still runs through every COIN
layer:

    CompletedGameContext fixture -> Narrative Context -> Narrative Feed
        -> Story Orchestrator / Story Package -> Story Writers

Nothing here reads the database or fetches MLB data, and nothing is persisted.
This is NOT a production path; it exists purely for review.
"""

from __future__ import annotations

from services.coin_story_inspection import inspect_team_story


MODE_SEEDED_FIXTURE_REVIEW = 'SEEDED_FIXTURE_REVIEW'

# A short, honest banner the Markdown artifact carries near the top.
SEEDED_REVIEW_WARNING = (
    'This corpus was generated from deterministic seeded fixtures, not live MLB '
    'data. It is intended for story-quality review only.'
)


def _completed_game_context(**over) -> dict:
    """A CompletedGameContext dict with every model field present (null by default)."""
    base = {
        'team_id': None, 'game_pk': None, 'game_date': '2026-06-25',
        'opponent_team_id': None, 'opponent_name': None, 'home_away': None,
        'final_score_for': None, 'final_score_against': None,
        'starter_player_id': None, 'starter_name': None, 'starter_ip': None,
        'starter_pitch_count': None, 'starter_exit_inning': None,
        'starter_exit_score_for': None, 'starter_exit_score_against': None,
        'bullpen_entry_inning': None, 'bullpen_entry_score_for': None,
        'bullpen_entry_score_against': None, 'lead_when_bullpen_entered': None,
        'deficit_when_bullpen_entered': None, 'largest_lead': None,
        'largest_deficit': None, 'late_runs_allowed': None,
        'runs_allowed_innings_7_to_9': None, 'lead_protected': None,
        'lead_lost': None, 'comeback_completed': None, 'turning_inning': None,
        'game_shape_created': None, 'game_shape_protected': None,
        'bullpen_story_tag': None, 'confidence': 'LOW', 'generated_at': None,
    }
    base.update(over)
    return base


def _team_context(team_id, *, optionality_band, concentration_band,
                  available_arms_count, clean_option_names=(),
                  stability_band='stable',
                  depth_pressure_band='moderate', workload_total=240):
    clean_options = [
        {'player_id': 1000 + index, 'name': name, 'availability': 'Available'}
        for index, name in enumerate(clean_option_names)
    ]
    return {
        'team_id': team_id,
        'bullpen_optionality_context': {
            'context_available': True,
            'available_arms_count': available_arms_count,
            'monitor_arms_count': 1,
            'limited_arms_count': 1,
            'restricted_arms_count': 1,
            'unavailable_arms_count': 1,
            'unknown_status_count': 0,
            'clean_workload_options': clean_options,
            'secondary_options': [{'player_id': 99, 'name': 'Secondary Arm',
                                   'availability': 'Monitor'}],
            'practical_close_game_paths_count': max(0, available_arms_count - 1),
            'optionality_band': optionality_band,
        },
        'bullpen_concentration_context': {
            'concentration_band': concentration_band,
            'window_days': 10,
            'bullpen_workload_total_10d': workload_total,
            'bullpen_workload_appearances_10d': 22,
            'top_three_workload_share_10d': 47.0,
        },
        'rotation_context': {'bullpen_coverage_ip_7d': 9.0, 'early_bullpen_entry_rate': 0.3},
        'role_stability_context': {'stability_band': stability_band, 'core_retention_count': 3},
        'injury_context': {'depth_pressure_band': depth_pressure_band,
                           'inactive_bullpen_arms_count': 1},
    }


# ── Fixture scenarios ─────────────────────────────────────────────────────────
# 1) Giants — lost_game_shape: 6 IP start, led 6-2, bullpen gave up 7 late, lost 9-6.
_GIANTS = {
    'team_id': 137,
    'fixture_name': 'giants_lost_game_shape',
    'expected_primary_story': 'lost_game_shape',
    'completed_game_context': _completed_game_context(
        team_id=137, game_pk=137000, opponent_team_id=135, opponent_name='San Diego Padres',
        team_name='the Giants', home_away='home', final_score_for=6, final_score_against=9,
        starter_name='Landen Roupp', starter_ip=6.0, starter_pitch_count=95,
        starter_exit_inning=6, starter_exit_score_for=6, starter_exit_score_against=2,
        bullpen_entry_inning=7, bullpen_entry_score_for=6, bullpen_entry_score_against=2,
        lead_when_bullpen_entered=4, largest_lead=4, largest_deficit=3,
        late_runs_allowed=7, runs_allowed_innings_7_to_9=7,
        lead_protected=False, lead_lost=True, comeback_completed=False, turning_inning=8,
        game_shape_created='normal_start', game_shape_protected=False,
        bullpen_story_tag='lost_game_shape', confidence='HIGH',
        # 4 + 3 = the 7 late runs; both arms pitched, so neither is a clean option.
        key_relief_appearances=[
            {'name': 'Ryan Walker', 'innings': 0.2, 'runs_allowed': 4},
            {'name': 'Tyler Rogers', 'innings': 1.0, 'runs_allowed': 3},
        ],
    ),
    'team_context': _team_context(137, optionality_band='thin',
                                  concentration_band='concentrated', available_arms_count=3,
                                  clean_option_names=['Erik Miller']),
}

# 2) Athletics — bullpen_kept_team_alive: entered down, held it, offense completed comeback.
_ATHLETICS = {
    'team_id': 133,
    'fixture_name': 'athletics_bullpen_kept_team_alive',
    'expected_primary_story': 'bullpen_kept_team_alive',
    'completed_game_context': _completed_game_context(
        team_id=133, game_pk=133000, opponent_team_id=117, opponent_name='Houston Astros',
        team_name='the Athletics', home_away='away', final_score_for=5, final_score_against=4,
        starter_name='JP Sears', starter_ip=5.0, starter_pitch_count=84,
        starter_exit_inning=5, starter_exit_score_for=2, starter_exit_score_against=4,
        bullpen_entry_inning=6, bullpen_entry_score_for=2, bullpen_entry_score_against=4,
        deficit_when_bullpen_entered=2, largest_lead=1, largest_deficit=3,
        late_runs_allowed=0, runs_allowed_innings_7_to_9=0,
        comeback_completed=True, turning_inning=8,
        game_shape_created='normal_start',
        bullpen_story_tag='bullpen_kept_team_alive', confidence='HIGH',
        # Bullpen held the opponent at 4 (0 late runs) while the offense rallied.
        key_relief_appearances=[
            {'name': 'Mason Miller', 'innings': 2.0, 'runs_allowed': 0},
            {'name': 'Lucas Erceg', 'innings': 1.0, 'runs_allowed': 0},
        ],
    ),
    'team_context': _team_context(133, optionality_band='flexible',
                                  concentration_band='normal', available_arms_count=5,
                                  clean_option_names=['Tyler Ferguson', 'T.J. McFarland',
                                                      'Michel Otañez']),
}

# 3) Rays — protected_game_shape: starter handed a lead, bullpen shut the door, no late runs.
_RAYS = {
    'team_id': 139,
    'fixture_name': 'rays_protected_game_shape',
    'expected_primary_story': 'protected_game_shape',
    'completed_game_context': _completed_game_context(
        team_id=139, game_pk=139000, opponent_team_id=141, opponent_name='Toronto Blue Jays',
        team_name='the Rays', home_away='home', final_score_for=4, final_score_against=1,
        starter_name='Shane Baz', starter_ip=6.0, starter_pitch_count=89,
        starter_exit_inning=6, starter_exit_score_for=3, starter_exit_score_against=1,
        bullpen_entry_inning=7, bullpen_entry_score_for=3, bullpen_entry_score_against=1,
        lead_when_bullpen_entered=2, largest_lead=3, largest_deficit=0,
        late_runs_allowed=0, runs_allowed_innings_7_to_9=0,
        lead_protected=True, lead_lost=False, comeback_completed=False,
        game_shape_created='normal_start', game_shape_protected=True,
        bullpen_story_tag='protected_game_shape', confidence='HIGH',
        # The only opponent run was off the starter; the pen gave nothing back.
        key_relief_appearances=[
            {'name': 'Pete Fairbanks', 'innings': 1.0, 'runs_allowed': 0},
            {'name': 'Jason Adam', 'innings': 1.0, 'runs_allowed': 0},
        ],
    ),
    'team_context': _team_context(139, optionality_band='deep',
                                  concentration_band='balanced', available_arms_count=6,
                                  clean_option_names=['Garrett Cleavinger', 'Colin Poche',
                                                      'Edwin Uceta']),
}

# 4) Yankees — bullpen_overexposed: short start forced the pen to cover heavy innings.
_YANKEES = {
    'team_id': 147,
    'fixture_name': 'yankees_bullpen_overexposed',
    'expected_primary_story': 'bullpen_overexposed',
    'completed_game_context': _completed_game_context(
        team_id=147, game_pk=147000, opponent_team_id=111, opponent_name='Boston Red Sox',
        team_name='the Yankees', home_away='away', final_score_for=3, final_score_against=5,
        starter_name='Carlos Rodon', starter_ip=3.0, starter_pitch_count=62,
        starter_exit_inning=3, starter_exit_score_for=1, starter_exit_score_against=2,
        bullpen_entry_inning=4, bullpen_entry_score_for=1, bullpen_entry_score_against=2,
        largest_lead=0, largest_deficit=2,
        late_runs_allowed=1, runs_allowed_innings_7_to_9=1,
        game_shape_created='short_start',
        bullpen_story_tag='bullpen_overexposed', confidence='MEDIUM',
        # The pen covered six innings; Hamilton's run is the lone late one.
        key_relief_appearances=[
            {'name': 'Ian Hamilton', 'innings': 2.1, 'runs_allowed': 1},
            {'name': 'Tim Hill', 'innings': 1.2, 'runs_allowed': 0},
        ],
    ),
    'team_context': _team_context(147, optionality_band='narrow',
                                  concentration_band='concentrated', available_arms_count=2,
                                  clean_option_names=['Luke Weaver']),
}

SEEDED_FIXTURES = [_GIANTS, _ATHLETICS, _RAYS, _YANKEES]
SEEDED_TEAM_IDS = [fixture['team_id'] for fixture in SEEDED_FIXTURES]
_FIXTURES_BY_TEAM = {fixture['team_id']: fixture for fixture in SEEDED_FIXTURES}


def fixture_for(team_id) -> dict:
    return _FIXTURES_BY_TEAM[team_id]


def fixture_meta(team_id) -> dict:
    """The review-only labels attached to each seeded entry."""
    fixture = _FIXTURES_BY_TEAM.get(team_id)
    if fixture is None:
        return {'fixture_name': None, 'expected_primary_story': None}
    return {
        'fixture_name': fixture['fixture_name'],
        'expected_primary_story': fixture['expected_primary_story'],
    }


def build_seeded_inspect_fn():
    """An inspect_fn that injects the seeded fixtures (no DB, no MLB, ignores app)."""
    def inspect(team_id, *, app=None, reference_date=None, writer='all',
                include_unpublishable=False):
        fixture = fixture_for(team_id)
        return inspect_team_story(
            team_id,
            app=None,  # seeded mode never touches the database
            reference_date=reference_date,
            writer=writer,
            include_unpublishable=include_unpublishable,
            completed_game_context=fixture['completed_game_context'],
            team_context=fixture['team_context'],
        )
    return inspect
