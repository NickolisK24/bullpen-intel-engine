"""Replay the verified publication's workload and availability dates in disposable clusters."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta
import json
from pathlib import Path

from services.availability_reference_date import SCHEDULE_CONFIRMATION_LOOKAHEAD_DAYS
from services.club_competition_status import POSTSEASON_GAME_TYPES
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.capture_day import capture
from sync_v3.competition_calendar import calendar_games, competition_status
from sync_v3.discovery import calendar_requests, competition_calendar_request
from sync_v3.public_identities import from_observed_publication
from sync_v3.eligibility_recovery import recover
from sync_v3.rehearse import isolated_cluster, run
from sync_v3.replay import install, run_fixture
from sync_v3.sources import RetainedResponse


def replay_offseason_recovery(directory, bindir):
    """Exercise the private worker using only receipts retained in this shadow run."""
    capture_path = directory / 'capture.json'
    current = json.loads(capture_path.read_text())
    day = date.fromisoformat(current['baseball_date'])
    reference = day + timedelta(days=1)
    request = competition_calendar_request(reference.year)
    calendars = [r for r in current['responses'] if r['endpoint'] == request.endpoint and r['params'] == request.params()]
    if not calendars:
        return dict(status='reference_calendar_unavailable', date=str(day))
    calendar, = calendars
    games = calendar_games(request.params(), calendar['body'])
    finals = {pk: played for pk, (played, row, _) in games.items()
              if row['game_type'] == 'W' and row['status_state'] == 'final' and played <= day}
    if not finals:
        return dict(status='no_completed_world_series_game', date=str(day))
    # Use calendar scores only to find a completed-series test case. The
    # classifier still needs the independently confirmed winning pitching lines.
    wins = Counter()
    series_length = games[next(iter(finals))][1]['games_in_series']
    for pk in finals:
        _, _, game = games[pk]
        sides = game['teams'].values()
        winners = [side['team']['id'] for side in sides if side.get('isWinner') is True]
        if len(winners) == 1:
            wins[winners[0]] += 1
    if not wins or max(wins.values()) < series_length // 2 + 1:
        return dict(status='calendar_has_no_series_clinch', date=str(day))
    inputs = {}
    for played in sorted(set(finals.values())):
        path = capture_path if played == day else directory / 'publication-fixtures' / f'{played}.json'
        if not path.is_file():
            return dict(status='dated_fixture_unavailable', date=str(day), missing=str(played))
        data = json.loads(path.read_text())
        if data['baseball_date'] != str(played):
            raise ValueError('Postseason fixture date mismatch')
        schedule, _ = calendar_requests(played)
        wanted = {(schedule.endpoint, tuple(sorted(schedule.params().items())))}
        wanted.update((f'/game/{pk}/boxscore', ()) for pk, d in finals.items() if d == played)
        for row in data['responses']:
            key = row['endpoint'], tuple(sorted(row['params'].items()))
            if key in wanted:
                if key in inputs:
                    raise ValueError('Duplicate retained World Series request')
                inputs[key] = row
        if wanted - inputs.keys():
            return dict(status='dated_response_unavailable', date=str(day), missing=str(played))

    def transport(endpoint, params):
        row = inputs[endpoint, tuple(sorted(params.items()))]
        return RetainedResponse(row['body'], datetime.fromisoformat(row['retrieved_at'].replace('Z', '+00:00')))

    with isolated_cluster(bindir) as (owner, connect):
        install(owner)
        with closing(connect()) as worker:
            run_fixture(worker, capture_path)
            def inventory():
                with worker, worker.cursor() as cur:
                    cur.execute('SELECT count(*) FROM candidate.core_selections')
                    if cur.fetchone() != (0,):
                        raise ValueError('Offseason recovery advanced a selection')
                    report = competition_status(cur, reference)
                return dict(clubs={k: v['status'] for k, v in report['clubs'].items()},
                            verified=sorted(report['decision_sources']), missing=report['missing_decisions'])
            before = inventory()
            unresolved = [team for team, state in before['clubs'].items() if state == 'undetermined']
            batches = []
            if unresolved and set(finals).intersection(before['missing']):
                # Seven World Series schedules and seven boxes fit in five batches.
                for _ in range(5):
                    with closing(connect()) as resumed:
                        batch = recover(resumed, min(unresolved), day, fetch=transport, max_jobs=3, include_workload=True)
                    batches.append(batch)
                    if batch['status'] != 'batch_limit':
                        break
            after = inventory()
            repeat = None
            if unresolved and batches and batches[-1]['status'] == 'season_complete':
                with closing(connect()) as resumed:
                    repeat = recover(resumed, min(unresolved), day, fetch=transport, max_jobs=3, include_workload=True)
                if repeat['receipts'] or inventory() != after:
                    raise ValueError('Repeated offseason recovery changed the settled evidence')
    return dict(date=str(day), reference=str(reference), status='replayed', before=before, after=after, batches=batches, repeat=repeat)


def replay(directory, bindir):
    proof = (directory / 'proof.zip', (directory / 'proof-digest').read_text().strip())
    archive = from_observed_publication(*proof)
    through = date.fromisoformat(archive.provenance['data_through'])
    reference = date.fromisoformat(archive.availability_reference)
    if through.isoformat() != archive.membership_reference or not 0 <= (reference - through).days <= 30:
        raise ValueError('Publication dates outside the supported matched replay')
    print(json.dumps(dict(scope='publication_replay_target', snapshot=archive.provenance['snapshot_id'],
                          workload=str(through), membership=archive.membership_reference,
                          availability=str(reference))), flush=True)
    captures = directory / 'publication-fixtures'
    captures.mkdir()

    def fixture(day):
        return captures / f'{day}.json'

    # Preserve the original daily capture separately. These files belong to the cited publication.
    capture(reference, fixture(reference), teams=MLB_TEAM_IDS if reference == through else (),
            competition=True, statcast=reference == through)
    request = competition_calendar_request(reference.year)
    season, = [r for r in json.loads(fixture(reference).read_text())['responses']
               if r['endpoint'] == request.endpoint and r['params'] == request.params()]
    games = calendar_games(request.params(), season['body'])
    playoff_days = {day for day, row, _ in games.values()
                    if day < reference and row['game_type'] in POSTSEASON_GAME_TYPES and row['status_state'] == 'final'}
    dates = {through, reference}
    if reference > through + timedelta(days=1):
        horizon = reference + timedelta(days=SCHEDULE_CONFIRMATION_LOOKAHEAD_DAYS)
        dates.update(through + timedelta(days=n) for n in range(1, (horizon - through).days + 1))
    for day in sorted((dates | playoff_days) - {reference}):
        capture(day, fixture(day), teams=MLB_TEAM_IDS if day == through else (), statcast=day == through)

    # Competition has an explicit comparison date. The complete generation must
    # independently resolve availability from retained schedules and may refuse it.
    run(bindir=bindir, measure_replay=True, fixture=[fixture(d) for d in sorted(playoff_days | {reference})],
        competition=True, through=reference, identity_proof=proof)
    run(bindir=bindir, measure_replay=True, fixture=[fixture(d) for d in sorted(dates | playoff_days)], through=through,
        availability_as_of=reference, build_generation=True, exercise_selection=True, identity_proof=proof)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('bindir')
    args = parser.parse_args()
    replay(args.directory, args.bindir)
    recovery = replay_offseason_recovery(args.directory, args.bindir)
    (args.directory / 'offseason-recovery.json').write_text(json.dumps(recovery, sort_keys=True))
    if recovery['status'] == 'replayed' and (
            len(recovery['after']['clubs']) != 30 or set(recovery['after']['clubs'].values()) != {'season_complete'}):
        raise ValueError('Retained postseason evidence did not certify all clubs as season complete')
