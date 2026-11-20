"""Bind optional Team Board facts to the completed game's official pitching lines."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from hashlib import sha256
from typing import NamedTuple
import json

from models.game_ingestion_work_item import GameIngestionWorkItem
from models.pitcher import Pitcher

CONTRACT = 'team_board_official_pitching_lines_v1'
FIELDS = {
    'home_runs_allowed': 'homeRuns', 'strikeouts': 'strikeOuts',
    'walks': 'baseOnBalls', 'batters_faced': 'battersFaced',
    'inherited_runners': 'inheritedRunners', 'inherited_runners_scored': 'inheritedRunnersScored',
}
DOMAINS = {
    'home_runs_allowed': ('home_runs_allowed',),
    'k_bb_percent': ('strikeouts', 'walks', 'batters_faced'),
    'inherited_runner_context': ('inherited_runners', 'inherited_runners_scored'),
}


class Comparison(NamedTuple):
    verified: dict
    totals: dict
    lines: list
    source: str


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _mapping(value):
    return value if isinstance(value, dict) else {}


def count(value):
    return value if type(value) is int and value >= 0 else None


_daily_splits = ContextVar('team_performance_daily_splits', default=None)


@contextmanager
def capture_daily_splits():
    """Only the publishing sync may consume its already-acquired season responses."""
    token = _daily_splits.set({})
    try:
        yield
    finally:
        _daily_splits.reset(token)


def remember_splits(mlb_id, season, splits):
    current = _daily_splits.get()
    if current is None:
        return
    lines = {}
    for split in splits or ():
        if not isinstance(split, dict):
            lines = {}
            break
        if split.get('gameType') != 'R':
            if split.get('gameType'):
                continue
            lines = {}
            break
        game = _mapping(split.get('game')).get('gamePk')
        day = split.get('date')
        team = _mapping(split.get('team')).get('id')
        stats = _mapping(split.get('stat'))
        starts = count(stats.get('gamesStarted'))
        try:
            day_year = date.fromisoformat(day).year
        except (TypeError, ValueError):
            day_year = None
        if (not count(game) or not count(team) or day_year != season or game in lines
                or _mapping(split.get('player')).get('id') != mlb_id
                or starts not in (0, 1) or _mapping(split.get('sport')).get('id') != 1):
            lines = {}
            break
        lines[game] = (day, {
            'team': team, 'role': 'start' if starts else 'relief',
            **{field: count(stats.get(key)) for field, key in FIELDS.items()},
        })
    current[mlb_id] = lines


def _season_receipts(identities, through, team_id):
    receipts = {}
    for mlb_id in identities.values():
        lines = _daily_splits.get().get(mlb_id)
        if not lines:
            return {}
        for pk, (day, line) in lines.items():
            if day[:4] != str(through.year) or day > through.isoformat() or line['team'] != team_id:
                continue
            receipt = receipts.setdefault(pk, {'date': day, 'lines': {}})
            if receipt['date'] != day:
                return {}
            receipt['lines'][str(mlb_id)] = line
    for receipt in receipts.values():
        receipt['revision'] = _digest(receipt['lines'])
    return receipts


def game_receipt(game_pk, game_date, revision, boxscore, appearances):
    """Checkpoint only explicit official integers. Missing never equals zero."""
    lines = {}
    for appearance in appearances:
        player = appearance.get('pitcher_mlb_id')
        side = ((boxscore or {}).get('teams') or {}).get(appearance.get('side')) or {}
        entry = (side.get('players') or {}).get(f'ID{player}') or {}
        if ((entry.get('person') or {}).get('id') != player
                or (side.get('team') or {}).get('id') != appearance.get('team_id')
                or str(player) in lines):
            return None
        stats = (entry.get('stats') or {}).get('pitching') or {}
        lines[str(player)] = {
            'team': appearance['team_id'], 'role': appearance.get('appearance_role'),
            **{field: count(stats.get(key)) for field, key in FIELDS.items()},
        }
    return {'contract': CONTRACT, 'game_pk': game_pk, 'date': str(game_date),
            'revision': revision, 'lines': lines}


def load_comparisons(rows, pitcher_ids, team_id, through):
    """Read bounded sets once per club. Legacy or superseded checkpoints cannot qualify."""
    identities = dict(Pitcher.query.with_entities(Pitcher.id, Pitcher.mlb_id)
                      .filter(Pitcher.id.in_(pitcher_ids)).all())
    if len(identities) != len(set(pitcher_ids)):
        return compare(rows, identities, {}, team_id)
    if _daily_splits.get():
        return compare(rows, identities, _season_receipts(identities, through, team_id), team_id,
                       source='mlb_pitching_game_log')
    games = {row.mlb_game_pk for row in rows}
    items = GameIngestionWorkItem.query.filter(
        GameIngestionWorkItem.mlb_game_pk.in_(games),
        GameIngestionWorkItem.status == GameIngestionWorkItem.STATUS_COMPLETED,
        GameIngestionWorkItem.game_type == 'R',
    ).all()
    receipts = {}
    for item in items:
        receipt = _mapping(item.completion_proof).get('performance_lines')
        if (isinstance(receipt, dict) and receipt.get('contract') == CONTRACT
                and receipt.get('game_pk') == item.mlb_game_pk
                and receipt.get('date') == str(item.game_date)
                and receipt.get('revision') == item.source_revision and item.source_revision
                and isinstance(receipt.get('lines'), dict)
                and all(isinstance(line, dict) for line in receipt['lines'].values())
                and len(receipt['lines']) == item.rows_expected == item.rows_reconciled):
            receipts[item.mlb_game_pk] = receipt
    return compare(rows, identities, receipts, team_id)


def compare(rows, identities, receipts, team_id, *, source='mlb_final_boxscore'):
    counts = dict.fromkeys(DOMAINS, 0)
    totals = dict.fromkeys(FIELDS, 0)
    sample = []
    active = {str(p) for p in identities.values()}
    selected = {(r.mlb_game_pk, str(identities.get(r.pitcher_id))) for r in rows}
    for pk, receipt in receipts.items():
        for player, line in receipt['lines'].items():
            if (player in active and line.get('role') == 'relief' and line.get('team') == team_id
                    and (pk, player) not in selected):
                return Comparison(counts, totals, [], source)
    if len(selected) != len(rows):
        return Comparison(counts, totals, [], source)
    for row in rows:
        player = str(identities.get(row.pitcher_id))
        receipt = receipts.get(row.mlb_game_pk)
        if not receipt or receipt['date'] != str(row.game_date):
            continue
        line = receipt['lines'].get(player)
        if not line or line.get('team') != team_id or line.get('role') != 'relief':
            continue
        # Freeze the exact official inputs and identity used for this comparison.
        sample.append([row.mlb_game_pk, row.pitcher_id, int(player), receipt['date'],
                       receipt['revision'], [line.get(field) for field in FIELDS]])
        for domain, fields in DOMAINS.items():
            if domain == 'home_runs_allowed' and count(row.home_runs_allowed) is None:
                continue
            if any(count(line.get(f)) is None or
                   getattr(row, f, None) not in (None, line[f]) for f in fields):
                continue
            if domain == 'k_bb_percent' and line['strikeouts'] + line['walks'] > line['batters_faced']:
                continue
            if domain == 'inherited_runner_context' and line['inherited_runners_scored'] > line['inherited_runners']:
                continue
            counts[domain] += 1
            for f in fields:
                totals[f] += line[f]
    return Comparison(counts, totals, sorted(sample), source)


def qualify(capabilities, rows, comparison, team_id, through):
    counts, totals, sample, _ = comparison
    digest = _digest(sample)
    for domain, fields in DOMAINS.items():
        cap = capabilities[domain]
        cap.setdefault('coverage', {})['official_rows_verified'] = counts[domain]
        if not rows or counts[domain] != len(rows):
            continue
        inputs = {field: totals[field] for field in fields}
        cap['proof'] = {
            'contract': CONTRACT, 'team_id': team_id, 'through': through.isoformat(),
            'appearances': len(rows), 'sample_sha256': digest, 'inputs': inputs,
        }
        if domain == 'k_bb_percent':
            cap.update(_k_bb_result(inputs))
        else:
            cap.update(status='qualified', value=display(domain, inputs), reason_code=None, reason_codes=[])


def _k_bb_result(inputs):
    from services.performance_intelligence import AppearanceComponents, _exact_ratio
    from services.performance_metrics import CURRENT_ACTIVE_PEN_K_BB as K_BB

    components = AppearanceComponents(**{key: inputs[key] for key in DOMAINS['k_bb_percent']})
    bf = K_BB.denominator(components)
    reason = None
    value = None
    if bf == 0:
        reason = K_BB.denominator_zero_reason
    elif bf < K_BB.minimum_sample:
        reason = 'below_minimum_batters_faced'
    else:
        rate = _exact_ratio(K_BB.numerator(components), bf, K_BB.display_precision)
        value = K_BB.formatter('0.0' if rate == '-0.0' else rate)
    return dict(metric_id=K_BB.metric_id, method_version=K_BB.version,
                minimum_sample=K_BB.minimum_sample, minimum_sample_unit=K_BB.minimum_sample_unit,
                minimum_sample_authority=K_BB.minimum_sample_authority,
                status='unavailable' if reason else 'qualified', value=value,
                reason_code=reason, reason_codes=[reason] if reason else [])


def display(domain, inputs):
    if domain == 'inherited_runner_context':
        return f"{inputs['inherited_runners_scored']} of {inputs['inherited_runners']} scored"
    return str(inputs['home_runs_allowed'])


def valid_capability(domain, cap, *, team_id, through, appearances):
    if not isinstance(cap, dict):
        return False
    evidence_only = (domain == 'k_bb_percent' and cap.get('status') == 'unavailable'
                     and cap.get('value') is None and cap.get('reason_code') == 'metric_publication_rule_unapproved')
    if cap.get('status') == 'unavailable' and 'proof' not in cap:
        return (cap.get('value') is None and 'metric_id' not in cap
                and cap.get('reason_code') not in ('metric_publication_rule_unapproved',
                                                   'zero_batters_faced', 'below_minimum_batters_faced'))
    proof = cap.get('proof')
    if (domain != 'k_bb_percent' and cap.get('status') != 'qualified') or not isinstance(proof, dict):
        return False
    inputs = proof.get('inputs')
    digest = proof.get('sample_sha256')
    if (proof.get('contract') != CONTRACT or proof.get('team_id') != team_id
            or proof.get('through') != through or not count(appearances)
            or proof.get('appearances') != appearances
            or _mapping(cap.get('coverage')).get('official_rows_verified') != appearances
            or not isinstance(digest, str) or len(digest) != 64
            or any(c not in '0123456789abcdef' for c in digest)
            or not isinstance(inputs, dict)
            or any(count(inputs.get(f)) is None for f in DOMAINS[domain])):
        return False
    if domain == 'k_bb_percent':
        if inputs['strikeouts'] + inputs['walks'] > inputs['batters_faced']:
            return False
        if evidence_only:
            return 'metric_id' not in cap  # Preserve the frozen pre-approval package.
        return all(cap.get(key) == value for key, value in _k_bb_result(inputs).items())
    if domain == 'inherited_runner_context' and inputs['inherited_runners_scored'] > inputs['inherited_runners']:
        return False
    return cap.get('value') == display(domain, inputs)


def valid_comparison(read, team_id, through, population):
    caps = read.get('capabilities')
    if not isinstance(caps, dict) or not all(
        valid_capability(key, caps.get(key), team_id=team_id, through=through,
                         appearances=read.get('relief_appearances'))
        for key in DOMAINS
    ):
        return False
    qualified = [key for key in DOMAINS if 'proof' in caps[key]]
    if not qualified:
        return True
    receipt = read.get('official_comparison')
    if (not isinstance(receipt, dict) or receipt.get('contract') != CONTRACT
            or not isinstance(through, str) or len(through) != 10
            or receipt.get('team_id') != team_id or receipt.get('through') != through
            or receipt.get('source') not in ('mlb_pitching_game_log', 'mlb_final_boxscore')
            or receipt.get('fields') != list(FIELDS)):
        return False
    lines = receipt.get('lines')
    if not isinstance(lines, list) or len(lines) != read.get('relief_appearances'):
        return False
    keys = set()
    bf_fields = [list(FIELDS).index(field) for field in DOMAINS['k_bb_percent']]
    for line in lines:
        if not isinstance(line, list) or len(line) != 6:
            return False
        game, pitcher, mlb, day, revision, inputs = line
        if (not count(game) or not count(pitcher) or pitcher not in population or not count(mlb)
                or not isinstance(day, str) or not through[:4] + '-01-01' <= day <= through
                or not isinstance(revision, str) or len(revision) != 64
                or not isinstance(inputs, list) or len(inputs) != len(FIELDS)
                or (game, mlb) in keys):
            return False
        keys.add((game, mlb))
        if 'k_bb_percent' in qualified:
            k, bb, bf = (count(inputs[index]) for index in bf_fields)
            if None in (k, bb, bf) or k + bb > bf:
                return False
    digest = _digest(lines)
    for domain in qualified:
        proof = caps[domain]['proof']
        if proof['sample_sha256'] != digest:
            return False
        for field in DOMAINS[domain]:
            index = list(FIELDS).index(field)
            values = [count(line[5][index]) for line in lines]
            if None in values or sum(values) != proof['inputs'][field]:
                return False
    return True
