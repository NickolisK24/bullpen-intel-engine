"""Daily-cycle realization proof for the game-driven shadow lane.

The daily sync runs the game-driven lane BEFORE its legacy pitcher writer. When
newly final or corrected games exist, the projection therefore legitimately
reports inserts and updates: those are *projected reconciliation actions*, not
database writes performed by shadow. Shadow writes nothing, ever.

That ordering makes "zero projected mutations" the wrong daily question. The
right one is:

    the projection said the canonical rows should end up in a particular state —
    did the writer that ran afterwards actually put them there?

This module answers exactly that, and nothing else.

What it does NOT do
-------------------
* It does not call MLB. The official evidence was fetched once, by the lane.
* It does not re-plan. It consumes the plan the lane already produced.
* It does not re-run ingestion.
* It does not write. Every query here is a read.

How the comparison is safe
--------------------------
Each plan row carries the fields it intends to determine and a digest of the
values it intends them to hold (``target_fields`` / ``target_state_digest``,
owned by ``game_log_reconciliation``). After the writer, the stored row is read
and the *same* encoder digests the *same* field names. Equal digests mean the
writer realized the projected target.

Only field names, governed identifiers, classifications, and digests are
reported. No raw row, no before/after value, no payload, no path, no credential,
and no exception text can travel in this proof — the values themselves never
leave the process.
"""

from __future__ import annotations

from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity


CYCLE_DAILY = 'daily'

# Row-level verdicts.
RESULT_REALIZED = 'realized'
RESULT_ALREADY_MATCHING = 'already_matching'
RESULT_MISSING = 'missing'
RESULT_DIVERGENT = 'divergent'
RESULT_DUPLICATE = 'duplicate'
RESULT_UNRESOLVED = 'unresolved'
RESULT_NOT_APPLICABLE = 'not_applicable'

UNRESOLVED_RESULTS = frozenset({
    RESULT_MISSING, RESULT_DIVERGENT, RESULT_DUPLICATE, RESULT_UNRESOLVED,
})

# Identity actions a clean daily projection may contain. D-009 already reduced
# the vocabulary to these plus ``blocked``; anything else is a governance gap
# and fails closed rather than being tolerated.
ALLOWED_IDENTITY_ACTIONS = frozenset({
    pitcher_identity.ACTION_UNCHANGED,
    pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY,
    None,
})

SOURCE_REVISION_MATCHED = 'matched'
SOURCE_REVISION_CHANGED = 'changed'
SOURCE_REVISION_NO_CHECKPOINT = 'no_checkpoint'


def build_daily_realization(report) -> dict:
    """Prove whether the daily writer realized the projected canonical targets.

    ``report`` is the game-driven run report the lane already produced. Returns
    a safe, serializable proof section. Never raises for data reasons: an
    unprovable row is reported as unresolved, which fails the activation gate,
    rather than being silently dropped.
    """
    report = report or {}
    games = list(report.get('games') or ())
    proof = _empty_proof()

    if not games:
        # A cycle that planned nothing has nothing to realize. That is a clean
        # result, not an unproven one.
        proof['applicable'] = False
        proof['work_state'] = 'no_candidates'
        proof['all_projected_targets_realized'] = True
        return proof

    proof['applicable'] = True
    proof['work_state'] = 'candidates_planned'

    rows = [row for game in games for row in (game.get('rows') or ())]
    proof['projected_rows'] = len(rows)

    local_ids = _local_pitcher_ids(rows)
    stored = _stored_rows(rows)

    for row in rows:
        entry = _classify_row(row, local_ids=local_ids, stored=stored)
        proof['rows'].append(entry)
        _fold_row(proof, row, entry)

    proof['source_revisions'] = _source_revision_states(games)
    proof['source_revision_match'] = all(
        state['state'] != SOURCE_REVISION_CHANGED
        for state in proof['source_revisions']
    )
    proof['safe_digest_match'] = proof['divergent_rows'] == 0
    proof['unresolved_rows'] = sum(
        1 for entry in proof['rows'] if entry['result'] in UNRESOLVED_RESULTS
    )
    proof['unresolved_identities'] = [
        _identity_ref(entry) for entry in proof['rows']
        if entry['result'] in UNRESOLVED_RESULTS
    ]
    proof['divergent_identities'] = [
        _identity_ref(entry) for entry in proof['rows']
        if entry['result'] == RESULT_DIVERGENT
    ]
    proof['all_projected_targets_realized'] = bool(
        proof['unresolved_rows'] == 0
        and proof['prohibited_identity_actions'] == 0
        and proof['source_revision_match']
    )
    return proof


# ── Row classification ──────────────────────────────────────────────────────


def _classify_row(row, *, local_ids, stored) -> dict:
    action = row.get('action')
    game_pk = row.get('game_pk')
    pitcher_mlb_id = row.get('pitcher_mlb_id')
    target_field_names = list(row.get('target_fields') or ())
    entry = {
        'game_pk': game_pk,
        'pitcher_mlb_id': pitcher_mlb_id,
        'projected_action': action,
        'target_fields': target_field_names,
        'result': RESULT_NOT_APPLICABLE,
        'reason': None,
        'identity_action': row.get('pitcher_identity_action'),
        'identity_realized': None,
    }

    if action == reconciliation.ACTION_BLOCKED:
        # A blocked plan intends no stored state, so there is nothing for a
        # writer to realize — but a blocked row is never clean, and the
        # validator refuses the cycle on the projected blocked count.
        entry['result'] = RESULT_NOT_APPLICABLE
        entry['reason'] = 'projected_blocked'
        return entry

    local_id = local_ids.get(pitcher_mlb_id)
    if local_id is None:
        entry['result'] = (
            RESULT_MISSING if action == reconciliation.ACTION_INSERT
            else RESULT_UNRESOLVED
        )
        entry['reason'] = 'pitcher_identity_not_resolvable'
        entry['identity_realized'] = False
        return entry

    entry['identity_realized'] = True
    matches = stored.get((local_id, game_pk)) or []
    if len(matches) > 1:
        entry['result'] = RESULT_DUPLICATE
        entry['reason'] = 'duplicate_canonical_appearance'
        return entry
    if not matches:
        entry['result'] = RESULT_MISSING
        entry['reason'] = 'canonical_row_absent_after_writer'
        return entry

    if action == reconciliation.ACTION_UNCHANGED:
        entry['result'] = RESULT_ALREADY_MATCHING
        return entry

    if not target_field_names:
        # An insert or update that named no target field cannot be proven
        # either way. Fail closed rather than call it realized.
        entry['result'] = RESULT_UNRESOLVED
        entry['reason'] = 'plan_declared_no_target_state'
        return entry

    realized_digest = reconciliation.stored_state_digest(
        matches[0], target_field_names
    )
    if realized_digest == row.get('target_state_digest'):
        entry['result'] = RESULT_REALIZED
        return entry

    entry['result'] = RESULT_DIVERGENT
    entry['reason'] = 'stored_state_differs_from_projected_target'
    return entry


def _fold_row(proof, row, entry) -> None:
    action = row.get('action')
    if action == reconciliation.ACTION_INSERT:
        proof['projected_inserts'] += 1
    elif action == reconciliation.ACTION_UPDATE:
        proof['projected_updates'] += 1
    elif action == reconciliation.ACTION_UNCHANGED:
        proof['projected_unchanged'] += 1
    elif action == reconciliation.ACTION_BLOCKED:
        proof['projected_blocked'] += 1

    if entry['result'] == RESULT_REALIZED:
        proof['realized_rows'] += 1
        if action == reconciliation.ACTION_INSERT:
            proof['realized_inserts'] += 1
        elif action == reconciliation.ACTION_UPDATE:
            proof['realized_updates'] += 1
    elif entry['result'] == RESULT_ALREADY_MATCHING:
        proof['already_matching_rows'] += 1
    elif entry['result'] == RESULT_MISSING:
        proof['missing_rows'] += 1
    elif entry['result'] == RESULT_DIVERGENT:
        proof['divergent_rows'] += 1
    elif entry['result'] == RESULT_DUPLICATE:
        proof['duplicate_rows'] += 1

    identity_action = row.get('pitcher_identity_action')
    if identity_action not in ALLOWED_IDENTITY_ACTIONS:
        proof['prohibited_identity_actions'] += 1
        proof['prohibited_identity_action_counts'][str(identity_action)] = (
            proof['prohibited_identity_action_counts'].get(
                str(identity_action), 0
            ) + 1
        )
    if identity_action == pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY:
        proof['identity_creations_projected'] += 1
        if entry['identity_realized']:
            proof['identity_creations_realized'] += 1
    if row.get('pitcher_identity_current_authority_mutation_refused'):
        # A refusal is D-009 working, not a defect. Counted so a reader can see
        # that suppression happened rather than inferring it from silence.
        proof['current_state_mutations_refused'] += 1

    if row.get('appearance_team_reason'):
        proof['appearance_team_actions_projected'] += 1
        if entry['result'] in (RESULT_REALIZED, RESULT_ALREADY_MATCHING):
            proof['appearance_team_actions_realized'] += 1

    if row.get('is_statistical_correction'):
        proof['corrections_projected'] += 1
        if entry['result'] in (RESULT_REALIZED, RESULT_ALREADY_MATCHING):
            proof['corrections_realized'] += 1

    if 'innings_pitched_outs' in (row.get('semantic_changed_fields') or ()):
        proof['canonical_outs_corrections_projected'] += 1
        if entry['result'] == RESULT_REALIZED:
            proof['canonical_outs_corrections_realized'] += 1


# ── Database reads (after the writer, read-only) ────────────────────────────


def _local_pitcher_ids(rows) -> dict:
    mlb_ids = sorted({
        row.get('pitcher_mlb_id') for row in rows
        if row.get('pitcher_mlb_id') is not None
    })
    if not mlb_ids:
        return {}
    return {
        pitcher.mlb_id: pitcher.id
        for pitcher in Pitcher.query.filter(Pitcher.mlb_id.in_(mlb_ids)).all()
    }


def _stored_rows(rows) -> dict:
    game_pks = sorted({
        row.get('game_pk') for row in rows if row.get('game_pk') is not None
    })
    if not game_pks:
        return {}
    stored: dict = {}
    for row in GameLog.query.filter(GameLog.mlb_game_pk.in_(game_pks)).all():
        stored.setdefault((row.pitcher_id, row.mlb_game_pk), []).append(row)
    return stored


def _source_revision_states(games) -> list[dict]:
    """Compare each game's observed source revision with its checkpoint.

    A game with no durable checkpoint has nothing to compare against — the lane
    has never written one — and is reported as ``no_checkpoint`` rather than
    being counted as a match it cannot prove.
    """
    game_pks = sorted({
        game.get('game_pk') for game in games if game.get('game_pk') is not None
    })
    if not game_pks:
        return []
    checkpoints = {
        item.mlb_game_pk: item.source_revision
        for item in GameIngestionWorkItem.query.filter(
            GameIngestionWorkItem.mlb_game_pk.in_(game_pks)
        ).all()
    }
    states = []
    for game in games:
        game_pk = game.get('game_pk')
        observed = game.get('source_revision')
        recorded = checkpoints.get(game_pk)
        if recorded is None:
            state = SOURCE_REVISION_NO_CHECKPOINT
        elif recorded == observed:
            state = SOURCE_REVISION_MATCHED
        else:
            state = SOURCE_REVISION_CHANGED
        states.append({
            'game_pk': game_pk,
            'state': state,
            'observed_source_revision': observed,
        })
    states.sort(key=lambda item: item['game_pk'] or 0)
    return states


# ── Shape ───────────────────────────────────────────────────────────────────


def _identity_ref(entry) -> dict:
    return {
        'game_pk': entry['game_pk'],
        'pitcher_mlb_id': entry['pitcher_mlb_id'],
        'projected_action': entry['projected_action'],
        'result': entry['result'],
        'reason': entry['reason'],
    }


def _empty_proof() -> dict:
    return {
        'applicable': False,
        'cycle_kind': CYCLE_DAILY,
        'work_state': 'no_candidates',
        'projected_rows': 0,
        'projected_inserts': 0,
        'projected_updates': 0,
        'projected_unchanged': 0,
        'projected_blocked': 0,
        'realized_rows': 0,
        'realized_inserts': 0,
        'realized_updates': 0,
        'already_matching_rows': 0,
        'unresolved_rows': 0,
        'divergent_rows': 0,
        'missing_rows': 0,
        'duplicate_rows': 0,
        'identity_creations_projected': 0,
        'identity_creations_realized': 0,
        'prohibited_identity_actions': 0,
        'prohibited_identity_action_counts': {},
        'current_state_mutations_refused': 0,
        'appearance_team_actions_projected': 0,
        'appearance_team_actions_realized': 0,
        'corrections_projected': 0,
        'corrections_realized': 0,
        'canonical_outs_corrections_projected': 0,
        'canonical_outs_corrections_realized': 0,
        'all_projected_targets_realized': False,
        'unresolved_identities': [],
        'divergent_identities': [],
        'source_revisions': [],
        'source_revision_match': True,
        'safe_digest_match': True,
        'rows': [],
    }
