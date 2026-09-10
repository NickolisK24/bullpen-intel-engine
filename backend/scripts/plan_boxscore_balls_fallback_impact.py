"""Bounded, read-only impact plan for the box-score ``balls`` fallback.

A production audit established that the completed-game box score is the only
source that carries ``balls`` for a pitching appearance: the player game-log
split omits the key entirely, so the daily correction lane — which reads the
split — can never correct the field, no matter how many times it re-sweeps the
horizon. Stored values that disagree with the official triple are therefore
uncorrectable rather than disputed.

Before any writer changes, this tool answers the only question that authorizes
one: **exactly which stored rows would change, and would anything other than
``balls`` move?**

It answers it in two bounded stages, each one narrowing the next:

1. **Box-score stage** — one box-score fetch per distinct game in the horizon.
   A row becomes a candidate only when the box score's own pitch accounting
   validates (``balls + strikes == numberOfPitches``) *and* its ``balls``
   differs from what is stored. Rows that already agree are counted and
   dropped here, so the split stage never sees them.
2. **Split stage** — one game-log fetch per *candidate pitcher* (not per
   rostered pitcher). It rebuilds the appearance exactly as the daily lane
   would: real split → canonical values builder → fallback decision → canonical
   ``plan_row``. The resulting plan is the proposed change, observed rather
   than described.

The second stage is what makes the claim "only ``balls`` moves" evidence
instead of intention: it runs the real planner over the real split and reports
whatever ``changed_fields`` comes back, including fields nobody expected.

Read-only, and provably so: a read-only transaction, a write probe that must be
refused, a horizon fingerprint taken before and after, and an explicit
rollback. It creates no work item, no dead letter, no SyncFailure, advances no
checkpoint, corrects nothing, and publishes nothing.

Reporting is deliberately narrow: the approved fallback field and the two
companions needed to interpret it, plus identifiers already present in run
artifacts. No raw payloads, no connection strings, no credentials, no
filesystem paths, no exception messages.

    python scripts/plan_boxscore_balls_fallback_impact.py \
        --days-back 7 --output artifacts/fallback-impact/balls-impact.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'
# This tool must never be able to write, whatever the environment says.
os.environ['GAME_DRIVEN_INGESTION_MODE'] = 'off'


# The approved fallback field and the companions required to interpret it.
REPORTABLE_SOURCE_KEYS = ('balls', 'strikes', 'numberOfPitches')
REPORTABLE_VALUE_FIELDS = ('balls', 'strikes', 'pitches_thrown')

# Why a horizon row never became a candidate. Every row is accounted for.
SKIP_ROW_NO_BOXSCORE = 'boxscore_unavailable'
SKIP_ROW_NO_LINE = 'no_boxscore_pitching_line'
SKIP_ROW_INVALID_LINE = 'boxscore_values_inconsistent_or_absent'
SKIP_ROW_ALREADY_MATCHING = 'stored_value_already_matches_boxscore'
SKIP_ROW_NOT_FINAL = 'game_not_final'
SKIP_ROW_NO_PITCHER = 'pitcher_identity_unresolved'

# Why a candidate produced no confirmed plan.
UNCONFIRMED_SPLIT_UNAVAILABLE = 'split_fetch_unavailable'
UNCONFIRMED_NO_SPLIT_FOR_GAME = 'no_split_for_game'
UNCONFIRMED_FALLBACK_REFUSED = 'fallback_refused'
UNCONFIRMED_SPLIT_SUPPLIES_FIELD = 'split_supplies_field'
UNCONFIRMED_NOT_ATTEMPTED = 'split_stage_not_attempted'
UNCONFIRMED_TRUNCATED = 'beyond_candidate_limit'

EXIT_OK = 0
EXIT_PLAN_INCOMPLETE = 1
EXIT_UNSAFE = 2
EXIT_OUT_OF_SCOPE = 3


def _fingerprint(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:32]


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Bounded read-only impact plan for the completed-game box-score '
            'fallback. Performs no write of any kind.'
        )
    )
    parser.add_argument(
        '--days-back', type=int, default=7,
        help='Correction horizon in days. Defaults to the daily lane default.',
    )
    parser.add_argument(
        '--max-candidates', type=int, default=250,
        help='Upper bound on candidates carried into the split stage. Any '
             'excess is reported explicitly, never silently dropped.',
    )
    parser.add_argument(
        '--skip-split-confirmation', action='store_true',
        help='Run the box-score stage only. Produces candidates but no '
             'confirmed plans, and exits incomplete.',
    )
    parser.add_argument('--output', help='Optional durable artifact path.')
    return parser.parse_args(argv)


# ── Horizon ─────────────────────────────────────────────────────────────────


def _horizon_rows(days_back):
    """Stored appearances inside the correction horizon, oldest first."""
    from datetime import datetime, timezone

    from models.game_log import GameLog
    from services.availability_reference_date import resolve_product_day

    reference_date = resolve_product_day(datetime.now(timezone.utc)).calendar_date
    cutoff = reference_date - timedelta(days=max(int(days_back or 0), 0))
    rows = (
        GameLog.query
        .filter(GameLog.game_date >= cutoff, GameLog.game_date <= reference_date)
        .order_by(GameLog.game_date, GameLog.mlb_game_pk, GameLog.pitcher_id)
        .all()
    )
    return rows, cutoff, reference_date


def _horizon_fingerprint(rows):
    """Digest of every reportable stored value across the horizon.

    Taken before and after the plan. Any difference means something wrote, and
    the tool fails rather than reporting a plan it may itself have invalidated.
    """
    return _fingerprint([
        [
            row.pitcher_id, row.mlb_game_pk,
            *(getattr(row, field, None) for field in REPORTABLE_VALUE_FIELDS),
        ]
        for row in rows
    ])


# ── Stage 1: box-score candidates ───────────────────────────────────────────


def _boxscore_stage(rows, *, plan, pitcher_by_id):
    """Narrow the horizon to rows the box score would actually move."""
    from services import gamelog_source_authority as authority
    from services import sync as sync_service

    lines_cache = {}
    unavailable = set()
    finality_cache = {}
    candidates = []
    skipped = {}

    for row in rows:
        game_pk = row.mlb_game_pk
        pitcher = pitcher_by_id.get(row.pitcher_id)
        if pitcher is None or pitcher.mlb_id is None:
            skipped[SKIP_ROW_NO_PITCHER] = skipped.get(SKIP_ROW_NO_PITCHER, 0) + 1
            continue

        finality = sync_service.resolve_scheduled_game_finality(
            game_pk, finality_cache,
        )
        if finality == sync_service.SPLIT_FINALITY_NOT_FINAL:
            skipped[SKIP_ROW_NOT_FINAL] = skipped.get(SKIP_ROW_NOT_FINAL, 0) + 1
            continue

        if game_pk not in lines_cache and game_pk not in unavailable:
            plan['boxscore_fetches'] += 1
            try:
                lines_cache[game_pk] = (
                    sync_service.mlb_client.get_game_pitching_lines(game_pk) or []
                )
            except Exception as exc:  # noqa: BLE001 - class only, never message
                unavailable.add(game_pk)
                plan['boxscore_fetch_failures'] += 1
                plan.setdefault('fetch_error_classes', {})
                key = type(exc).__name__
                plan['fetch_error_classes'][key] = (
                    plan['fetch_error_classes'].get(key, 0) + 1
                )

        if game_pk in unavailable:
            skipped[SKIP_ROW_NO_BOXSCORE] = skipped.get(SKIP_ROW_NO_BOXSCORE, 0) + 1
            continue

        stats, refusal = authority.select_boxscore_line(
            lines_cache[game_pk], pitcher.mlb_id,
        )
        if refusal is not None:
            skipped[SKIP_ROW_NO_LINE] = skipped.get(SKIP_ROW_NO_LINE, 0) + 1
            continue

        field_authority = authority.authority_for('balls')
        if field_authority.validate(stats) is not None:
            skipped[SKIP_ROW_INVALID_LINE] = (
                skipped.get(SKIP_ROW_INVALID_LINE, 0) + 1
            )
            continue

        boxscore_balls = _safe_int(stats.get('balls'))
        stored_balls = _safe_int(getattr(row, 'balls', None))
        if boxscore_balls == stored_balls:
            skipped[SKIP_ROW_ALREADY_MATCHING] = (
                skipped.get(SKIP_ROW_ALREADY_MATCHING, 0) + 1
            )
            continue

        candidates.append({
            'game_pk': game_pk,
            'game_date': getattr(row, 'game_date', None),
            'pitcher_mlb_id': pitcher.mlb_id,
            'local_pitcher_id': pitcher.id,
            'stored': {
                field: _safe_int(getattr(row, field, None))
                for field in REPORTABLE_VALUE_FIELDS
            },
            'boxscore': {
                key: _safe_int(stats.get(key)) for key in REPORTABLE_SOURCE_KEYS
            },
            'source_revision': authority.fallback_evidence_revision(
                game_pk=game_pk, pitcher_mlb_id=pitcher.mlb_id, stats=stats,
            ),
            'boxscore_stats': stats,
            'row': row,
        })

    plan['rows_skipped'] = dict(sorted(skipped.items()))
    return candidates


# ── Stage 2: split confirmation ─────────────────────────────────────────────


def _split_stage(candidates, *, plan, pitcher_by_id, limit):
    """Rebuild each candidate the way the daily lane would, and plan it.

    One game-log fetch per candidate pitcher, cached — a pitcher with three
    affected appearances is fetched once.
    """
    from services import game_log_reconciliation as reconciliation
    from services import gamelog_source_authority as authority
    from services import sync as sync_service

    splits_cache = {}
    unavailable_pitchers = set()
    confirmed = []
    unconfirmed = {}

    def _mark(reason):
        unconfirmed[reason] = unconfirmed.get(reason, 0) + 1

    for index, candidate in enumerate(candidates):
        if index >= limit:
            _mark(UNCONFIRMED_TRUNCATED)
            continue

        pitcher = pitcher_by_id.get(candidate['local_pitcher_id'])
        row = candidate['row']
        season = getattr(candidate['game_date'], 'year', None)
        cache_key = (pitcher.mlb_id, season)

        if cache_key not in splits_cache and cache_key not in unavailable_pitchers:
            plan['split_fetches'] += 1
            try:
                splits_cache[cache_key] = (
                    sync_service.mlb_client.get_pitcher_game_logs(
                        pitcher.mlb_id, season=season,
                    ) or []
                )
            except Exception as exc:  # noqa: BLE001 - class only, never message
                unavailable_pitchers.add(cache_key)
                plan['split_fetch_failures'] += 1
                plan.setdefault('fetch_error_classes', {})
                key = type(exc).__name__
                plan['fetch_error_classes'][key] = (
                    plan['fetch_error_classes'].get(key, 0) + 1
                )

        if cache_key in unavailable_pitchers:
            _mark(UNCONFIRMED_SPLIT_UNAVAILABLE)
            continue

        split = next(
            (
                item for item in splits_cache[cache_key]
                if (item.get('game') or {}).get('gamePk') == candidate['game_pk']
            ),
            None,
        )
        if split is None:
            _mark(UNCONFIRMED_NO_SPLIT_FOR_GAME)
            continue

        stat = split.get('stat') or {}
        values = _values_from(sync_service, row, pitcher, candidate, stat)
        uncomparable = reconciliation.uncomparable_fields(values, stat)

        if not authority.approved_uncomparable_fields(uncomparable):
            # The split carries the field after all, so the daily lane can
            # already correct it and this row is outside the repair's scope.
            # Not a refusal — the fallback was never reached.
            _mark(UNCONFIRMED_SPLIT_SUPPLIES_FIELD)
            continue

        decision = authority.resolve_fallback_values(
            split_stats=stat,
            boxscore_stats=candidate['boxscore_stats'],
            uncomparable=uncomparable,
            game_pk=candidate['game_pk'],
            pitcher_mlb_id=pitcher.mlb_id,
            game_final=True,
        )
        if not decision['applied_fields']:
            # A fail-closed backstop. The box-score stage validated this same
            # line, so reaching here means the two stages disagree — which is
            # reported, never resolved by preferring one of them.
            _mark(UNCONFIRMED_FALLBACK_REFUSED)
            plan.setdefault('fallback_refusals', {})
            for reason in decision['refusals'].values():
                plan['fallback_refusals'][reason] = (
                    plan['fallback_refusals'].get(reason, 0) + 1
                )
            continue

        enriched = authority.enriched_stats(stat, decision)
        enriched_values = _values_from(sync_service, row, pitcher, candidate, enriched)
        row_plan = reconciliation.plan_row(
            existing=row,
            values=enriched_values,
            stats=enriched,
            include_leverage_index=False,
            game_pk=candidate['game_pk'],
            pitcher_mlb_id=pitcher.mlb_id,
            local_pitcher_id=pitcher.id,
        )
        changed = sorted(row_plan.get('changed_fields') or ())
        confirmed.append({
            'game_pk': candidate['game_pk'],
            'game_date': str(candidate['game_date']),
            'pitcher_mlb_id': pitcher.mlb_id,
            'stored_balls': candidate['stored']['balls'],
            'proposed_balls': _safe_int(decision['values'].get('balls')),
            'boxscore': candidate['boxscore'],
            'split_supplies_balls': 'balls' in stat
            and stat.get('balls') not in (None, ''),
            'split_uncomparable_fields': list(uncomparable),
            'applied_fallback_fields': list(decision['applied_fields']),
            'source_authority': decision['authority_contract'],
            'source_revision': decision['source_revision'],
            'action': row_plan.get('action'),
            'changed_fields': changed,
            'difference_classifications': list(
                row_plan.get('difference_classifications') or ()
            ),
            'target_state_digest': row_plan.get('target_state_digest'),
            'stored_state_digest': row_plan.get('stored_state_digest'),
            'out_of_scope_fields': [
                field for field in changed
                if field not in authority.APPROVED_FALLBACK_FIELDS
            ],
        })

    plan['unconfirmed_candidates'] = dict(sorted(unconfirmed.items()))
    if 'fallback_refusals' in plan:
        plan['fallback_refusals'] = dict(sorted(plan['fallback_refusals'].items()))
    return confirmed


def _values_from(sync_service, row, pitcher, candidate, stats):
    """Governed values for this appearance, built by the canonical builder.

    Game metadata comes from the stored row so the plan isolates the source
    difference under test: a metadata change would otherwise show up as
    fallback impact when it has nothing to do with the fallback.
    """
    return sync_service._game_log_values_from_stats(
        stats=stats,
        pitcher=pitcher,
        game_pk=candidate['game_pk'],
        game_date=candidate['game_date'],
        game_type=getattr(row, 'game_type', 'R') or 'R',
        opponent=getattr(row, 'opponent', None),
        opponent_abbreviation=getattr(row, 'opponent_abbreviation', None),
        games_started=_safe_int(getattr(row, 'games_started', 0)) or 0,
    )


# ── Entry point ─────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from models.pitcher import Pitcher
    from services import gamelog_source_authority as authority
    from utils.db import db

    plan = {
        'tool': 'boxscore_fallback_impact_planner',
        'authority_contract': authority.AUTHORITY_CONTRACT,
        'authority_version': authority.AUTHORITY_VERSION,
        'approved_fallback_fields': list(authority.APPROVED_FALLBACK_FIELDS),
        'days_back': args.days_back,
        'max_candidates': args.max_candidates,
        'split_confirmation_requested': not args.skip_split_confirmation,
        'read_only_transaction': False,
        'write_probe_refused': False,
        'database_writes_performed': 0,
        'horizon_fingerprint_before': None,
        'horizon_fingerprint_after': None,
        'horizon_unchanged': None,
        'horizon_rows': 0,
        'horizon_games': 0,
        'boxscore_fetches': 0,
        'boxscore_fetch_failures': 0,
        'split_fetches': 0,
        'split_fetch_failures': 0,
        'candidates': 0,
        'confirmed_changes': 0,
        'out_of_scope_changes': 0,
        'affected_rows': [],
    }

    with app.app_context():
        db.session.execute(db.text('SET TRANSACTION READ ONLY'))
        plan['read_only_transaction'] = True
        try:
            db.session.execute(
                db.text('CREATE TEMP TABLE _fallback_impact_write_probe (x int)')
            )
        except Exception:
            db.session.rollback()
            db.session.execute(db.text('SET TRANSACTION READ ONLY'))
            plan['write_probe_refused'] = True

        if not plan['write_probe_refused']:
            db.session.rollback()
            print(
                '::error::Write probe was NOT refused. The session is not '
                'read-only; refusing to continue.'
            )
            return EXIT_UNSAFE

        rows, cutoff, reference_date = _horizon_rows(args.days_back)
        plan['horizon_start'] = cutoff.isoformat()
        plan['horizon_end'] = reference_date.isoformat()
        plan['horizon_rows'] = len(rows)
        plan['horizon_games'] = len({row.mlb_game_pk for row in rows})
        plan['horizon_fingerprint_before'] = _horizon_fingerprint(rows)

        pitcher_by_id = {
            pitcher.id: pitcher
            for pitcher in Pitcher.query.filter(
                Pitcher.id.in_({row.pitcher_id for row in rows})
            ).all()
        } if rows else {}

        candidates = _boxscore_stage(
            rows, plan=plan, pitcher_by_id=pitcher_by_id,
        )
        plan['candidates'] = len(candidates)

        if args.skip_split_confirmation:
            plan['unconfirmed_candidates'] = {
                UNCONFIRMED_NOT_ATTEMPTED: len(candidates),
            }
            confirmed = []
        else:
            confirmed = _split_stage(
                candidates, plan=plan, pitcher_by_id=pitcher_by_id,
                limit=max(int(args.max_candidates or 0), 0),
            )

        plan['confirmed_changes'] = len(confirmed)
        plan['out_of_scope_changes'] = sum(
            1 for item in confirmed if item['out_of_scope_fields']
        )
        plan['affected_rows'] = confirmed
        plan['affected_game_pks'] = sorted({item['game_pk'] for item in confirmed})
        plan['affected_pitcher_mlb_ids'] = sorted(
            {item['pitcher_mlb_id'] for item in confirmed}
        )

        after, _cutoff, _reference = _horizon_rows(args.days_back)
        plan['horizon_fingerprint_after'] = _horizon_fingerprint(after)
        plan['horizon_unchanged'] = (
            plan['horizon_fingerprint_before'] == plan['horizon_fingerprint_after']
        )
        db.session.rollback()

    plan['every_change_is_approved_field_only'] = (
        plan['out_of_scope_changes'] == 0
    )
    plan['affected_set_fully_enumerated'] = not plan.get('unconfirmed_candidates')
    plan['plan_fingerprint'] = _fingerprint([
        (item['game_pk'], item['pitcher_mlb_id'], item['target_state_digest'])
        for item in plan['affected_rows']
    ])
    _render(plan)

    if args.output:
        from utils.summary_output import SummaryOutputError, write_summary

        try:
            write_summary(plan, args.output)
        except SummaryOutputError as exc:
            print(f'::error::Impact plan output failed (reason={exc.reason}).')
            return EXIT_PLAN_INCOMPLETE

    if not plan['horizon_unchanged']:
        print('::error::The horizon changed during a read-only impact plan.')
        return EXIT_UNSAFE
    if not plan['every_change_is_approved_field_only']:
        print(
            '::error::A proposed change touches a field outside the approved '
            'fallback set. The repair is NOT authorized as scoped.'
        )
        return EXIT_OUT_OF_SCOPE
    if not plan['affected_set_fully_enumerated']:
        print(
            '::warning::Some candidates could not be confirmed. The affected '
            'set is a lower bound, not a complete enumeration.'
        )
        return EXIT_PLAN_INCOMPLETE
    return EXIT_OK


def _render(plan) -> None:
    print('\nBox-score fallback impact plan')
    print(f"  horizon:               {plan.get('horizon_start')} .. "
          f"{plan.get('horizon_end')} ({plan['days_back']}d)")
    print(f"  read-only transaction: {plan['read_only_transaction']}")
    print(f"  write probe refused:   {plan['write_probe_refused']}")
    print(f"  database writes performed: {plan['database_writes_performed']}")
    print(f"  horizon unchanged:     {plan['horizon_unchanged']}")
    print(f"  horizon rows / games:  {plan['horizon_rows']} / "
          f"{plan['horizon_games']}")
    print(f"  boxscore fetches:      {plan['boxscore_fetches']} "
          f"(failed {plan['boxscore_fetch_failures']})")
    print(f"  split fetches:         {plan['split_fetches']} "
          f"(failed {plan['split_fetch_failures']})")
    print(f"  rows skipped:          {plan.get('rows_skipped') or {}}")
    print(f"  candidates:            {plan['candidates']}")
    print(f"  confirmed changes:     {plan['confirmed_changes']}")
    print(f"  unconfirmed:           {plan.get('unconfirmed_candidates') or {}}")
    print(f"  fallback refusals:     {plan.get('fallback_refusals') or {}}")
    print(f"  out-of-scope changes:  {plan['out_of_scope_changes']}")
    print(f"  affected games:        {len(plan.get('affected_game_pks') or ())}")
    print(f"  plan fingerprint:      {plan['plan_fingerprint']}")
    for item in (plan.get('affected_rows') or ())[:25]:
        print(
            f"    game_pk={item['game_pk']} pitcher={item['pitcher_mlb_id']} "
            f"balls {item['stored_balls']} -> {item['proposed_balls']} "
            f"action={item['action']} changed={item['changed_fields']}"
        )
    if len(plan.get('affected_rows') or ()) > 25:
        print(f"    ... {len(plan['affected_rows']) - 25} more in the artifact")
    print()


if __name__ == '__main__':
    raise SystemExit(main())
