#!/usr/bin/env python
"""Forensic inspection of Pitcher state behind the first controlled write.

The first Foundation 3C controlled write covered five games. It created 14
false GameLog correction-provenance events, and — because completed-game
evidence was still acting as current-roster authority — it may also have
changed `Pitcher` rows for the arms in those games.

This tool reports what the database can still prove TODAY. It changes nothing:
the transaction is set read-only and a write probe must be refused before a
single row is read. Its purpose is to establish honestly what is and is not
reconstructible, so a cleanup decision can be made on evidence rather than on
inference.

    read-only manifest -> founder review -> separate apply -> read-only closeout

It performs no cleanup and proposes no values. Where a prior value is not
retained anywhere durable, the report says so rather than guessing.

Output is safe structured evidence only — MLB ids, governed field values,
provenance source names, and timestamps. No credentials, connection strings,
headers, raw payloads, filesystem paths, or exception text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


EXIT_OK = 0
EXIT_ERROR = 2

# The five games of the first controlled write.
FIRST_WRITE_GAME_PKS = (823518, 824735, 823761, 824083, 824327)

# The retired path stamped this source onto any Pitcher row it touched. Its
# presence is the only durable marker that a completed game wrote current state.
RETIRED_POSTGAME_SOURCE = (
    'mlb_stats_api:postgame_boxscore_pitching_line'
)

# What the evidence can support. Chosen from these three, never invented.
CONCLUSION_RECONSTRUCTIBLE = 'exact_mutations_reconstructible'
CONCLUSION_PARTIAL = 'categories_known_prior_values_not_retained'
CONCLUSION_INSEPARABLE = 'not_separable_from_later_roster_synchronization'


class ReadOnlyNotEnforced(RuntimeError):
    """The session could not be proven read-only, so nothing is inspected."""


def _enforce_read_only(session) -> dict:
    """Set the transaction read-only and PROVE a write is refused.

    Fails closed. ``session.bind`` is None until the session has been used, so
    the engine is resolved explicitly — reading it lazily is how a guard like
    this silently degrades to no protection at all.
    """
    from sqlalchemy import text

    bind = session.get_bind()
    dialect = bind.dialect.name
    if dialect != 'postgresql':
        raise ReadOnlyNotEnforced(dialect)

    session.execute(text('SET TRANSACTION READ ONLY'))
    protection = 'postgresql_read_only_transaction'
    try:
        session.execute(text(
            'UPDATE pitchers SET active = active WHERE 1 = 0'
        ))
        refused = False
    except Exception:  # noqa: BLE001 - the refusal itself is the signal
        session.rollback()
        session.execute(text('SET TRANSACTION READ ONLY'))
        refused = True

    if not refused:
        raise ReadOnlyNotEnforced(protection)
    return {
        'dialect': dialect,
        'protection': protection,
        'write_probe_refused': refused,
    }


def _iso(value):
    return value.isoformat() if value is not None else None


def _pitcher_evidence(pitcher) -> dict:
    """Current, safe Pitcher state. No prior values are inferred."""
    return {
        'pitcher_mlb_id': pitcher.mlb_id,
        'active': pitcher.active,
        'full_name_present': bool(pitcher.full_name),
        'position': pitcher.position,
        'team_id': pitcher.team_id,
        'team_abbreviation': pitcher.team_abbreviation,
        'team_assignment_status': pitcher.team_assignment_status,
        'team_assignment_source': pitcher.team_assignment_source,
        'team_assignment_updated_at': _iso(pitcher.team_assignment_updated_at),
        'roster_status': pitcher.roster_status,
        'roster_status_source': pitcher.roster_status_source,
        'roster_status_updated_at': _iso(pitcher.roster_status_updated_at),
        'updated_at': _iso(pitcher.updated_at),
    }


def _attribution(pitcher) -> dict:
    """Whether the retired completed-game path is still attributable here.

    The only durable marker is the provenance source it stamped. A later roster
    sync overwrites that source, which is exactly why attribution decays.
    """
    assignment_attributable = (
        pitcher.team_assignment_source == RETIRED_POSTGAME_SOURCE
    )
    roster_attributable = (
        pitcher.roster_status_source == RETIRED_POSTGAME_SOURCE
    )
    return {
        'team_assignment_attributable_to_completed_game': assignment_attributable,
        'roster_status_attributable_to_completed_game': roster_attributable,
        'any_marker_present': assignment_attributable or roster_attributable,
        # The schema keeps no before-image of a Pitcher field, so a prior value
        # cannot be read back from anywhere. Stated as a fact, not a guess.
        'prior_values_retained': False,
    }


def _identity_plan_today(pitcher, appearance_team_id):
    """What the repaired rules would plan for this row now."""
    from services import pitcher_identity_reconciliation as identity

    plan = identity.plan_identity(
        existing=pitcher,
        player_mlb_id=pitcher.mlb_id,
        line_name=pitcher.full_name,
        appearance_team={'team_id': appearance_team_id},
    )
    return {
        'action': plan['action'],
        'changed_fields': plan['changed_fields'],
        'suppressed_current_state_fields': plan[
            'suppressed_current_state_fields'
        ],
        'would_mutate': identity.is_mutation(plan),
    }


def collect_evidence(game_pks) -> dict:
    """Read the evidence. Separated from the read-only guard so the reporting
    logic is directly testable without a live PostgreSQL transaction — the guard
    itself is asserted on its own, and ``inspect`` still refuses to call this
    until protection is proven."""
    from models.game_log import GameLog
    from models.pitcher import Pitcher

    games = []
    appearances = 0
    attributable = 0
    would_mutate_today = 0
    pitchers_seen = set()

    for game_pk in sorted(game_pks):
        rows = (
            GameLog.query
            .filter(GameLog.mlb_game_pk == game_pk)
            .order_by(GameLog.pitcher_id)
            .all()
        )
        pitcher_ids = [row.pitcher_id for row in rows]
        pitchers = {
            pitcher.id: pitcher
            for pitcher in Pitcher.query.filter(
                Pitcher.id.in_(pitcher_ids or [-1])
            ).all()
        }

        entries = []
        for row in rows:
            pitcher = pitchers.get(row.pitcher_id)
            if pitcher is None:
                entries.append({
                    'game_log_id': row.id,
                    'pitcher_mlb_id': None,
                    'evidence': None,
                    'attribution': None,
                    'identity_plan_today': None,
                    'note': 'appearance_has_no_local_pitcher_row',
                })
                continue
            appearances += 1
            pitchers_seen.add(pitcher.mlb_id)
            attribution = _attribution(pitcher)
            plan_today = _identity_plan_today(pitcher, row.appearance_team_id)
            if attribution['any_marker_present']:
                attributable += 1
            if plan_today['would_mutate']:
                would_mutate_today += 1
            entries.append({
                'game_log_id': row.id,
                'pitcher_mlb_id': pitcher.mlb_id,
                'appearance_team_id': row.appearance_team_id,
                'appearance_team_source': row.appearance_team_source,
                'evidence': _pitcher_evidence(pitcher),
                'attribution': attribution,
                'identity_plan_today': plan_today,
            })

        games.append({
            'game_pk': game_pk,
            'appearance_rows': len(rows),
            'entries': entries,
        })

    # One honest conclusion, chosen from the three the evidence can support.
    if attributable == 0:
        conclusion = CONCLUSION_INSEPARABLE
        conclusion_detail = (
            'No Pitcher row in these five games still carries the retired '
            'completed-game provenance source. Either the path never wrote '
            'them or a later roster synchronization has since overwritten the '
            'only marker. The two cases are indistinguishable from stored '
            'state, so no prior Pitcher value can be attributed to the first '
            'controlled write.'
        )
    else:
        conclusion = CONCLUSION_PARTIAL
        conclusion_detail = (
            f'{attributable} Pitcher rows still carry the retired '
            'completed-game provenance source, so the CATEGORY of mutation and '
            'its timing are attributable. The schema retains no before-image '
            'of any Pitcher field, so the prior values themselves are not '
            'recoverable and are not reconstructed here.'
        )

    return {
        'stage': 'first_write_pitcher_identity_forensics',
        'game_pks': sorted(game_pks),
        'appearance_rows_examined': appearances,
        'unique_pitchers_examined': len(pitchers_seen),
        'rows_attributable_to_completed_game_write': attributable,
        'rows_that_would_mutate_under_repaired_rules': would_mutate_today,
        'prior_values_reconstructible': False,
        'conclusion': conclusion,
        'conclusion_detail': conclusion_detail,
        'cleanup_performed': False,
        'cleanup_proposed': False,
        'games': games,
    }


def inspect(game_pks) -> dict:
    """Prove the session is read-only, THEN read. Fails closed."""
    from utils.db import db

    read_only = _enforce_read_only(db.session)
    report = collect_evidence(game_pks)
    report['read_only'] = read_only
    report['read_only_after'] = _enforce_read_only(db.session)
    return report


def build_app():
    import app as app_module

    return app_module.create_app()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Read-only forensic inspection of Pitcher state behind the first '
            'Foundation 3C controlled write.'
        ),
    )
    parser.add_argument(
        '--game-pk', type=int, action='append', default=None,
        help='Repeatable. Defaults to the five first-write games.',
    )
    parser.add_argument('--output', help='Write the JSON report to this path.')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    game_pks = args.game_pk or list(FIRST_WRITE_GAME_PKS)
    try:
        flask_app = build_app()
        with flask_app.app_context():
            report = inspect(game_pks)
        exit_code = EXIT_OK
    except ReadOnlyNotEnforced as failure:
        report = {
            'stage': 'first_write_pitcher_identity_forensics',
            'result': 'ERROR',
            'error': 'read_only_not_enforced',
            'observed_protection': str(failure),
            'cleanup_performed': False,
            'sanitized': True,
        }
        exit_code = EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - never leak exception text
        report = {
            'stage': 'first_write_pitcher_identity_forensics',
            'result': 'ERROR',
            'exception_type': type(exc).__name__,
            'cleanup_performed': False,
            'sanitized': True,
        }
        exit_code = EXIT_ERROR

    encoded = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded + '\n', encoding='utf-8')
    else:
        print(encoded)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
