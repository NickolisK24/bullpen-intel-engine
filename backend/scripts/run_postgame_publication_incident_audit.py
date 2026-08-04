#!/usr/bin/env python
"""Read-only postgame publication incident audit for run 30873422601.

    python scripts/run_postgame_publication_incident_audit.py \
        --expected-head-sha <40 hex> \
        --confirmation AUDIT_POSTGAME_PUBLICATION_INCIDENT_30873422601 \
        --evidence-dir incident-evidence \
        --artifact-dir ../artifacts/postgame-publication-incident-audit

Manual only, exact scope, read-only. Reconstructs the failed postgame
publication cycle for slate 2026-08-03 and answers eight explicit questions
about it from three independent evidence sources: the run's own retained
artifacts, current production state, and the canonical MLB client.

It CALLS the canonical authorities — schedule finality, the planner, the
appearance ledger, game-ingestion completeness, the snapshot service, the
publication proof — and never reimplements them. Identifying a root cause is
information. It repairs nothing and authorizes nothing.

Exit codes: 0 COMPLETE (root cause identified / no platform defect proven /
incident not reproducible), 1 FAILED, 2 UNPROVEN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import postgame_publication_incident_audit as audit  # noqa: E402
from services import noop_write_qualification as qualification  # noqa: E402


SUMMARY_JSON = 'incident-audit-summary.json'
SUMMARY_MARKDOWN = 'incident-audit-summary.md'
METADATA_JSON = 'incident-audit-metadata.json'
ARTIFACT_METADATA_FILENAME = 'artifact-metadata.json'

REQUIRED_REPOSITORY = qualification.REQUIRED_REPOSITORY
REQUIRED_REF = qualification.REQUIRED_REF
REQUIRED_EVENT_NAME = qualification.REQUIRED_EVENT_NAME
REQUIRED_ACTOR = qualification.REQUIRED_ACTOR

# Canonical modules whose behaviour Question 3 compares against the incident.
CANONICAL_MODULES = tuple(audit.INCIDENT_CANONICAL_MODULE_DIGESTS)


class _AuditHalt(Exception):
    """Stop collecting; the verdict is decided from what was proven."""


class _StageFailure(Exception):
    """A stage raised. The ledger holds the safe description of what and where.

    Carrying no payload is deliberate: an exception that travels with detail
    is an exception whose detail can be printed. Everything a reader is
    allowed to know lives in the ledger, in a closed vocabulary.
    """


class _StageLedger:
    """Where the run got to, in terms a reader may safely be told.

    The first production run stopped inside completeness and reported only
    ``audit_execution_error`` — true, unactionable, and indistinguishable from
    a failure anywhere else in the run. This records the last stage that
    finished, the stage that stopped, and a bounded class for why, and it
    persists each observer's result the instant that observer returns so a
    later exception cannot erase earlier proof.
    """

    def __init__(self):
        self.last_completed = audit.STAGE_NOT_STARTED
        self.failed_stage = None
        self.error_class = audit.ERROR_CLASS_NONE
        self.completed_stages: list[str] = []

    def completed(self, stage):
        stage = audit.safe_stage(stage)
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        # ``last_completed`` answers "how far did the run get before it
        # stopped", so it freezes at the first failure. The closing
        # fingerprint stages deliberately run AFTER a stop, to finish the
        # read-only proof; letting them advance this would report a run that
        # died in completeness as having got all the way to the end. They are
        # still listed in ``completed_stages``, which is a record of what ran.
        if self.failed_stage is None:
            self.last_completed = stage

    def failed(self, stage, exc):
        # Only the exception's TYPE is consulted; the instance is dropped here
        # and never stored, so there is nothing left to leak downstream.
        if self.failed_stage is None:
            self.failed_stage = audit.safe_stage(stage)
            self.error_class = audit.classify_error(exc)

    def stage(self, name, observations, key, produce):
        """Run one observer, keep its result, then advance the stage.

        The result is written before the stage is marked complete, so a crash
        between the two can only under-report progress, never over-report it.
        """
        try:
            value = produce()
        except Exception as exc:  # noqa: BLE001 - never leak exception text
            self.failed(name, exc)
            raise _StageFailure() from None
        if key is not None:
            observations[key] = value
        self.completed(name)
        return value

    def state(self) -> dict:
        return {
            'last_completed_stage': self.last_completed,
            'failed_stage': self.failed_stage,
            'safe_error_class': self.error_class,
            'completed_stages': list(self.completed_stages),
            'stages_total': len(audit.EXECUTION_STAGES),
            'execution_complete': (
                self.failed_stage is None
                and self.last_completed == audit.STAGE_COMPLETE
            ),
            'error_observed': self.failed_stage is not None,
            'error_detail_withheld': True,
            'error_vocabulary': list(audit.SAFE_ERROR_CLASSES),
        }


def _close_fingerprints(collected, observations, ledger, db) -> None:
    """Digest the unresolved scope, then close the read-only proof.

    BEFORE, phase two: the unresolved-game scope cannot be digested until the
    canonical completeness proof has told us which games are in it. It is
    digested the moment that set is known and re-digested at the end. The
    earlier scopes keep their original phase-one digest, so no span of this
    run is left unprotected by a shifting baseline. The unresolved games sit
    inside the ledger-window horizon anyway, so phase one already covers them;
    this scope adds precision, not first-time coverage.

    This runs even when an observer stopped the run. A partial audit still
    owes the reader a complete answer to "did this change anything?", and the
    phase-one baseline it needs has already been persisted.
    """
    before = collected.get('before_fingerprints')
    unresolved_pks = [
        entry['game_pk'] for entry in (
            (observations.get('completeness') or {})
            .get('unresolved_classification', {})
            .get('games') or []
        )
    ]
    if unresolved_pks:
        try:
            unresolved_before = audit.scoped_fingerprints(
                db.session, unresolved_game_pks=unresolved_pks,
            )
        except Exception as exc:  # noqa: BLE001 - never leak exception text
            ledger.failed(audit.STAGE_UNRESOLVED_FINGERPRINTS, exc)
            unresolved_before = None
        if unresolved_before is not None:
            collected['before_fingerprints'] = {
                **before,
                audit.SCOPE_UNRESOLVED_GAMES: unresolved_before[
                    audit.SCOPE_UNRESOLVED_GAMES
                ],
            }
            ledger.completed(audit.STAGE_UNRESOLVED_FINGERPRINTS)
    else:
        ledger.completed(audit.STAGE_UNRESOLVED_FINGERPRINTS)

    collected['scope_plan'] = audit.fingerprint_scope_plan(unresolved_pks)
    try:
        collected['after_fingerprints'] = audit.scoped_fingerprints(
            db.session, unresolved_game_pks=unresolved_pks,
        )
    except Exception as exc:  # noqa: BLE001 - never leak exception text
        ledger.failed(audit.STAGE_AFTER_FINGERPRINTS, exc)
        collected['after_fingerprints'] = None
        return
    ledger.completed(audit.STAGE_AFTER_FINGERPRINTS)
    if ledger.failed_stage is None:
        ledger.completed(audit.STAGE_COMPLETE)


# ── Arguments and authorization ─────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Read-only postgame publication incident audit.',
    )
    parser.add_argument('--expected-head-sha', required=True)
    parser.add_argument('--confirmation', required=True)
    parser.add_argument(
        '--evidence-dir', default='incident-evidence',
        help=(
            'Directory holding the downloaded incident artifacts, one '
            'subdirectory per artifact name.'
        ),
    )
    parser.add_argument(
        '--artifact-dir',
        default='artifacts/postgame-publication-incident-audit',
    )
    parser.add_argument('--operator-note', default='')
    return parser.parse_args(argv)


def event_context(args, environ=None) -> dict:
    env = environ if environ is not None else os.environ
    return {
        'event_name': env.get('GITHUB_EVENT_NAME'),
        'repository': env.get('GITHUB_REPOSITORY'),
        'actor': env.get('GITHUB_ACTOR'),
        'ref': env.get('GITHUB_REF'),
        'github_sha': env.get('GITHUB_SHA'),
        'run_id': env.get('GITHUB_RUN_ID'),
        'run_attempt': env.get('GITHUB_RUN_ATTEMPT'),
        'workflow': env.get('GITHUB_WORKFLOW'),
        'expected_head_sha': args.expected_head_sha,
        'confirmation': args.confirmation,
    }


def validate_authorization(context) -> list[str]:
    """Every workflow gate re-validated here; the workflow is not trusted."""
    failures: list[str] = []
    if str(context.get('event_name') or '') != REQUIRED_EVENT_NAME:
        failures.append('event_not_workflow_dispatch')
    if str(context.get('repository') or '') != REQUIRED_REPOSITORY:
        failures.append('repository_not_authorized')
    if str(context.get('actor') or '') != REQUIRED_ACTOR:
        failures.append('actor_not_authorized')
    if str(context.get('ref') or '') != REQUIRED_REF:
        failures.append('ref_not_main')

    expected = qualification.normalize_sha(context.get('expected_head_sha'))
    actual = qualification.normalize_sha(context.get('github_sha'))
    if not qualification._SHA_PATTERN.match(expected):
        failures.append('expected_head_sha_malformed')
    elif not qualification._SHA_PATTERN.match(actual) or expected != actual:
        failures.append('expected_head_sha_mismatch')

    if str(context.get('confirmation') or '') != audit.CONFIRMATION:
        failures.append('confirmation_mismatch')
    return failures


def build_app():
    import app as app_module

    return app_module.create_app()


def current_module_digests() -> dict:
    """Digest the canonical modules as they exist in this checkout."""
    digests = {}
    for relative in CANONICAL_MODULES:
        path = BACKEND_ROOT / relative
        try:
            digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digests[relative] = None
    return digests


def load_observed_artifact_metadata(evidence_dir) -> dict:
    """Read the artifact metadata the workflow captured from the API."""
    path = Path(evidence_dir) / ARTIFACT_METADATA_FILENAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


class SourceGateway:
    """The only place in this package that touches the MLB client.

    Every call reserves budget first, then records success or failure with its
    latency, so what the artifact reports and what actually went over the wire
    are the same number by construction. Nothing here fetches twice: callers
    that need a payload again get the one already observed.

    ``required=False`` marks an opportunistic call. Refusing one of those is
    not an evidence gap; refusing a required one is.
    """

    def __init__(self, budget, client=None):
        self._budget = budget
        self._client = client
        self.refusals: list[dict] = []
        self.errors: list[dict] = []
        # A required call that was reserved, dialled and FAILED is still
        # missing evidence. The budget cannot see that — it only knows the
        # reservation succeeded — so the gateway carries it.
        self.required_attempted = 0
        self.required_succeeded = 0
        self.recoveries: list[dict] = []
        self.missing_evidence: set = set()
        # The one horizon response, fetched once and reused by every consumer.
        self.window_games = None
        self.window_fetched = False

    @property
    def client(self):
        if self._client is None:
            from services.mlb_api import mlb_client

            self._client = mlb_client
        return self._client

    def _call(self, kind, label, invoke, *, required):
        if not self._budget.reserve(kind, required=required):
            self.refusals.append({
                'kind': kind, 'label': label, 'required': required,
            })
            return None
        if required:
            self.required_attempted += 1
        started = perf_counter()
        try:
            result = invoke()
        except Exception:  # noqa: BLE001 - never leak the source message
            self._budget.record_failure(
                kind, latency_ms=(perf_counter() - started) * 1000,
            )
            self.errors.append({
                'kind': kind, 'label': label, 'required': required,
            })
            return None
        self._budget.record_success(
            kind, latency_ms=(perf_counter() - started) * 1000,
        )
        if required:
            self.required_succeeded += 1
        return result

    def record_recovery(self, label, *, recovered_by, evidence):
        """A governed fallback positively recovered a failed required call.

        Recovery has to be claimed explicitly and say WHAT it recovered,
        because a fallback usually restores only part of what the failed call
        would have provided. A successful exact-game call for one game does
        not recover schedule evidence for every other game in the window.
        """
        self.recoveries.append({
            'failed_call': label,
            'recovered_by': recovered_by,
            'evidence_recovered': list(evidence),
        })

    def recovered_evidence(self) -> set:
        return {
            item for entry in self.recoveries
            for item in entry['evidence_recovered']
        }

    def required_failures(self) -> list[dict]:
        return [entry for entry in self.errors if entry.get('required')]

    def schedule_window(self, start, end, *, required=True):
        """One governed call for a whole date range, never one call per date."""
        return self._call(
            audit.CALL_KIND_SCHEDULE, f'schedule {start}..{end}',
            lambda: self.client.get_schedule(
                start_date=start.isoformat() if hasattr(start, 'isoformat')
                else str(start),
                end_date=end.isoformat() if hasattr(end, 'isoformat')
                else str(end),
            ),
            required=required,
        )

    def fetch_window(self, start, end):
        """Fetch the horizon exactly once; later callers reuse the response.

        This one call buys official status for the disputed game AND for every
        unresolved game in the window. If it fails, both are missing until
        something positively recovers them.
        """
        if not self.window_fetched:
            self.window_fetched = True
            self.window_games = self.schedule_window(start, end)
            if self.window_games is None:
                self.missing_evidence.update({
                    audit.EVIDENCE_DISPUTED_GAME_OFFICIAL_STATUS,
                    audit.EVIDENCE_UNRESOLVED_WINDOW_OFFICIAL_STATUS,
                })
        return self.window_games

    def outstanding_evidence(self) -> set:
        """Required evidence still missing after any governed recovery."""
        return self.missing_evidence - self.recovered_evidence()

    def exact_game_day(self, day, *, required=True):
        """A single date, used only when a game is absent from the window."""
        value = day.isoformat() if hasattr(day, 'isoformat') else str(day)
        return self._call(
            audit.CALL_KIND_EXACT_GAME, f'exact_game {value}',
            lambda: self.client.get_schedule(start_date=value, end_date=value),
            required=required,
        )

    def boxscore(self, game_pk, *, required=True):
        return self._call(
            audit.CALL_KIND_BOXSCORE, f'boxscore {game_pk}',
            lambda: self.client.get_game_boxscore(game_pk),
            required=required,
        )

    def state(self) -> dict:
        required_failed = self.required_failures()
        return {
            'refusals': list(self.refusals),
            'source_errors': list(self.errors),
            'required_refusals': [
                entry for entry in self.refusals if entry['required']
            ],
            'required_calls_attempted': self.required_attempted,
            'required_calls_succeeded': self.required_succeeded,
            'required_calls_failed': len(required_failed),
            'optional_calls_failed': len(self.errors) - len(required_failed),
            'failed_required_labels': [
                entry['label'] for entry in required_failed
            ],
            'recoveries': list(self.recoveries),
            'recovered_evidence': sorted(self.recovered_evidence()),
            # A reserved-and-dialled call that failed is missing evidence just
            # as surely as one the budget refused.
            'required_source_failure': bool(required_failed),
            'missing_required_evidence': sorted(self.missing_evidence),
            'outstanding_required_evidence': sorted(
                self.outstanding_evidence()
            ),
            # Recovery is only recovery if something is actually restored.
            'all_required_evidence_recovered': not self.outstanding_evidence(),
        }


# ── Official MLB source evidence (Question 1) ───────────────────────────────

def observe_official_status(game_pk, stored, gateway, *, window_games=None) -> dict:
    """Current official MLB record for the disputed game.

    ``window_games`` is the already-fetched horizon response. The disputed game
    is normally inside it, so answering Question 1 usually costs no additional
    call at all; an exact-game call is spent only when the game is genuinely
    absent from that window.

    The box score is fetched at most ONCE, and the safe pitcher-id set is
    extracted from that same response. Player attribution consumes what is
    recorded here rather than fetching again.
    """
    from services import game_finality

    observation = {
        'evidence_source': audit.SOURCE_OFFICIAL,
        'game_found_in_source': False,
        'found_in_window_response': False,
        'dates_queried': [],
        'normalized': {field: None for field in audit.OFFICIAL_STATUS_FIELDS},
        'canonical_finality_state': None,
        'canonical_finality_reason': None,
        'canonical_status_state': None,
        'official_classification': audit.OFFICIAL_CLASS_UNKNOWN,
        'boxscore_requested': False,
        'boxscore_observed': False,
        'boxscore_usable': None,
        'boxscore_reason': None,
        'boxscore_pitching_line_count': None,
        'pitching_line_extraction_failed': False,
        # The safe projection of the box score. The raw payload is never kept.
        'boxscore_pitcher_ids': [],
        'raw_boxscore_retained': False,
        'source_calls_refused': False,
        'source_error': False,
        'relationship': {
            'is_rescheduled': False, 'is_resumed': False,
            'rescheduled_from_game_pk': None, 'resumed_from_game_pk': None,
            'replacement_game_pk': None, 'resolved': False,
        },
    }

    game = _find_game(window_games, game_pk)
    if game is not None:
        observation['found_in_window_response'] = True
    else:
        # Absent from the window: try the stored dates, cheapest first.
        candidates = [audit.INCIDENT_SLATE_DATE.isoformat()]
        for row in (stored or {}).get('rows') or ():
            value = row.get('game_date')
            if value and value not in candidates:
                candidates.append(value)
        for day in candidates:
            observation['dates_queried'].append(day)
            games = gateway.exact_game_day(day)
            if games is None:
                observation['source_calls_refused'] = True
                break
            game = _find_game(games, game_pk)
            if game is not None:
                # This recovers the disputed game's official status and
                # nothing else. The other games in the window are still
                # unobserved, so Question 7 stays unrecovered.
                gateway.record_recovery(
                    'schedule window',
                    recovered_by=f'exact_game {day}',
                    evidence=[
                        audit.EVIDENCE_DISPUTED_GAME_OFFICIAL_STATUS,
                    ],
                )
                break

    if game is None:
        return observation

    status = game.get('status') or {}
    decision = game_finality.classify_status(status, game_pk=game_pk)

    observation['game_found_in_source'] = True
    observation['canonical_finality_state'] = decision.state
    observation['canonical_finality_reason'] = decision.reason
    observation['canonical_status_state'] = (
        game_finality.normalize_schedule_status_state(game)
    )
    observation['official_classification'] = _official_class(decision.state)
    observation['relationship'] = _official_relationship(game)
    observation['normalized'] = _normalize_official_game(
        game, observation['official_classification'],
    )

    # The box score is the positive proof that appearance rows should exist,
    # so it is fetched only when the official record says the game is final.
    if not decision.final_status:
        return observation

    observation['boxscore_requested'] = True
    boxscore = gateway.boxscore(game_pk)
    if boxscore is None:
        gateway.missing_evidence.add(audit.EVIDENCE_DISPUTED_BOXSCORE)
        if gateway.refusals and gateway.refusals[-1]['kind'] == (
            audit.CALL_KIND_BOXSCORE
        ):
            observation['source_calls_refused'] = True
        else:
            observation['source_error'] = True
        return observation

    usability = game_finality.classify_boxscore_usability(boxscore)
    lines = _pitching_lines(boxscore)
    if lines is None:
        # Extraction failed. That is not "no pitchers appeared"; it is not
        # knowing who did, and it leaves attribution without its evidence.
        observation['pitching_line_extraction_failed'] = True
        gateway.missing_evidence.add(audit.EVIDENCE_DISPUTED_BOXSCORE)
    observation['boxscore_observed'] = True
    observation['boxscore_usable'] = usability.is_final_and_usable
    observation['boxscore_reason'] = usability.reason
    observation['boxscore_pitching_line_count'] = (
        None if lines is None else len(lines)
    )
    observation['boxscore_pitcher_ids'] = sorted({
        entry.get('player_id') for entry in (lines or ())
        if entry.get('player_id') is not None
    })
    return observation


def _find_game(games, game_pk):
    for game in games or ():
        if _int(game.get('gamePk')) == int(game_pk):
            return game
    return None


def _pitching_lines(boxscore):
    if not isinstance(boxscore, dict):
        return None
    try:
        from services.sync import _extract_pitching_lines_from_boxscore

        return _extract_pitching_lines_from_boxscore(boxscore) or []
    except Exception:  # noqa: BLE001 - unknown lines are unproven, not empty
        return None


def _normalize_official_game(game, probable_classification=None) -> dict:
    """Safe normalized fields only. The raw MLB payload is never reproduced."""
    status = game.get('status') or {}
    teams = game.get('teams') or {}
    normalized = {
        'game_pk': _int(game.get('gamePk')),
        'official_date': _text(game.get('officialDate')),
        'original_date': _text(
            game.get('originalDate') or game.get('rescheduledFromDate')
        ),
        'resume_date': _text(
            game.get('resumeDate') or game.get('resumedFromDate')
        ),
        'reschedule_date': _text(game.get('rescheduleDate')),
        'game_type': _text(game.get('gameType')),
        'doubleheader': _text(game.get('doubleHeader')),
        'game_number': _int(game.get('gameNumber')),
        'abstract_game_state': _text(status.get('abstractGameState')),
        'detailed_state': _text(status.get('detailedState')),
        'coded_game_state': _text(status.get('codedGameState')),
        'status_code': _text(status.get('statusCode')),
        'reason': _text(status.get('reason')),
        'home_team_id': _int(
            ((teams.get('home') or {}).get('team') or {}).get('id')
        ),
        'away_team_id': _int(
            ((teams.get('away') or {}).get('team') or {}).get('id')
        ),
        'venue_id': _int((game.get('venue') or {}).get('id')),
        'probable_classification': probable_classification,
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'source_revision': None,
    }
    # The source revision is a digest of the NORMALIZED fields, so the artifact
    # carries a stable identity for what was observed without carrying the
    # payload it came from.
    stable = {
        key: value for key, value in normalized.items()
        if key not in ('retrieved_at', 'source_revision')
    }
    normalized['source_revision'] = hashlib.sha256(
        json.dumps(stable, sort_keys=True, default=str).encode('utf-8')
    ).hexdigest()[:32]
    return normalized


def _official_class(state) -> str:
    from services import game_finality

    return {
        game_finality.FINAL_AND_USABLE: audit.OFFICIAL_CLASS_FINAL,
        game_finality.FINAL_PENDING_DATA: audit.OFFICIAL_CLASS_FINAL,
        game_finality.POSTPONED: audit.OFFICIAL_CLASS_POSTPONED,
        game_finality.SUSPENDED: audit.OFFICIAL_CLASS_SUSPENDED,
        game_finality.CANCELLED: audit.OFFICIAL_CLASS_CANCELLED,
        game_finality.NOT_FINAL: audit.OFFICIAL_CLASS_NON_FINAL,
    }.get(state, audit.OFFICIAL_CLASS_UNKNOWN)


def _official_relationship(game) -> dict:
    rescheduled_from = _int(
        (game.get('rescheduledFrom') or {}).get('gamePk')
        if isinstance(game.get('rescheduledFrom'), dict)
        else game.get('rescheduledFrom')
    )
    resumed_from = _int(
        (game.get('resumedFrom') or {}).get('gamePk')
        if isinstance(game.get('resumedFrom'), dict)
        else game.get('resumedFrom')
    )
    replacement = _int(
        (game.get('rescheduledTo') or {}).get('gamePk')
        if isinstance(game.get('rescheduledTo'), dict)
        else game.get('rescheduledTo')
    )
    return {
        'is_rescheduled': (
            rescheduled_from is not None or replacement is not None
        ),
        'is_resumed': resumed_from is not None,
        'rescheduled_from_game_pk': rescheduled_from,
        'resumed_from_game_pk': resumed_from,
        'replacement_game_pk': replacement,
        'resolved': True,
    }



# ── Stored schedule evidence (Question 2) ───────────────────────────────────

def observe_stored_schedule(game_pk) -> dict:
    """All production schedule rows for the game, plus the surrounding slate."""
    from models.scheduled_game import ScheduledGame
    from services import game_finality

    rows = (
        ScheduledGame.query
        .filter(ScheduledGame.game_pk == game_pk)
        .order_by(ScheduledGame.team_id.asc())
        .all()
    )
    stored = [
        {
            'team_id': row.team_id,
            'opponent_team_id': row.opponent_team_id,
            'home_away': row.home_away,
            'game_date': _iso(row.game_date),
            'game_datetime': _iso(row.game_datetime),
            'status_code': row.status_code,
            'status_state': row.status_state,
            'game_type': row.game_type,
            'doubleheader': row.doubleheader,
            'game_number': row.game_number,
            'original_game_date': _iso(row.original_game_date),
            'original_product_date': _iso(row.original_product_date),
            'resumed_game_date': _iso(row.resumed_game_date),
            'resumed_product_date': _iso(row.resumed_product_date),
            'resumed_from_game_pk': row.resumed_from_game_pk,
            'resumed_to_game_pk': row.resumed_to_game_pk,
            'source': row.source,
            'created_at': _iso(getattr(row, 'created_at', None)),
            'updated_at': _iso(getattr(row, 'updated_at', None)),
        }
        for row in rows
    ]
    states = sorted({row.status_state for row in rows})
    codes = sorted({row.status_code for row in rows if row.status_code})
    team_ids = [row.team_id for row in rows]
    agreement = _row_agreement(rows)

    slate_rows = (
        ScheduledGame.query
        .with_entities(ScheduledGame.game_pk, ScheduledGame.status_state)
        .filter(ScheduledGame.game_date == audit.INCIDENT_SLATE_DATE)
        .all()
    )
    slate: dict[int, set] = {}
    for slate_game_pk, state in slate_rows:
        slate.setdefault(slate_game_pk, set()).add(state)

    return {
        'evidence_source': audit.SOURCE_CURRENT_DB,
        'row_count': len(rows),
        'rows': stored,
        'team_ids': team_ids,
        'duplicate_team_rows': len(team_ids) != len(set(team_ids)),
        'distinct_status_states': states,
        'distinct_status_codes': codes,
        # status_state agreement alone is far too narrow: two rows can agree
        # that a game is final and still disagree about which teams played it.
        'row_agreement': agreement,
        'full_row_governance_agreement': agreement[
            'full_row_governance_agreement'
        ],
        'disagreeing_fields': agreement['disagreeing_fields'],
        'rows_agree': agreement['full_row_governance_agreement'],
        'paired_row_disagreement': not agreement[
            'full_row_governance_agreement'
        ],
        'status_state_agreement': len(states) <= 1,
        'stored_status_state': states[0] if len(states) == 1 else None,
        'counts_as_ledger_final': (
            game_finality.FINAL_STATUS_STATE in states
        ),
        'all_rows_final': bool(states) and states == [
            game_finality.FINAL_STATUS_STATE
        ],
        'unresolved_resumed_linkage': (
            game_finality.scheduled_rows_have_unresolved_resumed_linkage(rows)
        ),
        'linked_replacement_game_pks': sorted({
            value for row in rows
            for value in (row.resumed_from_game_pk, row.resumed_to_game_pk)
            if value is not None
        }),
        'slate_game_count': len(slate),
        'slate_status_states': {
            str(key): sorted(value) for key, value in sorted(slate.items())
        },
    }


def _row_agreement(rows) -> dict:
    """Governed identity and finality agreement across a game's stored rows.

    Schedule storage is one row per team, so a complete governed reading needs
    an EXACT reciprocal pair. Anything else cannot agree, whatever its fields
    say: a lone row has nothing to be reciprocal with, and three rows for a
    two-team game is an identity conflict on its face. Deriving agreement from
    "no check returned False" would let both of those report full agreement,
    because an unevaluable check returns None rather than False.

    So full agreement requires all three of: the matrix was evaluated, the rows
    are an exact two-team pair, and every governed check is exactly True.

    `created_at`/`updated_at` are deliberately excluded: two rows written
    microseconds apart are a write-ordering artefact, not a baseball identity
    conflict, and counting them would make every game look broken.
    """
    checks: dict[str, bool | None] = {
        field: None for field in audit.ROW_AGREEMENT_FIELDS
    }
    team_ids = [row.team_id for row in rows or ()]
    unique_teams = set(team_ids)

    if not rows:
        return {
            'evaluated': False,
            'row_count': 0,
            'unique_team_count': 0,
            'checks': checks,
            'disagreeing_fields': [],
            'unevaluated_fields': sorted(checks),
            'exact_team_row_pair': False,
            'full_row_governance_agreement': False,
            'pair_shape': audit.ROW_SHAPE_NO_ROWS,
            'timestamps_excluded': ['created_at', 'updated_at'],
        }

    exact_pair = len(rows) == 2 and len(unique_teams) == 2
    if len(rows) == 1:
        shape = audit.ROW_SHAPE_INCOMPLETE_PAIR
    elif len(rows) > 2:
        shape = audit.ROW_SHAPE_TOO_MANY_ROWS
    elif not exact_pair:
        shape = audit.ROW_SHAPE_DUPLICATE_TEAM_ROWS
    else:
        shape = audit.ROW_SHAPE_EXACT_PAIR

    checks['exact_team_row_pair'] = exact_pair
    checks['unique_team_rows'] = len(team_ids) == len(unique_teams)

    if exact_pair:
        first, second = rows
        checks['reciprocal_team_identity'] = (
            first.opponent_team_id == second.team_id
            and second.opponent_team_id == first.team_id
        )
        roles = [first.home_away, second.home_away]
        checks['reciprocal_home_away_roles'] = (
            None if None in roles else set(roles) == {'home', 'away'}
        )
    # Without an exact pair the reciprocal checks stay None, and None is not
    # agreement — it is the absence of a reading.

    def shared(attribute):
        return len({getattr(row, attribute, None) for row in rows}) <= 1

    for field in (
        'game_date', 'status_state', 'status_code', 'game_type',
        'game_number', 'doubleheader', 'resumed_from_game_pk',
        'resumed_to_game_pk', 'source',
    ):
        checks[field] = shared(field)
    checks['original_product_date'] = (
        shared('original_game_date') and shared('original_product_date')
    )

    disagreeing = sorted(
        field for field, value in checks.items() if value is False
    )
    unevaluated = sorted(
        field for field, value in checks.items() if value is None
    )
    return {
        'evaluated': True,
        'row_count': len(rows),
        'unique_team_count': len(unique_teams),
        'checks': checks,
        'disagreeing_fields': disagreeing,
        'unevaluated_fields': unevaluated,
        'exact_team_row_pair': exact_pair,
        'full_row_governance_agreement': (
            exact_pair
            and not disagreeing
            and not unevaluated
        ),
        'pair_shape': shape,
        'timestamps_excluded': ['created_at', 'updated_at'],
    }


def classify_row_shape(agreement) -> str:
    """What the stored rows mean when they are not a clean reciprocal pair."""
    shape = (agreement or {}).get('pair_shape')
    if shape == audit.ROW_SHAPE_NO_ROWS:
        return audit.UNRESOLVED_SCHEDULE_AUTHORITY_MISSING
    if shape in (
        audit.ROW_SHAPE_TOO_MANY_ROWS, audit.ROW_SHAPE_DUPLICATE_TEAM_ROWS,
    ):
        return audit.UNRESOLVED_DOUBLEHEADER_IDENTITY
    return audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT


# ── Stored baseball state (Question 5) ──────────────────────────────────────

def observe_baseball_state(game_pk) -> dict:
    """Every relevant table for the disputed game, read-only."""
    from sqlalchemy import func

    from models.completed_game_context import CompletedGameContext
    from models.game_ingestion_work_item import GameIngestionWorkItem
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from models.play_by_play_foundation import GamePlayByPlayEvent
    from models.postgame_processed_game import PostgameProcessedGame
    from models.sync_failure import SyncFailure
    from models.team_game_pitching_split import TeamGamePitchingSplit
    from utils.db import db

    appearance_rows = int(
        db.session.query(func.count(GameLog.id))
        .filter(GameLog.mlb_game_pk == game_pk).scalar() or 0
    )
    pitcher_ids = sorted({
        mlb_id for (mlb_id,) in (
            db.session.query(Pitcher.mlb_id)
            .join(GameLog, GameLog.pitcher_id == Pitcher.id)
            .filter(GameLog.mlb_game_pk == game_pk).all()
        ) if mlb_id is not None
    })
    # D-008: integer recorded outs are the innings authority. The decimal
    # companion is derived and is never inspected as a baseball fact here.
    recorded_outs = (
        db.session.query(func.sum(GameLog.innings_pitched_outs))
        .filter(GameLog.mlb_game_pk == game_pk).scalar()
    )
    corrections = int(
        db.session.query(func.sum(GameLog.stat_correction_count))
        .filter(GameLog.mlb_game_pk == game_pk).scalar() or 0
    )

    marker = (
        PostgameProcessedGame.query
        .filter(PostgameProcessedGame.mlb_game_pk == game_pk).first()
    )
    work_item = (
        GameIngestionWorkItem.query
        .filter(GameIngestionWorkItem.mlb_game_pk == game_pk).first()
    )
    splits = int(
        db.session.query(func.count(TeamGamePitchingSplit.id))
        .filter(TeamGamePitchingSplit.mlb_game_pk == game_pk).scalar() or 0
    )
    contexts = int(
        db.session.query(func.count(CompletedGameContext.id))
        .filter(CompletedGameContext.game_pk == game_pk).scalar() or 0
    )
    events = int(
        db.session.query(func.count(GamePlayByPlayEvent.id))
        .filter(GamePlayByPlayEvent.mlb_game_pk == game_pk).scalar() or 0
    )
    failures = (
        SyncFailure.query
        .filter(SyncFailure.entity_ref == str(game_pk)).all()
    )

    return {
        'evidence_source': audit.SOURCE_CURRENT_DB,
        'game_logs': _table_state(appearance_rows, {
            'distinct_pitcher_mlb_ids': pitcher_ids,
            'recorded_outs_total': (
                int(recorded_outs) if recorded_outs is not None else None
            ),
            'stat_correction_count_total': corrections,
        }),
        'innings_semantics_note': (
            'innings_pitched_outs is the integer semantic authority; the '
            'decimal companion is derived and is never inspected as a '
            'baseball fact here (D-008).'
        ),
        'correction_provenance_note': (
            'Correction provenance is columnar in this schema, not a separate '
            'table: it lives on game_logs, team_game_pitching_splits, '
            'game_play_by_play_events, and game_ingestion_work_items.'
        ),
        'postgame_processed_game': _table_state(
            0 if marker is None else 1,
            None if marker is None else {
                'processing_status': marker.processing_status,
                'pitching_lines_seen': int(marker.pitching_lines_seen or 0),
                'logs_added': int(marker.logs_added or 0),
                'pitchers_touched': int(marker.pitchers_touched or 0),
                'pitcher_resolution_failures': int(
                    marker.pitcher_resolution_failures or 0
                ),
                'correction_attempts_failed': int(
                    marker.correction_attempts_failed or 0
                ),
                'attempt_count': int(marker.attempt_count or 0),
                'incomplete_reason': marker.incomplete_reason,
                'final_state': marker.final_state,
                'game_date': _iso(marker.game_date),
                'processed_at': _iso(marker.processed_at),
                'failed_at': _iso(marker.failed_at),
            },
        ),
        'game_ingestion_work_item': _table_state(
            0 if work_item is None else 1,
            None if work_item is None else {
                'status': work_item.status,
                'criticality': work_item.criticality,
                'candidate_reason': work_item.candidate_reason,
                'finality_state': work_item.finality_state,
                'represented_date': _iso(work_item.represented_date),
                'attempt_count': int(work_item.attempt_count or 0),
                'rows_expected': work_item.rows_expected,
                'rows_reconciled': int(work_item.rows_reconciled or 0),
                'correction_count': int(work_item.correction_count or 0),
                'error_class': work_item.error_class,
                'source_authority': work_item.source_authority,
                'source_revision_present': bool(work_item.source_revision),
                'completed_at': _iso(work_item.completed_at),
                # completion_proof is deliberately NOT copied: it is a raw
                # proof document and the artifact must not carry it.
                'completion_proof_present': (
                    work_item.completion_proof is not None
                ),
            },
        ),
        'team_game_pitching_splits': _table_state(splits, None),
        'completed_game_contexts': _table_state(contexts, None),
        'game_play_by_play_events': _table_state(events, None),
        'sync_failures': _table_state(len(failures), {
            'unresolved': sum(
                1 for row in failures if not getattr(row, 'resolved', False)
            ),
            'job_names': sorted({
                row.job_name for row in failures if row.job_name
            }),
            # Raw `error` text is never copied: it can carry an exception body.
            'error_text_copied': False,
        }),
    }


def _table_state(row_count, detail) -> dict:
    count = int(row_count or 0)
    return {
        'rows_exist': count > 0,
        'row_count': count,
        'content_state': 'present' if count else 'absent',
        'detail': detail,
    }


# ── Appearance ledger (Question 4) ──────────────────────────────────────────

def observe_appearance_ledger(game_pk, stored_schedule) -> dict:
    """The canonical appearance ledger for the incident slate."""
    from services import appearance_ledger

    ledger = appearance_ledger.build_appearance_ledger(
        end_date=audit.INCIDENT_SLATE_DATE,
    )
    missing = {entry['game_pk'] for entry in ledger['missing_games']}
    deficits = {entry['game_pk'] for entry in ledger['count_deficit_games']}
    incomplete = {
        entry['game_pk'] for entry in ledger['incomplete_marker_games']
    }
    dates = [
        row.get('game_date')
        for row in (stored_schedule or {}).get('rows') or ()
        if row.get('game_date')
    ]
    within = (
        any(
            ledger['window_start'] <= value <= ledger['window_end']
            for value in dates
        ) if dates else None
    )

    return {
        'evidence_source': audit.SOURCE_CURRENT_DB,
        'gate_enabled': appearance_ledger.ledger_gate_enabled(),
        'window_start': ledger['window_start'],
        'window_end': ledger['window_end'],
        'window_days': ledger['window_days'],
        'expected_games': ledger['expected_games'],
        'represented_games': ledger['represented_games'],
        'expected_appearances': ledger['expected_appearances'],
        'stored_appearances': ledger['stored_appearances'],
        'complete': ledger['complete'],
        'reasons': list(ledger['reasons']),
        'missing_game_count': len(missing),
        'count_deficit_game_count': len(deficits),
        'incomplete_marker_game_count': len(incomplete),
        'deficit_game_pks': sorted(missing | deficits | incomplete),
        # Membership itself belongs to services.appearance_ledger. What is
        # recorded here is the two separately derivable facts behind it.
        'disputed_game_in_deficit_set': game_pk in (
            missing | deficits | incomplete
        ),
        'disputed_game_has_stored_final_row': bool(
            (stored_schedule or {}).get('counts_as_ledger_final')
        ),
        'disputed_game_within_window': within,
        'membership_authority': 'services.appearance_ledger',
        'membership_rule': (
            'A game is an expected completed game when ANY stored '
            'scheduled_games row carries status_state=final inside the '
            'trailing window. The planner instead requires EVERY stored row '
            'for the game to agree on final. The two are different tests.'
        ),
    }


# ── Completeness and unresolved-game classification (Question 7) ────────────

def observe_completeness(game_pk, gateway) -> dict:
    """Canonical planner + completeness proof, then per-game classification."""
    from services import game_ingestion_completeness, game_ingestion_planner

    plan = game_ingestion_planner.plan_game_work(audit.INCIDENT_SLATE_DATE)
    completeness = (
        game_ingestion_completeness.build_game_ingestion_completeness(
            audit.INCIDENT_SLATE_DATE, plan=plan,
        )
    )

    excluded_reason = None
    for reason, game_pks in (plan.get('excluded_game_pks') or {}).items():
        if game_pk in set(game_pks or ()):
            excluded_reason = reason
            break

    classification = classify_unresolved_games(plan, completeness, gateway)

    return {
        'evidence_source': audit.SOURCE_CURRENT_DB,
        'plan': {
            'reference_date': plan['reference_date'],
            'window_start': plan['window_start'],
            'games_discovered': plan['games_discovered'],
            'games_planned': plan['games_planned'],
            'excluded_counts': dict(plan['excluded_counts']),
            'finality_conflicts': list(plan['finality_conflicts']),
            'schedule_authority_missing': list(
                plan['schedule_authority_missing']
            ),
            'disputed_game_planned': game_pk in set(plan['planned_game_pks']),
            'disputed_game_exclusion_reason': excluded_reason,
        },
        'completeness': {
            'represented_date': completeness['represented_date'],
            'window_start': completeness['window_start'],
            'horizon_days': completeness['horizon_days'],
            'expected_final_games': completeness['expected_final_games'],
            'completed_final_games': completeness['completed_final_games'],
            'unresolved_final_games': completeness['unresolved_final_games'],
            'terminal_failure_games': completeness['terminal_failure_games'],
            'correction_pending_games': completeness[
                'correction_pending_games'
            ],
            'critical_appearance_rows_expected': completeness[
                'critical_appearance_rows_expected'
            ],
            'critical_appearance_rows_reconciled': completeness[
                'critical_appearance_rows_reconciled'
            ],
            'publication_complete': completeness['publication_complete'],
            'decision_reasons': list(completeness['decision_reasons']),
        },
        'unresolved_classification': classification,
        'completeness_authority': (
            'services.game_ingestion_completeness.'
            'build_game_ingestion_completeness'
        ),
        'membership_authority': (
            'services.game_ingestion_completeness.'
            'unresolved_final_game_membership'
        ),
    }


def classify_unresolved_games(plan, completeness, gateway) -> dict:
    """Classify exactly the games the completeness proof calls unresolved.

    Membership comes from ``unresolved_final_game_membership``, the same
    function the published count is len() of, so the audit cannot classify a
    set the authority never claimed. Every planned critical game is NOT that
    set: the union of outstanding-critical and unresolved work items is
    smaller, and using the planned total instead would inflate the answer.

    Official status for the whole horizon comes from ONE governed schedule
    call, not one per date.
    """
    from sqlalchemy import func

    from models.game_ingestion_work_item import GameIngestionWorkItem
    from models.game_log import GameLog
    from models.scheduled_game import ScheduledGame
    from services import game_ingestion_completeness
    from utils.db import db

    membership = game_ingestion_completeness.unresolved_final_game_membership(
        audit.INCIDENT_SLATE_DATE, plan=plan,
    )
    game_pks = list(membership['game_pks'])
    authority_count = int(completeness['unresolved_final_games'])

    work_items = {
        item.mlb_game_pk: item
        for item in GameIngestionWorkItem.query
        .filter(GameIngestionWorkItem.mlb_game_pk.in_(game_pks)).all()
    } if game_pks else {}

    stored_rows: dict[int, list] = {}
    if game_pks:
        for row in (
            ScheduledGame.query
            .filter(ScheduledGame.game_pk.in_(game_pks)).all()
        ):
            stored_rows.setdefault(row.game_pk, []).append(row)

    row_counts: dict[int, int] = {}
    if game_pks:
        for value, count in (
            db.session.query(GameLog.mlb_game_pk, func.count(GameLog.id))
            .filter(GameLog.mlb_game_pk.in_(game_pks))
            .group_by(GameLog.mlb_game_pk).all()
        ):
            row_counts[value] = int(count or 0)

    official = _official_states(gateway.window_games, set(game_pks))
    schedule_missing = set(plan.get('schedule_authority_missing') or ())

    classified: list[dict] = []
    counts: dict[str, int] = {}
    for value in game_pks:
        entry = _classify_one_unresolved_game(
            value,
            work_item=work_items.get(value),
            rows=stored_rows.get(value) or [],
            stored_row_count=row_counts.get(value, 0),
            official=official.get(value),
            schedule_missing=value in schedule_missing,
        )
        counts[entry['classification']] = counts.get(
            entry['classification'], 0
        ) + 1
        classified.append(entry)

    by_category: dict[str, list[int]] = {}
    for entry in classified:
        by_category.setdefault(entry['classification'], []).append(
            entry['game_pk']
        )

    reconciles = len(classified) == authority_count
    missing_members = [
        value for value in game_pks
        if value not in {entry['game_pk'] for entry in classified}
    ]
    scope_invalid = sum(
        1 for entry in classified
        if entry['classification'] in audit.UNRESOLVED_NON_DEFICIT_CATEGORIES
    )
    # Dates the gate actually reaches for, read from classified games rather
    # than inferred from the fact that a horizon exists at all.
    dates = sorted({
        entry['represented_date'] for entry in classified
        if entry.get('represented_date')
    })
    outside_slate = [
        value for value in dates
        if value != audit.INCIDENT_SLATE_DATE.isoformat()
    ]

    return {
        'evidence_source': audit.SOURCE_INFERENCE,
        'membership_provenance': audit.MEMBERSHIP_CURRENT_RECONSTRUCTION,
        'membership_authority': (
            'services.game_ingestion_completeness.'
            'unresolved_final_game_membership'
        ),
        'membership_note': (
            'Membership is the canonical unresolved set, not every planned '
            'critical game. The retained incident artifacts carry the '
            'unresolved COUNT and not the list, so this set is a CURRENT '
            'reconstruction and is never presented as incident membership.'
        ),
        'incident_reported_count': (
            audit.INCIDENT_COMPLETENESS['unresolved_final_games']
        ),
        'critical_planned_count': len(membership['critical_planned_game_pks']),
        'reconstructed_count': len(classified),
        'authority_unresolved_final_games': authority_count,
        'reconciles_with_authority': reconciles,
        'missing_canonical_members': missing_members,
        'extra_games_beyond_authority': max(
            len(classified) - authority_count, 0
        ),
        'classification_counts': counts,
        'classified_total': sum(counts.values()),
        'category_totals_match': sum(counts.values()) == len(classified),
        'games_by_category': {
            key: sorted(value)[:audit.MAX_REPORTED_GAMES_PER_CATEGORY]
            for key, value in sorted(by_category.items())
        },
        'games': classified[:audit.MAX_REPORTED_GAMES_PER_CATEGORY],
        'represented_dates': dates,
        'dates_outside_incident_slate': outside_slate,
        'scope_valid_count': len(classified) - scope_invalid,
        'scope_invalid_count': scope_invalid,
        'unproven_count': counts.get(audit.UNRESOLVED_UNPROVEN, 0),
        'members_missing_required_official_evidence': sorted(
            entry['game_pk'] for entry in classified
            if entry['category_depends_on_official_evidence']
            and not entry['official_evidence_present']
        ),
        'every_member_classified_once': (
            len({entry['game_pk'] for entry in classified})
            == len(classified) == len(game_pks)
        ),
        'membership_available': True,
        'window_evidence_observed': gateway.window_games is not None,
        'outstanding_required_evidence': sorted(
            gateway.outstanding_evidence()
        ),
        'window_start': membership['window_start'],
        'source_evidence': {
            'window_response_present': gateway.window_games is not None,
            'games_resolved': len(official),
            'games_requested': len(game_pks),
            'required_refusals': len(gateway.state()['required_refusals']),
        },
        'all_classified': len(classified) == sum(counts.values()),
    }


def _official_states(window_games, game_pks) -> dict:
    """Project the one window response onto the games we care about."""
    from services import game_finality

    by_game: dict[int, dict] = {}
    for game in window_games or ():
        value = _int(game.get('gamePk'))
        if value is None or value not in game_pks:
            continue
        decision = game_finality.classify_status(
            game.get('status') or {}, game_pk=value,
        )
        by_game[value] = {
            'classification': _official_class(decision.state),
            'finality_state': decision.state,
            'reason': decision.reason,
            'relationship': _official_relationship(game),
            'doubleheader': _text(game.get('doubleHeader')),
            'game_number': _int(game.get('gameNumber')),
        }
    return by_game


def _classify_one_unresolved_game(
    game_pk, *, work_item, rows, stored_row_count, official, schedule_missing,
) -> dict:
    """One deterministic category per game; first match wins."""
    from models.game_ingestion_work_item import GameIngestionWorkItem
    from services import game_finality

    states = sorted({row.status_state for row in rows})
    stored_final = game_finality.FINAL_STATUS_STATE in states
    all_final = bool(states) and states == [game_finality.FINAL_STATUS_STATE]
    official = official or {}
    official_class = official.get('classification')
    relationship = official.get('relationship') or {}
    expected_rows = int(getattr(work_item, 'rows_expected', 0) or 0)

    if schedule_missing or not rows:
        category = audit.UNRESOLVED_SCHEDULE_AUTHORITY_MISSING
    elif official_class == audit.OFFICIAL_CLASS_POSTPONED:
        category = audit.UNRESOLVED_POSTPONED
    elif official_class == audit.OFFICIAL_CLASS_SUSPENDED:
        category = audit.UNRESOLVED_SUSPENDED
    elif official_class == audit.OFFICIAL_CLASS_CANCELLED:
        category = audit.UNRESOLVED_CANCELLED
    elif relationship.get('is_rescheduled') or relationship.get('is_resumed'):
        category = audit.UNRESOLVED_RESCHEDULED
    elif len(rows) != len({row.team_id for row in rows}):
        category = audit.UNRESOLVED_DOUBLEHEADER_IDENTITY
    elif work_item is not None and work_item.status == (
        GameIngestionWorkItem.STATUS_TERMINAL_FAILURE
    ):
        category = audit.UNRESOLVED_TERMINAL_FAILURE
    elif work_item is not None and work_item.status in (
        GameIngestionWorkItem.UNRESOLVED_STATUSES
    ):
        category = audit.UNRESOLVED_RETRYABLE
    elif official_class is None:
        category = audit.UNRESOLVED_UNPROVEN
    elif official_class == audit.OFFICIAL_CLASS_UNKNOWN:
        category = audit.UNRESOLVED_UNPROVEN
    elif official_class != audit.OFFICIAL_CLASS_FINAL and stored_final:
        category = audit.UNRESOLVED_STORED_FINAL_SOURCE_NON_FINAL
    elif official_class == audit.OFFICIAL_CLASS_FINAL and not all_final:
        category = audit.UNRESOLVED_SOURCE_FINAL_STORED_NON_FINAL
    elif official_class == audit.OFFICIAL_CLASS_FINAL and stored_row_count == 0:
        category = audit.UNRESOLVED_FINAL_MISSING_ROWS
    elif (
        official_class == audit.OFFICIAL_CLASS_FINAL
        and work_item is None
        and stored_row_count > 0
    ):
        # The lane has only ever run in shadow, so it has never created a
        # durable work item. A fully represented final game with no work item
        # is that condition, not a baseball deficit.
        category = audit.UNRESOLVED_WORK_ITEM_ABSENT_SHADOW_ONLY
    elif (
        official_class == audit.OFFICIAL_CLASS_FINAL
        and expected_rows
        and 0 < stored_row_count < expected_rows
    ):
        category = audit.UNRESOLVED_FINAL_PARTIAL
    elif official_class == audit.OFFICIAL_CLASS_FINAL and stored_row_count > 0:
        category = audit.UNRESOLVED_FINAL_FULLY_REPRESENTED
    else:
        category = audit.UNRESOLVED_OTHER

    return {
        'game_pk': game_pk,
        'classification': category,
        'official_classification': official_class,
        'stored_status_states': states,
        'stored_appearance_rows': stored_row_count,
        'rows_expected': expected_rows or None,
        'work_item_status': getattr(work_item, 'status', None),
        'work_item_present': work_item is not None,
        'official_evidence_present': bool(official),
        'category_depends_on_official_evidence': (
            category in audit.OFFICIAL_DEPENDENT_UNRESOLVED_CATEGORIES
        ),
        'represented_date': _iso(getattr(work_item, 'represented_date', None))
        or (rows[0].game_date.isoformat() if rows and rows[0].game_date
            else None),
    }


# ── Player mismatch attribution (Question 6) ────────────────────────────────

def attribute_player_mismatches(ledger_report, ledger_observation, official):
    """Attribute each of the nine reported mismatches individually.

    A player is never attributed to game 822867 merely because the ledger
    listed them in the same report. Attribution to the disputed game requires
    POSITIVE evidence: the player must appear in that game's official box-score
    pitching lines.
    """
    from sqlalchemy import func

    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from utils.db import db

    report = ledger_report if isinstance(ledger_report, dict) else {}
    reported = list(report.get('player_mismatches') or [])
    # The nine incident players are the authority for WHO must be attributed;
    # the parsed artifact is cross-checked against them.
    incident_players = [
        dict(entry) for entry in audit.INCIDENT_PLAYER_MISMATCHES
    ]
    reported_ids = {
        entry.get('player_id') for entry in reported
        if entry.get('player_id') is not None
    }

    disputed_line_ids = set(
        (official or {}).get('boxscore_pitcher_ids') or ()
    )
    disputed_official_class = (official or {}).get('official_classification')

    attributed: list[dict] = []
    counts: dict[str, int] = {}
    for entry in incident_players:
        player_id = entry['player_id']
        pitcher = Pitcher.query.filter_by(mlb_id=player_id).first()

        latest_stored = None
        stored_disputed_rows = 0
        if pitcher is not None:
            latest_stored = (
                db.session.query(func.max(GameLog.game_date))
                .filter(GameLog.pitcher_id == pitcher.id).scalar()
            )
            stored_disputed_rows = int(
                db.session.query(func.count(GameLog.id))
                .filter(GameLog.pitcher_id == pitcher.id)
                .filter(GameLog.mlb_game_pk == audit.INCIDENT_GAME_PK)
                .scalar() or 0
            )

        in_disputed_boxscore = player_id in disputed_line_ids

        if pitcher is None:
            category = audit.PLAYER_CAUSED_BY_IDENTITY_PROBLEM
        elif in_disputed_boxscore and stored_disputed_rows == 0:
            category = audit.PLAYER_CAUSED_BY_DISPUTED_GAME
        elif in_disputed_boxscore and stored_disputed_rows > 0:
            # The row exists now, so the ledger's "missing" reading is a query
            # or timing artefact rather than a baseball gap.
            category = audit.PLAYER_CAUSED_BY_LEDGER_QUERY
        elif disputed_official_class in (
            audit.OFFICIAL_CLASS_POSTPONED, audit.OFFICIAL_CLASS_SUSPENDED,
            audit.OFFICIAL_CLASS_CANCELLED,
        ):
            category = audit.PLAYER_CAUSED_BY_RESCHEDULE_RELATIONSHIP
        elif not disputed_line_ids:
            # Without the disputed game's official pitching lines there is no
            # positive evidence either way. Unproven, never guessed.
            category = audit.PLAYER_UNPROVEN
        elif latest_stored is not None and entry['last_stored_appearance'] and (
            _iso(latest_stored) != entry['last_stored_appearance']
        ):
            category = audit.PLAYER_CAUSED_BY_STALE_DATA
        else:
            category = audit.PLAYER_CAUSED_BY_ANOTHER_GAME

        counts[category] = counts.get(category, 0) + 1
        # `caused_by_another_game` is only positive when the disputed game's
        # lines were actually observed and this player was not in them.
        # Without those lines it is a guess, and the classifier says unproven.
        evidence_positive = (
            category in audit.PLAYER_POSITIVE_EVIDENCE_CLASSIFICATIONS
            and (category != audit.PLAYER_CAUSED_BY_ANOTHER_GAME
                 or bool(disputed_line_ids))
        )
        attributed.append({
            'evidence_positive': evidence_positive,
            'player_id': player_id,
            'name': entry['name'],
            'incident_last_stored_appearance': entry['last_stored_appearance'],
            'current_latest_stored_appearance': _iso(latest_stored),
            'pitcher_tracked': pitcher is not None,
            'in_disputed_game_official_lines': in_disputed_boxscore,
            'stored_rows_for_disputed_game': stored_disputed_rows,
            'expected_source_game_pk': (
                audit.INCIDENT_GAME_PK if in_disputed_boxscore else None
            ),
            'attributable_to_disputed_game': (
                category == audit.PLAYER_CAUSED_BY_DISPUTED_GAME
            ),
            'classification': category,
            'reason_codes': [category],
        })

    return {
        'evidence_source': audit.SOURCE_INFERENCE,
        'incident_reported_count': len(incident_players),
        'artifact_reported_count': len(reported),
        'artifact_ids_match_incident': (
            reported_ids == set(audit.INCIDENT_PLAYER_IDS)
            if reported_ids else None
        ),
        'attributed_count': len(attributed),
        'classification_counts': counts,
        'unproven_count': counts.get(audit.PLAYER_UNPROVEN, 0),
        'attributed_to_disputed_game': counts.get(
            audit.PLAYER_CAUSED_BY_DISPUTED_GAME, 0
        ),
        'classifications_with_positive_evidence': sorted({
            entry['classification'] for entry in attributed
            if entry['evidence_positive']
        }),
        'every_classification_has_positive_evidence': all(
            entry['evidence_positive'] for entry in attributed
        ),
        'players': attributed,
        'all_attributed_exactly_once': (
            len(attributed) == len(audit.INCIDENT_PLAYER_IDS)
            and len({entry['player_id'] for entry in attributed})
            == len(audit.INCIDENT_PLAYER_IDS)
        ),
        'raw_boxscore_excluded': True,
    }


# ── Snapshot publication gate (Question 8) ──────────────────────────────────

def observe_snapshot_gate(sync_summary, completeness, ledger_report=None):
    """Incident snapshot facts and current snapshot facts, kept apart.

    Production has since recovered and serves a newer snapshot. That says
    nothing about whether withholding snapshot 344 during the incident was
    correct, so the incident verdict is derived from the RETAINED publication
    proof and never from today's serving selection.
    """
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from services import dashboard_snapshot as snapshot_service
    from utils.db import db

    candidate = db.session.get(
        DashboardSnapshot, audit.INCIDENT_CANDIDATE_SNAPSHOT_ID
    )
    prior = db.session.get(
        DashboardSnapshot, audit.INCIDENT_SERVING_SNAPSHOT_ID
    )
    served = snapshot_service.get_latest_valid_dashboard_snapshot()
    sync_run = db.session.get(SyncRun, audit.INCIDENT_SYNC_RUN_ID)
    served_id = getattr(served, 'id', None)

    artifact_proof = (
        (sync_summary or {}).get('publication_proof')
        if isinstance(sync_summary, dict) else None
    )
    artifact_proof = artifact_proof if isinstance(artifact_proof, dict) else {}
    incident_reason_codes = list(
        artifact_proof.get('reason_codes')
        or audit.INCIDENT_PUBLICATION_REASON_CODES
    )

    # ── Incident: from retained evidence only ────────────────────────────
    incident_candidate = dict(audit.INCIDENT_SNAPSHOT_CANDIDATE)
    incident_verified = artifact_proof.get('verified')
    incident_withheld = (
        incident_candidate['status'] != snapshot_service.SNAPSHOT_STATUS_READY
        and incident_candidate['is_published'] is False
        and incident_candidate['published_at'] is None
        and incident_verified is not True
        and bool(incident_reason_codes)
        and audit.INCIDENT_SNAPSHOT_SERVED['remained_public'] is True
    )

    # ── Current: today's state, never used to judge the incident ─────────
    current_status = getattr(candidate, 'status', None)
    currently_pending = (
        current_status == snapshot_service.SNAPSHOT_STATUS_PENDING
        if candidate is not None else None
    )
    published_later = (
        bool(getattr(candidate, 'published_at', None))
        if candidate is not None else None
    )
    recovered = (
        served_id is not None
        and served_id != audit.INCIDENT_SERVING_SNAPSHOT_ID
    )

    unresolved = (completeness or {}).get('unresolved_classification') or {}
    blockers = _incident_blocker_set(ledger_report)

    return {
        'evidence_source': audit.SOURCE_INFERENCE,
        'incident': {
            'evidence_source': audit.SOURCE_INCIDENT,
            'incident_candidate_snapshot_id': (
                audit.INCIDENT_CANDIDATE_SNAPSHOT_ID
            ),
            'incident_candidate_status': incident_candidate['status'],
            'incident_candidate_published': incident_candidate['is_published'],
            'incident_served_snapshot_id': audit.INCIDENT_SERVING_SNAPSHOT_ID,
            'incident_publication_proof_status': (
                artifact_proof.get('status')
                if artifact_proof else 'from_immutable_incident_facts'
            ),
            'incident_publication_proof_verified': incident_verified,
            'incident_publication_reason_codes': incident_reason_codes,
            'incident_withholding_was_fail_closed': incident_withheld,
            'derived_from': (
                'retained incident publication proof and immutable incident '
                'snapshot facts, not the current serving selection'
            ),
        },
        'current': {
            'evidence_source': audit.SOURCE_CURRENT_DB,
            'candidate_snapshot_currently_exists': candidate is not None,
            'candidate_current_status': current_status,
            'candidate_currently_published': (
                bool(getattr(candidate, 'is_published', False))
                if candidate is not None else None
            ),
            'candidate_published_later': published_later,
            'candidate_still_pending': currently_pending,
            'current_served_snapshot_id': served_id,
            'current_condition_recovered': recovered,
            'prior_snapshot_still_serving': (
                served_id == audit.INCIDENT_SERVING_SNAPSHOT_ID
            ),
            'candidate_snapshot': _snapshot_view(candidate, snapshot_service),
            'prior_snapshot': _snapshot_view(prior, snapshot_service),
            'sync_run': None if sync_run is None else {
                'id': sync_run.id,
                'job_name': getattr(sync_run, 'job_name', None),
                'status': getattr(sync_run, 'status', None),
                'stage': getattr(sync_run, 'stage', None),
                'published_dashboard_snapshot_id': getattr(
                    sync_run, 'published_dashboard_snapshot_id', None
                ),
            },
            'slate_coverage': _slate_coverage(candidate),
        },
        'gate_scope': {
            'publication_horizon_days': (
                (completeness or {}).get('completeness') or {}
            ).get('horizon_days'),
            # Read from the dates the classified games actually carry, not
            # from the mere existence of a horizon setting.
            'classified_dates': unresolved.get('represented_dates') or [],
            'dates_outside_incident_slate': (
                unresolved.get('dates_outside_incident_slate') or []
            ),
            'requires_games_outside_slate': bool(
                unresolved.get('dates_outside_incident_slate')
            ),
            'unresolved_games_outside_true_deficit': int(
                unresolved.get('scope_invalid_count') or 0
            ),
            'disputed_game_is_sole_blocker': blockers['sole_blocker'],
            'sole_blocker_evidence': blockers,
            # Whether the 60-game signal fed the incident gate has to come
            # from incident evidence. A non-empty CURRENT reconstruction is
            # not proof of what blocked the gate then.
            'sixty_game_signal_contributes': _incident_signal_contribution(
                incident_reason_codes
            ),
        },
        'gate_owner': (
            'services.dashboard_snapshot.publish_dashboard_snapshot decides '
            'publication; services.sync_publication_proof decides whether the '
            "run's candidate is serving. Neither is reimplemented here."
        ),
    }


def _incident_blocker_set(ledger_report) -> dict:
    """Was game 822867 the ONLY thing blocking the incident gate?

    True demands positive evidence that the blocker set is exactly {822867}.
    The incident ledger names one missing game, but the incident completeness
    proof reported 60 unresolved final games and the retained artifacts carry
    that COUNT without the membership. So the exact blocker set is not
    knowable from retained evidence, and the honest answer is unproven —
    not "yes, because the ledger only named one game".
    """
    report = ledger_report if isinstance(ledger_report, dict) else {}
    # `or` would turn an OBSERVED empty blocker list into the incident default
    # and report a sole blocker where there are none. Absent and empty are
    # different observations and must stay that way.
    observed = report.get('missing_game_pks')
    ledger_missing = set(
        observed if observed is not None
        else audit.INCIDENT_LEDGER['missing_game_pks']
    )
    incident_unresolved = int(
        audit.INCIDENT_COMPLETENESS['unresolved_final_games']
    )

    membership_known = incident_unresolved == 0
    if not membership_known:
        sole = 'unproven'
    elif ledger_missing == {audit.INCIDENT_GAME_PK}:
        sole = True
    else:
        sole = False

    return {
        'ledger_missing_game_pks': sorted(ledger_missing),
        'incident_unresolved_final_games': incident_unresolved,
        'exact_blocker_membership_known': membership_known,
        'why_unknown': (
            None if membership_known else
            'the incident completeness proof reported '
            f'{incident_unresolved} unresolved final games and the retained '
            'artifacts carry the count, not the membership'
        ),
        'sole_blocker': sole,
    }


def _incident_signal_contribution(reason_codes):
    """Did the unresolved-final-game signal reach the incident snapshot gate?"""
    codes = set(reason_codes or ())
    if audit.REASON_UNRESOLVED_FINAL_GAMES_CODE in codes:
        return True
    # The retained publication proof names slate coverage and candidate
    # readiness. It does not name the unresolved-final-game signal, so whether
    # that signal fed this gate is not established by the evidence we hold.
    return 'unproven'



def _slate_coverage(snapshot) -> dict | None:
    payload = getattr(snapshot, 'payload', None)
    if not isinstance(payload, dict):
        return None
    freshness = payload.get('freshness')
    if not isinstance(freshness, dict):
        return None
    coverage = freshness.get('slate_coverage')
    if not isinstance(coverage, dict):
        return None
    return {
        'slate_date': coverage.get('slate_date'),
        'coverage_known': coverage.get('coverage_known'),
        'games_scheduled': coverage.get('games_scheduled'),
        'games_final': coverage.get('games_final'),
        'games_fully_ingested': coverage.get('games_fully_ingested'),
        'validations_passed': coverage.get('validations_passed'),
        'complete_enough_to_publish': coverage.get(
            'complete_enough_to_publish'
        ),
        'reason_codes': list(coverage.get('reason_codes') or ()),
        'marker_counts': coverage.get('marker_counts'),
    }


def _snapshot_view(snapshot, snapshot_service) -> dict | None:
    if snapshot is None:
        return None
    return {
        'id': snapshot.id,
        'status': snapshot.status,
        'is_published': bool(getattr(snapshot, 'is_published', False)),
        'published_at': _iso(getattr(snapshot, 'published_at', None)),
        'data_through': _iso(getattr(snapshot, 'data_through', None)),
        'availability_reference_date': _iso(
            getattr(snapshot, 'availability_reference_date', None)
        ),
        'sync_run_id': getattr(snapshot, 'sync_run_id', None),
        'error_message': getattr(snapshot, 'error_message', None),
        'unavailable_reason': snapshot_service.snapshot_unavailable_reason(
            snapshot
        ),
    }


def observe_unresolved_sync_failures() -> dict:
    """Observed dead-letter backlog. Reported, never asserted as zero."""
    from sqlalchemy import func

    from models.sync_failure import SyncFailure
    from utils.db import db

    try:
        total = (
            db.session.query(func.count(SyncFailure.id))
            .filter(SyncFailure.resolved.is_(False)).scalar()
        )
    except Exception:  # noqa: BLE001 - an unobserved backlog is not zero
        return {
            'observed': False, 'unresolved_sync_failures': None,
            'governed_backlog': audit.GOVERNED_DEAD_LETTER_BACKLOG,
            'note': audit.DEAD_LETTER_BACKLOG_NOTE,
            'dead_letters_created_by_this_audit': 0,
        }
    return {
        'observed': True,
        'unresolved_sync_failures': int(total or 0),
        'governed_backlog': audit.GOVERNED_DEAD_LETTER_BACKLOG,
        'note': audit.DEAD_LETTER_BACKLOG_NOTE,
        'dead_letters_created_by_this_audit': 0,
    }


# ── Authority comparison ────────────────────────────────────────────────────

def build_authority_comparison(observations) -> dict:
    """Where the four authorities disagree, stated explicitly."""
    official = observations.get('official_status') or {}
    stored = observations.get('stored_schedule') or {}
    ledger = observations.get('appearance_ledger') or {}
    completeness = observations.get('completeness') or {}
    plan = completeness.get('plan') or {}

    official_class = official.get('official_classification')
    mapped = official.get('canonical_status_state')
    stored_state = stored.get('stored_status_state')
    ledger_counts = ledger.get('disputed_game_has_stored_final_row')

    # A plan that was never observed is not a plan that excluded the game.
    # The first production run stopped before completeness and still reported
    # planner_classification 'excluded' with a null reason, which reads as a
    # finding about the planner when it is only an absence of evidence about
    # it. Absence is its own answer here, and it is UNPROVEN.
    planner_observed = 'disputed_game_planned' in plan
    planner_planned = plan.get('disputed_game_planned')
    if not planner_observed or planner_planned is None:
        planner_classification = audit.PLANNER_CLASS_UNPROVEN
    elif planner_planned:
        planner_classification = audit.PLANNER_CLASS_PLANNED
    else:
        planner_classification = audit.PLANNER_CLASS_EXCLUDED

    disagreements = []
    if official.get('game_found_in_source') and mapped and stored_state and (
        mapped != stored_state
    ):
        disagreements.append('current_mapping_differs_from_stored_state')
    if ledger_counts and planner_planned is False:
        disagreements.append('ledger_counts_game_planner_cannot_plan')
    if official_class == audit.OFFICIAL_CLASS_FINAL and stored_state and (
        stored_state != 'final'
    ):
        disagreements.append('official_final_but_stored_not_final')
    if official_class in (
        audit.OFFICIAL_CLASS_POSTPONED, audit.OFFICIAL_CLASS_SUSPENDED,
        audit.OFFICIAL_CLASS_CANCELLED,
    ) and ledger_counts:
        disagreements.append('official_non_final_but_ledger_counts_completed')
    if stored.get('paired_row_disagreement'):
        disagreements.append('paired_schedule_rows_disagree')

    return {
        'evidence_source': audit.SOURCE_INFERENCE,
        'official_source_classification': official_class,
        'schedule_parser_classification': official.get(
            'canonical_finality_state'
        ),
        'canonical_mapped_status_state': mapped,
        'stored_schedule_classification': stored_state,
        'stored_status_states': stored.get('distinct_status_states'),
        'planner_classification': planner_classification,
        'planner_evidence_observed': planner_observed,
        # An exclusion reason is only meaningful once an exclusion is proven.
        'planner_exclusion_reason': (
            plan.get('disputed_game_exclusion_reason')
            if planner_classification == audit.PLANNER_CLASS_EXCLUDED
            else None
        ),
        'appearance_ledger_classification': (
            'counted_as_completed_game' if ledger_counts
            else 'not_counted'
        ),
        'incident_preflight_status_state': (
            audit.INCIDENT_PREFLIGHT_STATUS_STATES.get(audit.INCIDENT_GAME_PK)
        ),
        'exact_disagreements': disagreements,
        'any_disagreement': bool(disagreements),
    }


# ── Findings ────────────────────────────────────────────────────────────────

def build_findings(observations, comparison, module_drift) -> list[dict]:
    """Positive-evidence findings. Nothing is concluded from an absence."""
    official = observations.get('official_status') or {}
    stored = observations.get('stored_schedule') or {}
    ledger = observations.get('appearance_ledger') or {}
    baseball = observations.get('baseball_state') or {}
    completeness = observations.get('completeness') or {}
    snapshot = observations.get('snapshot_gate') or {}
    plan = completeness.get('plan') or {}
    unresolved = completeness.get('unresolved_classification') or {}

    official_class = official.get('official_classification')
    observed = bool(official.get('game_found_in_source'))
    stored_state = stored.get('stored_status_state')
    rows = int(
        ((baseball.get('game_logs') or {}).get('row_count')) or 0
    )
    findings: list[dict] = []

    # 1. Paired/duplicate schedule rows disagree.
    findings.append(_finding(
        audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT,
        proven=bool(
            stored.get('paired_row_disagreement')
            or stored.get('duplicate_team_rows')
        ),
        supporting=_present([
            f"governed fields disagree across the stored rows: "
            f"{stored.get('disagreeing_fields')}"
            if stored.get('disagreeing_fields') else None,
            'duplicate team rows for one game'
            if stored.get('duplicate_team_rows') else None,
        ]),
        counter=_present([
            'every governed identity and finality field agrees across the '
            'stored rows' if stored.get(
                'full_row_governance_agreement'
            ) else None,
            f"row count {stored.get('row_count')}",
            'timestamps are excluded from the agreement matrix by design',
        ]),
        confidence=audit.CONFIDENCE_HIGH,
        sources=[audit.SOURCE_CURRENT_DB],
        persists=bool(stored.get('paired_row_disagreement')),
    ))

    # 2. Reschedule / suspension identity conflated.
    relationship = official.get('relationship') or {}
    findings.append(_finding(
        audit.CLASSIFICATION_RESCHEDULE_OR_SUSPENSION_IDENTITY_DEFECT,
        proven=bool(
            observed
            and (relationship.get('is_rescheduled')
                 or relationship.get('is_resumed'))
            and stored.get('linked_replacement_game_pks') == []
        ),
        supporting=_present([
            'official record carries a reschedule/resume relationship'
            if relationship.get('is_rescheduled')
            or relationship.get('is_resumed') else None,
            'stored schedule carries no linked replacement game'
            if stored.get('linked_replacement_game_pks') == [] else None,
        ]),
        counter=_present([
            f"stored linked games "
            f"{stored.get('linked_replacement_game_pks')}"
            if stored.get('linked_replacement_game_pks') else None,
            'official record carries no reschedule or resume relationship'
            if observed and not (relationship.get('is_rescheduled')
                                 or relationship.get('is_resumed')) else None,
            'official record not observed' if not observed else None,
        ]),
        confidence=audit.CONFIDENCE_MEDIUM,
        sources=[audit.SOURCE_OFFICIAL, audit.SOURCE_CURRENT_DB],
        persists=bool(
            relationship.get('is_rescheduled')
            or relationship.get('is_resumed')
        ),
    ))

    # 3. Ledger counted a game the official source says is not final.
    ledger_counts = bool(ledger.get('disputed_game_has_stored_final_row'))
    non_final = official_class in (
        audit.OFFICIAL_CLASS_POSTPONED, audit.OFFICIAL_CLASS_SUSPENDED,
        audit.OFFICIAL_CLASS_CANCELLED, audit.OFFICIAL_CLASS_NON_FINAL,
    )
    findings.append(_finding(
        audit.CLASSIFICATION_APPEARANCE_LEDGER_COMPLETION_AUTHORITY_DEFECT,
        proven=bool(observed and non_final and ledger_counts),
        supporting=_present([
            f'official classification {official_class}' if non_final else None,
            'a stored schedule row carries status_state=final, which is what '
            'puts the game into ledger membership' if ledger_counts else None,
        ]),
        counter=_present([
            f'official classification {official_class}'
            if official_class == audit.OFFICIAL_CLASS_FINAL else None,
            'no stored row carries final' if not ledger_counts else None,
            'official record not observed' if not observed else None,
        ]),
        confidence=(
            audit.CONFIDENCE_HIGH if observed else audit.CONFIDENCE_LOW
        ),
        sources=[audit.SOURCE_OFFICIAL, audit.SOURCE_CURRENT_DB],
        persists=bool(non_final and ledger_counts),
    ))

    # 4. Official proves final, stored/planner authority did not follow.
    mapping_drift = bool(
        observed
        and official_class == audit.OFFICIAL_CLASS_FINAL
        and (stored_state != 'final'
             or plan.get('disputed_game_planned') is False)
    )
    findings.append(_finding(
        audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT,
        proven=mapping_drift,
        supporting=_present([
            'official source classifies the game final'
            if official_class == audit.OFFICIAL_CLASS_FINAL else None,
            f'stored schedule state is {stored_state!r}'
            if stored_state != 'final' else None,
            'the canonical planner could not plan the game'
            if plan.get('disputed_game_planned') is False else None,
        ]),
        counter=_present([
            f'canonical mapper currently returns '
            f"{official.get('canonical_status_state')!r} for the observed "
            f'official status',
            'canonical modules are byte-identical to the incident SHA'
            if module_drift and not module_drift.get(
                'any_change_since_incident'
            ) else None,
            'official record not observed' if not observed else None,
        ]),
        confidence=(
            audit.CONFIDENCE_HIGH if observed else audit.CONFIDENCE_LOW
        ),
        sources=[audit.SOURCE_OFFICIAL, audit.SOURCE_CURRENT_DB],
        persists=mapping_drift,
    ))

    # 5. Rows exist but the ledger still reports the game absent.
    query_defect = bool(
        rows > 0 and ledger.get('disputed_game_in_deficit_set')
    )
    findings.append(_finding(
        audit.CLASSIFICATION_APPEARANCE_LEDGER_QUERY_DEFECT,
        proven=query_defect,
        supporting=_present([
            f'{rows} appearance row(s) exist for the game' if rows else None,
            'the canonical ledger still names the game in a deficit list'
            if ledger.get('disputed_game_in_deficit_set') else None,
        ]),
        counter=_present([
            'no appearance rows exist for the game' if rows == 0 else None,
            'the ledger does not name the game in any deficit list'
            if not ledger.get('disputed_game_in_deficit_set') else None,
        ]),
        confidence=audit.CONFIDENCE_HIGH,
        sources=[audit.SOURCE_CURRENT_DB],
        persists=query_defect,
    ))

    # 6. Both authorities say final and the rows are genuinely missing.
    ingestion_gap = bool(
        observed
        and official_class == audit.OFFICIAL_CLASS_FINAL
        and stored.get('all_rows_final')
        and rows == 0
    )
    findings.append(_finding(
        audit.CLASSIFICATION_EXACT_GAME_INGESTION_GAP,
        proven=ingestion_gap,
        supporting=_present([
            'official source classifies the game final'
            if official_class == audit.OFFICIAL_CLASS_FINAL else None,
            'every stored schedule row agrees on final'
            if stored.get('all_rows_final') else None,
            'zero appearance rows are stored' if rows == 0 else None,
        ]),
        counter=_present([
            f'{rows} appearance row(s) already exist' if rows else None,
            'stored rows do not all agree on final'
            if not stored.get('all_rows_final') else None,
        ]),
        confidence=audit.CONFIDENCE_HIGH,
        sources=[audit.SOURCE_OFFICIAL, audit.SOURCE_CURRENT_DB],
        persists=ingestion_gap,
        genuine_source_gap=ingestion_gap,
    ))

    # 7. The gate requires games outside valid postgame publication scope.
    scope_invalid = int(unresolved.get('scope_invalid_count') or 0)
    scope_defect = bool(
        scope_invalid > 0
        and unresolved.get('reconciles_with_authority') is True
    )
    findings.append(_finding(
        audit.CLASSIFICATION_PUBLICATION_GATE_SCOPE_DEFECT,
        proven=scope_defect,
        supporting=_present([
            f'{scope_invalid} unresolved game(s) fall into categories that '
            f'are not a true final-game deficit' if scope_invalid else None,
            'the reconstruction reconciles with the completeness authority'
            if unresolved.get('reconciles_with_authority') else None,
        ]),
        counter=_present([
            'every unresolved game is a genuine final-game deficit'
            if scope_invalid == 0 else None,
            'the reconstruction does not reconcile with the authority count'
            if unresolved.get('reconciles_with_authority') is False else None,
        ]),
        confidence=audit.CONFIDENCE_MEDIUM,
        sources=[audit.SOURCE_CURRENT_DB, audit.SOURCE_INFERENCE],
        persists=scope_defect,
    ))

    # 8. Coverage complete yet the candidate stayed pending.
    current = snapshot.get('current') or {}
    coverage = current.get('slate_coverage') or {}
    transition_defect = bool(
        coverage.get('complete_enough_to_publish') is True
        and coverage.get('validations_passed') is True
        and current.get('candidate_still_pending') is True
    )
    findings.append(_finding(
        audit.CLASSIFICATION_SNAPSHOT_STATE_TRANSITION_DEFECT,
        proven=transition_defect,
        supporting=_present([
            'slate coverage reports complete_enough_to_publish'
            if coverage.get('complete_enough_to_publish') else None,
            'the candidate snapshot is still pending'
            if current.get('candidate_still_pending') else None,
        ]),
        counter=_present([
            f"slate coverage reason codes {coverage.get('reason_codes')}"
            if coverage.get('reason_codes') else None,
            'slate coverage is not complete enough to publish'
            if coverage.get('complete_enough_to_publish') is not True
            else None,
        ]),
        confidence=audit.CONFIDENCE_MEDIUM,
        sources=[audit.SOURCE_CURRENT_DB],
        persists=transition_defect,
    ))

    return findings


def _finding(classification, *, proven, supporting, counter, confidence,
             sources, persists, genuine_source_gap=False) -> dict:
    return {
        'classification': classification,
        'proven': bool(proven),
        'confidence': confidence,
        'supporting_evidence': list(supporting),
        'counter_evidence': list(counter),
        'evidence_sources': list(sources),
        'current_condition_persists': bool(persists),
        'genuine_source_gap': bool(genuine_source_gap),
    }


def _present(values) -> list[str]:
    return [str(value) for value in values if value]


# ── Questions ───────────────────────────────────────────────────────────────

def build_questions(observations, comparison, module_drift,
                    incident_mapping=None) -> list[dict]:
    official = observations.get('official_status') or {}
    stored = observations.get('stored_schedule') or {}
    baseball = observations.get('baseball_state') or {}
    ledger = observations.get('appearance_ledger') or {}
    completeness = observations.get('completeness') or {}
    players = observations.get('player_mismatches') or {}
    snapshot = observations.get('snapshot_gate') or {}
    unresolved = completeness.get('unresolved_classification') or {}

    questions = []

    observed = bool(official.get('game_found_in_source'))
    questions.append(_question(
        audit.QUESTION_OFFICIAL_STATUS, answered=observed,
        answer=(
            f"MLB reports detailed_state "
            f"{official['normalized'].get('detailed_state')!r}, status_code "
            f"{official['normalized'].get('status_code')!r}; the canonical "
            f"finality authority classifies it "
            f"{official.get('canonical_finality_state')!r} "
            f"({official.get('canonical_finality_reason')!r}), which this "
            f"audit records as official classification "
            f"{official.get('official_classification')!r}."
            if observed else
            'The official record was not observed within the source-call '
            'budget, so the official status is unproven.'
        ),
        evidence={
            'official': official,
            'authority': 'services.game_finality.classify_status',
        },
        unproven_reason=None if observed else 'official_record_not_observed',
    ))

    has_rows = int(stored.get('row_count') or 0) > 0
    questions.append(_question(
        audit.QUESTION_STORED_SCHEDULE_STATE, answered=has_rows,
        answer=(
            f"{stored.get('row_count')} stored schedule row(s) carry "
            f"status_state(s) {stored.get('distinct_status_states')} for "
            f"team(s) {stored.get('team_ids')}; the rows "
            f"{'agree' if stored.get('rows_agree') else 'DISAGREE'}. "
            f"Linked replacement games: "
            f"{stored.get('linked_replacement_game_pks')}."
            if has_rows else
            'No stored schedule rows exist for the game.'
        ),
        evidence={'stored_schedule': stored},
        unproven_reason=None if has_rows else 'no_stored_schedule_rows',
    ))

    mapped = official.get('canonical_status_state')
    incident_state = audit.INCIDENT_PREFLIGHT_STATUS_STATES.get(
        audit.INCIDENT_GAME_PK
    )
    # Question 3 asks why the INCIDENT produced 'other'. Only the incident's
    # own mapping input can answer that. Observing today's official record
    # establishes what the game maps to NOW; when that differs from 'other'
    # it shows the input has changed, which is the opposite of an explanation.
    # The question is therefore answered only on a positive reconstruction of
    # the incident-time mapping input, never on current non-reproduction.
    reconstruction = incident_mapping or audit.incident_mapping_input(None)
    input_recovered = bool(reconstruction.get('input_recovered'))
    incident_reproduced = reconstruction.get('reproduces_incident_state')
    q3_answered = bool(input_recovered and incident_reproduced)
    current_reproduces = mapped is not None and mapped == incident_state
    questions.append(_question(
        audit.QUESTION_PREFLIGHT_PRODUCED_OTHER, answered=q3_answered,
        answer=(
            f"The incident-time status payload was recovered and re-mapped "
            f"through game_finality.normalize_schedule_status_state, which "
            f"returns {reconstruction.get('remapped_status_state')!r} and "
            f"reproduces the incident's {incident_state!r}. 'other' is the "
            f"state the authority uses for cancelled, live/in-progress, "
            f"abstract-final-without-final-status, and unknown status. "
            f"Canonical modules changed since the incident SHA: "
            f"{module_drift.get('any_change_since_incident')}."
            if q3_answered else
            'The incident-time mapping input was not reconstructed, so why '
            'the preflight produced "other" is unproven. The currently '
            f"observed official status maps to {mapped!r}, which is a fact "
            'about today and not about the incident: a current result that '
            "does not reproduce 'other' shows the input changed, and does "
            'not explain the original mapping.'
        ),
        evidence={
            'incident_mapping_reconstruction': reconstruction,
            'incident_mapping_input_recovered': input_recovered,
            'incident_preflight_status_state': incident_state,
            'incident_mapping_reproduced': incident_reproduced,
            # Kept, clearly labelled, and explicitly NOT the answer.
            'current_mapped_status_state': mapped,
            'current_result_reproduces_incident': current_reproduces,
            'current_observation_is_not_an_incident_explanation': True,
            'incident_reconstructible_from_artifacts': input_recovered,
            'canonical_module_drift': module_drift,
            'authority': (
                'services.game_finality.normalize_schedule_status_state'
            ),
        },
        unproven_reason=(
            None if q3_answered
            else audit.MAPPING_INPUT_NOT_RECONSTRUCTED
        ),
    ))

    plan = completeness.get('plan') or {}
    # Question 4 contrasts the ledger against the planner, so it needs BOTH.
    # A plan that was never observed cannot be reported as one that excluded
    # the game: absent planner evidence is unproven, never 'excluded'.
    planner_classification = comparison.get('planner_classification')
    planner_observed = (
        planner_classification is not None
        and planner_classification != audit.PLANNER_CLASS_UNPROVEN
    )
    ledger_answered = bool(ledger) and planner_observed
    questions.append(_question(
        audit.QUESTION_LEDGER_COUNTED_COMPLETED, answered=ledger_answered,
        answer=(
            f"{ledger.get('membership_rule')} The disputed game "
            f"{'has' if ledger.get('disputed_game_has_stored_final_row') else 'does not have'}"
            f" a stored final row, and the canonical planner "
            f"{planner_classification}"
            f" it (exclusion reason "
            f"{comparison.get('planner_exclusion_reason')!r}). "
            f"Ledger reasons: {ledger.get('reasons')}."
            if ledger_answered else
            'The appearance ledger could not be computed.'
            if not ledger else
            'The canonical plan was not observed, so how the planner treated '
            'the disputed game is unproven. An unobserved plan is not an '
            'exclusion, and the ledger/planner contrast this question asks '
            'for cannot be drawn from one side alone.'
        ),
        evidence={
            'appearance_ledger': ledger,
            'planner': plan,
            'planner_classification': planner_classification,
            'planner_evidence_observed': planner_observed,
            'authority': 'services.appearance_ledger.build_appearance_ledger',
        },
        unproven_reason=(
            None if ledger_answered
            else 'appearance_ledger_unavailable' if not ledger
            else 'planner_evidence_not_observed'
        ),
    ))

    questions.append(_question(
        audit.QUESTION_EXACT_BASEBALL_STATE, answered=bool(baseball),
        answer=(
            f"game_logs {(baseball.get('game_logs') or {}).get('row_count')}, "
            f"postgame marker "
            f"{(baseball.get('postgame_processed_game') or {}).get('row_count')}, "
            f"work item "
            f"{(baseball.get('game_ingestion_work_item') or {}).get('row_count')}, "
            f"team splits "
            f"{(baseball.get('team_game_pitching_splits') or {}).get('row_count')}, "
            f"completed-game contexts "
            f"{(baseball.get('completed_game_contexts') or {}).get('row_count')}, "
            f"play-by-play "
            f"{(baseball.get('game_play_by_play_events') or {}).get('row_count')}, "
            f"sync failures "
            f"{(baseball.get('sync_failures') or {}).get('row_count')}."
            if baseball else 'Stored baseball state could not be read.'
        ),
        evidence={'baseball_state': baseball},
        unproven_reason=None if baseball else 'baseball_state_unavailable',
    ))

    # Q6 is answered only on positive evidence for every one of the nine. A
    # failed box score, an unusable response, or failed line extraction leaves
    # attribution without the thing it attributes FROM.
    official_class = official.get('official_classification')
    relationship = official.get('relationship') or {}
    if official_class == audit.OFFICIAL_CLASS_FINAL:
        source_evidence_ok = bool(
            official.get('boxscore_observed')
            and not official.get('pitching_line_extraction_failed')
        )
    elif official_class in (
        audit.OFFICIAL_CLASS_POSTPONED, audit.OFFICIAL_CLASS_SUSPENDED,
        audit.OFFICIAL_CLASS_CANCELLED,
    ):
        # A non-final classification needs the official relationship to be
        # resolved, not merely absent.
        source_evidence_ok = bool(relationship.get('resolved'))
    else:
        source_evidence_ok = False

    player_conditions = {
        'all_nine_attributed_exactly_once': bool(
            players.get('all_attributed_exactly_once')
        ),
        'artifact_ids_match_incident': (
            players.get('artifact_ids_match_incident') is True
        ),
        'zero_unproven_players': players.get('unproven_count') == 0,
        'every_classification_has_positive_evidence': bool(
            players.get('every_classification_has_positive_evidence')
        ),
        'required_source_evidence_observed': source_evidence_ok,
    }
    players_answered = all(player_conditions.values())
    questions.append(_question(
        audit.QUESTION_PLAYER_MISMATCH_ATTRIBUTION, answered=players_answered,
        answer=(
            f"All {players.get('attributed_count')} reported mismatches "
            f"attributed individually: "
            f"{players.get('classification_counts')}. Attributed to game "
            f"{audit.INCIDENT_GAME_PK} on positive box-score evidence: "
            f"{players.get('attributed_to_disputed_game')}."
            if players_answered else
            'The nine reported mismatches were not each attributed exactly '
            'once, so the attribution is incomplete.'
        ),
        evidence={
            'player_mismatches': players,
            'completion_conditions': player_conditions,
            'unmet_conditions': sorted(
                key for key, value in player_conditions.items() if not value
            ),
        },
        unproven_reason=(
            None if players_answered
            else audit.UNPROVEN_PLAYER_EVIDENCE_INCOMPLETE
        ),
    ))

    # Classifying a set the authority never claimed is not an answer, and
    # neither is classifying it without the evidence the categories rest on.
    unresolved_conditions = {
        'canonical_membership_available': bool(
            unresolved.get('membership_available')
        ),
        'reconciles_with_authority': (
            unresolved.get('reconciles_with_authority') is True
        ),
        'no_missing_canonical_members': not unresolved.get(
            'missing_canonical_members'
        ),
        'no_extra_games': not unresolved.get('extra_games_beyond_authority'),
        'category_totals_match': bool(
            unresolved.get('category_totals_match')
        ),
        'every_member_classified_once': bool(
            unresolved.get('every_member_classified_once')
        ),
        'zero_unproven_games': unresolved.get('unproven_count') == 0,
        'official_window_evidence_observed': bool(
            unresolved.get('window_evidence_observed')
        ),
        'official_evidence_for_every_dependent_member': not unresolved.get(
            'members_missing_required_official_evidence'
        ),
        'no_unrecovered_required_source_failure': not unresolved.get(
            'outstanding_required_evidence'
        ),
    }
    unresolved_answered = all(unresolved_conditions.values())
    questions.append(_question(
        audit.QUESTION_UNRESOLVED_GAME_CLASSIFICATION,
        answered=unresolved_answered,
        answer=(
            f"{unresolved.get('reconstructed_count')} unresolved final "
            f"game(s) classified as {unresolved.get('classification_counts')} "
            f"({unresolved.get('membership_provenance')}). The completeness "
            f"authority counts "
            f"{unresolved.get('authority_unresolved_final_games')}; the "
            f"reconstruction reconciles: "
            f"{unresolved.get('reconciles_with_authority')}. Incident "
            f"reported {unresolved.get('incident_reported_count')}."
            if unresolved_answered else
            'The unresolved-game set could not be classified completely.'
        ),
        evidence={
            'unresolved_classification': unresolved,
            'completeness': completeness.get('completeness'),
            'authority': completeness.get('completeness_authority'),
            'completion_conditions': unresolved_conditions,
            'unmet_conditions': sorted(
                key for key, value in unresolved_conditions.items()
                if not value
            ),
        },
        unproven_reason=(
            None if unresolved_answered
            else (
                'unresolved_membership_does_not_reconcile_with_authority'
                if unresolved.get('reconciles_with_authority') is False
                else audit.UNPROVEN_UNRESOLVED_EVIDENCE_INCOMPLETE
            )
        ),
    ))

    incident_block = snapshot.get('incident') or {}
    current_block = snapshot.get('current') or {}
    scope_block = snapshot.get('gate_scope') or {}
    candidate = current_block.get('candidate_snapshot') or {}

    # Question 8 asks five things. Having the blocks is not having the
    # answers: an explicit `unproven` value is a recorded absence of a
    # conclusion, and labelling that "answered" is exactly the failure the
    # whole result contract exists to prevent.
    snapshot_conditions = {
        'incident_candidate_state_known': bool(
            incident_block.get('incident_candidate_status')
        ),
        'incident_served_snapshot_known': (
            incident_block.get('incident_served_snapshot_id') is not None
        ),
        'incident_publication_proof_known': bool(
            incident_block.get('incident_publication_reason_codes')
        ),
        'sync_run_known': current_block.get('sync_run') is not None,
        'incident_withholding_judgment_known': isinstance(
            incident_block.get('incident_withholding_was_fail_closed'), bool
        ),
        'sole_blocker_is_boolean': isinstance(
            scope_block.get('disputed_game_is_sole_blocker'), bool
        ),
        'sixty_game_contribution_is_boolean': isinstance(
            scope_block.get('sixty_game_signal_contributes'), bool
        ),
        'gate_scope_conclusion_known': isinstance(
            scope_block.get('requires_games_outside_slate'), bool
        ),
    }
    snapshot_answered = all(snapshot_conditions.values())
    questions.append(_question(
        audit.QUESTION_SNAPSHOT_GATE, answered=snapshot_answered,
        answer=(
            f"AT THE INCIDENT: candidate "
            f"{incident_block.get('incident_candidate_snapshot_id')} was "
            f"{incident_block.get('incident_candidate_status')} and "
            f"unpublished while "
            f"{incident_block.get('incident_served_snapshot_id')} kept "
            f"serving, for reason codes "
            f"{incident_block.get('incident_publication_reason_codes')}; "
            f"withholding was fail-closed: "
            f"{incident_block.get('incident_withholding_was_fail_closed')}. "
            f"NOW: the candidate is {current_block.get('candidate_current_status')}, "
            f"published_later="
            f"{current_block.get('candidate_published_later')}, and the "
            f"snapshot currently serving is "
            f"{current_block.get('current_served_snapshot_id')} "
            f"(condition recovered: "
            f"{current_block.get('current_condition_recovered')}). Today's "
            f"serving selection does not change the incident verdict. "
            f"Disputed game the sole blocker: "
            f"{(snapshot.get('gate_scope') or {}).get('disputed_game_is_sole_blocker')}."
            if snapshot_answered else
            'Snapshot gate evidence could not be read.'
        ),
        evidence={
            'snapshot_gate': snapshot,
            'completion_conditions': snapshot_conditions,
            'unmet_conditions': sorted(
                key for key, value in snapshot_conditions.items()
                if not value
            ),
        },
        unproven_reason=(
            None if snapshot_answered
            else (
                audit.UNPROVEN_SNAPSHOT_GATE_INCOMPLETE
                if incident_block or current_block
                else audit.UNPROVEN_SNAPSHOT_EVIDENCE_MISSING
            )
        ),
    ))

    return questions


def _question(question_id, *, answered, answer, evidence, unproven_reason):
    return {
        'question_id': question_id,
        'question': audit.QUESTION_TEXT[question_id],
        'answered': bool(answered),
        'answer': answer,
        'evidence': evidence,
        'unproven_reason': unproven_reason,
    }


# ── Orchestration ───────────────────────────────────────────────────────────

def run(args) -> dict:
    context = event_context(args)
    note = qualification.sanitize_note(args.operator_note)
    budget = audit.SourceCallBudget()
    gateway = SourceGateway(budget)
    module_drift = audit.canonical_module_drift(current_module_digests())

    failures = validate_authorization(context)
    if failures:
        return build_document(
            context=context, note=note, observations={}, questions=[],
            comparison={}, module_drift=module_drift, read_only={},
            artifact_ingestion={}, budget_state=budget.state(),
            decision=_refuse(failed=(
                [audit.FAILED_UNAUTHORIZED_INVOCATION] + failures
            )),
        )

    ingestion = audit.ingest_incident_artifacts(
        args.evidence_dir,
        observed_metadata=load_observed_artifact_metadata(args.evidence_dir),
    )
    shadow = (ingestion.get('artifacts') or {}).get(audit.ARTIFACT_SHADOW) or {}
    ledger_artifact = (
        (ingestion.get('artifacts') or {}).get(audit.ARTIFACT_LEDGER_AUDIT)
        or {}
    )

    identity_failures = audit.validate_incident_scope(
        run_id=audit.INCIDENT_RUN_ID,
        cycle=audit.INCIDENT_CYCLE,
        slate_date=audit.INCIDENT_SLATE_DATE,
        game_pk=audit.INCIDENT_GAME_PK,
        head_sha=audit.INCIDENT_HEAD_SHA,
    )

    flask_app = build_app()

    from services import game_ingestion_planner
    from services import sync_metadata
    from utils.db import db

    observations: dict = {}
    collected: dict = {}
    ledger = _StageLedger()
    with flask_app.app_context():
        guard_state = {
            'guard_acquired': False,
            'guard_release_attempted': False,
            'guard_released': False,
        }
        guard = None
        try:
            # Acquire-only guard: it takes the public sync advisory lock and
            # never creates, reclaims, or updates a SyncRun row.
            guard = sync_metadata.acquire_public_sync_read_lock(
                source=sync_metadata.SOURCE_GITHUB_ACTIONS,
            )
            guard_state['guard_acquired'] = guard is not None
        except Exception:  # noqa: BLE001 - a contended lock is UNPROVEN
            guard = None

        try:
            if not guard_state['guard_acquired']:
                raise _AuditHalt()
            ledger.completed(audit.STAGE_GUARD_ACQUIRED)

            try:
                read_only = audit.enforce_read_only(db.session)
            except audit.ReadOnlyProbeViolation as violation:
                collected['read_only_enabled'] = False
                collected['read_only_detail'] = violation.evidence
                ledger.failed(audit.STAGE_READ_ONLY_ENFORCED, violation)
                raise _AuditHalt()
            collected['read_only_enabled'] = True
            collected['read_only_detail'] = read_only
            ledger.completed(audit.STAGE_READ_ONLY_ENFORCED)

            # BEFORE, phase one: every scope whose membership is already known
            # is digested before any other work happens, and is PERSISTED the
            # moment it exists. Holding it in a local until the end meant a
            # single later exception discarded a baseline that had already been
            # earned, and with it the only proof that this run changed nothing.
            before = audit.scoped_fingerprints(db.session)
            collected['before_fingerprints'] = before
            if before is None:
                raise _AuditHalt()
            ledger.completed(audit.STAGE_BEFORE_FINGERPRINTS)

            game_pk = audit.INCIDENT_GAME_PK

            # ONE schedule call covers the whole completeness horizon, and the
            # disputed game is normally inside it. Fetching per date would need
            # nine calls against an allowance of eight and refuse the last one.
            def _window():
                horizon = int(game_ingestion_planner.ingestion_horizon_days())
                gateway.fetch_window(
                    audit.INCIDENT_SLATE_DATE - timedelta(days=horizon),
                    audit.INCIDENT_SLATE_DATE,
                )
                return None

            # Each observer is run through the ledger, which writes the result
            # into ``observations`` and advances the stage BEFORE the next one
            # starts. Everything already observed therefore survives a later
            # exception, and the artifact can say exactly where the run
            # stopped without saying anything about what it read.
            ledger.stage(
                audit.STAGE_SOURCE_WINDOW, observations, None, _window,
            )
            ledger.stage(
                audit.STAGE_STORED_SCHEDULE, observations, 'stored_schedule',
                lambda: observe_stored_schedule(game_pk),
            )
            ledger.stage(
                audit.STAGE_OFFICIAL_STATUS, observations, 'official_status',
                lambda: observe_official_status(
                    game_pk, observations.get('stored_schedule'), gateway,
                    window_games=gateway.window_games,
                ),
            )
            ledger.stage(
                audit.STAGE_BASEBALL_STATE, observations, 'baseball_state',
                lambda: observe_baseball_state(game_pk),
            )
            ledger.stage(
                audit.STAGE_APPEARANCE_LEDGER, observations,
                'appearance_ledger',
                lambda: observe_appearance_ledger(
                    game_pk, observations.get('stored_schedule'),
                ),
            )
            ledger.stage(
                audit.STAGE_COMPLETENESS, observations, 'completeness',
                lambda: observe_completeness(game_pk, gateway),
            )
            # Attribution consumes the pitcher ids already extracted from the
            # single box-score response; it never fetches again.
            ledger.stage(
                audit.STAGE_PLAYER_ATTRIBUTION, observations,
                'player_mismatches',
                lambda: attribute_player_mismatches(
                    ledger_artifact.get('ledger_report'),
                    observations.get('appearance_ledger'),
                    observations.get('official_status'),
                ),
            )
            ledger.stage(
                audit.STAGE_SNAPSHOT_GATE, observations, 'snapshot_gate',
                lambda: observe_snapshot_gate(
                    shadow.get('sync_summary'),
                    observations.get('completeness'),
                    ledger_report=ledger_artifact.get('ledger_report'),
                ),
            )
            ledger.stage(
                audit.STAGE_DEAD_LETTER, observations, 'dead_letter_backlog',
                observe_unresolved_sync_failures,
            )
        except _AuditHalt:
            pass
        except _StageFailure:
            # The stage ledger already recorded where and what class. The
            # exception itself is deliberately never rendered.
            pass
        except Exception as exc:  # noqa: BLE001 - never leak exception text
            ledger.failed(audit.STAGE_NOT_STARTED, exc)
        finally:
            # Phase two and the closing digest run whether or not an observer
            # stopped, so that a partial run still carries a complete
            # read-only proof. They are only attempted once the baseline
            # exists, and they can never stop the guard from being released.
            try:
                if collected.get('before_fingerprints') is not None:
                    _close_fingerprints(collected, observations, ledger, db)
            except Exception:  # noqa: BLE001 - never leak exception text
                pass
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

    read_only_proof = _read_only_proof(collected, guard_state)
    comparison = (
        build_authority_comparison(observations) if observations else {}
    )
    findings = (
        build_findings(observations, comparison, module_drift)
        if observations else []
    )
    # Reading a retained artifact costs no database access and no source call,
    # so it is recovered outside the observation stages and survives any
    # failure inside them.
    incident_mapping = audit.incident_mapping_input(shadow)
    questions = (
        build_questions(
            observations, comparison, module_drift,
            incident_mapping=incident_mapping,
        )
        if observations else []
    )

    execution = ledger.state()

    extra_unproven = []
    if execution['error_observed']:
        extra_unproven.append(audit.UNPROVEN_AUDIT_EXECUTION_ERROR)

    decision = audit.decide(
        questions=questions,
        findings=findings,
        read_only_proof=read_only_proof,
        artifact_ingestion=ingestion,
        # The reducer needs the gateway's view too: the budget knows what was
        # refused, only the gateway knows what was dialled and failed.
        budget_state={**budget.state(), **gateway.state()},
        identity_failures=identity_failures,
        extra_unproven=extra_unproven,
    )

    return build_document(
        context=context, note=note, observations=observations,
        questions=questions, comparison=comparison, module_drift=module_drift,
        read_only=read_only_proof, artifact_ingestion=ingestion,
        budget_state={**budget.state(), **gateway.state()},
        decision=decision, execution=execution,
        incident_mapping=incident_mapping,
    )



def _read_only_proof(collected, guard_state) -> dict:
    detail = collected.get('read_only_detail') or {}
    before = collected.get('before_fingerprints')
    after = collected.get('after_fingerprints')
    return {
        'advisory_guard_acquired': guard_state['guard_acquired'],
        'advisory_guard_release_attempted': guard_state[
            'guard_release_attempted'
        ],
        'advisory_guard_released': guard_state['guard_released'],
        'transaction_read_only_enabled': bool(
            collected.get('read_only_enabled')
        ),
        'fingerprint_scopes': list(audit.FINGERPRINT_SCOPE_NAMES),
        'fingerprint_scope_plan': collected.get('scope_plan'),
        'fingerprinted_tables': list(audit.FINGERPRINTED_TABLES),
        'before_fingerprints': before,
        'after_fingerprints': after,
        'fingerprints_match': audit.fingerprint_scopes_match(before, after),
        'changed_scopes': audit.changed_fingerprint_scopes(before, after),
        # One bounded, refused proof statement is attempted. Zero durable
        # writes are attempted. Different facts, different fields.
        **audit.probe_evidence(detail),
        'durable_rows_created': 0,
        'durable_rows_updated': 0,
        'durable_rows_deleted': 0,
        'commits_performed_by_audit': 0,
    }


def _refuse(*, failed=(), unproven=()) -> dict:
    result = audit.RESULT_FAILED if failed else audit.RESULT_UNPROVEN
    return {
        'result': result,
        'exit_code': audit.EXIT_CODES[result],
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)) or (
            [] if failed else [audit.UNPROVEN_AUDIT_EXECUTION_ERROR]
        ),
        'unanswered_question_ids': list(audit.QUESTION_IDS),
        'questions_answered': 0,
        'questions_total': len(audit.QUESTION_IDS),
        'primary_classification': audit.CLASSIFICATION_UNPROVEN,
        'contributing_classifications': [],
        'confidence': audit.CONFIDENCE_LOW,
        'current_condition_persists': 'unproven',
        'recommended_next_package': audit.NEXT_ADDITIONAL_EVIDENCE_REQUIRED,
        'recommendation_informational_only': True,
        'recommendation_note': audit.NEXT_PACKAGE_DISCLAIMER,
        'findings': [],
        'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
    }


def build_document(*, context, note, observations, questions, comparison,
                   module_drift, read_only, artifact_ingestion, budget_state,
                   decision, execution=None, incident_mapping=None) -> dict:
    proof = read_only or {}
    ingestion = artifact_ingestion or {}
    artifacts = ingestion.get('artifacts') or {}
    return {
        'execution': execution or _StageLedger().state(),
        'incident_mapping_reconstruction': (
            incident_mapping or audit.incident_mapping_input(None)
        ),
        'identity': {
            'schema_version': audit.SCHEMA_VERSION,
            'audit_type': audit.AUDIT_TYPE,
            'repository': context.get('repository'),
            'workflow_name': context.get('workflow'),
            'workflow_run_id': context.get('run_id'),
            'workflow_run_attempt': context.get('run_attempt'),
            'commit_sha': qualification.normalize_sha(
                context.get('github_sha')
            ),
            'ref': context.get('ref'),
            'actor': context.get('actor'),
            'event_name': context.get('event_name'),
            'executed_at': datetime.now(timezone.utc).isoformat(),
        },
        'incident_identity': {
            **audit.incident_identity(),
            'artifact_availability': {
                name: {
                    'required': entry.get('required'),
                    'present': entry.get('present'),
                    'readable': entry.get('readable'),
                    'files': entry.get('files'),
                    'parse_error': entry.get('parse_error'),
                    'expected_artifact_id': entry.get('expected_artifact_id'),
                    'expected_retention_days': entry.get(
                        'expected_retention_days'
                    ),
                    'digest_status': entry.get('digest_status'),
                    'digest_verified': entry.get('digest_verified'),
                    'digest_mismatch': entry.get('digest_mismatch'),
                }
                for name, entry in artifacts.items()
            },
            'incident_validation': ingestion.get('incident_validation'),
            'immutable_incident_facts': audit.immutable_incident_facts(),
        },
        'request': {
            'confirmation_valid': 'confirmation_mismatch' not in (
                decision['failed_reasons']
            ),
            'expected_head_sha_valid': not (
                {'expected_head_sha_malformed', 'expected_head_sha_mismatch'}
                & set(decision['failed_reasons'])
            ),
            'operator_note': note,
        },
        'read_only_proof': proof,
        'source_call_budget': budget_state,
        'canonical_module_drift': module_drift,
        'official_game_evidence': observations.get('official_status'),
        'stored_game_evidence': {
            'schedule': observations.get('stored_schedule'),
            'baseball_state': observations.get('baseball_state'),
        },
        'authority_comparison': comparison,
        'appearance_ledger_evidence': observations.get('appearance_ledger'),
        'player_attribution': observations.get('player_mismatches'),
        'unresolved_final_games': (
            (observations.get('completeness') or {})
            .get('unresolved_classification')
        ),
        'game_ingestion_completeness': (
            (observations.get('completeness') or {}).get('completeness')
        ),
        'snapshot_publication': observations.get('snapshot_gate'),
        'dead_letter_backlog': observations.get('dead_letter_backlog'),
        'questions': questions,
        'root_cause': {
            'result': decision['result'],
            'primary_classification': decision['primary_classification'],
            'contributing_classifications': decision[
                'contributing_classifications'
            ],
            'confidence': decision['confidence'],
            'current_condition_persists': decision[
                'current_condition_persists'
            ],
            'findings': decision['findings'],
            'recommended_next_package': decision['recommended_next_package'],
            'recommendation_informational_only': True,
            'recommendation_note': decision['recommendation_note'],
            'classification_vocabulary': list(audit.PRIMARY_CLASSIFICATIONS),
        },
        'verdict': {
            'result': decision['result'],
            'exit_code': decision['exit_code'],
            'failed_reasons': decision['failed_reasons'],
            'unproven_reasons': decision['unproven_reasons'],
            'unanswered_question_ids': decision['unanswered_question_ids'],
            'questions_answered': decision['questions_answered'],
            'questions_total': decision['questions_total'],
            'explanation': audit.explanation(decision),
            'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
        },
    }


# ── Rendering ───────────────────────────────────────────────────────────────

REQUIRED_MARKDOWN_SECTIONS = (
    '# Postgame publication incident audit',
    '## Incident identity',
    '## Read-only proof',
    '## Evidence artifacts',
    '## MLB source-call budget',
    '## Official game evidence',
    '## Stored game evidence',
    '## Authority comparison',
    '## Player attribution',
    '## Unresolved final games',
    '## Snapshot publication',
    '## Questions',
    '## Root cause',
)


def render_markdown(document) -> str:
    identity = document['identity']
    incident = document['incident_identity']
    verdict = document['verdict']
    proof = document['read_only_proof']
    budget = document['source_call_budget']
    root = document['root_cause']
    comparison = document.get('authority_comparison') or {}
    players = document.get('player_attribution') or {}
    unresolved = document.get('unresolved_final_games') or {}
    snapshot = document.get('snapshot_publication') or {}
    official = document.get('official_game_evidence') or {}
    stored = (document.get('stored_game_evidence') or {}).get('schedule') or {}
    baseball = (
        (document.get('stored_game_evidence') or {}).get('baseball_state')
        or {}
    )

    lines = [
        '# Postgame publication incident audit',
        '',
        f"**Result: {verdict['result']}**",
        '',
        verdict['explanation'],
        '',
        '## Incident identity',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| incident run | {incident['workflow_run_id']} |",
        f"| incident head | `{incident['head_sha']}` |",
        f"| cycle | {incident['cycle_kind']} |",
        f"| slate | {incident['slate_date']} |",
        f"| disputed game | {incident['disputed_game_pk']} |",
        f"| candidate snapshot | {incident['candidate_snapshot_id']} |",
        f"| served snapshot | {incident['served_snapshot_id']} |",
        f"| sync run | {incident['sync_run_id']} |",
        f"| audit commit | `{identity.get('commit_sha')}` |",
        f"| executed at | {identity.get('executed_at')} |",
        '',
        'Incident interpretation preserved from the run:',
        '',
        '| stage | outcome |',
        '| :--- | :--- |',
    ]
    for stage, outcome in (
        incident['immutable_incident_facts']['interpretation'].items()
    ):
        lines.append(f'| {stage} | {outcome} |')

    lines += [
        '',
        '## Read-only proof',
        '',
        '| check | value |',
        '| :--- | :--- |',
        f"| advisory guard acquired | "
        f"{proof.get('advisory_guard_acquired')} |",
        f"| release attempted | "
        f"{proof.get('advisory_guard_release_attempted')} |",
        f"| release confirmed | {proof.get('advisory_guard_released')} |",
        f"| transaction read-only | "
        f"{proof.get('transaction_read_only_enabled')} |",
        f"| probe attempted | {proof.get('read_only_probe_attempted')} |",
        f"| probe count | {proof.get('read_only_probe_count')} |",
        f"| probe class | `{proof.get('read_only_probe_statement_class')}` |",
        f"| bounded to zero rows | "
        f"{proof.get('read_only_probe_bounded_to_zero_rows')} |",
        f"| probe refused | {proof.get('read_only_probe_refused')} |",
        f"| durable write attempts | {proof.get('durable_write_attempts')} |",
        f"| rows created/updated/deleted | "
        f"{proof.get('durable_rows_created')}/"
        f"{proof.get('durable_rows_updated')}/"
        f"{proof.get('durable_rows_deleted')} |",
        f"| commits performed | {proof.get('commits_performed_by_audit')} |",
        f"| fingerprint scopes | {proof.get('fingerprint_scopes')} |",
        f"| fingerprints match | {proof.get('fingerprints_match')} |",
        f"| changed scopes | {proof.get('changed_scopes')} |",
        '',
        '## Evidence artifacts',
        '',
        '| artifact | required | present | digest | parse error |',
        '| :--- | :--- | :--- | :--- | :--- |',
    ]
    for name, entry in sorted(
        (incident.get('artifact_availability') or {}).items()
    ):
        lines.append(
            f"| `{name}` | {entry.get('required')} | {entry.get('present')} "
            f"| {entry.get('digest_status')} | {entry.get('parse_error')} |"
        )

    lines += [
        '',
        '## MLB source-call budget',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| limits | {budget.get('limits')} |",
        f"| total limit | {budget.get('total_limit')} |",
        f"| attempted | {budget.get('calls_attempted')} |",
        f"| succeeded | {budget.get('calls_succeeded')} |",
        f"| failed | {budget.get('calls_failed')} |",
        f"| retries | {budget.get('total_retries')} |",
        f"| refused by budget | {budget.get('calls_refused_by_budget')} |",
        f"| total latency (ms) | {budget.get('total_source_latency_ms')} |",
        f"| budget remaining | {budget.get('budget_remaining')} |",
        f"| exhausted | {budget.get('budget_exhausted')} |",
        '',
        '## Official game evidence',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| observed | {official.get('game_found_in_source')} |",
        f"| official classification | "
        f"{official.get('official_classification')} |",
        f"| canonical finality state | "
        f"{official.get('canonical_finality_state')} |",
        f"| canonical status state | "
        f"{official.get('canonical_status_state')} |",
        f"| source revision | "
        f"`{(official.get('normalized') or {}).get('source_revision')}` |",
        f"| relationship | {official.get('relationship')} |",
        '',
        '## Stored game evidence',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| schedule rows | {stored.get('row_count')} |",
        f"| status states | {stored.get('distinct_status_states')} |",
        f"| full row governance agreement | "
        f"{stored.get('full_row_governance_agreement')} |",
        f"| disagreeing fields | {stored.get('disagreeing_fields')} |",
        f"| linked replacement games | "
        f"{stored.get('linked_replacement_game_pks')} |",
        f"| game_logs | "
        f"{(baseball.get('game_logs') or {}).get('row_count')} |",
        f"| postgame marker | "
        f"{(baseball.get('postgame_processed_game') or {}).get('row_count')} |",
        f"| work item | "
        f"{(baseball.get('game_ingestion_work_item') or {}).get('row_count')} |",
        '',
        '## Authority comparison',
        '',
        '| authority | classification |',
        '| :--- | :--- |',
        f"| official source | "
        f"{comparison.get('official_source_classification')} |",
        f"| schedule parser | "
        f"{comparison.get('schedule_parser_classification')} |",
        f"| stored schedule | "
        f"{comparison.get('stored_schedule_classification')} |",
        f"| planner | {comparison.get('planner_classification')} |",
        f"| appearance ledger | "
        f"{comparison.get('appearance_ledger_classification')} |",
        '',
        f"Exact disagreements: {comparison.get('exact_disagreements')}",
        '',
        '## Player attribution',
        '',
        '| player | tracked | in disputed lines | classification |',
        '| ---: | :--- | :--- | :--- |',
    ]
    for entry in players.get('players') or ():
        lines.append(
            f"| {entry.get('player_id')} | {entry.get('pitcher_tracked')} "
            f"| {entry.get('in_disputed_game_official_lines')} "
            f"| `{entry.get('classification')}` |"
        )

    lines += [
        '',
        '## Unresolved final games',
        '',
        f"- membership provenance: `{unresolved.get('membership_provenance')}`",
        f"- incident reported count: "
        f"{unresolved.get('incident_reported_count')}",
        f"- reconstructed count: {unresolved.get('reconstructed_count')}",
        f"- authority count: "
        f"{unresolved.get('authority_unresolved_final_games')}",
        f"- reconciles: {unresolved.get('reconciles_with_authority')}",
        f"- scope valid / invalid: {unresolved.get('scope_valid_count')} / "
        f"{unresolved.get('scope_invalid_count')}",
        '',
        '| category | count |',
        '| :--- | ---: |',
    ]
    for key, value in sorted(
        (unresolved.get('classification_counts') or {}).items()
    ):
        lines.append(f'| `{key}` | {value} |')

    lines += [
        '',
        '## Snapshot publication',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| INCIDENT candidate | "
        f"{(snapshot.get('incident') or {}).get('incident_candidate_status')} |",
        f"| INCIDENT served | "
        f"{(snapshot.get('incident') or {}).get('incident_served_snapshot_id')} |",
        f"| INCIDENT withholding fail-closed | "
        f"{(snapshot.get('incident') or {}).get('incident_withholding_was_fail_closed')} |",
        f"| CURRENT candidate status | "
        f"{(snapshot.get('current') or {}).get('candidate_current_status')} |",
        f"| CURRENT published later | "
        f"{(snapshot.get('current') or {}).get('candidate_published_later')} |",
        f"| CURRENT served | "
        f"{(snapshot.get('current') or {}).get('current_served_snapshot_id')} |",
        f"| CURRENT condition recovered | "
        f"{(snapshot.get('current') or {}).get('current_condition_recovered')} |",
        f"| sole blocker | "
        f"{(snapshot.get('gate_scope') or {}).get('disputed_game_is_sole_blocker')} |",
        f"| requires games outside slate | "
        f"{(snapshot.get('gate_scope') or {}).get('requires_games_outside_slate')} |",
        '',
        '## Questions',
        '',
        '| # | question | answered |',
        '| ---: | :--- | :--- |',
    ]
    for position, question in enumerate(document['questions'], start=1):
        lines.append(
            f"| {position} | {question['question']} | {question['answered']} |"
        )
    for question in document['questions']:
        lines += [
            '', f"### {question['question']}", '', question['answer'] or '',
        ]
        if question.get('unproven_reason'):
            lines += ['', f"Unproven: `{question['unproven_reason']}`"]

    lines += [
        '',
        '## Root cause',
        '',
        f"- primary: `{root.get('primary_classification')}`",
        f"- contributing: {root.get('contributing_classifications')}",
        f"- confidence: {root.get('confidence')}",
        f"- current condition persists: "
        f"{root.get('current_condition_persists')}",
        f"- recommended next package: "
        f"`{root.get('recommended_next_package')}`",
        '',
        root.get('recommendation_note') or '',
        '',
        '| classification | proven | supporting | counter |',
        '| :--- | :--- | ---: | ---: |',
    ]
    for finding in root.get('findings') or ():
        lines.append(
            f"| `{finding.get('classification')}` | {finding.get('proven')} "
            f"| {len(finding.get('supporting_evidence') or ())} "
            f"| {len(finding.get('counter_evidence') or ())} |"
        )

    if verdict['failed_reasons']:
        lines += ['', '## Failed reasons', '']
        lines += [f'- `{reason}`' for reason in verdict['failed_reasons']]
    if verdict['unproven_reasons']:
        lines += ['', '## Unproven reasons', '']
        lines += [f'- `{reason}`' for reason in verdict['unproven_reasons']]

    lines += ['', '---', '', verdict['non_authorization_statement'], '']
    return '\n'.join(lines)


def write_artifacts(document, artifact_dir) -> dict:
    target = Path(artifact_dir)
    target.mkdir(parents=True, exist_ok=True)

    (target / SUMMARY_JSON).write_text(
        json.dumps(document, indent=2, sort_keys=True, default=str) + '\n',
        encoding='utf-8',
    )
    (target / SUMMARY_MARKDOWN).write_text(
        render_markdown(document), encoding='utf-8',
    )
    metadata = {
        'schema_version': audit.SCHEMA_VERSION,
        'audit_type': audit.AUDIT_TYPE,
        'incident_run_id': audit.INCIDENT_RUN_ID,
        'incident_head_sha': audit.INCIDENT_HEAD_SHA,
        'result': document['verdict']['result'],
        'exit_code': document['verdict']['exit_code'],
        'questions_answered': document['verdict']['questions_answered'],
        'questions_total': document['verdict']['questions_total'],
        'primary_classification': document['root_cause'][
            'primary_classification'
        ],
        'contributing_classifications': document['root_cause'][
            'contributing_classifications'
        ],
        'confidence': document['root_cause']['confidence'],
        'recommended_next_package': document['root_cause'][
            'recommended_next_package'
        ],
        'recommendation_informational_only': True,
        'commit_sha': document['identity'].get('commit_sha'),
        'workflow_run_id': document['identity'].get('workflow_run_id'),
        'summary_filename': SUMMARY_JSON,
        'markdown_filename': SUMMARY_MARKDOWN,
        'metadata_filename': METADATA_JSON,
        'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
    }
    (target / METADATA_JSON).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + '\n', encoding='utf-8',
    )
    return metadata


# ── Small helpers ───────────────────────────────────────────────────────────

def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _text(value, *, limit=60):
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        document = run(args)
    except Exception:  # noqa: BLE001 - never leak exception text
        document = build_document(
            context=event_context(args),
            note=qualification.sanitize_note(args.operator_note),
            observations={}, questions=[], comparison={},
            module_drift=audit.canonical_module_drift({}), read_only={},
            artifact_ingestion={},
            budget_state=audit.SourceCallBudget().state(),
            decision=_refuse(unproven=[audit.UNPROVEN_AUDIT_EXECUTION_ERROR]),
        )

    try:
        write_artifacts(document, args.artifact_dir)
    except Exception:  # noqa: BLE001 - an unwritable artifact is UNPROVEN
        document['verdict']['unproven_reasons'] = sorted(set(
            list(document['verdict']['unproven_reasons'])
            + [audit.UNPROVEN_ARTIFACT_CONSTRUCTION_FAILED]
        ))
        document['verdict']['result'] = audit.RESULT_UNPROVEN
        document['verdict']['exit_code'] = audit.EXIT_CODES[
            audit.RESULT_UNPROVEN
        ]

    print(json.dumps(document, indent=2, sort_keys=True, default=str))
    return int(document['verdict']['exit_code'])


if __name__ == '__main__':
    os.environ.setdefault('AUTO_SYNC', 'false')
    raise SystemExit(main())
