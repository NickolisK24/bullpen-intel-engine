"""Measure bounded acquisition and 24 hourly batches for the retained August acceptance slate."""
import argparse
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic

from psycopg2.extras import Json

from shadow_current_worker import checkpoint
from sync_v3.comparison import compare_finals
from sync_v3.current_worker import acquisition_failed, process
from sync_v3.cycle import run_cycle
from sync_v3.rehearse import isolated_cluster
from sync_v3.render_staging import BATCH_LIMIT
from sync_v3.replay import install

DAY = date(2017, 8, 28)


# Derived independently from the retained August official roster lists, stats request
# identities and boxscores (archive SHA-256 in the Sync v3 acceptance ledger).
EXPECTED = {
    'roster_members': '94910c221e627a57ac9b6773dc5d006708ecb48aa32a518a6623f2db4769fa90',
    'pitcher_profiles': 'ede6e190ee6d3306a232a5ebd9a5cff1db6c4ccb710942881df7a1bd4fbb571f',
    'pitching_lines': '80faae87f1b59c7aae197f958da247b80624c71363d49bcb93e9bc0870acee0b',
}


def fingerprint(rows):
    return sha256(json.dumps(sorted(rows), separators=(',', ':')).encode()).hexdigest()


def coverage(connection):
    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        finals, lines = compare_finals(cur)
        cur.execute("""SELECT DISTINCT ON (identity) facts FROM candidate.revisions
                       WHERE domain='roster' AND facts->>'represented'=%s ORDER BY identity,revision DESC""",
                    (DAY.isoformat(),))
        rosters = [roster for roster, in cur]
        members = [(r['team'], r['type'], m['id']) for r in rosters for m in r['members']]
        cur.execute("""SELECT DISTINCT endpoint FROM candidate.fetches
                       WHERE endpoint LIKE '/people/%/stats' AND outcome='received'""")
        pitchers = [int(endpoint.split('/')[2]) for endpoint, in cur]
        cur.execute("""SELECT DISTINCT ON (identity) facts FROM candidate.revisions
                       WHERE domain='final' ORDER BY identity,revision DESC""")
        pitching = []
        for facts, in cur:
            for line in facts:
                innings, outs = divmod(line['outs_recorded'], 3)
                pitching.append((line['game_pk'], line['team_id'], line['pitcher_mlb_id'], f'{innings}.{outs}',
                                 line['pitches_thrown'], line['strikeouts'], line['walks']))
        cur.execute('SELECT count(*) FROM candidate.core_selections')
        selections, = cur.fetchone()
        cur.execute('SELECT pg_database_size(current_database())')
        size, = cur.fetchone()
    return dict(clubs=len({r['team'] for r in rosters}), roster_lists=len(rosters), finals=finals,
                pitching_lines=lines, pitcher_profiles=len(pitchers), selections=selections, database_bytes=size,
                cohort=dict(roster_members=fingerprint(members), pitcher_profiles=fingerprint(pitchers),
                            pitching_lines=fingerprint(pitching)))


def run(directory, bindir, client_bin):
    directory.mkdir()
    report = dict(represented=str(DAY), acquisition_batches=[], hourly_replay=[])
    start = monotonic()
    with isolated_cluster(bindir) as (source, connect):
        install(source)
        for _ in range(16):
            batch_start = monotonic()
            with closing(connect()) as worker:
                batch = process(worker, DAY, max_jobs=BATCH_LIMIT, profiles=True)
            report['acquisition_batches'].append(dict(seconds=monotonic()-batch_start, **batch))
            if acquisition_failed(batch):
                (directory / 'performance.json').write_text(json.dumps(report, sort_keys=True))
                checkpoint(source, client_bin, directory / 'played-source.pgdump')
                raise ValueError(f'Official played-slate acquisition failed: {batch}')
            if set(batch['jobs_for_date']) == {'done'}:
                break
        else:
            raise ValueError('Played-slate source queue did not drain within its batch budget')
        report['acquisition_seconds'] = monotonic()-start
        report['acquisition_coverage'] = coverage(source)
        report['checkpoint_sha256'] = checkpoint(source, client_bin, directory / 'played-source.pgdump')

        # Replay the latest retained payload for each request at the end of acquisition.
        # The runner clock advances. Provider responses represent one retrospective slate.
        with source, source.cursor() as retained, isolated_cluster(bindir) as (destination, resume):
            retained.execute('SET TRANSACTION READ ONLY')
            install(destination)

            def fetch(endpoint, params):
                retained.execute("""SELECT p.encoded_json,p.sha256 FROM candidate.fetches f
                                    JOIN candidate.payloads p USING (sha256)
                                    WHERE f.endpoint=%s AND f.parameters=%s AND f.outcome='received'
                                    ORDER BY f.received_at DESC,f.id DESC LIMIT 1""", (endpoint, Json(params)))
                row = retained.fetchone()
                if row is None or sha256(row[0]).hexdigest() != row[1]:
                    raise ValueError('Missing or damaged played-slate response')
                return json.loads(bytes(row[0]))

            for hour in range(24):
                at = datetime.combine(DAY, datetime.min.time(), timezone.utc) + timedelta(hours=hour)
                batch_start = monotonic()
                with closing(resume()) as worker:
                    receipts = run_cycle(worker, DAY, fetch, max_jobs=BATCH_LIMIT, competition=True,
                                         statcast=True, active_roster_profiles=True, clock=lambda: at)
                    with worker, worker.cursor() as cur:
                        cur.execute('SELECT state,count(*) FROM candidate.jobs GROUP BY state')
                        states = dict(cur.fetchall())
                report['hourly_replay'].append(dict(hour=hour, receipts=len(receipts), jobs=states,
                                                    seconds=monotonic()-batch_start))
                if any(outcome != 'received' for _, outcome in receipts) or states.get('dead'):
                    raise ValueError(f'Incomplete played-slate replay at hour {hour}')
            report['replay_coverage'] = coverage(destination)
    (directory / 'performance.json').write_text(json.dumps(report, sort_keys=True))
    for result in (report['acquisition_coverage'], report['replay_coverage']):
        if (result['cohort'] != EXPECTED or result['roster_lists'] != 60 or result['clubs'] != 30
                or result['finals'] != 10 or result['selections']):
            raise ValueError(f'Played-slate coverage differs from the August acceptance cohort: {result}')
    if any(b['seconds'] >= 300 for b in report['acquisition_batches']):
        raise ValueError('A played-slate acquisition batch exceeded the staging command timeout')
    if receipts or set(states) != {'done'}:
        raise ValueError('Played-slate hourly replay did not finish with an empty repeat')
    print(json.dumps(dict(coverage=report['replay_coverage'], completed=states['done'],
                          acquisition_seconds=report['acquisition_seconds'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('bindir', type=Path)
    parser.add_argument('--client-bin', type=Path)
    args = parser.parse_args()
    run(args.directory, args.bindir, args.client_bin or args.bindir)
