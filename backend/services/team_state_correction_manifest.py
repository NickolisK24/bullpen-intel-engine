"""Dry-run correction manifest for frozen Team State artifacts (WP-0.1, EOS-003).

From October 2026, idle and eliminated clubs were published as Vulnerable or
Stretched because an arm with no recent appearance counted as a constraint
(EOS-001) and no club was ever recognised as finished (EOS-002). Each of those
reads was frozen as an immutable Share Artifact.

This module decides, for each published Team State artifact, whether its claim
was wrong *when it was published* and what correction is proposed. It changes
nothing: it never supersedes, withdraws, or edits an artifact. Executing a
correction is a separate, explicitly authorized operation.

Each decision is reproducible from stored evidence only:

* the artifact's own frozen public state, team, and product date;
* the durable Team State publication proof for the artifact's source snapshot,
  which recorded the Contract A partition and every arm's public read and
  data state (``snapshot_team_state_generation_inputs``); and
* the club competition status at the read's availability reference date,
  from the stored schedule and official decisions.

Proposed actions:

``propose_supersede_with_correction``
    The published claim was wrong at publication: the club was not in active
    competition, or re-counting its idle arms as rested (the only change
    WP-0.1 makes to the partition) yields a different Team State.
``retain``
    The claim stands under corrected semantics.
``review_required``
    The stored evidence cannot settle it (no proof inputs, or an undetermined
    competition status). A person decides.

Withdrawal is never proposed: the Constitution corrects history by
supersession, and these artifacts are authentic records of what was published.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from fractions import Fraction
from typing import Any, Iterable, Mapping, Optional


CONTRACT = 'team_state_correction_manifest_v1'

ACTION_SUPERSEDE = 'propose_supersede_with_correction'
ACTION_RETAIN = 'retain'
ACTION_REVIEW = 'review_required'

REASON_NOT_IN_COMPETITION = 'club_not_in_active_competition'
REASON_INACTIVITY_CONSTRAINT = 'inactivity_counted_as_constraint'
REASON_STATE_STANDS = 'state_stands_under_corrected_semantics'
REASON_INPUTS_MISSING = 'publication_proof_inputs_missing'
REASON_COMPETITION_UNDETERMINED = 'competition_status_undetermined'

ERROR_TIMING_AT_PUBLICATION = 'incorrect_when_published'

PUBLIC_BY_STATUS = {
    'operationally_stable': 'fresh',
    'operationally_constrained': 'stretched',
    'operationally_stressed': 'vulnerable',
}
CLEAN_READ_KEY = 'clean_option'


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _contract_a(clean, moderate, severe, unknown, thresholds) -> Optional[str]:
    """Contract A over a partition, using the thresholds the proof recorded."""
    total = clean + moderate + severe + unknown
    if total <= 0:
        return None
    try:
        clean_share_min = Fraction(*thresholds['clean_share_fresh_min'])
        severe_share_min = Fraction(*thresholds['severe_share_vulnerable_min'])
        clean_count_min = int(thresholds['clean_count_fresh_min'])
        severe_count_max = int(thresholds['severe_count_fresh_max'])
        vulnerable_max = int(thresholds['clean_count_vulnerable_max'])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    if clean <= vulnerable_max or Fraction(severe, total) >= severe_share_min:
        return 'operationally_stressed'
    if (
        Fraction(clean, total) >= clean_share_min
        and clean >= clean_count_min
        and severe <= severe_count_max
    ):
        return 'operationally_stable'
    return 'operationally_constrained'


def corrected_team_state(team_inputs: Mapping[str, Any]) -> Optional[dict]:
    """Re-count idle arms as rested and re-apply the recorded Contract A.

    Under the retired semantics an arm whose data state was ``stale`` (no
    appearance inside the freshness window) or ``missing`` (no workload
    record) was internally Monitor: it sat in the moderate bucket and read
    Limited Read. WP-0.1 counts a stale arm clean and a missing arm unknown.
    Those are the only partition changes, so they are the only adjustments.
    """
    readiness = _mapping(team_inputs.get('readiness'))
    evidence = _mapping(readiness.get('team_state_evidence'))
    counts = [evidence.get(key) for key in (
        'clean_count', 'moderate_count', 'severe_count', 'unknown_count',
    )]
    if not all(isinstance(value, int) for value in counts):
        return None
    clean, moderate, severe, unknown = counts
    arm_reads = _mapping(team_inputs.get('arm_reads')).get('records') or []

    def _moderate_arms(data_state):
        return sorted(
            _mapping(arm).get('pitcher_id') for arm in arm_reads
            if _mapping(_mapping(arm).get('evidence_state')).get('data_state') == data_state
            and _mapping(_mapping(arm).get('public_read')).get('key')
            not in {CLEAN_READ_KEY, 'unavailable'}
        )

    idle_non_clean = _moderate_arms('stale')
    missing_non_clean = _moderate_arms('missing')
    moved = min(len(idle_non_clean), moderate)
    to_unknown = min(len(missing_non_clean), moderate - moved)
    corrected = (clean + moved, moderate - moved - to_unknown, severe, unknown + to_unknown)
    corrected_status = _contract_a(
        *corrected, _mapping(evidence.get('thresholds_applied')),
    )
    return {
        'recorded_partition': {
            'clean_count': clean, 'moderate_count': moderate,
            'severe_count': severe, 'unknown_count': unknown,
        },
        'idle_arms_counted_as_constraint': idle_non_clean,
        'missing_evidence_arms_counted_as_constraint': missing_non_clean,
        'corrected_partition': {
            'clean_count': corrected[0], 'moderate_count': corrected[1],
            'severe_count': corrected[2], 'unknown_count': corrected[3],
        },
        'corrected_status_code': corrected_status,
        'corrected_public_state': PUBLIC_BY_STATUS.get(corrected_status),
    }


def classify_artifact_for_correction(
    artifact: Mapping[str, Any],
    *,
    competition_status: Optional[Mapping[str, Any]],
    team_inputs: Optional[Mapping[str, Any]],
) -> dict:
    """One deterministic manifest entry. Never mutates anything.

    ``artifact`` carries ``public_id``, ``team_id``, ``product_date``,
    ``source_snapshot_id`` and ``published_public_state``.
    """
    published_state = artifact.get('published_public_state')
    entry = {
        'public_id': artifact.get('public_id'),
        'team_id': artifact.get('team_id'),
        'team_abbreviation': artifact.get('team_abbreviation'),
        'product_date': _iso(artifact.get('product_date')),
        'source_snapshot_id': artifact.get('source_snapshot_id'),
        'published_public_state': published_state,
        'competition_status': (
            {key: competition_status.get(key) for key in (
                'status', 'basis', 'reference_date', 'last_final_game_date',
            )}
            if isinstance(competition_status, Mapping) else None
        ),
        'correction': None,
        'proposed_action': ACTION_REVIEW,
        'reasons': [],
        'error_timing': None,
    }
    status = (competition_status or {}).get('status')
    if status == 'season_complete':
        entry.update(
            proposed_action=ACTION_SUPERSEDE,
            reasons=[REASON_NOT_IN_COMPETITION],
            error_timing=ERROR_TIMING_AT_PUBLICATION,
        )
    correction = corrected_team_state(team_inputs) if team_inputs else None
    entry['correction'] = correction
    if status == 'season_complete':
        if correction and correction['idle_arms_counted_as_constraint']:
            entry['reasons'].append(REASON_INACTIVITY_CONSTRAINT)
        return entry
    if correction is None:
        entry['reasons'] = [REASON_INPUTS_MISSING]
        return entry
    if (
        correction['corrected_public_state'] is not None
        and correction['corrected_public_state'] != published_state
    ):
        entry.update(
            proposed_action=ACTION_SUPERSEDE,
            reasons=[REASON_INACTIVITY_CONSTRAINT],
            error_timing=ERROR_TIMING_AT_PUBLICATION,
        )
        return entry
    if status != 'active':
        entry['reasons'] = [REASON_COMPETITION_UNDETERMINED]
        return entry
    entry.update(proposed_action=ACTION_RETAIN, reasons=[REASON_STATE_STANDS])
    return entry


def build_manifest(entries: Iterable[Mapping[str, Any]], *, scope: Mapping[str, Any]) -> dict:
    """Assemble a deterministic manifest with a content digest."""
    ordered = sorted(
        (dict(entry) for entry in entries),
        key=lambda item: (
            str(item.get('product_date') or ''),
            int(item.get('team_id') or 0),
            str(item.get('public_id') or ''),
        ),
    )
    counts = {}
    for entry in ordered:
        counts[entry['proposed_action']] = counts.get(entry['proposed_action'], 0) + 1
    by_state = {}
    for entry in ordered:
        if entry['proposed_action'] == ACTION_SUPERSEDE:
            key = entry.get('published_public_state') or 'unknown'
            by_state[key] = by_state.get(key, 0) + 1
    body = json.dumps(ordered, sort_keys=True, separators=(',', ':'), default=str)
    return {
        'contract': CONTRACT,
        'mode': 'dry_run',
        'execution_authorized': False,
        'scope': dict(scope),
        'artifact_count': len(ordered),
        'action_counts': dict(sorted(counts.items())),
        'supersede_counts_by_published_state': dict(sorted(by_state.items())),
        'entries_digest': 'sha256:' + hashlib.sha256(body.encode('utf-8')).hexdigest(),
        'entries': ordered,
    }


def load_manifest_entries(start_date: date, end_date: date, *, session=None):
    """Read-only: classify every published Team State artifact in the window."""
    from models.share_artifact import LIFECYCLE_PUBLISHED, ShareArtifact
    from models.team_state_publication_proof import TeamStatePublicationProof
    from services.club_competition_status import resolve_club_competition_status
    from utils.db import db

    session = session or db.session
    artifacts = (
        session.query(ShareArtifact)
        .filter(ShareArtifact.artifact_type == 'team_state')
        .filter(ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED)
        .filter(ShareArtifact.product_date >= start_date)
        .filter(ShareArtifact.product_date <= end_date)
        .all()
    )
    proofs = {}
    entries = []
    for artifact in artifacts:
        snapshot_id = artifact.source_snapshot_id
        if snapshot_id not in proofs:
            row = (
                session.query(TeamStatePublicationProof)
                .filter(TeamStatePublicationProof.snapshot_id == snapshot_id)
                .first()
            )
            proofs[snapshot_id] = _mapping(row.proof) if row is not None else {}
        proof = proofs[snapshot_id]
        inputs = _mapping(
            _mapping(proof.get('snapshot_team_state_generation_inputs')).get(
                str(artifact.team_id)
            )
        )
        reference = _mapping(inputs.get('reference_dates')).get('availability_reference_date')
        try:
            reference_date = date.fromisoformat(str(reference)) if reference else None
        except ValueError:
            reference_date = None
        if reference_date is None and artifact.product_date is not None:
            reference_date = artifact.product_date + timedelta(days=1)
        competition = resolve_club_competition_status(
            artifact.team_id, reference_date, session=session,
        ).to_dict()
        payload = _mapping(artifact.payload)
        state = _mapping(_mapping(payload.get('public_copy')).get('state'))
        team = _mapping(payload.get('team'))
        entries.append(classify_artifact_for_correction(
            {
                'public_id': artifact.public_id,
                'team_id': artifact.team_id,
                'team_abbreviation': team.get('team_abbreviation'),
                'product_date': artifact.product_date,
                'source_snapshot_id': snapshot_id,
                'published_public_state': state.get('public_code'),
            },
            competition_status=competition,
            team_inputs=inputs or None,
        ))
    return entries


def static_inventory_entries(share_root) -> list[dict]:
    """Offline inventory of committed ``/share`` pages (no classification).

    The committed preview pages carry identity, state, and date but not the
    competition status or per-arm evidence a decision needs, so every entry is
    ``review_required`` with an explicit reason until the database dry run is
    executed. This only makes the candidate population reviewable.
    """
    import re
    from pathlib import Path

    meta = re.compile(r'<meta name="baseballos:([a-z-]+)" content="([^"]*)"')
    entries = []
    for page in sorted(Path(share_root).glob('*/index.html')):
        fields = dict(meta.findall(page.read_text(encoding='utf-8', errors='ignore')))
        if fields.get('artifact-type') != 'team_state':
            continue
        entries.append({
            'public_id': fields.get('public-id'),
            'team_id': None,
            'team_abbreviation': fields.get('team'),
            'product_date': fields.get('data-through'),
            'source_snapshot_id': int(fields['snapshot-id']) if fields.get('snapshot-id', '').isdigit() else None,
            'published_public_state': (fields.get('team-state') or '').lower() or None,
            'competition_status': None,
            'correction': None,
            'proposed_action': ACTION_REVIEW,
            'reasons': ['requires_database_dry_run'],
            'error_timing': None,
        })
    return entries
