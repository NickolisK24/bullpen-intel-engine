"""Measure bounded acquisition and 24 hourly batches for the retained August acceptance slate."""
import argparse
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic

from psycopg2.extras import Json

from services.mlb_api import MLBApiClient
from shadow_current_worker import checkpoint, inventory, restore
from sync_v3 import evidence, savant
from sync_v3.acquisition_receipt import played_day_acquisition
from sync_v3.comparison import compare_finals
from sync_v3.current_worker import acquisition_failed, process
from sync_v3.cycle import run_cycle
from sync_v3.eligibility_recovery import recover
from sync_v3.readiness import represented_readiness
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
        official_counts = {}
        for facts, in cur:
            for line in facts:
                official_counts[line['game_pk'], line['pitcher_mlb_id']] = line['pitches_thrown']
                innings, outs = divmod(line['outs_recorded'], 3)
                pitching.append((line['game_pk'], line['team_id'], line['pitcher_mlb_id'], f'{innings}.{outs}',
                                 line['pitches_thrown'], line['strikeouts'], line['walks']))
        request = savant.day_request(DAY)
        receipt = evidence.latest_qualified_source(cur, request.endpoint, request.params())
        provider = None
        if receipt is not None:
            body = evidence.replay(cur, receipt).body
            provider = dict(sha256=body['sha256'], **savant.compare_pitch_counts(body['csv'], official_counts))
        cur.execute('SELECT count(*) FROM candidate.core_selections')
        selections, = cur.fetchone()
        cur.execute('SELECT pg_database_size(current_database())')
        size, = cur.fetchone()
    return dict(clubs=len({r['team'] for r in rosters}), roster_lists=len(rosters), finals=finals,
                pitching_lines=lines, pitcher_profiles=len(pitchers), selections=selections, database_bytes=size,
                statcast=provider,
                cohort=dict(roster_members=fingerprint(members), pitcher_profiles=fingerprint(pitchers),
                            pitching_lines=fingerprint(pitching)))


def recover_boston(connect):
    # Expected reads come from the independent August board-111.json.
    # SHA-256 of the complete board: 76bfa4359ad2791bc7ed656e0e8d78fffc55e9f35921bb33ca430a1b0a5169c2.
    client = MLBApiClient()
    with closing(connect()) as reader, reader, reader.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        initial = represented_readiness(cur, 111, DAY)
    if initial['team_state'] is not None or not initial['reason']:
        raise ValueError('The played checkpoint did not reproduce missing Boston readiness')
    batches = []
    with closing(client.session):
        for _ in range(12):
            with closing(connect()) as worker:
                outcome = recover(worker, 111, DAY, max_jobs=32, include_workload=True,
                                  fetch=lambda endpoint, params: client._get(endpoint, params=params))
            batches.append(dict(status=outcome['status'], received=len(outcome['receipts'])))
            if outcome['status'] == 'ready' and not outcome['receipts']:
                break
            if outcome['status'] not in ('batch_limit', 'ready'):
                raise ValueError(f"Boston recovery refused: {outcome}")
        else:
            raise ValueError(f'Boston recovery exceeded its historical request budget: {batches}')
    if not any(batch['received'] for batch in batches):
        raise ValueError('Historical readiness recovered without a new receipt')
    return dict(**boston_evidence(connect), initial_refusal=initial['reason'], batches=batches)


def boston_evidence(connect):
    with closing(connect()) as reader, reader, reader.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        report = represented_readiness(cur, 111, DAY)
        reads = sorted((int(pid), arm['read']['arm_read']) for pid, arm in report['arms'].items())
        digest = sha256(json.dumps(reads, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        cur.execute('SELECT count(*) FROM candidate.core_selections')
        selections, = cur.fetchone()
    if (report['membership_date'], report['reference_date'], report['team_state']['public_label'], digest, selections) != (
            '2017-08-28', '2017-08-29', 'Vulnerable', '13909568729de1806f113e791a4b1a8b91332add6b3a6ae4cba3c957d2583f82', 0):
        raise ValueError(f'Boston readiness differs from the archived board: {report}')
    return dict(club=111, membership=report['membership_date'], availability=report['reference_date'],
                state=report['team_state']['public_label'], arm_count=len(reads), arm_sha256=digest,
                selections=selections)


def acquisition_receipt(connect):
    with closing(connect(reviewer=True)) as reader, reader, reader.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return played_day_acquisition(cur, DAY)


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
        report['acquisition_receipt'] = acquisition_receipt(connect)
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
        report['historical_readiness'] = recover_boston(connect)
        dump = directory / 'played-readiness.pgdump'
        report['readiness_checkpoint_sha256'] = checkpoint(source, client_bin, dump)
        (directory / 'performance.json').write_text(json.dumps(report, sort_keys=True))
        before_restore = inventory(source)
    with isolated_cluster(bindir) as (restored, read_restored):
        restore(restored, client_bin, dump)
        if before_restore != inventory(restored):
            raise ValueError('Historical acquisition changed during checkpoint restore')
        report['restored_readiness'] = boston_evidence(read_restored)
        report['restored_acquisition_receipt'] = acquisition_receipt(read_restored)
        if report['restored_acquisition_receipt'] != report['acquisition_receipt']:
            raise ValueError('Played-day canonical acquisition receipt changed across recovery')

    (directory / 'performance.json').write_text(json.dumps(report, sort_keys=True))
    for result in (report['acquisition_coverage'], report['replay_coverage']):
        if (result['cohort'] != EXPECTED or result['roster_lists'] != 60 or result['clubs'] != 30
                or result['finals'] != 10 or result['selections'] or not result['statcast']
                or result['statcast']['status'] != 'pitch_counts_match'
                or (result['statcast']['thrown_pitch_rows'], result['statcast']['automatic_calls']) != (2808, 16)):
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
