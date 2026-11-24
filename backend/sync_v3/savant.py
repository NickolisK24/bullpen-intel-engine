"""Retain one represented day of MLB's Statcast CSV as provider evidence."""

import csv
from datetime import date
from hashlib import sha256
from io import StringIO

import requests

from sync_v3.discovery import Request


URL = 'https://baseballsavant.mlb.com/statcast_search/csv'
MAX_BYTES = 16 * 1024 * 1024
FIELDS = {'game_date', 'game_pk', 'at_bat_number', 'pitch_number', 'pitcher', 'batter', 'description',
          'launch_speed', 'launch_speed_angle', 'estimated_ba_using_speedangle',
          'estimated_slg_using_speedangle', 'estimated_woba_using_speedangle', 'woba_value', 'woba_denom'}


def day_request(day):
    params = dict(all='true', type='details', player_type='pitcher',
                  game_date_gt=day.isoformat(), game_date_lt=day.isoformat())
    return Request(URL, tuple(sorted(params.items())), 21600)


def request_day(params):
    day = date.fromisoformat(params['game_date_gt'])
    if day.year < 2015 or params != day_request(day).params():
        raise ValueError('Expected a single Statcast-era day and the full pitch detail scope')
    return day


def after_final(day, game_requests):
    if day.year >= 2015 and any(r.endpoint.endswith('/boxscore') for r in game_requests):
        return [day_request(day)]
    return []


def fetch(params):
    request_day(params)
    content = bytearray()
    with requests.get(URL, params=params, timeout=(5, 30), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Incomplete Savant HTTP response')
        for chunk in response.iter_content(chunk_size=65536):
            if len(content) + len(chunk) > MAX_BYTES:
                raise ValueError('Savant daily capture exceeds its size budget')
            content.extend(chunk)
    return {'csv': content.decode('utf-8'), 'sha256': sha256(content).hexdigest()}


def inspect(params, body):
    day = request_day(params).isoformat()
    raw = body.get('csv')
    if not isinstance(raw, str) or len(raw) > MAX_BYTES:
        raise ValueError('Missing or oversized Savant CSV')
    data = raw.encode('utf-8')
    if len(data) > MAX_BYTES or sha256(data).hexdigest() != body.get('sha256'):
        raise ValueError('Savant CSV content digest mismatch')
    rows = csv.DictReader(StringIO(raw.removeprefix('\ufeff'), newline=''), strict=True)
    try:
        names = rows.fieldnames or []
        if len(names) != len(set(names)) or not FIELDS.issubset(names):
            raise ValueError('Missing or duplicate Savant columns')
        pitches = set()
        for row in rows:
            if None in row or None in row.values() or row['game_date'] != day:
                raise ValueError('Unexpected Savant row shape or represented date')
            ids = tuple(int(row[key]) for key in ('game_pk', 'at_bat_number', 'pitch_number', 'pitcher', 'batter'))
            if min(ids) <= 0 or ids[:3] in pitches:
                raise ValueError('Ambiguous Savant pitch identity')
            pitches.add(ids[:3])
    except csv.Error as exc:
        raise ValueError('Malformed Savant CSV') from exc
    if not pitches:
        raise ValueError('Savant returned no pitch evidence for the played date')


def compare_pitch_counts(raw, official):
    """Compare thrown pitches by game and arm. Preserve automatic calls in the source."""
    from collections import Counter

    thrown = Counter()
    seen = set()
    automatic = 0
    for row in csv.DictReader(StringIO(raw.removeprefix('\ufeff'), newline='')):
        identity = int(row['game_pk']), int(row['pitcher'])
        seen.add(identity)
        if row['description'] in ('automatic_ball', 'automatic_strike'):
            automatic += 1
        else:
            thrown[identity] += 1
    differences = []
    for game, pitcher in sorted(seen | official.keys()):
        key = game, pitcher
        if key not in seen or key not in official or official[key] != thrown[key]:
            differences.append(dict(game_pk=game, mlb_pitcher_id=pitcher, official=official.get(key),
                                    provider=thrown[key] if key in seen else None))
    return dict(status='pitch_counts_match' if official and not differences else 'unqualified',
                official_lines=len(official), provider_lines=len(seen), thrown_pitch_rows=thrown.total(),
                automatic_calls=automatic, differences=differences)


def review_capture(cur, capture):
    """Read only provider evidence and official final revisions confirmed in this capture."""
    from sync_v3.evidence import replay

    cur.execute("""SELECT f.id FROM candidate.jobs j JOIN candidate.attempts a ON a.job_id=j.id
                   JOIN candidate.fetches f ON f.token=a.token
                   WHERE j.budget='historical' AND j.payload->>'capture'=%s
                     AND f.endpoint=%s AND f.outcome='received'""", (capture, URL))
    receipts = cur.fetchall()
    if not receipts:
        return None
    if len(receipts) != 1:
        raise ValueError('Expected a single received Savant observation for the capture')
    source = replay(cur, receipts[0][0])
    cur.execute("""SELECT r.facts FROM candidate.jobs j JOIN candidate.attempts a ON a.job_id=j.id
                   JOIN candidate.fetches f ON f.token=a.token
                   JOIN candidate.confirmations c ON c.source_id=f.id AND c.domain='final'
                   JOIN candidate.revisions r ON r.id=c.revision_id
                   WHERE j.budget='historical' AND j.payload->>'capture'=%s""", (capture,))
    official = {}
    for lines, in cur:
        for line in lines:
            key = line['game_pk'], line['pitcher_mlb_id']
            if key in official:
                raise ValueError('Ambiguous official final within a Savant comparison')
            official[key] = line['pitches_thrown']
    return dict(capture=capture, provider_sha256=source.body['sha256'],
                **compare_pitch_counts(source.body['csv'], official))
