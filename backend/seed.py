"""
BaseballOS Database Seeder
---------------------------
Pulls historical data from MLB Stats API (2024–2025) for all 30 teams.
Populates pitchers, game logs, fatigue scores, and sample prospects.

Run: python seed.py
"""

import sys
import time
from datetime import datetime, date, timedelta
from app import create_app
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.prospect import Prospect
from models.fatigue_score import FatigueScore
from services.mlb_api import mlb_client
from services.fatigue import calculate_fatigue

app = create_app()

# All 30 MLB team IDs
ALL_TEAM_IDS = [
    108, 109, 110, 111, 112, 113, 114, 115, 116, 117,
    118, 119, 120, 121, 133, 134, 135, 136, 137, 138,
    139, 140, 141, 142, 143, 144, 145, 146, 147, 158
]

# Seasons to pull — 2024 (full) + 2025 (current/upcoming)
HISTORICAL_SEASONS = [2024, 2025]


# ─── Pitchers ────────────────────────────────────────────────────────────────

def seed_pitchers():
    """Seed pitchers from all 30 MLB team rosters."""
    print("\n📋 Seeding pitchers (all 30 teams)...")
    teams = mlb_client.get_all_teams()
    team_map = {t['id']: t for t in teams}

    seeded = 0
    for team_id in ALL_TEAM_IDS:
        team = team_map.get(team_id)
        if not team:
            print(f"  ⚠️  Team ID {team_id} not found")
            continue

        print(f"  → {team['name']} (ID: {team_id})")
        roster = mlb_client.get_team_roster(team_id, roster_type='40Man')

        for player in roster:
            person = player.get('person', {})
            position = player.get('position', {})

            if position.get('abbreviation') not in ['P', 'SP', 'RP', 'CL']:
                continue

            player_id = person.get('id')
            if not player_id:
                continue

            existing = Pitcher.query.filter_by(mlb_id=player_id).first()
            if existing:
                continue

            info = mlb_client.get_player_info(player_id)
            if not info:
                continue

            pitcher = Pitcher(
                mlb_id=player_id,
                full_name=info.get('fullName', person.get('fullName', 'Unknown')),
                team_id=team_id,
                team_name=team.get('name'),
                team_abbreviation=team.get('abbreviation'),
                position=position.get('abbreviation', 'P'),
                throws=info.get('pitchHand', {}).get('code'),
                age=info.get('currentAge'),
                jersey_number=player.get('jerseyNumber'),
                active=True,
            )
            db.session.add(pitcher)
            seeded += 1

        db.session.commit()
        print(f"     ✓ Done")
        time.sleep(0.3)

    print(f"\n  ✅ Seeded {seeded} new pitchers")
    return seeded


# ─── Game Logs ────────────────────────────────────────────────────────────────

def seed_game_logs():
    """
    Seed full-season game logs for all pitchers across 2024–2025.
    No date cutoff — pulls every appearance for each season.
    """
    print(f"\n📊 Seeding game logs for seasons: {HISTORICAL_SEASONS}...")
    pitchers = Pitcher.query.filter_by(active=True).all()
    seeded = 0
    skipped = 0
    errors = 0

    for i, pitcher in enumerate(pitchers):
        if i % 25 == 0:
            print(f"  → Processing pitcher {i}/{len(pitchers)} ({pitcher.full_name})...")

        for season in HISTORICAL_SEASONS:
            try:
                logs = mlb_client.get_pitcher_game_logs(pitcher.mlb_id, season=season)
            except Exception as e:
                errors += 1
                continue

            for split in logs:
                game_info = split.get('game', {})
                stat = split.get('stat', {})
                game_pk = game_info.get('gamePk')
                game_date_str = split.get('date')

                if not game_pk or not game_date_str:
                    continue

                try:
                    game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()
                except ValueError:
                    continue

                existing = GameLog.query.filter_by(
                    pitcher_id=pitcher.id,
                    mlb_game_pk=game_pk
                ).first()
                if existing:
                    skipped += 1
                    continue

                opponent = split.get('opponent', {})

                log = GameLog(
                    pitcher_id=pitcher.id,
                    mlb_game_pk=game_pk,
                    game_date=game_date,
                    opponent=opponent.get('name'),
                    opponent_abbreviation=opponent.get('abbreviation'),
                    innings_pitched=float(stat.get('inningsPitched', 0) or 0),
                    pitches_thrown=int(stat.get('numberOfPitches', 0) or 0),
                    strikes=int(stat.get('strikes', 0) or 0),
                    hits_allowed=int(stat.get('hits', 0) or 0),
                    runs_allowed=int(stat.get('runs', 0) or 0),
                    earned_runs=int(stat.get('earnedRuns', 0) or 0),
                    walks=int(stat.get('baseOnBalls', 0) or 0),
                    strikeouts=int(stat.get('strikeOuts', 0) or 0),
                    home_runs_allowed=int(stat.get('homeRuns', 0) or 0),
                    save_situation=stat.get('saveOpportunities', 0) > 0,
                    hold=stat.get('holds', 0) > 0,
                    blown_save=stat.get('blownSaves', 0) > 0,
                    win=stat.get('wins', 0) > 0,
                    loss=stat.get('losses', 0) > 0,
                    save=stat.get('saves', 0) > 0,
                )
                db.session.add(log)
                seeded += 1

            time.sleep(0.1)

        if i % 50 == 0:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"  ❌ Batch commit error at pitcher {i}: {e}")

    try:
        db.session.commit()
        print(f"  ✅ Seeded {seeded} game logs | Skipped {skipped} duplicates | {errors} API errors")
    except Exception as e:
        db.session.rollback()
        print(f"  ❌ Final commit error: {e}")

    return seeded


# ─── Fatigue Scores ──────────────────────────────────────────────────────────

def seed_fatigue_scores():
    """
    Calculate fatigue scores using the 14-day window before each pitcher's
    most recent game. Works correctly for both historical and current data.
    """
    print("\n🔥 Calculating fatigue scores...")
    pitchers = Pitcher.query.filter_by(active=True).all()
    scored = 0

    for pitcher in pitchers:
        latest_log = (
            GameLog.query
            .filter_by(pitcher_id=pitcher.id)
            .order_by(GameLog.game_date.desc())
            .first()
        )

        if not latest_log:
            continue

        window_start = latest_log.game_date - timedelta(days=14)
        logs = (
            GameLog.query
            .filter(
                GameLog.pitcher_id == pitcher.id,
                GameLog.game_date >= window_start
            )
            .order_by(GameLog.game_date.desc())
            .all()
        )

        score = calculate_fatigue(pitcher, logs)
        db.session.add(score)
        scored += 1

    db.session.commit()
    print(f"  ✅ Scored {scored} pitchers")
    return scored


# ─── Prospects ───────────────────────────────────────────────────────────────

def seed_sample_prospects():
    """Seed a curated set of prospects with real context."""
    print("\n🌱 Seeding prospects...")

    sample_prospects = [
        {
            'full_name': 'Jackson Holliday', 'team_name': 'Baltimore Orioles', 'team_abbreviation': 'BAL',
            'position': 'SS', 'bats': 'L', 'throws': 'R', 'age': 21, 'current_level': 'MLB',
            'eta_year': 2024, 'hit_grade': 60, 'power_grade': 55, 'speed_grade': 55,
            'field_grade': 55, 'arm_grade': 55, 'overall_grade': 60,
            'batting_average': 0.234, 'on_base_pct': 0.312, 'slugging_pct': 0.378, 'ops': 0.690,
        },
        {
            'full_name': 'Paul Skenes', 'team_name': 'Pittsburgh Pirates', 'team_abbreviation': 'PIT',
            'position': 'SP', 'bats': 'R', 'throws': 'R', 'age': 22, 'current_level': 'MLB',
            'eta_year': 2024, 'hit_grade': 40, 'power_grade': 40, 'speed_grade': 30,
            'field_grade': 50, 'arm_grade': 80, 'overall_grade': 70,
            'era': 1.96, 'whip': 0.95, 'k_per_9': 11.8, 'bb_per_9': 2.1,
        },
        {
            'full_name': 'Wyatt Langford', 'team_name': 'Texas Rangers', 'team_abbreviation': 'TEX',
            'position': 'LF', 'bats': 'R', 'throws': 'R', 'age': 22, 'current_level': 'MLB',
            'eta_year': 2024, 'hit_grade': 60, 'power_grade': 60, 'speed_grade': 60,
            'field_grade': 55, 'arm_grade': 55, 'overall_grade': 65,
            'batting_average': 0.265, 'on_base_pct': 0.338, 'slugging_pct': 0.435, 'ops': 0.773,
        },
        {
            'full_name': 'Chase Burns', 'team_name': 'Cincinnati Reds', 'team_abbreviation': 'CIN',
            'position': 'SP', 'bats': 'R', 'throws': 'R', 'age': 23, 'current_level': 'MLB',
            'eta_year': 2025, 'hit_grade': 40, 'power_grade': 40, 'speed_grade': 35,
            'field_grade': 50, 'arm_grade': 70, 'overall_grade': 65,
            'era': 3.42, 'whip': 1.10, 'k_per_9': 10.4, 'bb_per_9': 2.8,
        },
        {
            'full_name': 'Junior Caminero', 'team_name': 'Tampa Bay Rays', 'team_abbreviation': 'TB',
            'position': '3B', 'bats': 'R', 'throws': 'R', 'age': 21, 'current_level': 'AA',
            'eta_year': 2025, 'hit_grade': 55, 'power_grade': 65, 'speed_grade': 45,
            'field_grade': 55, 'arm_grade': 60, 'overall_grade': 65,
            'batting_average': 0.310, 'on_base_pct': 0.365, 'slugging_pct': 0.540, 'ops': 0.905,
        },
        {
            'full_name': 'Dylan Crews', 'team_name': 'Washington Nationals', 'team_abbreviation': 'WSH',
            'position': 'CF', 'bats': 'R', 'throws': 'R', 'age': 22, 'current_level': 'AA',
            'eta_year': 2025, 'hit_grade': 60, 'power_grade': 55, 'speed_grade': 60,
            'field_grade': 60, 'arm_grade': 55, 'overall_grade': 60,
            'batting_average': 0.290, 'on_base_pct': 0.375, 'slugging_pct': 0.470, 'ops': 0.845,
        },
        {
            'full_name': 'Colton Cowser', 'team_name': 'Baltimore Orioles', 'team_abbreviation': 'BAL',
            'position': 'LF', 'bats': 'L', 'throws': 'R', 'age': 24, 'current_level': 'MLB',
            'eta_year': 2024, 'hit_grade': 55, 'power_grade': 55, 'speed_grade': 55,
            'field_grade': 60, 'arm_grade': 55, 'overall_grade': 60,
            'batting_average': 0.243, 'on_base_pct': 0.322, 'slugging_pct': 0.412, 'ops': 0.734,
        },
        {
            'full_name': 'Kyle Harrison', 'team_name': 'San Francisco Giants', 'team_abbreviation': 'SF',
            'position': 'SP', 'bats': 'L', 'throws': 'L', 'age': 23, 'current_level': 'MLB',
            'eta_year': 2024, 'hit_grade': 40, 'power_grade': 40, 'speed_grade': 40,
            'field_grade': 50, 'arm_grade': 60, 'overall_grade': 55,
            'era': 4.12, 'whip': 1.28, 'k_per_9': 9.8, 'bb_per_9': 3.5,
        },
        {
            'full_name': 'Evan Carter', 'team_name': 'Texas Rangers', 'team_abbreviation': 'TEX',
            'position': 'LF', 'bats': 'L', 'throws': 'R', 'age': 21, 'current_level': 'MLB',
            'eta_year': 2023, 'hit_grade': 60, 'power_grade': 55, 'speed_grade': 60,
            'field_grade': 60, 'arm_grade': 55, 'overall_grade': 60,
            'batting_average': 0.258, 'on_base_pct': 0.355, 'slugging_pct': 0.420, 'ops': 0.775,
        },
        {
            'full_name': 'Yoshinobu Yamamoto', 'team_name': 'Los Angeles Dodgers', 'team_abbreviation': 'LAD',
            'position': 'SP', 'bats': 'R', 'throws': 'R', 'age': 26, 'current_level': 'MLB',
            'eta_year': 2024, 'hit_grade': 40, 'power_grade': 40, 'speed_grade': 30,
            'field_grade': 55, 'arm_grade': 80, 'overall_grade': 70,
            'era': 3.00, 'whip': 1.06, 'k_per_9': 10.2, 'bb_per_9': 2.0,
        },
    ]

    added = 0
    for data in sample_prospects:
        existing = Prospect.query.filter_by(full_name=data['full_name']).first()
        if not existing:
            prospect = Prospect(**data)
            db.session.add(prospect)
            added += 1

    db.session.commit()
    print(f"  ✅ Seeded {added} prospects")


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        print("⚾  BaseballOS Seeder")
        print("=" * 45)
        print(f"Seasons: {HISTORICAL_SEASONS}")
        print(f"Teams:   All 30 MLB teams")
        print("=" * 45)

        try:
            pitchers_seeded = seed_pitchers()
            logs_seeded = seed_game_logs()
            fatigue_seeded = seed_fatigue_scores()
            seed_sample_prospects()

            print("\n" + "=" * 45)
            print("✅ Seed complete!")
            print(f"   Pitchers:  {pitchers_seeded}")
            print(f"   Game Logs: {logs_seeded}")
            print(f"   Fatigue:   {fatigue_seeded} scored")
            print("=" * 45)

        except Exception as e:
            print(f"\n❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)