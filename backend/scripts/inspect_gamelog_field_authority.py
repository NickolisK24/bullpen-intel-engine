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
and the minimum companions needed to interpret it are reported, because the
question cannot be answered without them. Nothing else is: no raw payload, no
unrelated player, no connection string, no credential, no path, no exception
text.

What may be reported is declared per audited field, in ``REPORT_PROFILES``. A
field with no profile is refused rather than audited with someone else's
allowlist: reporting the wrong statistic's values under a new field's name
would be worse than reporting nothing.

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


class FieldReportProfile:
    """What one audited field is permitted to report, and under which keys.

    Two allowlists, because the audited statistic alone is rarely
    interpretable: ``value_fields`` are stored columns whose exact values may
    be printed, ``source_keys`` are source-payload keys whose exact values may
    be printed. Both are closed sets — anything not named here is reported as
    presence and shape only, or not at all.

    ``audited_source_keys`` is not declared by hand. The canonical planner
    already owns the alias set for every optional statistic
    (``OPTIONAL_INT_STAT_FIELDS``), and an audit that maintained a second copy
    could report presence for a key the planner does not read.
    """

    def __init__(self, *, field, value_fields, source_keys, interpretation):
        self.field = field
        self.value_fields = tuple(value_fields)
        self.source_keys = tuple(source_keys)
        self.interpretation = interpretation

    @property
    def audited_source_keys(self) -> tuple:
        from services import game_log_reconciliation as reconciliation

        for model_field, keys in reconciliation.OPTIONAL_INT_STAT_FIELDS:
            if model_field == self.field:
                return tuple(keys)
        return (self.field,)


# Fields whose exact values may be reported, per audited field. Enough to
# interpret the audited statistic, and nothing beyond it.
REPORT_PROFILES = {
    'balls': FieldReportProfile(
        field='balls',
        value_fields=('balls', 'strikes', 'pitches_thrown'),
        source_keys=('balls', 'strikes', 'numberOfPitches'),
        interpretation='balls + strikes should account for every pitch thrown',
    ),
    'inherited_runners': FieldReportProfile(
        field='inherited_runners',
        # The scored companion is the only other value needed to read an
        # inherited-runner count: a count is not interpretable without knowing
        # how many of those runners came home, and the two are governed and
        # sourced together.
        value_fields=('inherited_runners', 'inherited_runners_scored'),
        source_keys=(
            'inheritedRunners', 'inherited_runners',
            'inheritedRunnersScored', 'inherited_runners_scored',
        ),
        interpretation=(
            'inherited_runners_scored can never exceed inherited_runners'
        ),
    ),
}

DEFAULT_FIELD = 'balls'

# Retained under their original names: the audit still defaults to `balls`, and
# these are that field's allowlists.
REPORTABLE_VALUE_FIELDS = REPORT_PROFILES[DEFAULT_FIELD].value_fields
REPORTABLE_SOURCE_KEYS = REPORT_PROFILES[DEFAULT_FIELD].source_keys

# Context fields reported as presence and shape only.
CONTEXT_FIELDS = (
    'batters_faced', 'innings_pitched_outs', 'games_started', 'game_date',
)

# Provenance columns are not reported as evidence about the statistic, but they
# are part of the row fingerprint: a write that corrected the audited field
# would stamp them, so covering them makes "the row did not change" a stronger
# claim than covering the statistic alone.
FINGERPRINT_PROVENANCE_FIELDS = (
    'stat_correction_count',
    'last_stat_correction_at',
    'last_stat_correction_source',
)

# ── Absence reasons ─────────────────────────────────────────────────────────
# Absence is never allowed to read as agreement, and the two ways a source can
# fail to supply a field are not the same fact.
ABSENT_KEY_MISSING = 'source_key_absent'
ABSENT_KEY_EMPTY = 'source_key_present_but_empty'

# ── Discrepancy classification vocabulary ───────────────────────────────────
CLASSIFICATION_NO_PROJECTED_DIFFERENCE = 'no_projected_difference'
CLASSIFICATION_SOURCE_SHAPE_GAP = 'source_shape_authority_gap'
CLASSIFICATION_STALE_STORED_VALUE = 'stale_canonical_value'
CLASSIFICATION_SOURCE_CONFLICT = 'source_conflict'
CLASSIFICATION_PLANNER_DEFECT = 'planner_or_normalization_defect'
CLASSIFICATION_SOURCE_REVISION = 'legitimate_source_revision'
CLASSIFICATION_UNRESOLVED = 'unresolved'

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
        '--field', default=DEFAULT_FIELD,
        choices=sorted(REPORT_PROFILES),
        help='Governed field to audit. Restricted to fields with a declared '
             'report profile; defaults to the field this tool was written for.',
    )
    parser.add_argument('--output', help='Optional durable artifact path.')
    return parser.parse_args(argv)


# ── Evidence collection ─────────────────────────────────────────────────────


def _audited_field_evidence(profile, stats):
    """What this source shape says about the audited field, absence included.

    Presence is decided by the canonical ``stat_key_present`` — the same
    predicate ``correctable_fields`` uses — so what this reports as present is
    exactly what the planner would have compared. A key carrying ``None`` or
    ``''`` is absent by that rule, and saying so is the whole point: a source
    that did not supply the field has not agreed with the stored value.
    """
    from services import game_log_reconciliation as reconciliation

    stats = stats or {}
    keys = profile.audited_source_keys
    keys_present = [key for key in keys if key in stats]
    present = reconciliation.stat_key_present(stats, keys)

    value = None
    if present:
        for key in keys:
            if key in stats and stats.get(key) not in (None, ''):
                value = _safe_int(stats.get(key))
                break

    return {
        'field': profile.field,
        'present': present,
        # Exact value, or an explicit absence reason. Never a default: a
        # missing inherited-runner count is not zero inherited runners.
        'value': value,
        'absent_reason': (
            None if present
            else (ABSENT_KEY_EMPTY if keys_present else ABSENT_KEY_MISSING)
        ),
        'source_keys_checked': list(keys),
        'source_keys_present': sorted(keys_present),
    }


def _source_evidence(profile, stats, source):
    """The reportable shape of one source line."""
    return {
        'available': True,
        'source': source,
        'stat_keys_present': sorted(
            key for key in profile.source_keys if key in stats
        ),
        'values': {
            key: _safe_int(stats.get(key)) for key in profile.source_keys
        },
        'audited_field': _audited_field_evidence(profile, stats),
        'stats_key_count': len(stats),
        'payload_fingerprint': _fingerprint(sorted(stats.items())),
    }


def _boxscore_evidence(game_pk, pitcher_mlb_id, profile):
    """The completed-game box score line for this pitcher."""
    from services import sync as sync_service

    boxscore = sync_service.mlb_client.get_game_boxscore(game_pk)
    lines = sync_service._extract_pitching_lines_from_boxscore(boxscore)
    for line in lines:
        if line.get('player_id') == pitcher_mlb_id or (
            line.get('person_id') == pitcher_mlb_id
        ):
            return _source_evidence(
                profile, line.get('stats') or {}, 'completed_game_boxscore',
            )
    return {
        'available': False,
        'source': 'completed_game_boxscore',
        'reason': 'no_pitching_line_for_pitcher',
    }


def _game_log_split_evidence(game_pk, pitcher_mlb_id, season, profile):
    """The player game-log split for the same appearance."""
    from services import sync as sync_service

    splits = sync_service.mlb_client.get_pitcher_game_logs(
        pitcher_mlb_id, season=season,
    ) or []
    for split in splits:
        game = split.get('game') or {}
        if game.get('gamePk') != game_pk:
            continue
        return _source_evidence(
            profile, split.get('stat') or {}, 'player_game_log_split',
        )
    return {
        'available': False,
        'source': 'player_game_log_split',
        'reason': 'no_split_for_game',
    }


def _stored_evidence(game_pk, pitcher_mlb_id, profile):
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
            for field in profile.value_fields
        },
        # Stated separately from the value: a stored NULL and a stored 0 are
        # different facts, and `values` alone cannot distinguish "absent" from
        # "none inherited".
        'audited_field_stored': getattr(row, profile.field, None) is not None,
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
            for field in sorted(
                profile.value_fields + CONTEXT_FIELDS
                + FINGERPRINT_PROVENANCE_FIELDS
            )
        ]),
    }
    return evidence, row


def _planner_verdict(row, source_evidence, source_stats, pitcher, game_pk, profile):
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
    changed = list(plan.get('changed_fields') or ())
    uncomparable = list(plan.get('uncomparable_fields') or ())
    return {
        'available': True,
        'derived_values': {
            field: _safe_int(values.get(field))
            for field in profile.value_fields
        },
        'action': plan.get('action'),
        'changed_fields': changed,
        'uncomparable_fields': uncomparable,
        'difference_classifications': list(
            plan.get('difference_classifications') or ()
        ),
        'blocked_reason': plan.get('blocked_reason'),
        'target_state_digest': plan.get('target_state_digest'),
        'stored_state_digest': plan.get('stored_state_digest'),
        # The two facts the conclusion turns on, pulled from the planner's own
        # answer rather than re-derived: did THIS source shape project the
        # audited field, and could it compare it at all?
        'audited_field_changed': profile.field in changed,
        'audited_field_uncomparable': profile.field in uncomparable,
    }


# ── Entry point ─────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    profile = REPORT_PROFILES.get(args.field)
    if profile is None:
        # Unreachable through the CLI, which restricts --field to the declared
        # profiles. Kept because the entry point is importable, and auditing a
        # field with another field's allowlist would report the wrong numbers.
        print(
            f'::error::No report profile declared for field {args.field!r}; '
            'refusing to audit a field whose reportable values are undeclared.'
        )
        return EXIT_AUDIT_INCOMPLETE

    audit = {
        'audited_field': args.field,
        # The coherence rule a reader needs to judge the reported values. It is
        # documentation, never a comparator: nothing in this tool decides
        # anything from it.
        'interpretation_rule': profile.interpretation,
        'game_pk': args.game_pk,
        'pitcher_mlb_id': args.pitcher_mlb_id,
        'read_only_transaction': False,
        'write_probe_refused': False,
        'database_writes_performed': 0,
        'row_fingerprint_before': None,
        'row_fingerprint_after': None,
        'row_unchanged': None,
    }

    try:
        from app import app
        from models.pitcher import Pitcher
        from utils.db import db
    except Exception as exc:  # noqa: BLE001 - class only, never the message
        # An unconfigured environment is a real audit outcome, not a crash. A
        # traceback proves nothing and prints paths; a fail-closed artifact says
        # exactly which evidence was unobtainable. Only the exception CLASS is
        # reported — the message can name a connection setting.
        audit['environment_configured'] = False
        audit['environment_error_class'] = type(exc).__name__
        return _conclude(
            audit, profile, args.output, exit_code=EXIT_AUDIT_INCOMPLETE,
        )

    audit['environment_configured'] = True

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

        stored, row = _stored_evidence(args.game_pk, args.pitcher_mlb_id, profile)
        audit['stored'] = stored
        audit['row_fingerprint_before'] = stored.get('row_fingerprint')

        pitcher = Pitcher.query.filter_by(mlb_id=args.pitcher_mlb_id).first()
        season = getattr(getattr(row, 'game_date', None), 'year', None)

        try:
            audit['boxscore'] = _boxscore_evidence(
                args.game_pk, args.pitcher_mlb_id, profile,
            )
        except Exception as exc:  # noqa: BLE001 - class only, never the message
            audit['boxscore'] = {
                'available': False, 'source': 'completed_game_boxscore',
                'reason': 'fetch_failed', 'error_class': type(exc).__name__,
            }
        try:
            audit['game_log_split'] = _game_log_split_evidence(
                args.game_pk, args.pitcher_mlb_id, season, profile,
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
                        row, evidence, stats, pitcher, args.game_pk, profile,
                    )
                except Exception as exc:  # noqa: BLE001
                    audit[label] = {
                        'available': False, 'reason': 'plan_failed',
                        'error_class': type(exc).__name__,
                    }

        after, _ = _stored_evidence(args.game_pk, args.pitcher_mlb_id, profile)
        audit['row_fingerprint_after'] = after.get('row_fingerprint')
        audit['row_unchanged'] = (
            audit['row_fingerprint_before'] == audit['row_fingerprint_after']
        )
        db.session.rollback()

    return _conclude(audit, profile, args.output)


def _conclude(audit, profile, output, *, exit_code=None) -> int:
    """Classify, report, persist, and choose the exit code.

    Shared by every path out of the audit, so an audit that could not run
    produces the same shaped artifact as one that did — with its conclusion set
    to ``unresolved`` rather than absent. ``exit_code`` is forced only when the
    audit never opened a transaction, where "did the row change?" is not a
    question the run is entitled to answer either way.
    """
    classification, explanation = _classify(audit, profile)
    audit['discrepancy_classification'] = classification
    audit['discrepancy_explanation'] = explanation
    audit['authority_resolved'] = _authority_resolved(audit)
    _render(audit)

    if output:
        from utils.summary_output import SummaryOutputError, write_summary

        try:
            write_summary(audit, output)
        except SummaryOutputError as exc:
            print(f'::error::Audit output failed (reason={exc.reason}).')
            return EXIT_AUDIT_INCOMPLETE

    if exit_code is not None:
        return exit_code
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


def _evidence_complete(audit) -> bool:
    """Both sources observed, the row read, and both planner verdicts taken."""
    return all(
        (audit.get(label) or {}).get('available')
        for label in (
            'stored', 'boxscore', 'game_log_split',
            'boxscore_plan', 'game_log_split_plan',
        )
    )


def _classify(audit, profile):
    """Name the discrepancy from the evidence, or refuse to name it.

    Every branch is decided by facts the audit actually holds: what each source
    supplied, what the stored row holds, and what the CANONICAL planner did
    with each source shape. Where the evidence cannot distinguish two
    explanations, this returns ``unresolved`` rather than picking the likelier
    one — a diagnostic that guesses is worse than one that stops.
    """
    if audit.get('environment_configured') is False:
        return CLASSIFICATION_UNRESOLVED, (
            'The audit could not run: this environment is not configured for '
            'the canonical database, so no stored row, no source line, and no '
            'planner verdict was obtained.'
        )

    if not _evidence_complete(audit):
        missing = sorted(
            label for label in (
                'stored', 'boxscore', 'game_log_split',
                'boxscore_plan', 'game_log_split_plan',
            )
            if not (audit.get(label) or {}).get('available')
        )
        return CLASSIFICATION_UNRESOLVED, (
            f'Evidence incomplete — unobtainable: {", ".join(missing)}. The '
            f'audit fails closed rather than reasoning from a partial record.'
        )

    field = profile.field
    stored_value = (audit['stored']['values'] or {}).get(field)
    box = audit['boxscore']['audited_field']
    split = audit['game_log_split']['audited_field']
    box_plan = audit['boxscore_plan']
    split_plan = audit['game_log_split_plan']

    box_projects = box_plan['audited_field_changed']
    split_projects = split_plan['audited_field_changed']

    if box_plan['blocked_reason'] and split_plan['blocked_reason']:
        return CLASSIFICATION_UNRESOLVED, (
            'Both source lines were blocked by the canonical correction-safety '
            'rule, so neither lane evaluated the field.'
        )

    if not box_projects and not split_projects:
        return CLASSIFICATION_NO_PROJECTED_DIFFERENCE, (
            f'Neither source shape causes the canonical planner to project '
            f'{field}; the shadow difference is not attributable to this field '
            f'as currently sourced.'
        )

    if box['present'] and split['present']:
        if box['value'] != split['value']:
            return CLASSIFICATION_SOURCE_CONFLICT, (
                f'Both sources supply {field} and they disagree '
                f'(box score {box["value"]}, split {split["value"]}); stored '
                f'holds {stored_value}. Choosing between them requires an '
                f'explicit authority decision, not a diagnostic.'
            )
        if box['value'] == stored_value:
            return CLASSIFICATION_PLANNER_DEFECT, (
                f'Both sources supply {field}={box["value"]} and the stored row '
                f'already holds it, yet the canonical planner still projects a '
                f'change — the difference is in normalization, not in the data.'
            )
        if (audit['stored'].get('stat_correction_count') or 0) > 0:
            return CLASSIFICATION_SOURCE_REVISION, (
                f'Both sources now agree on {field}={box["value"]} while the '
                f'stored row holds {stored_value}, and the row already carries '
                f'a recorded statistical correction — the stored value was '
                f'reconciled against official evidence that has since moved.'
            )
        return CLASSIFICATION_STALE_STORED_VALUE, (
            f'Both sources agree on {field}={box["value"]} and the stored row '
            f'holds {stored_value}, with no recorded correction on the row: a '
            f'stale canonical value that no lane has yet corrected.'
        )

    if box['present'] != split['present']:
        supplier, supplied, omitter, omission = (
            ('completed_game_boxscore', box, 'player_game_log_split', split)
            if box['present']
            else ('player_game_log_split', split, 'completed_game_boxscore', box)
        )
        if supplied['value'] == stored_value:
            return CLASSIFICATION_PLANNER_DEFECT, (
                f'Only {supplier} supplies {field}, at {supplied["value"]}, '
                f'which the stored row already holds — yet the planner projects '
                f'a change from that source shape.'
            )
        return CLASSIFICATION_SOURCE_SHAPE_GAP, (
            f'{supplier} supplies {field}={supplied["value"]} against a stored '
            f'{stored_value}, while {omitter} does not supply it at all '
            f'({omission["absent_reason"]}) and therefore never compares it. '
            f'The lanes differ because of source shape, not because the sources '
            f'disagree — the omitting lane has not agreed with the stored value, '
            f'it has never looked at it.'
        )

    return CLASSIFICATION_UNRESOLVED, (
        f'The canonical planner projects {field} but neither source line '
        f'supplies it, which the evidence cannot explain.'
    )


def _authority_resolved(audit) -> bool:
    """Both sources observed and the discrepancy attributable to a named cause."""
    return bool(
        _evidence_complete(audit)
        and audit.get('discrepancy_classification') != CLASSIFICATION_UNRESOLVED
    )


def _render(audit) -> None:
    field = audit['audited_field']
    print(f"\nField-authority audit — {field}")
    print(f"  game_pk={audit['game_pk']} pitcher_mlb_id={audit['pitcher_mlb_id']}")
    if audit.get('environment_configured') is False:
        print('  environment: NOT CONFIGURED for the canonical database '
              f"({audit.get('environment_error_class')})")
    print(f"  read-only transaction: {audit['read_only_transaction']}")
    print(f"  write probe refused:   {audit['write_probe_refused']}")
    print(f"  row unchanged:         {audit['row_unchanged']}")
    print(f"  database writes:       {audit['database_writes_performed']}")
    for label in ('boxscore', 'game_log_split'):
        evidence = audit.get(label) or {}
        if evidence.get('available'):
            audited = evidence['audited_field']
            supplies = (
                f"{field}={audited['value']}" if audited['present']
                else f"{field} ABSENT ({audited['absent_reason']})"
            )
            print(f"  {label}: {supplies} keys={evidence['stat_keys_present']} "
                  f"values={evidence['values']}")
        else:
            print(f"  {label}: unavailable ({evidence.get('reason')})")
    stored = audit.get('stored') or {}
    if stored.get('available'):
        print(f"  stored: values={stored['values']} "
              f"stat_corrections={stored['stat_correction_count']}")
    for label in ('boxscore_plan', 'game_log_split_plan'):
        plan = audit.get(label) or {}
        if plan.get('available'):
            print(f"  {label}: action={plan['action']} "
                  f"changed={plan['changed_fields']} "
                  f"uncomparable={plan['uncomparable_fields']}")
    print(f"  classification: {audit.get('discrepancy_classification')}")
    print(f"  {audit.get('discrepancy_explanation')}")
    print(f"  authority resolved: {audit['authority_resolved']}\n")


if __name__ == '__main__':
    raise SystemExit(main())
