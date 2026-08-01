"""Read-only field-authority audit for one canonical appearance row.

Written for a specific unanswered question and generalized so it can answer the
next one: **which source actually owns a governed GameLog field, and why do two
production lanes disagree about it?**

The daily shadow lane and the postgame shadow lane both reach the same
canonical planner, but they feed it different source shapes — the daily legacy
writer reads the player game-log split, the game-driven lane reads the
completed-game box score. ``correctable_fields`` includes an optional stat only
when the source dict carries its key, so a field one source omits is never
compared and never corrected by that lane. It is not found equal; it is never
looked at.

This script gathers, for one appearance, the three values that settle it:

* what the completed-game box score says;
* what the player game-log split says;
* what is actually stored.

...and then runs both source shapes through the **existing** canonical
functions, so the planner's verdict is observed rather than re-derived.

Read-only, and provably so: it opens a read-only transaction, proves a write is
refused, fingerprints the row before and after, and rolls back. It creates no
work item, no dead letter, no SyncFailure, advances no checkpoint, and
publishes nothing.

Output is deliberately narrow. The exact numeric values for the audited field
and the two fields needed to interpret it (strikes, pitches) are reported,
because the question cannot be answered without them. Nothing else is: no raw
payload, no unrelated player, no connection string, no credential, no path, no
exception text.

    python scripts/inspect_gamelog_field_authority.py \
        --game-pk 824488 --pitcher-mlb-id 668716 --field balls \
        --output artifacts/field-authority/balls-824488.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'
# This tool must never be able to write, whatever the environment says.
os.environ['GAME_DRIVEN_INGESTION_MODE'] = 'off'


# Fields whose exact values may be reported. Enough to interpret the audited
# statistic, and nothing beyond it.
REPORTABLE_VALUE_FIELDS = ('balls', 'strikes', 'pitches_thrown')
REPORTABLE_SOURCE_KEYS = ('balls', 'strikes', 'numberOfPitches')

# Context fields reported as presence and shape only.
CONTEXT_FIELDS = (
    'batters_faced', 'innings_pitched_outs', 'games_started', 'game_date',
)

EXIT_OK = 0
EXIT_AUDIT_INCOMPLETE = 1
EXIT_UNSAFE = 2


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
            'Read-only authority audit for one governed GameLog field on one '
            'appearance. Performs no write of any kind.'
        )
    )
    parser.add_argument('--game-pk', required=True, type=int)
    parser.add_argument('--pitcher-mlb-id', required=True, type=int)
    parser.add_argument(
        '--field', default='balls',
        help='Governed field to audit. Defaults to the field this tool was '
             'written for.',
    )
    parser.add_argument('--output', help='Optional durable artifact path.')
    return parser.parse_args(argv)


# ── Evidence collection ─────────────────────────────────────────────────────


def _boxscore_evidence(game_pk, pitcher_mlb_id):
    """The completed-game box score line for this pitcher."""
    from services import sync as sync_service

    boxscore = sync_service.mlb_client.get_game_boxscore(game_pk)
    lines = sync_service._extract_pitching_lines_from_boxscore(boxscore)
    for line in lines:
        if line.get('player_id') == pitcher_mlb_id or (
            line.get('person_id') == pitcher_mlb_id
        ):
            stats = line.get('stats') or {}
            return {
                'available': True,
                'source': 'completed_game_boxscore',
                'stat_keys_present': sorted(
                    key for key in REPORTABLE_SOURCE_KEYS if key in stats
                ),
                'values': {
                    key: _safe_int(stats.get(key))
                    for key in REPORTABLE_SOURCE_KEYS
                },
                'stats_key_count': len(stats),
                'payload_fingerprint': _fingerprint(sorted(stats.items())),
            }
    return {
        'available': False,
        'source': 'completed_game_boxscore',
        'reason': 'no_pitching_line_for_pitcher',
    }


def _game_log_split_evidence(game_pk, pitcher_mlb_id, season):
    """The player game-log split for the same appearance."""
    from services import sync as sync_service

    splits = sync_service.mlb_client.get_pitcher_game_logs(
        pitcher_mlb_id, season=season,
    ) or []
    for split in splits:
        game = split.get('game') or {}
        if game.get('gamePk') != game_pk:
            continue
        stats = split.get('stat') or {}
        return {
            'available': True,
            'source': 'player_game_log_split',
            'stat_keys_present': sorted(
                key for key in REPORTABLE_SOURCE_KEYS if key in stats
            ),
            'values': {
                key: _safe_int(stats.get(key))
                for key in REPORTABLE_SOURCE_KEYS
            },
            'stats_key_count': len(stats),
            'payload_fingerprint': _fingerprint(sorted(stats.items())),
        }
    return {
        'available': False,
        'source': 'player_game_log_split',
        'reason': 'no_split_for_game',
    }


def _stored_evidence(game_pk, pitcher_mlb_id):
    from models.game_log import GameLog
    from models.pitcher import Pitcher

    pitcher = Pitcher.query.filter_by(mlb_id=pitcher_mlb_id).first()
    if pitcher is None:
        return {'available': False, 'reason': 'pitcher_not_found'}, None
    row = GameLog.query.filter_by(
        pitcher_id=pitcher.id, mlb_game_pk=game_pk,
    ).first()
    if row is None:
        return {'available': False, 'reason': 'appearance_row_not_found'}, None

    evidence = {
        'available': True,
        'values': {
            field: _safe_int(getattr(row, field, None))
            for field in REPORTABLE_VALUE_FIELDS
        },
        'context_present': {
            field: getattr(row, field, None) is not None
            for field in CONTEXT_FIELDS
        },
        'appearance_team_source': getattr(row, 'appearance_team_source', None),
        'appearance_team_status': getattr(row, 'appearance_team_status', None),
        'stat_correction_count': _safe_int(
            getattr(row, 'stat_correction_count', None)
        ),
        'last_stat_correction_source': getattr(
            row, 'last_stat_correction_source', None,
        ),
        'row_fingerprint': _fingerprint([
            (field, getattr(row, field, None))
            for field in sorted(REPORTABLE_VALUE_FIELDS + CONTEXT_FIELDS)
        ]),
    }
    return evidence, row


def _planner_verdict(row, source_evidence, source_stats, pitcher, game_pk):
    """Run the source through the CANONICAL planner. No second comparator."""
    from services import game_log_reconciliation as reconciliation
    from services import sync as sync_service

    if not source_evidence.get('available'):
        return {'available': False, 'reason': source_evidence.get('reason')}

    values = sync_service._game_log_values_from_stats(
        stats=source_stats,
        pitcher=pitcher,
        game_pk=game_pk,
        game_date=getattr(row, 'game_date', None),
        game_type=getattr(row, 'game_type', 'R') or 'R',
        opponent=getattr(row, 'opponent', None),
        opponent_abbreviation=getattr(row, 'opponent_abbreviation', None),
        games_started=_safe_int(getattr(row, 'games_started', 0)) or 0,
    )
    plan = reconciliation.plan_row(
        existing=row,
        values=values,
        stats=source_stats,
        include_leverage_index=False,
        game_pk=game_pk,
        pitcher_mlb_id=getattr(pitcher, 'mlb_id', None),
        local_pitcher_id=getattr(pitcher, 'id', None),
    )
    return {
        'available': True,
        'derived_values': {
            field: _safe_int(values.get(field))
            for field in REPORTABLE_VALUE_FIELDS
        },
        'action': plan.get('action'),
        'changed_fields': list(plan.get('changed_fields') or ()),
        'uncomparable_fields': list(plan.get('uncomparable_fields') or ()),
        'difference_classifications': list(
            plan.get('difference_classifications') or ()
        ),
        'blocked_reason': plan.get('blocked_reason'),
        'target_state_digest': plan.get('target_state_digest'),
        'stored_state_digest': plan.get('stored_state_digest'),
    }


# ── Entry point ─────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from models.pitcher import Pitcher
    from utils.db import db

    audit = {
        'audited_field': args.field,
        'game_pk': args.game_pk,
        'pitcher_mlb_id': args.pitcher_mlb_id,
        'read_only_transaction': False,
        'write_probe_refused': False,
        'database_writes_performed': 0,
        'row_fingerprint_before': None,
        'row_fingerprint_after': None,
        'row_unchanged': None,
    }

    with app.app_context():
        # Read-only for the whole audit, proven rather than asserted.
        db.session.execute(db.text('SET TRANSACTION READ ONLY'))
        audit['read_only_transaction'] = True
        try:
            db.session.execute(
                db.text('CREATE TEMP TABLE _field_authority_write_probe (x int)')
            )
        except Exception:
            db.session.rollback()
            db.session.execute(db.text('SET TRANSACTION READ ONLY'))
            audit['write_probe_refused'] = True

        if not audit['write_probe_refused']:
            db.session.rollback()
            print(
                '::error::Write probe was NOT refused. The session is not '
                'read-only; refusing to continue.'
            )
            return EXIT_UNSAFE

        stored, row = _stored_evidence(args.game_pk, args.pitcher_mlb_id)
        audit['stored'] = stored
        audit['row_fingerprint_before'] = stored.get('row_fingerprint')

        pitcher = Pitcher.query.filter_by(mlb_id=args.pitcher_mlb_id).first()
        season = getattr(getattr(row, 'game_date', None), 'year', None)

        try:
            audit['boxscore'] = _boxscore_evidence(
                args.game_pk, args.pitcher_mlb_id,
            )
        except Exception as exc:  # noqa: BLE001 - class only, never the message
            audit['boxscore'] = {
                'available': False, 'source': 'completed_game_boxscore',
                'reason': 'fetch_failed', 'error_class': type(exc).__name__,
            }
        try:
            audit['game_log_split'] = _game_log_split_evidence(
                args.game_pk, args.pitcher_mlb_id, season,
            )
        except Exception as exc:  # noqa: BLE001
            audit['game_log_split'] = {
                'available': False, 'source': 'player_game_log_split',
                'reason': 'fetch_failed', 'error_class': type(exc).__name__,
            }

        if row is not None and pitcher is not None:
            from services import sync as sync_service

            for label, evidence, fetch in (
                ('boxscore_plan', audit['boxscore'], _boxscore_raw),
                ('game_log_split_plan', audit['game_log_split'], _split_raw),
            ):
                try:
                    stats = fetch(
                        args.game_pk, args.pitcher_mlb_id, season,
                        sync_service,
                    ) if evidence.get('available') else {}
                    audit[label] = _planner_verdict(
                        row, evidence, stats, pitcher, args.game_pk,
                    )
                except Exception as exc:  # noqa: BLE001
                    audit[label] = {
                        'available': False, 'reason': 'plan_failed',
                        'error_class': type(exc).__name__,
                    }

        after, _ = _stored_evidence(args.game_pk, args.pitcher_mlb_id)
        audit['row_fingerprint_after'] = after.get('row_fingerprint')
        audit['row_unchanged'] = (
            audit['row_fingerprint_before'] == audit['row_fingerprint_after']
        )
        db.session.rollback()

    audit['authority_resolved'] = _authority_resolved(audit)
    _render(audit)

    if args.output:
        from utils.summary_output import SummaryOutputError, write_summary

        try:
            write_summary(audit, args.output)
        except SummaryOutputError as exc:
            print(f'::error::Audit output failed (reason={exc.reason}).')
            return EXIT_AUDIT_INCOMPLETE

    if not audit['row_unchanged']:
        print('::error::The audited row changed during a read-only audit.')
        return EXIT_UNSAFE
    return EXIT_OK if audit['authority_resolved'] else EXIT_AUDIT_INCOMPLETE


def _boxscore_raw(game_pk, pitcher_mlb_id, _season, sync_service):
    boxscore = sync_service.mlb_client.get_game_boxscore(game_pk)
    for line in sync_service._extract_pitching_lines_from_boxscore(boxscore):
        if pitcher_mlb_id in (line.get('player_id'), line.get('person_id')):
            return line.get('stats') or {}
    return {}


def _split_raw(game_pk, pitcher_mlb_id, season, sync_service):
    splits = sync_service.mlb_client.get_pitcher_game_logs(
        pitcher_mlb_id, season=season,
    ) or []
    for split in splits:
        if (split.get('game') or {}).get('gamePk') == game_pk:
            return split.get('stat') or {}
    return {}


def _authority_resolved(audit) -> bool:
    """Both sources observed and the stored value attributable to one of them."""
    box = audit.get('boxscore') or {}
    split = audit.get('game_log_split') or {}
    stored = audit.get('stored') or {}
    return bool(
        box.get('available') and split.get('available') and stored.get('available')
    )


def _render(audit) -> None:
    field = audit['audited_field']
    print(f"\nField-authority audit — {field}")
    print(f"  game_pk={audit['game_pk']} pitcher_mlb_id={audit['pitcher_mlb_id']}")
    print(f"  read-only transaction: {audit['read_only_transaction']}")
    print(f"  write probe refused:   {audit['write_probe_refused']}")
    print(f"  row unchanged:         {audit['row_unchanged']}")
    print(f"  database writes:       {audit['database_writes_performed']}")
    for label in ('boxscore', 'game_log_split'):
        evidence = audit.get(label) or {}
        if evidence.get('available'):
            print(f"  {label}: keys={evidence['stat_keys_present']} "
                  f"values={evidence['values']}")
        else:
            print(f"  {label}: unavailable ({evidence.get('reason')})")
    stored = audit.get('stored') or {}
    if stored.get('available'):
        print(f"  stored: values={stored['values']}")
    for label in ('boxscore_plan', 'game_log_split_plan'):
        plan = audit.get(label) or {}
        if plan.get('available'):
            print(f"  {label}: action={plan['action']} "
                  f"changed={plan['changed_fields']} "
                  f"uncomparable={plan['uncomparable_fields']}")
    print(f"  authority resolved: {audit['authority_resolved']}\n")


if __name__ == '__main__':
    raise SystemExit(main())
