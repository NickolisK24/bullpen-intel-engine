#!/usr/bin/env python
"""Read-only source-revision audit for MLB game 824487.

    python scripts/run_game_source_revision_audit.py \
        --expected-main-sha <40 hex> \
        --confirmation AUDIT_GAME_824487_SOURCE_REVISION_30999087370 \
        --evidence-dir source-revision-evidence \
        --artifact-dir ../artifacts/game-824487-source-revision-audit

Manual only, exact scope, read-only. Answers twelve explicit questions about
one game and two retained scheduled daily runs from four independent evidence
sources: the runs' own retained artifacts, the repository's code at both
historical SHAs, current production state, and one current official MLB
response.

It CALLS the canonical authorities — the game-ingestion planner, the single MLB
client, the single box-score parser, the canonical appearance extractor, the
canonical reconciliation planner — and reimplements none of them. It repairs
nothing, writes nothing, and authorizes nothing.

Exit codes: 0 COMPLETE (root cause identified / scope and materiality
identified with the field delta unavailable / no current defect),
1 FAILED, 2 UNPROVEN.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = BACKEND_ROOT.parent

from services import game_source_revision_audit as audit  # noqa: E402


SUMMARY_JSON = 'source-revision-audit.json'
SUMMARY_MARKDOWN = 'source-revision-audit-summary.md'
FIELD_MATRIX_JSON = 'source-revision-field-matrix.json'
CODE_DRIFT_JSON = 'source-revision-code-drift.json'
READ_ONLY_PROOF_JSON = 'source-revision-read-only-proof.json'
ARTIFACT_METADATA_FILENAME = 'artifact-metadata.json'

REVISION_PRIOR = 'prior_run_sha'
REVISION_LATER = 'failed_run_sha'
REVISION_AUDIT = 'audit_dispatch_sha'
REVISION_LABELS = (REVISION_PRIOR, REVISION_LATER, REVISION_AUDIT)

MAX_NOTE_LENGTH = 200


class _AuditHalt(Exception):
    """Stop collecting; the verdict is decided from what was proven."""


# ── Authorization ───────────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Read-only source-revision audit for game 824487.',
    )
    parser.add_argument('--expected-main-sha', required=True)
    parser.add_argument('--confirmation', required=True)
    parser.add_argument('--operator-note', default='')
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--artifact-dir', required=True)
    return parser.parse_args(argv)


def sanitize_note(raw) -> str:
    """Bounded, printable, never interpreted, never decision-relevant."""
    text = str(raw or '')
    safe = ''.join(
        char for char in text if char.isprintable() and char not in '`$\\'
    )
    return safe[:MAX_NOTE_LENGTH]


def event_context(args, environ=None) -> dict:
    environ = os.environ if environ is None else environ
    return {
        'event_name': environ.get('GITHUB_EVENT_NAME'),
        'repository': environ.get('GITHUB_REPOSITORY'),
        'actor': environ.get('GITHUB_ACTOR'),
        'ref': environ.get('GITHUB_REF'),
        'commit_sha': environ.get('GITHUB_SHA'),
        'workflow_run_id': environ.get('GITHUB_RUN_ID'),
        'workflow_run_attempt': environ.get('GITHUB_RUN_ATTEMPT'),
        'workflow': environ.get('GITHUB_WORKFLOW'),
        'expected_main_sha': str(args.expected_main_sha or '').strip().lower(),
        'confirmation_supplied': bool(args.confirmation),
    }


def validate_authorization(context, args) -> list[str]:
    """Every precondition, checked positively. Absence is never approval."""
    failures: list[str] = []
    if context.get('event_name') != audit.REQUIRED_EVENT_NAME:
        failures.append(audit.FAILED_EVENT_NOT_WORKFLOW_DISPATCH)
    if context.get('repository') != audit.REQUIRED_REPOSITORY:
        failures.append(audit.FAILED_REPOSITORY_NOT_AUTHORIZED)
    if context.get('actor') != audit.REQUIRED_ACTOR:
        failures.append(audit.FAILED_ACTOR_NOT_AUTHORIZED)
    if context.get('ref') != audit.REQUIRED_REF:
        failures.append(audit.FAILED_REF_NOT_MAIN)

    expected = audit.normalize_sha(context.get('expected_main_sha'))
    if expected is None:
        failures.append(audit.FAILED_EXPECTED_SHA_MALFORMED)
    else:
        resolved = audit.normalize_sha(context.get('commit_sha'))
        if resolved is None or resolved != expected:
            failures.append(audit.FAILED_EXPECTED_SHA_MISMATCH)

    if str(args.confirmation or '') != audit.CONFIRMATION:
        failures.append(audit.FAILED_CONFIRMATION_MISMATCH)
    return failures


def build_app():
    from app import create_app

    return create_app()


# ── Evidence: retained run artifacts ────────────────────────────────────────

def load_observed_artifact_metadata(evidence_dir) -> dict:
    path = Path(evidence_dir) / ARTIFACT_METADATA_FILENAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


# ── Evidence: code at historical SHAs ───────────────────────────────────────

def read_source_at_revision(revision, path) -> str | None:
    """``git show <revision>:<path>``.

    ``None`` means the revision itself is unavailable (a shallow clone, a
    pruned commit); the empty string means the revision exists but does not
    carry that file. The two are different facts and stay different.
    """
    try:
        completed = subprocess.run(
            ['git', 'show', f'{revision}:{path}'],
            cwd=str(REPO_ROOT), capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        stderr = (completed.stderr or b'').decode('utf-8', 'replace')
        if 'exists on disk' in stderr or 'does not exist' in stderr:
            return ''
        return None
    return completed.stdout.decode('utf-8', 'replace')


def revision_available(revision) -> bool:
    try:
        completed = subprocess.run(
            ['git', 'cat-file', '-e', f'{revision}^{{commit}}'],
            cwd=str(REPO_ROOT), capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def observe_code_drift(audit_sha, *, reader=read_source_at_revision,
                       availability=revision_available) -> dict:
    """Symbol-level comparison across both historical SHAs and the audit SHA."""
    revisions = {
        REVISION_PRIOR: audit.HISTORICAL_SHAS[audit.RUN_PRIOR],
        REVISION_LATER: audit.HISTORICAL_SHAS[audit.RUN_LATER],
        REVISION_AUDIT: audit_sha,
    }
    reachable = {
        label: bool(sha) and availability(sha)
        for label, sha in revisions.items()
    }

    cache: dict = {}
    comparisons = []
    for target in audit.CODE_DRIFT_TARGETS:
        sources = {}
        for label, sha in revisions.items():
            if not reachable[label]:
                sources[label] = None
                continue
            key = (sha, target['path'])
            if key not in cache:
                cache[key] = reader(sha, target['path'])
            sources[label] = cache[key]
        comparisons.append(
            audit.compare_symbol_across_revisions(target, sources)
        )

    summary = audit.summarize_code_drift(comparisons)
    summary['revisions'] = revisions
    summary['revisions_reachable'] = reachable
    summary['unreachable_revisions'] = sorted(
        label for label, ok in reachable.items() if not ok
    )
    summary['all_revisions_reachable'] = all(reachable.values())
    return summary


def realization_symbol_state(code_drift) -> str:
    for entry in (code_drift or {}).get('comparisons') or ():
        if entry['target_id'] == 'realization.build_daily_realization':
            return entry['state']
    return audit.DRIFT_UNAVAILABLE


# ── Evidence: current stored canonical state ────────────────────────────────

def observe_stored_state() -> dict:
    """Everything the audit reads as authoritative stored evidence.

    Read-only by construction: every statement here is a SELECT, executed
    inside the read-only transaction the caller has already proven.
    """
    from models.game_ingestion_work_item import GameIngestionWorkItem
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from models.scheduled_game import ScheduledGame

    schedule_rows = ScheduledGame.query.filter(
        ScheduledGame.game_pk == audit.GAME_PK
    ).order_by(ScheduledGame.team_id.asc()).all()
    game_logs = GameLog.query.filter(
        GameLog.mlb_game_pk == audit.GAME_PK
    ).order_by(GameLog.pitcher_id.asc()).all()
    pitcher_ids = sorted({row.pitcher_id for row in game_logs})
    pitchers = (
        Pitcher.query.filter(Pitcher.id.in_(pitcher_ids)).all()
        if pitcher_ids else []
    )
    pitcher_by_id = {row.id: row for row in pitchers}
    work_item = GameIngestionWorkItem.query.filter_by(
        mlb_game_pk=audit.GAME_PK
    ).first()

    opponent_by_team = {
        row.team_id: row.opponent_team_id for row in schedule_rows
    }

    stored_appearances = []
    duplicates: dict = {}
    for row in game_logs:
        pitcher = pitcher_by_id.get(row.pitcher_id)
        mlb_id = getattr(pitcher, 'mlb_id', None)
        duplicates[mlb_id] = duplicates.get(mlb_id, 0) + 1
        stored_appearances.append({
            'pitcher_mlb_id': mlb_id,
            'local_pitcher_id': row.pitcher_id,
            'team_id': row.appearance_team_id,
            'opponent_team_id': opponent_by_team.get(row.appearance_team_id),
            'appearance_role': (
                'start' if row.games_started == 1 else 'relief'
            ),
            'games_started': row.games_started,
            'outs_recorded': row.innings_pitched_outs,
            'innings_pitched': row.innings_pitched,
            'earned_runs': row.earned_runs,
            'runs_allowed': row.runs_allowed,
            'hits_allowed': row.hits_allowed,
            'walks': row.walks,
            'strikeouts': row.strikeouts,
            'home_runs_allowed': row.home_runs_allowed,
            'batters_faced': row.batters_faced,
            'pitches_thrown': row.pitches_thrown,
            'appearance_team_id': row.appearance_team_id,
            'appearance_team_source': row.appearance_team_source,
            'appearance_team_status': row.appearance_team_status,
            'appearance_team_reason': row.appearance_team_reason,
            'game_date': row.game_date.isoformat() if row.game_date else None,
            'game_type': row.game_type,
            'opponent': row.opponent,
            'opponent_abbreviation': row.opponent_abbreviation,
            'stat_correction_count': row.stat_correction_count,
            'last_stat_correction_at': (
                row.last_stat_correction_at.isoformat()
                if row.last_stat_correction_at else None
            ),
            'last_stat_correction_source': row.last_stat_correction_source,
            'last_stat_correction_sync_run_id': (
                row.last_stat_correction_sync_run_id
            ),
        })

    correction_provenance = [
        {
            'pitcher_mlb_id': entry['pitcher_mlb_id'],
            'stat_correction_count': entry['stat_correction_count'],
            'last_stat_correction_at': entry['last_stat_correction_at'],
            'last_stat_correction_source': entry[
                'last_stat_correction_source'
            ],
            'last_stat_correction_sync_run_id': entry[
                'last_stat_correction_sync_run_id'
            ],
        }
        for entry in stored_appearances
        if (entry['stat_correction_count'] or 0) > 0
    ]

    return {
        'schedule_rows': [
            {
                'team_id': row.team_id,
                'opponent_team_id': row.opponent_team_id,
                'home_away': row.home_away,
                'game_date': (
                    row.game_date.isoformat() if row.game_date else None
                ),
                'game_type': row.game_type,
                'status_code': row.status_code,
                'status_state': row.status_state,
            }
            for row in schedule_rows
        ],
        'schedule_row_count': len(schedule_rows),
        'stored_appearances': stored_appearances,
        'stored_appearance_count': len(stored_appearances),
        'stored_pitcher_mlb_ids': sorted(
            entry['pitcher_mlb_id'] for entry in stored_appearances
            if entry['pitcher_mlb_id'] is not None
        ),
        'stored_pitcher_identity_unresolved': sum(
            1 for entry in stored_appearances
            if entry['pitcher_mlb_id'] is None
        ),
        'duplicate_stored_pitchers': sorted(
            mlb_id for mlb_id, count in duplicates.items()
            if mlb_id is not None and count > 1
        ),
        'correction_provenance': correction_provenance,
        'correction_provenance_present': bool(correction_provenance),
        'work_item': work_item.to_dict() if work_item is not None else None,
        'work_item_exists': work_item is not None,
    }


def classify_current_revision(*, available, revision) -> str:
    """Question 4. An unavailable source is never "matches neither"."""
    if not available or not revision:
        return audit.CURRENT_SOURCE_UNAVAILABLE
    if revision == audit.LATER_SOURCE_REVISION:
        return audit.CURRENT_MATCHES_LATER
    if revision == audit.PRIOR_SOURCE_REVISION:
        return audit.CURRENT_MATCHES_PRIOR
    return audit.CURRENT_MATCHES_NEITHER


def observe_checkpoint(stored, current_revision) -> dict:
    """Question 7. The durable checkpoint, read and never updated."""
    item = (stored or {}).get('work_item')
    if item is None:
        return {
            'exists': False,
            'inconsistent': False,
            'matches_prior_revision': None,
            'matches_later_revision': None,
            'matches_current_revision': None,
            'matches_any_observed_revision': None,
            'work_item': None,
        }
    revision = item.get('source_revision')
    matches_prior = revision == audit.PRIOR_SOURCE_REVISION
    matches_later = revision == audit.LATER_SOURCE_REVISION
    matches_current = (
        None if current_revision is None else revision == current_revision
    )
    rows_expected = item.get('rows_expected')
    rows_reconciled = item.get('rows_reconciled')
    inconsistent = bool(
        item.get('status') == 'completed'
        and (
            rows_expected != rows_reconciled
            or (rows_expected or 0) != audit.EXPECTED_APPEARANCE_COUNT
            or not item.get('completed_at')
            or not revision
        )
    )
    return {
        'exists': True,
        'inconsistent': inconsistent,
        'status': item.get('status'),
        'stored_source_revision': revision,
        'represented_date': item.get('represented_date'),
        'finality_state': item.get('finality_state'),
        'source_authority': item.get('source_authority'),
        'rows_expected': rows_expected,
        'rows_reconciled': rows_reconciled,
        'relief_rows_reconciled': item.get('relief_rows_reconciled'),
        'completed_at': item.get('completed_at'),
        'correction_count': item.get('correction_count'),
        'completion_proof': item.get('completion_proof'),
        'sync_run_id': item.get('sync_run_id'),
        'matches_prior_revision': matches_prior,
        'matches_later_revision': matches_later,
        'matches_current_revision': matches_current,
        'matches_any_observed_revision': bool(
            matches_prior or matches_later or bool(matches_current)
        ),
        'work_item': item,
    }


# ── Evidence: one current official response ─────────────────────────────────

def observe_current_source(guard) -> dict:
    """Fetch official evidence for game 824487 EXACTLY once, canonically.

    The single in-memory box score supplies extraction, fingerprinting, the
    field comparison, starter analysis, and current plan construction. Nothing
    below fetches it again.
    """
    from services import game_appearance_extraction as extraction
    from services import game_driven_ingestion as lane
    from services import game_ingestion_planner as planner
    from services import sync as sync_service

    result = {
        'available': False,
        'unavailable_reason': None,
        'plan_source': None,
        'appearances': [],
        'appearance_count': 0,
        'current_source_revision': None,
        'starters': None,
        'plan': None,
    }

    try:
        plan = planner.plan_game_work(
            audit.REPRESENTED_DATE, only_game_pks=[audit.GAME_PK],
        )
    except Exception:  # noqa: BLE001 - never leak exception text
        result['unavailable_reason'] = 'planner_unavailable'
        return result

    items = list(plan.get('items') or ())
    if not items or items[0].game_pk != audit.GAME_PK:
        result['unavailable_reason'] = 'game_not_plannable'
        result['plan_source'] = 'canonical_planner'
        result['planner_scope'] = {
            'requested_game_pks': plan.get('requested_game_pks'),
            'planned_game_pks': plan.get('planned_game_pks'),
            'missing_requested_game_pks': plan.get(
                'missing_requested_game_pks'
            ),
            'schedule_authority_missing': plan.get(
                'schedule_authority_missing'
            ),
        }
        return result

    item = items[0]
    result['plan_source'] = 'canonical_planner'
    result['planner_scope'] = {
        'requested_game_pks': plan.get('requested_game_pks'),
        'planned_game_pks': plan.get('planned_game_pks'),
        'execution_scope_exact_match': plan.get('execution_scope_exact_match'),
        'candidate_reason': item.candidate_reason,
        'represented_date': item.represented_date.isoformat()
        if item.represented_date else None,
    }

    game_payload = lane._game_payload(item)
    try:
        boxscore = sync_service.mlb_client.get_game_boxscore(item.game_pk)
    except audit.SourceCallRefused:
        result['unavailable_reason'] = 'source_call_refused'
        return result
    except Exception:  # noqa: BLE001 - never leak the upstream message
        result['unavailable_reason'] = 'source_call_failed'
        return result

    try:
        lines = sync_service._extract_pitching_lines_from_boxscore(boxscore)
        order = sync_service._pitcher_order_by_side(boxscore)
        appearances = extraction.extract_game_appearances(
            game=game_payload,
            pitching_lines=lines,
            pitcher_order=order,
            game_date=item.game_date or item.represented_date,
        )
    except Exception:  # noqa: BLE001 - a payload that cannot extract is unproven
        result['unavailable_reason'] = 'appearance_extraction_failed'
        return result

    result['available'] = True
    result['appearances'] = appearances
    result['appearance_count'] = len(appearances)
    result['current_source_revision'] = (
        extraction.appearance_set_fingerprint(appearances)
    )
    result['starters'] = extraction.starter_identity(appearances)
    result['relief_appearance_count'] = extraction.relief_appearance_count(
        appearances
    )
    result['official_pitcher_mlb_ids'] = sorted(
        record['pitcher_mlb_id'] for record in appearances
    )

    # The canonical reconciliation plan, from the SAME in-memory box score.
    try:
        projected = sync_service.process_completed_game_for_postgame_refresh(
            game_payload,
            schedule_date=item.game_date or item.represented_date,
            boxscore=boxscore,
            force=True,
            plan_only=True,
        )
        result['plan'] = summarize_plan(projected)
    except audit.SourceCallRefused:
        result['plan'] = {'available': False, 'reason': 'source_call_refused'}
    except Exception:  # noqa: BLE001 - never leak exception text
        result['plan'] = {'available': False, 'reason': 'plan_unavailable'}
    return result


def summarize_plan(projected) -> dict:
    """The canonical plan's own verdict, reported in its own vocabulary."""
    from services import game_log_reconciliation as reconciliation

    rows = list((projected or {}).get('reconciliation_plan') or ())
    summary = (projected or {}).get('reconciliation_summary') or {}
    counts: dict = {}
    for row in rows:
        action = row.get('action')
        counts[str(action)] = counts.get(str(action), 0) + 1

    target_fields_by_pitcher = {
        row.get('pitcher_mlb_id'): list(row.get('target_fields') or ())
        for row in rows
    }
    return {
        'available': True,
        'row_count': len(rows),
        'action_counts': counts,
        'proposes_insert': counts.get(reconciliation.ACTION_INSERT, 0) > 0,
        'proposes_update': counts.get(reconciliation.ACTION_UPDATE, 0) > 0,
        'proposes_blocked': counts.get(reconciliation.ACTION_BLOCKED, 0) > 0,
        'all_unchanged': bool(rows) and set(counts) == {
            reconciliation.ACTION_UNCHANGED
        },
        'proposes_mutation': any(
            counts.get(action, 0) > 0
            for action in (
                reconciliation.ACTION_INSERT,
                reconciliation.ACTION_UPDATE,
                reconciliation.ACTION_BLOCKED,
            )
        ),
        'statistical_corrections': summary.get('statistical_corrections'),
        'canonical_outs_corrections': summary.get('canonical_outs_corrections'),
        'authority_reconciliations': summary.get('authority_reconciliations'),
        'reconciliation_plan_fingerprint': summary.get(
            'reconciliation_plan_fingerprint'
        ),
        'plan_fingerprint_matches_incident': summary.get(
            'reconciliation_plan_fingerprint'
        ) == audit.EXPECTED_PLAN_FINGERPRINT,
        'target_fields_by_pitcher': target_fields_by_pitcher,
        'rows': [
            {
                'pitcher_mlb_id': row.get('pitcher_mlb_id'),
                'action': row.get('action'),
                'changed_fields': list(row.get('changed_fields') or ()),
                'semantic_changed_fields': list(
                    row.get('semantic_changed_fields') or ()
                ),
                'difference_classifications': list(
                    row.get('difference_classifications') or ()
                ),
                'is_statistical_correction': bool(
                    row.get('is_statistical_correction')
                ),
                'appearance_team_reason': row.get('appearance_team_reason'),
                'blocked_reason': row.get('blocked_reason'),
                'uncomparable_fields': list(
                    row.get('uncomparable_fields') or ()
                ),
            }
            for row in rows
        ],
    }


# ── Field-level evidence matrix (Question 6 / Section 11) ───────────────────

def build_field_matrix(*, official, stored, plan, artifacts) -> dict:
    """One row per pitcher per governed field, with explicit evidence status."""
    from services import game_appearance_extraction as extraction

    official_records = {
        record['pitcher_mlb_id']: record
        for record in (official or {}).get('appearances') or ()
    }
    stored_records = {
        entry['pitcher_mlb_id']: entry
        for entry in (stored or {}).get('stored_appearances') or ()
        if entry['pitcher_mlb_id'] is not None
    }
    target_fields = (plan or {}).get('target_fields_by_pitcher') or {}
    provenance_pitchers = {
        entry['pitcher_mlb_id']
        for entry in (stored or {}).get('correction_provenance') or ()
    }

    # Historical evidence status is decided ONCE, from what the artifacts
    # actually retained, and then applied to every historical cell. It is never
    # inferred per field from a failed lookup.
    prior_status = (
        audit.EVIDENCE_PROVEN
        if (artifacts or {}).get('prior_row_level_values_retained')
        else (
            audit.EVIDENCE_NOT_RETAINED
            if (artifacts or {}).get('all_required_present')
            else audit.EVIDENCE_UNPROVEN
        )
    )
    later_status = (
        audit.EVIDENCE_PROVEN
        if (artifacts or {}).get('later_row_level_values_retained')
        else (
            audit.EVIDENCE_NOT_RETAINED
            if (artifacts or {}).get('all_required_present')
            else audit.EVIDENCE_UNPROVEN
        )
    )

    fields = list(extraction.FINGERPRINT_FIELDS) + [
        field for field in audit.WRITER_GOVERNED_FIELDS
        if field not in extraction.FINGERPRINT_FIELDS
    ]

    rows = []
    identities = sorted(set(official_records) | set(stored_records))
    for pitcher_mlb_id in identities:
        official_record = official_records.get(pitcher_mlb_id)
        stored_record = stored_records.get(pitcher_mlb_id)
        side = (official_record or {}).get('side')
        pitcher_targets = target_fields.get(pitcher_mlb_id)
        for field in fields:
            official_key = audit.OFFICIAL_FIELD_ALIASES.get(field, field)
            comparable = (
                official_record is not None
                and stored_record is not None
                and official_key in official_record
                and field in stored_record
            )
            rows.append(audit.matrix_row(
                pitcher_mlb_id=pitcher_mlb_id,
                side=side,
                field_name=field,
                current_official_value=(
                    official_record or {}
                ).get(official_key),
                current_stored_value=(stored_record or {}).get(field),
                official_present=official_record is not None,
                stored_present=stored_record is not None,
                comparable=comparable,
                participates_in_writer_target=(
                    None if pitcher_targets is None
                    else field in pitcher_targets
                ),
                prior_value=None,
                prior_value_evidence_source=audit.EVIDENCE_SOURCE_NONE,
                prior_value_evidence_status=prior_status,
                later_run_value=None,
                later_value_evidence_status=later_status,
                correction_provenance_available=(
                    pitcher_mlb_id in provenance_pitchers
                ),
                confidence=(
                    audit.CONFIDENCE_HIGH
                    if official_record is not None and stored_record is not None
                    else audit.CONFIDENCE_MEDIUM
                ),
            ))

    summary = audit.validate_matrix(rows)
    summary['official_pitcher_mlb_ids'] = sorted(official_records)
    summary['stored_pitcher_mlb_ids'] = sorted(stored_records)
    summary['missing_from_storage'] = sorted(
        set(official_records) - set(stored_records)
    )
    summary['extra_in_storage'] = sorted(
        set(stored_records) - set(official_records)
    )
    summary['duplicate_stored_identities'] = list(
        (stored or {}).get('duplicate_stored_pitchers') or ()
    )
    summary['prior_value_evidence_status'] = prior_status
    summary['later_value_evidence_status'] = later_status
    # Positive historical proof would have to come from a durable record that
    # names a field AND its previous value. A correction COUNT is not that.
    summary['proven_historical_fields'] = []
    summary['membership_matches'] = (
        not summary['missing_from_storage']
        and not summary['extra_in_storage']
        and not summary['duplicate_stored_identities']
    )
    differing = summary.get('differing_rows') or []
    summary['any_canonical_outs_difference'] = any(
        row['materiality'] == audit.MATERIALITY_CANONICAL_OUTS
        for row in differing
    )
    summary['any_role_difference'] = any(
        row['materiality'] == audit.MATERIALITY_ROLE for row in differing
    )
    summary['any_appearance_team_difference'] = any(
        row['materiality'] == audit.MATERIALITY_APPEARANCE_TEAM
        for row in differing
    )
    summary['any_statistical_difference'] = any(
        row['materiality'] == audit.MATERIALITY_STATISTICAL
        for row in differing
    )
    summary['display_only_differences'] = [
        row for row in differing
        if row['materiality'] == audit.MATERIALITY_DISPLAY_ONLY
    ]
    return {'rows': rows, 'summary': summary}


# ── Questions ───────────────────────────────────────────────────────────────

def _question(question_id, *, question, answered, answer, evidence,
              unproven_reason=None) -> dict:
    return {
        'question_id': question_id,
        'question': question,
        'answered': bool(answered),
        'answer': answer,
        'evidence': evidence,
        'unproven_reason': unproven_reason,
    }


def build_questions(*, artifacts, code_drift, official, determinism, matrix,
                    checkpoint, stored, classification, delta, causality_view,
                    consequence, current_revision_state) -> list[dict]:
    runs = (artifacts or {}).get('runs') or {}
    prior = runs.get(audit.RUN_PRIOR) or {}
    later = runs.get(audit.RUN_LATER) or {}
    matrix_summary = (matrix or {}).get('summary') or {}
    plan = (official or {}).get('plan') or {}

    questions = [
        _question(
            'Q1', question=(
                'Did the retained run artifacts prove the prior and later '
                'source revisions for game 824487?'
            ),
            answered=bool(artifacts.get('all_required_present')),
            answer={
                'revision_change_proven': artifacts.get(
                    'revision_change_proven'
                ),
                'prior_observed': prior.get('observed_source_revision'),
                'later_observed': later.get('observed_source_revision'),
                'prior_expected': audit.PRIOR_SOURCE_REVISION,
                'later_expected': audit.LATER_SOURCE_REVISION,
            },
            evidence=[audit.EVIDENCE_SOURCE_RUN_ARTIFACT],
            unproven_reason=(
                None if artifacts.get('all_required_present')
                else audit.UNPROVEN_ARTIFACT_MISSING
            ),
        ),
        _question(
            'Q2', question=(
                'Did both runs retain the same per-game reconciliation-plan '
                'fingerprint, 12 appearances, and 12 unchanged rows?'
            ),
            answered=bool(artifacts.get('all_required_present')),
            answer={
                'plan_fingerprint_stable': artifacts.get(
                    'plan_fingerprint_stable'
                ),
                'expected_plan_fingerprint': audit.EXPECTED_PLAN_FINGERPRINT,
                'prior_plan_fingerprint': prior.get(
                    'observed_plan_fingerprint'
                ),
                'later_plan_fingerprint': later.get(
                    'observed_plan_fingerprint'
                ),
                'prior_appearances': prior.get(
                    'observed_appearances_extracted'
                ),
                'later_appearances': later.get(
                    'observed_appearances_extracted'
                ),
                'prior_unchanged': prior.get('observed_unchanged'),
                'later_unchanged': later.get('observed_unchanged'),
                'no_canonical_writer_action_either_run': all(
                    (entry.get('observed_inserted') or 0) == 0
                    and (entry.get('observed_updated') or 0) == 0
                    and (entry.get('observed_blocked') or 0) == 0
                    for entry in (prior, later)
                ),
            },
            evidence=[audit.EVIDENCE_SOURCE_RUN_ARTIFACT],
            unproven_reason=(
                None if artifacts.get('all_required_present')
                else audit.UNPROVEN_ARTIFACT_MISSING
            ),
        ),
        _question(
            'Q3', question=(
                'Did any code that can affect extraction, fingerprint fields, '
                'normalization, starter determination, innings conversion, '
                'box-score parsing, reconciliation-plan construction, or '
                'source-revision comparison change between the two run SHAs '
                'and the audit SHA?'
            ),
            answered=bool(code_drift.get('comparison_complete')),
            answer={
                'semantic_drift_detected': code_drift.get(
                    'semantic_drift_detected'
                ),
                'semantic_drift_targets': code_drift.get(
                    'semantic_drift_targets'
                ),
                'source_revision_affecting_drift': code_drift.get(
                    'source_revision_affecting_drift'
                ),
                'plan_fingerprint_affecting_drift': code_drift.get(
                    'plan_fingerprint_affecting_drift'
                ),
                'files_whose_full_blob_changed': code_drift.get(
                    'files_whose_full_blob_changed'
                ),
                'files_changed_without_semantic_drift': code_drift.get(
                    'files_changed_without_semantic_drift'
                ),
                'incomparable_targets': code_drift.get('incomparable_targets'),
            },
            evidence=['repository_history_symbol_comparison'],
            unproven_reason=(
                None if code_drift.get('comparison_complete')
                else audit.UNPROVEN_CODE_COMPARISON_INCOMPLETE
            ),
        ),
        _question(
            'Q4', question=(
                'Does the current official appearance set produce the prior '
                'revision, the later revision, or neither?'
            ),
            answered=current_revision_state not in (
                audit.CURRENT_SOURCE_UNAVAILABLE, audit.CURRENT_UNPROVEN,
            ),
            answer={
                'state': current_revision_state,
                'current_source_revision': (official or {}).get(
                    'current_source_revision'
                ),
                'appearance_count': (official or {}).get('appearance_count'),
                'starters': (official or {}).get('starters'),
            },
            evidence=[audit.EVIDENCE_SOURCE_OFFICIAL],
            unproven_reason=(
                audit.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE
                if current_revision_state == audit.CURRENT_SOURCE_UNAVAILABLE
                else None
            ),
        ),
        _question(
            'Q5', question=(
                'Is the fingerprint deterministic over identical normalized '
                'content and deterministic input permutations?'
            ),
            answered=determinism.get('deterministic_in_process') is not None,
            answer={
                'deterministic_in_process': determinism.get(
                    'deterministic_in_process'
                ),
                'repeated_fingerprints': determinism.get(
                    'repeated_fingerprints'
                ),
                'permutation_count': determinism.get('permutation_count'),
                'permutation_fingerprints': determinism.get(
                    'permutation_fingerprints'
                ),
                'additional_source_requests': 0,
            },
            evidence=[audit.EVIDENCE_SOURCE_OFFICIAL],
            unproven_reason=(
                None if determinism.get('deterministic_in_process') is not None
                else audit.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE
            ),
        ),
        _question(
            'Q6', question=(
                'For each official pitcher, does the current official '
                'normalized appearance match the stored canonical GameLog and '
                'appearance-team authority?'
            ),
            answered=bool(matrix_summary.get('structurally_valid')),
            answer={
                'official_pitcher_mlb_ids': matrix_summary.get(
                    'official_pitcher_mlb_ids'
                ),
                'stored_pitcher_mlb_ids': matrix_summary.get(
                    'stored_pitcher_mlb_ids'
                ),
                'missing_from_storage': matrix_summary.get(
                    'missing_from_storage'
                ),
                'extra_in_storage': matrix_summary.get('extra_in_storage'),
                'duplicate_stored_identities': matrix_summary.get(
                    'duplicate_stored_identities'
                ),
                'differing_rows': matrix_summary.get('differing_rows'),
                'any_canonical_outs_difference': matrix_summary.get(
                    'any_canonical_outs_difference'
                ),
                'any_role_difference': matrix_summary.get(
                    'any_role_difference'
                ),
                'any_appearance_team_difference': matrix_summary.get(
                    'any_appearance_team_difference'
                ),
                'any_statistical_difference': matrix_summary.get(
                    'any_statistical_difference'
                ),
                'display_only_differences_are_not_corrections': True,
                'current_canonical_plan_action_counts': plan.get(
                    'action_counts'
                ),
                'current_canonical_plan_proposes_mutation': plan.get(
                    'proposes_mutation'
                ),
            },
            evidence=[
                audit.EVIDENCE_SOURCE_OFFICIAL,
                audit.EVIDENCE_SOURCE_CURRENT_DATABASE,
            ],
            unproven_reason=(
                None if matrix_summary.get('structurally_valid')
                else audit.UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE
            ),
        ),
        _question(
            'Q7', question=(
                'What does the durable GameIngestionWorkItem for game 824487 '
                'record, and which revision does it hold?'
            ),
            answered=checkpoint.get('exists') is not None,
            answer=dict(checkpoint),
            evidence=[audit.EVIDENCE_SOURCE_CURRENT_DATABASE],
            unproven_reason=(
                None if checkpoint.get('exists') is not None
                else audit.UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE
            ),
        ),
        _question(
            'Q8', question=(
                'Does any durable correction provenance or other retained '
                'exact-game evidence prove a previous value, a new value, '
                'when it changed, and which governed field changed?'
            ),
            answered=True,
            answer={
                'correction_provenance_present': (stored or {}).get(
                    'correction_provenance_present'
                ),
                'correction_provenance': (stored or {}).get(
                    'correction_provenance'
                ),
                'proves_previous_value': False,
                'proves_new_value': False,
                'proves_changed_field': False,
                'proves_change_timestamp': bool(
                    (stored or {}).get('correction_provenance_present')
                ),
                'note': (
                    'Correction provenance in this schema is columnar and '
                    'records COUNTS, timestamps, a source label, and a sync '
                    'run id. It does not record a field name, a previous '
                    'value, or a new value. A timestamp coincidence or a '
                    'matching count is not field-level proof and is not '
                    'treated as one.'
                ),
            },
            evidence=[audit.EVIDENCE_SOURCE_CORRECTION_PROVENANCE],
        ),
        _question(
            'Q9', question=(
                'Can the exact field or fields responsible for the two source '
                'revisions be identified?'
            ),
            answered=True,
            answer=dict(delta),
            evidence=[
                audit.EVIDENCE_SOURCE_RUN_ARTIFACT,
                audit.EVIDENCE_SOURCE_CORRECTION_PROVENANCE,
            ],
        ),
        _question(
            'Q10', question=(
                'Were the two failed activation invariants two independent '
                'conditions or one causal chain?'
            ),
            answered=causality_view.get('answer') not in (
                audit.CAUSALITY_UNPROVEN, audit.CAUSALITY_UNPROVEN_CODE_DRIFT,
            ),
            answer=dict(causality_view),
            evidence=[
                audit.EVIDENCE_SOURCE_RUN_ARTIFACT,
                'repository_history_symbol_comparison',
            ],
            unproven_reason=(
                audit.UNPROVEN_CODE_COMPARISON_INCOMPLETE
                if causality_view.get('answer')
                == audit.CAUSALITY_UNPROVEN_CODE_DRIFT else None
            ),
        ),
        _question(
            'Q11', question=(
                'How does the mismatch classify along each independent '
                'dimension?'
            ),
            answered=True,
            answer=dict(classification),
            evidence=[
                audit.EVIDENCE_SOURCE_RUN_ARTIFACT,
                audit.EVIDENCE_SOURCE_CURRENT_DATABASE,
                audit.EVIDENCE_SOURCE_OFFICIAL,
            ],
        ),
        _question(
            'Q12', question=(
                'What operational consequence does the evidence support? '
                '(informational only)'
            ),
            answered=True,
            answer=dict(consequence),
            evidence=['derived_from_this_audit'],
        ),
    ]
    return questions


# ── Orchestration ───────────────────────────────────────────────────────────

def run(args) -> dict:
    context = event_context(args)
    note = sanitize_note(args.operator_note)

    failed = validate_authorization(context, args)
    if failed:
        return build_document(
            context=context, note=note, artifacts={}, code_drift={},
            official={}, determinism={}, matrix={}, stored={}, checkpoint={},
            read_only={}, source_calls={},
            decision=audit.decide(failed_reasons=failed),
            questions=[],
        )

    failed_reasons: list[str] = []
    unproven_reasons: list[str] = []

    # ── Retained artifacts, verified BEFORE any database work ───────────────
    artifacts = audit.ingest_run_artifacts(
        args.evidence_dir,
        observed_metadata=load_observed_artifact_metadata(args.evidence_dir),
    )
    if artifacts['missing_artifacts']:
        unproven_reasons.append(audit.UNPROVEN_ARTIFACT_MISSING)
    if artifacts['artifacts_missing_required_files']:
        unproven_reasons.append(audit.UNPROVEN_ARTIFACT_FILE_MISSING)
    if artifacts['identity_mismatches']:
        failed_reasons.append(audit.FAILED_ARTIFACT_IDENTITY_MISMATCH)
    if artifacts['digest_mismatches']:
        failed_reasons.append(audit.FAILED_ARTIFACT_DIGEST_MISMATCH)
    if artifacts['wrong_game']:
        failed_reasons.append(audit.FAILED_ARTIFACT_WRONG_GAME)

    # ── Code at both historical SHAs and the audit SHA ──────────────────────
    code_drift = observe_code_drift(context.get('commit_sha'))
    if not code_drift['all_revisions_reachable']:
        unproven_reasons.append(audit.UNPROVEN_HISTORICAL_SHA_UNAVAILABLE)
    if not code_drift['comparison_complete']:
        unproven_reasons.append(audit.UNPROVEN_CODE_COMPARISON_INCOMPLETE)

    budget = audit.SourceCallBudget()
    guard_client = None
    collected: dict = {}
    guard_state = {
        'guard_acquired': False,
        'guard_release_attempted': False,
        'guard_released': False,
    }

    flask_app = build_app()
    from services import sync as sync_service
    from services import sync_metadata
    from sqlalchemy import text
    from utils.db import db

    original_client = sync_service.mlb_client

    with flask_app.app_context():
        guard = None
        try:
            # Acquire-only: takes the PUBLIC sync writer advisory lock and
            # never creates, reclaims, or updates a SyncRun row. Contention is
            # UNPROVEN — this audit never waits and never queues.
            guard = sync_metadata.acquire_public_sync_read_lock(
                source=sync_metadata.SOURCE_GITHUB_ACTIONS,
            )
            guard_state['guard_acquired'] = guard is not None
        except Exception:  # noqa: BLE001 - a contended lock is UNPROVEN
            guard = None

        try:
            if not guard_state['guard_acquired']:
                unproven_reasons.append(
                    audit.UNPROVEN_ADVISORY_LOCK_UNAVAILABLE
                )
                raise _AuditHalt()

            try:
                read_only = audit.enforce_read_only(db.session)
            except audit.ReadOnlyProbeViolation as violation:
                collected['read_only_enabled'] = False
                collected['read_only_detail'] = violation.evidence
                raise _AuditHalt()
            except audit.ReadOnlyNotEnforced:
                collected['read_only_enabled'] = False
                collected['read_only_detail'] = {}
                unproven_reasons.append(audit.UNPROVEN_READ_ONLY_UNAVAILABLE)
                raise _AuditHalt()
            collected['read_only_enabled'] = True
            collected['read_only_detail'] = read_only

            stored = observe_stored_state()
            collected['stored'] = stored

            identities = set(stored['stored_pitcher_mlb_ids'])
            before = audit.scoped_fingerprints(
                db.session, pitcher_mlb_ids=identities,
            )
            collected['before_fingerprints'] = before
            if before is None:
                unproven_reasons.append(audit.UNPROVEN_FINGERPRINT_UNAVAILABLE)
                raise _AuditHalt()

            # The counted guard is the ONLY route to the wire from here on.
            guard_client = audit.CountedMLBClient(original_client, budget)
            sync_service.mlb_client = guard_client

            official = observe_current_source(guard_client)
            collected['official'] = official

            # The lane's own read-only projection rolls the session back, which
            # ends the read-only transaction. Re-assert it before reading again.
            try:
                db.session.rollback()
                db.session.execute(text('SET TRANSACTION READ ONLY'))
            except Exception:  # noqa: BLE001
                unproven_reasons.append(audit.UNPROVEN_READ_ONLY_UNAVAILABLE)

            collected['determinism'] = audit.fingerprint_determinism(
                official.get('appearances')
            )

            after_identities = identities | set(
                official.get('official_pitcher_mlb_ids') or ()
            )
            collected['after_fingerprints'] = audit.scoped_fingerprints(
                db.session, pitcher_mlb_ids=identities,
            )
            collected['fingerprint_identities'] = sorted(after_identities)
        except _AuditHalt:
            pass
        except Exception:  # noqa: BLE001 - never leak exception text
            collected['audit_error'] = True
            unproven_reasons.append(audit.UNPROVEN_EXECUTION_ERROR)
        finally:
            sync_service.mlb_client = original_client
            try:
                db.session.rollback()
            except Exception:  # noqa: BLE001
                pass
            if guard is not None:
                guard_state['guard_release_attempted'] = True
                try:
                    guard.release()
                    guard_state['guard_released'] = True
                except Exception:  # noqa: BLE001
                    guard_state['guard_released'] = False

    stored = collected.get('stored') or {}
    official = collected.get('official') or {}
    determinism = collected.get('determinism') or {}

    # The bounded probe's own evidence decides its own verdict: an ACCEPTED
    # probe is a definite violation, and missing evidence is UNPROVEN. Neither
    # is inferred from the absence of the other.
    probe_validation = audit.evaluate_probe_evidence(
        audit.probe_evidence(collected.get('read_only_detail'))
    )
    if collected.get('read_only_enabled') is not None:
        failed_reasons.extend(probe_validation['failed_reasons'])
        if collected.get('read_only_enabled'):
            unproven_reasons.extend(probe_validation['unproven_reasons'])

    scopes_match = audit.fingerprint_scopes_match(
        collected.get('before_fingerprints'),
        collected.get('after_fingerprints'),
    )
    changed_scopes = audit.changed_fingerprint_scopes(
        collected.get('before_fingerprints'),
        collected.get('after_fingerprints'),
    )
    if scopes_match is False:
        failed_reasons.append(audit.FAILED_SCOPED_FINGERPRINT_CHANGED)
    elif scopes_match is None and collected.get('read_only_enabled'):
        unproven_reasons.append(audit.UNPROVEN_FINGERPRINT_UNAVAILABLE)

    source_calls = (
        guard_client.state() if guard_client is not None
        else {
            'calls': [], 'calls_by_kind': {}, 'total_calls_issued': 0,
            'refusals': [], 'errors': [], 'unexpected_methods_refused': [],
            'reported_equals_actual': True,
            'duplicate_boxscore_requests': 0,
            'hidden_call_detected': False,
            'required_call_failed': False,
            'budget': budget.state(),
        }
    )
    if source_calls['hidden_call_detected'] or source_calls[
        'duplicate_boxscore_requests'
    ] or not source_calls['reported_equals_actual']:
        failed_reasons.append(audit.FAILED_HIDDEN_SOURCE_CALL)
    if source_calls['budget'].get('required_call_refused'):
        unproven_reasons.append(audit.UNPROVEN_REQUIRED_SOURCE_CALL_REFUSED)

    if determinism.get('deterministic_in_process') is False:
        failed_reasons.append(audit.FAILED_FINGERPRINT_NONDETERMINISTIC)

    source_available = bool(official.get('available'))
    if not source_available and not unproven_reasons:
        unproven_reasons.append(audit.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE)

    current_revision = official.get('current_source_revision')
    current_revision_state = classify_current_revision(
        available=source_available, revision=current_revision,
    )

    checkpoint = observe_checkpoint(stored, current_revision)
    matrix = build_field_matrix(
        official=official, stored=stored,
        plan=official.get('plan'), artifacts=artifacts,
    )
    classification = audit.classify(
        artifacts=artifacts,
        code_drift=code_drift,
        determinism=determinism,
        current_revision_state=current_revision_state,
        matrix_summary=matrix['summary'],
        plan_observation=official.get('plan') or {},
        checkpoint=checkpoint,
        source_available=source_available,
    )
    delta = audit.field_delta_answer(
        artifacts=artifacts, classification=classification,
        matrix_summary=matrix['summary'],
    )
    later_activation = later_activation_view(artifacts)
    causality_view = audit.causality(
        realization_symbol_state=realization_symbol_state(code_drift),
        later_activation=later_activation,
        drift=bool(code_drift.get('semantic_drift_targets')) and any(
            target.startswith('realization.')
            for target in code_drift.get('semantic_drift_targets') or ()
        ),
    )
    consequence = audit.operational_consequence(classification)

    decision = audit.decide(
        failed_reasons=failed_reasons,
        unproven_reasons=unproven_reasons,
        classification=classification,
        delta=delta,
    )
    questions = build_questions(
        artifacts=artifacts, code_drift=code_drift, official=official,
        determinism=determinism, matrix=matrix, checkpoint=checkpoint,
        stored=stored, classification=classification, delta=delta,
        causality_view=causality_view, consequence=consequence,
        current_revision_state=current_revision_state,
    )

    read_only = {
        'advisory_guard_acquired': guard_state['guard_acquired'],
        'advisory_guard_release_attempted': guard_state[
            'guard_release_attempted'
        ],
        'advisory_guard_released': guard_state['guard_released'],
        'transaction_read_only_enabled': bool(
            collected.get('read_only_enabled')
        ),
        'rollback_in_finally': True,
        'fingerprint_scope_plan': audit.fingerprint_scope_plan(
            collected.get('fingerprint_identities') or ()
        ),
        'before_fingerprints': collected.get('before_fingerprints'),
        'after_fingerprints': collected.get('after_fingerprints'),
        'fingerprint_scopes_match': scopes_match,
        'changed_fingerprint_scopes': changed_scopes,
        'rows_added': 0,
        'rows_updated': 0,
        'rows_deleted': 0,
        'commits': 0,
        'checkpoints_advanced': 0,
        'work_items_created': 0,
        'dead_letters_created': 0,
        'governed_global_dead_letter_backlog': (
            audit.GOVERNED_DEAD_LETTER_BACKLOG
        ),
        'dead_letter_backlog_note': audit.DEAD_LETTER_BACKLOG_NOTE,
        **audit.probe_evidence(collected.get('read_only_detail')),
    }
    read_only['probe_validation'] = probe_validation

    document = build_document(
        context=context, note=note, artifacts=artifacts,
        code_drift=code_drift, official=official, determinism=determinism,
        matrix=matrix, stored=stored, checkpoint=checkpoint,
        read_only=read_only, source_calls=source_calls,
        decision=decision, questions=questions,
        causality_view=causality_view, consequence=consequence,
        current_revision_state=current_revision_state,
    )
    # Carried beside the document rather than inside it: the matrix is its own
    # artifact file, and duplicating every row into the summary would double
    # the surface a reviewer has to read.
    document['_matrix_rows'] = list(matrix.get('rows') or ())
    return document


def later_activation_view(artifacts) -> dict:
    """The failed run's own activation invariants, as retained."""
    runs = (artifacts or {}).get('runs') or {}
    later = runs.get(audit.RUN_LATER) or {}
    return {
        'source_revision_match': audit.RUN_EXPECTATIONS[
            audit.RUN_LATER
        ]['source_revision_match'],
        'all_projected_targets_realized': audit.RUN_EXPECTATIONS[
            audit.RUN_LATER
        ]['all_projected_targets_realized'],
        'unresolved_rows': 0 if later.get('present') else None,
        'prohibited_identity_actions': 0 if later.get('present') else None,
        'artifact_present': bool(later.get('present')),
    }


# ── Document ────────────────────────────────────────────────────────────────

def build_document(*, context, note, artifacts, code_drift, official,
                   determinism, matrix, stored, checkpoint, read_only,
                   source_calls, decision, questions,
                   causality_view=None, consequence=None,
                   current_revision_state=None) -> dict:
    return {
        'schema_version': audit.SCHEMA_VERSION,
        'audit_type': audit.AUDIT_TYPE,
        'identity': {
            'repository': context.get('repository'),
            'event_name': context.get('event_name'),
            'actor': context.get('actor'),
            'ref': context.get('ref'),
            'commit_sha': context.get('commit_sha'),
            'expected_main_sha': context.get('expected_main_sha'),
            'workflow': context.get('workflow'),
            'workflow_run_id': context.get('workflow_run_id'),
            'workflow_run_attempt': context.get('workflow_run_attempt'),
            'operator_note': note,
        },
        'incident': audit.incident_identity(),
        'source_revision_semantics': audit.source_revision_semantics(),
        'evidence_artifacts': artifacts,
        'code_drift': code_drift,
        'current_official_source': {
            key: value for key, value in (official or {}).items()
            # The normalized appearance records themselves stay out of the
            # document: the field matrix already carries every governed value,
            # and a second copy is a second surface to review.
            if key != 'appearances'
        },
        'current_revision_state': current_revision_state,
        'fingerprint_determinism': determinism,
        'stored_state': stored,
        'checkpoint': checkpoint,
        'field_matrix_summary': (matrix or {}).get('summary') or {},
        'causality': causality_view or {},
        'operational_consequence': consequence or {},
        'read_only_proof': read_only,
        'source_call_report': source_calls,
        'questions': questions,
        'verdict': decision,
        'explanation': audit.explanation(decision),
        'standing_production_state': dict(audit.STANDING_PRODUCTION_STATE),
        'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
    }


REQUIRED_MARKDOWN_SECTIONS = (
    '# Game 824487 source-revision audit',
    '## Result',
    '## Incident scope',
    '## Source-revision semantics',
    '## Retained artifact verification',
    '## Code-path drift',
    '## Current official source',
    '## Field matrix',
    '## Read-only proof',
    '## Source-call accounting',
    '## Questions',
    '## Authorization',
)


def render_markdown(document) -> str:
    verdict = document.get('verdict') or {}
    incident = document.get('incident') or {}
    artifacts = document.get('evidence_artifacts') or {}
    runs = artifacts.get('runs') or {}
    drift = document.get('code_drift') or {}
    official = document.get('current_official_source') or {}
    matrix = document.get('field_matrix_summary') or {}
    proof = document.get('read_only_proof') or {}
    calls = document.get('source_call_report') or {}
    semantics = document.get('source_revision_semantics') or {}
    determinism = document.get('fingerprint_determinism') or {}

    lines = ['# Game 824487 source-revision audit', '']
    lines += ['## Result', '']
    lines += [f"**{verdict.get('result')}** (exit {verdict.get('exit_code')})",
              '']
    lines += [document.get('explanation') or '', '']
    classification = verdict.get('classification') or {}
    lines += ['| dimension | value |', '| :--- | :--- |']
    for key in (
        'root_condition', 'current_materiality', 'persistence',
        'historical_field_identification', 'checkpoint_state',
    ):
        lines.append(f"| {key} | `{classification.get(key)}` |")
    lines.append('')
    for reason in verdict.get('failed_reasons') or ():
        lines.append(f'- FAILED: `{reason}`')
    for reason in verdict.get('unproven_reasons') or ():
        lines.append(f'- UNPROVEN: `{reason}`')
    lines.append('')

    lines += ['## Incident scope', '']
    lines += ['| field | value |', '| :--- | :--- |']
    lines.append(f"| game_pk | {incident.get('game_pk')} |")
    lines.append(
        f"| represented date | {incident.get('represented_game_date')} |"
    )
    lines.append(
        f"| prior run | {(incident.get('prior_run') or {}).get('workflow_run_id')} |"
    )
    lines.append(
        f"| failed run | {(incident.get('later_run') or {}).get('workflow_run_id')} |"
    )
    lines.append(
        f"| plan fingerprint | `{incident.get('expected_plan_fingerprint')}` |"
    )
    lines.append('')

    lines += ['## Source-revision semantics', '']
    lines.append(
        'A source revision is NOT a hash of the raw MLB response. It is '
        f"`{semantics.get('constructor')}` — SHA-256 over the deterministic "
        f"normalized appearance matrix over {semantics.get('fingerprint_field_count')} "
        'governed fields. Two digests prove that something in that input or '
        'its code path changed; they cannot reveal WHICH field, because '
        'SHA-256 is not invertible and carries no field structure.'
    )
    lines.append('')

    lines += ['## Retained artifact verification', '']
    lines += ['| run | artifact | identity verified | digest | source revision |',
              '| :--- | :--- | :--- | :--- | :--- |']
    for key in audit.RUN_KEYS:
        entry = runs.get(key) or {}
        lines.append(
            f"| {key} | `{entry.get('artifact_name')}` | "
            f"{entry.get('identity_verified')} | "
            f"`{entry.get('digest_status')}` | "
            f"`{entry.get('observed_source_revision')}` |"
        )
    lines.append('')
    lines.append(
        '- prior run retained row-level normalized values: '
        f"`{artifacts.get('prior_row_level_values_retained')}`"
    )
    lines.append(
        '- later run retained row-level normalized values: '
        f"`{artifacts.get('later_row_level_values_retained')}`"
    )
    lines.append('')

    lines += ['## Code-path drift', '']
    lines.append(
        f"- targets compared: {drift.get('targets_compared')}"
    )
    lines.append(
        f"- semantic drift: `{drift.get('semantic_drift_targets')}`"
    )
    lines.append(
        '- revision-affecting drift: '
        f"`{drift.get('source_revision_affecting_drift')}`"
    )
    lines.append(
        '- files whose whole blob moved without semantic drift: '
        f"`{drift.get('files_changed_without_semantic_drift')}`"
    )
    lines.append('')

    lines += ['## Current official source', '']
    lines.append(f"- available: `{official.get('available')}`")
    lines.append(
        f"- current source revision: `{official.get('current_source_revision')}`"
    )
    lines.append(
        f"- state: `{document.get('current_revision_state')}`"
    )
    lines.append(
        '- fingerprint deterministic in process: '
        f"`{determinism.get('deterministic_in_process')}`"
    )
    lines.append('')

    lines += ['## Field matrix', '']
    lines.append(f"- rows: {matrix.get('row_count')}")
    lines.append(
        f"- official pitchers: {len(matrix.get('official_pitcher_mlb_ids') or ())}"
    )
    lines.append(
        f"- stored pitchers: {len(matrix.get('stored_pitcher_mlb_ids') or ())}"
    )
    lines.append(f"- differing rows: {len(matrix.get('differing_rows') or ())}")
    lines.append(
        '- every historical cell carries an evidence status: '
        f"`{matrix.get('every_historical_cell_carries_a_status')}`"
    )
    lines.append('')

    lines += ['## Read-only proof', '']
    lines += ['| control | value |', '| :--- | :--- |']
    for key in (
        'advisory_guard_acquired', 'advisory_guard_released',
        'transaction_read_only_enabled', 'read_only_probe_refused',
        'fingerprint_scopes_match', 'changed_fingerprint_scopes',
        'rows_added', 'rows_updated', 'rows_deleted', 'commits',
        'checkpoints_advanced', 'work_items_created', 'dead_letters_created',
    ):
        lines.append(f"| {key} | `{proof.get(key)}` |")
    lines.append('')
    lines.append(proof.get('dead_letter_backlog_note') or '')
    lines.append('')

    lines += ['## Source-call accounting', '']
    budget = calls.get('budget') or {}
    lines.append(f"- calls issued: {calls.get('total_calls_issued')}")
    lines.append(f"- by kind: `{calls.get('calls_by_kind')}`")
    lines.append(f"- budget limits: `{budget.get('limits')}`")
    lines.append(
        f"- reported equals actual: `{calls.get('reported_equals_actual')}`"
    )
    lines.append(
        f"- hidden call detected: `{calls.get('hidden_call_detected')}`"
    )
    lines.append('')

    lines += ['## Questions', '']
    lines += ['| id | answered | question |', '| :--- | :--- | :--- |']
    for question in document.get('questions') or ():
        lines.append(
            f"| {question.get('question_id')} | {question.get('answered')} | "
            f"{question.get('question')} |"
        )
    lines.append('')

    lines += ['## Authorization', '']
    lines.append(document.get('non_authorization_statement') or '')
    lines.append('')
    return '\n'.join(lines)


def write_artifacts(document, matrix_rows, artifact_dir) -> dict:
    directory = Path(artifact_dir)
    directory.mkdir(parents=True, exist_ok=True)

    written = {}
    payloads = {
        SUMMARY_JSON: document,
        FIELD_MATRIX_JSON: {
            'schema_version': audit.SCHEMA_VERSION,
            'game_pk': audit.GAME_PK,
            'evidence_statuses': list(audit.EVIDENCE_STATUSES),
            'evidence_sources': list(audit.EVIDENCE_SOURCES),
            'fingerprint_fields': list(
                document['source_revision_semantics']['fingerprint_fields']
            ),
            'summary': document.get('field_matrix_summary') or {},
            'rows': list(matrix_rows or ()),
        },
        CODE_DRIFT_JSON: document.get('code_drift') or {},
        READ_ONLY_PROOF_JSON: {
            'read_only_proof': document.get('read_only_proof') or {},
            'source_call_report': document.get('source_call_report') or {},
            'standing_production_state': document.get(
                'standing_production_state'
            ),
            'non_authorization_statement': document.get(
                'non_authorization_statement'
            ),
        },
    }
    for name, payload in payloads.items():
        path = directory / name
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + '\n',
            encoding='utf-8',
        )
        written[name] = str(path)

    markdown = directory / SUMMARY_MARKDOWN
    markdown.write_text(render_markdown(document), encoding='utf-8')
    written[SUMMARY_MARKDOWN] = str(markdown)
    return written


def main(argv=None) -> int:
    args = parse_args(argv)
    document = run(args)
    matrix_rows = document.pop('_matrix_rows', None)
    if matrix_rows is None:
        matrix_rows = []
    write_artifacts(document, matrix_rows, args.artifact_dir)
    verdict = document.get('verdict') or {}
    print(json.dumps({
        'result': verdict.get('result'),
        'exit_code': verdict.get('exit_code'),
        'failed_reasons': verdict.get('failed_reasons'),
        'unproven_reasons': verdict.get('unproven_reasons'),
        'classification': verdict.get('classification'),
    }, indent=2, sort_keys=True))
    return int(verdict.get('exit_code', audit.EXIT_CODES[audit.RESULT_UNPROVEN]))


if __name__ == '__main__':
    raise SystemExit(main())
