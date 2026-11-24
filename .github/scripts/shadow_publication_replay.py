"""Replay the verified publication's workload and availability dates in disposable clusters."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path

from services.availability_reference_date import SCHEDULE_CONFIRMATION_LOOKAHEAD_DAYS
from services.club_competition_status import POSTSEASON_GAME_TYPES
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.capture_day import capture
from sync_v3.competition_calendar import calendar_games
from sync_v3.discovery import competition_calendar_request
from sync_v3.public_identities import from_observed_publication
from sync_v3.rehearse import run


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
            competition=True)
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
        capture(day, fixture(day), teams=MLB_TEAM_IDS if day == through else ())

    # Competition has an explicit comparison date. The complete generation must
    # independently resolve availability from retained schedules and may refuse it.
    run(bindir=bindir, measure_replay=True, fixture=[fixture(d) for d in sorted(playoff_days | {reference})],
        competition=True, through=reference, identity_proof=proof)
    run(bindir=bindir, measure_replay=True, fixture=[fixture(d) for d in sorted(dates | playoff_days)], through=through,
        availability_as_of=reference, build_generation=True, identity_proof=proof)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('bindir')
    args = parser.parse_args()
    replay(args.directory, args.bindir)
