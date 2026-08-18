"""Team State vNext production proof — an env-gated side-channel evidence artifact.

The immutable Team State Share Artifact deliberately carries no
``team_state_evidence``, no ``contract_version``, and no partition (see
``services.team_state_payload``, and the test that pins that omission). That is the
right shape for a published document and the wrong shape for proving what the
runtime actually did: the evidence vector exists for the length of one generation
call and is then gone. Diagnosing snapshot 437 required reading a committed HTML
preview page, because nothing else survived.

This module observes the exact runtime objects of one natural publication, from
inside the post-publication hook, and writes them to a JSON file for a workflow to
upload. It changes no artifact, no schema, and no publication behavior:

* it runs only when ``TEAM_STATE_VNEXT_PROOF_PATH`` is set, so the deployed web
  process and every test are unaffected by default;
* it runs after the publication transaction has already committed, so it cannot
  roll back, unpublish, or alter anything;
* it never raises — a proof problem must never become a publication problem;
* it observes; it does not recompute. Team State is never re-derived from later
  pitcher rows, and the reference dates are the ones the resolver recorded as it
  used them, not a re-derivation of what they should have been.

The proof answers, for one publication, eight questions. Seven are the original
vNext gate. The eighth, ``reference_date_alignment``, exists because the first
natural publication would have passed all seven while classifying the whole league
a day early (D-056).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import date, datetime
from fractions import Fraction
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


CAPABILITY = 'team_state_vnext_production_proof'
CONTRACT = 'team_state_vnext_production_proof_v1'
SCHEMA_VERSION = '1.0.0'
OBSERVATION_MODE = 'in_process_publication_hook'

# Set by the workflow step that runs the publication. Unset -> this module does
# nothing at all.
PROOF_PATH_ENV = 'TEAM_STATE_VNEXT_PROOF_PATH'
# Optional. The already-passed v3_phase_4 -> v3_phase_5 boundary publication whose
# frozen What Changed block is carried as historical boundary evidence. Never
# hard-coded here: the boundary is a fact about production, not about this module.
BOUNDARY_SNAPSHOT_ENV = 'TEAM_STATE_VNEXT_BOUNDARY_SNAPSHOT_ID'

EXPECTED_METHOD_VERSION = 'v3_phase_5'

RESULT_PASS = 'PASS'
RESULT_FAIL = 'FAIL'
RESULT_INCONCLUSIVE = 'INCONCLUSIVE'

VERDICT_PASS = 'PASS'
VERDICT_PASS_WITH_INCONCLUSIVE = 'PASS_WITH_INCONCLUSIVE'
VERDICT_FAIL = 'FAIL'

INVARIANTS = (
    'all_teams_published',
    'method_version_observed',
    'partition_integrity',
    'team_state_evidence_complete',
    'reference_date_alignment',
    'distribution_consistent',
    'no_historical_rewrite',
    'no_false_cross_version_change',
)

# The evidence vector keys a complete production capture must carry. Sourced from
# the vector the classifier actually emits; a narrowing of that contract should be
# caught here rather than silently reducing what the proof can show.
REQUIRED_EVIDENCE_KEYS = (
    'method_version', 'contract', 'basis', 'readiness_status_code',
    'active_pitcher_count', 'clean_count', 'moderate_count', 'severe_count',
    'unknown_count', 'clean_share', 'moderate_share', 'severe_share',
    'unknown_share', 'decisive_rule', 'decisive_inputs', 'thresholds_applied',
    'trust_state', 'trust_data_state', 'freshness_state', 'material_limitations',
    'evidence_references',
)

# Public Team State vocabulary, for the league tally.
PUBLIC_STATES = ('fresh', 'stretched', 'vulnerable')

# Bound on the changed-artifact detail emitted when the historical inventory moves.
# The digests prove the fact; the list is there to make it actionable.
MAX_CHANGED_ENTRIES = 50

# Team State vocabulary a What Changed payload must never contain. A Team State
# transition is not a What Changed change type, and the method-version boundary
# must not be able to manufacture one.
TEAM_STATE_TOKENS = (
    'Fresh', 'Stretched', 'Vulnerable', 'team_state',
    'operationally_stable', 'operationally_constrained', 'operationally_stressed',
)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


class ProofCollector:
    """Records each per-team generation result as the batch produces it.

    Installed through the generation seam the publication hook already exposes
    (``run_post_publication_generation(snapshot, generator=...)``), so the batch,
    the single-team service, and the classifier are all unchanged and unaware.
    """

    def __init__(self):
        self.results = []

    def wrap(self, generate):
        def _generate(team_id, **kwargs):
            result = generate(team_id, **kwargs)
            try:
                self.results.append((team_id, result))
            except Exception:  # pragma: no cover - defensive
                logger.exception('Team State proof collection failed for team_id=%s.', team_id)
            return result
        return _generate


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _json_safe(value):
    """Canonical, JSON-serializable form. Dict key order is left to the writer."""
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _digest(value) -> str:
    import json
    return 'sha256:' + hashlib.sha256(
        json.dumps(_json_safe(value), sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


# ---------------------------------------------------------------------------
# Per-team entries
# ---------------------------------------------------------------------------


def _published_public_state(artifact) -> Optional[str]:
    """The public Team State frozen into the published artifact, or ``None``.

    Read from the document the reader receives, not re-projected from the internal
    status code, so the proof can compare the two rather than assume they agree.
    """
    payload = getattr(artifact, 'payload', None)
    public_copy = _mapping(_mapping(payload).get('public_copy'))
    state = _mapping(public_copy.get('state'))
    return state.get('public_code')


def _reproduce_contract_a(evidence: Mapping[str, Any]) -> dict:
    """Re-derive the state from the RECORDED partition and RECORDED thresholds.

    Pure arithmetic over values already in the artifact — no database read, no
    re-classification. This is what makes the method-version claim a behavioral
    observation rather than a stamp check: the retired worst-arm-wins aggregation
    cannot reproduce these outcomes from these partitions.
    """
    thresholds = _mapping(evidence.get('thresholds_applied'))
    total = evidence.get('active_pitcher_count')
    clean = evidence.get('clean_count')
    severe = evidence.get('severe_count')
    if not isinstance(total, int) or not total or not isinstance(clean, int) or not isinstance(severe, int):
        return {'reproduced': None, 'status_code': None, 'decisive_rule': None,
                'reason': 'no_partition_recorded'}
    try:
        clean_share_min = Fraction(*thresholds['clean_share_fresh_min'])
        severe_share_min = Fraction(*thresholds['severe_share_vulnerable_min'])
        clean_count_min = int(thresholds['clean_count_fresh_min'])
        severe_count_max = int(thresholds['severe_count_fresh_max'])
        clean_count_vulnerable_max = int(thresholds['clean_count_vulnerable_max'])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return {'reproduced': None, 'status_code': None, 'decisive_rule': None,
                'reason': 'thresholds_unreadable'}

    if clean <= clean_count_vulnerable_max:
        status_code, rule = 'operationally_stressed', 'margin_floor'
    elif Fraction(severe, total) >= severe_share_min:
        status_code, rule = 'operationally_stressed', 'severity_share'
    elif (
        Fraction(clean, total) >= clean_share_min
        and clean >= clean_count_min
        and severe <= severe_count_max
    ):
        status_code, rule = 'operationally_stable', 'fresh_coverage'
    else:
        status_code, rule = 'operationally_constrained', 'residual_stretched'

    return {
        'reproduced': (
            status_code == evidence.get('readiness_status_code')
            and rule == evidence.get('decisive_rule')
        ),
        'status_code': status_code,
        'decisive_rule': rule,
        'reason': None,
    }


def build_team_entry(team_id, result, *, expected_availability_reference_date=None,
                     data_through=None) -> dict:
    """One team's complete production evidence, from the objects that produced it."""
    readiness = _mapping(getattr(result, 'readiness', None))
    evidence = _mapping(readiness.get('team_state_evidence'))
    status_code = _mapping(readiness.get('readiness')).get('status_code')
    public_state = _published_public_state(getattr(result, 'artifact', None))

    total = evidence.get('active_pitcher_count')
    parts = [evidence.get(key) for key in
             ('clean_count', 'moderate_count', 'severe_count', 'unknown_count')]
    if all(isinstance(part, int) for part in parts) and isinstance(total, int):
        partition_sum = sum(parts)
        invariant_holds = partition_sum == total
        invariant_state = 'evaluated'
    else:
        # A refused / data-limited read records a null partition by design. That is
        # not a violation, and it must never be counted as a pass either.
        partition_sum = None
        invariant_holds = None
        invariant_state = 'not_applicable'

    membership_reference_date = getattr(result, 'membership_reference_date', None)
    availability_reference_date = getattr(result, 'availability_reference_date', None)
    alignment = _reference_date_alignment(
        membership_reference_date, availability_reference_date,
        data_through=data_through,
        expected_availability=expected_availability_reference_date,
    )

    return {
        'team_id': team_id,
        'outcome': getattr(result, 'outcome', None),
        'public_id': getattr(result, 'public_id', None),
        'artifact_payload_version': getattr(result, 'payload_version', None),
        'source_snapshot_id': getattr(result, 'source_snapshot_id', None),
        'source_sync_run_id': getattr(result, 'source_sync_run_id', None),
        'product_date': _iso(getattr(result, 'product_date', None)),
        'final_team_state': {
            'readiness_status_code': status_code,
            'published_public_state': public_state,
            'public_state_matches_status_code': _public_state_matches(status_code, public_state),
        },
        'contract_version': readiness.get('contract_version'),
        'method_version': evidence.get('method_version'),
        'method_version_matches_expected': (
            evidence.get('method_version') == EXPECTED_METHOD_VERSION
            and readiness.get('contract_version') == EXPECTED_METHOD_VERSION
        ),
        'active_pitcher_count': total,
        'partition': {
            'clean_count': evidence.get('clean_count'),
            'moderate_count': evidence.get('moderate_count'),
            'severe_count': evidence.get('severe_count'),
            'unknown_count': evidence.get('unknown_count'),
        },
        'partition_sum': partition_sum,
        'partition_invariant_holds': invariant_holds,
        'partition_invariant_state': invariant_state,
        'decisive_rule': evidence.get('decisive_rule'),
        'decisive_inputs': _json_safe(evidence.get('decisive_inputs')),
        'thresholds_applied': _json_safe(evidence.get('thresholds_applied')),
        'contract_a_reproduction': _reproduce_contract_a(evidence),
        'membership_reference_date': _iso(membership_reference_date),
        'availability_reference_date': _iso(availability_reference_date),
        'reference_date_alignment': alignment,
        'evidence_keys_present': sorted(evidence),
        'evidence_complete': all(key in evidence for key in REQUIRED_EVIDENCE_KEYS),
        'team_state_evidence': _json_safe(evidence),
    }


def _public_state_matches(status_code, public_state) -> Optional[bool]:
    from services.team_state_public_vocabulary import INTERNAL_TO_PUBLIC_STATE

    if status_code is None or public_state is None:
        return None
    return INTERNAL_TO_PUBLIC_STATE.get(status_code) == public_state


def _reference_date_alignment(membership, availability, *, data_through,
                              expected_availability) -> dict:
    """Whether one team's read used the governed pair of reference dates (D-056).

    Membership must be the publication's slate; availability must be the canonical
    next-day reference the same slate resolves to. ``expected_availability`` is
    supplied by the shared authority rather than recomputed here, so the proof
    validates against the date owner instead of duplicating its rule.
    """
    membership_iso, availability_iso = _iso(membership), _iso(availability)
    slate_iso, expected_iso = _iso(data_through), _iso(expected_availability)
    if membership_iso is None or availability_iso is None:
        return {'aligned': None, 'reason': 'reference_dates_not_recorded',
                'expected_membership': slate_iso, 'expected_availability': expected_iso}
    membership_ok = slate_iso is not None and membership_iso == slate_iso
    availability_ok = expected_iso is not None and availability_iso == expected_iso
    return {
        'aligned': bool(membership_ok and availability_ok),
        'membership_matches_data_through': membership_ok,
        'availability_matches_canonical_next_day': availability_ok,
        'expected_membership': slate_iso,
        'expected_availability': expected_iso,
        'reason': None if (membership_ok and availability_ok) else 'reference_date_misaligned',
    }


# ---------------------------------------------------------------------------
# Historical immutability
# ---------------------------------------------------------------------------


def historical_team_state_inventory(exclude_source_snapshot_id, *, session=None) -> dict:
    """Identity + content + lifecycle of every PRIOR published Team State artifact.

    Four indexed columns, no payload load, and the stored ``integrity_hash`` is read
    rather than recomputed (recomputing a season of artifacts would not fit the
    daily final-phase budget). Taken once before generation and once after, the
    digests prove that publishing today's artifacts changed none of them — content,
    identity, or lifecycle, so a silent supersession is caught as well as a silent
    rewrite. Today's own artifacts are excluded: they are supposed to be new.
    """
    from models.share_artifact import ShareArtifact
    from utils.db import db

    session = session or db.session
    query = (
        session.query(
            ShareArtifact.id,
            ShareArtifact.public_id,
            ShareArtifact.integrity_hash,
            ShareArtifact.lifecycle_state,
            ShareArtifact.superseded_at,
        )
        .filter(ShareArtifact.artifact_type == 'team_state')
        .filter(ShareArtifact.lifecycle_state.in_(('published', 'superseded')))
    )
    if exclude_source_snapshot_id is not None:
        query = query.filter(ShareArtifact.source_snapshot_id != exclude_source_snapshot_id)

    entries = [
        [row[0], row[1], row[2], row[3], _iso(row[4])]
        for row in query.order_by(ShareArtifact.id).all()
    ]
    return {'entries': entries, 'count': len(entries), 'digest': _digest(entries)}


def _historical_block(before, after) -> dict:
    if before is None or after is None:
        return {
            'scope': 'published_team_state_share_artifacts_from_prior_publications',
            'window_scope': 'daily_league_publication_hook',
            'unchanged': None,
            'reason': 'inventory_unavailable',
        }
    before_by_id = {entry[0]: entry for entry in before['entries']}
    after_by_id = {entry[0]: entry for entry in after['entries']}
    changed = [
        {'artifact_id': artifact_id,
         'before': before_by_id.get(artifact_id),
         'after': after_by_id.get(artifact_id)}
        for artifact_id in sorted(set(before_by_id) | set(after_by_id))
        if before_by_id.get(artifact_id) != after_by_id.get(artifact_id)
    ]
    return {
        'scope': 'published_team_state_share_artifacts_from_prior_publications',
        'window_scope': 'daily_league_publication_hook',
        'selector': "artifact_type='team_state' AND lifecycle_state IN "
                    "('published','superseded') AND source_snapshot_id <> this_publication",
        'digest_algorithm': 'sha256(canonical_json([[id, public_id, integrity_hash, '
                            'lifecycle_state, superseded_at], ...]))',
        'artifact_count_before': before['count'],
        'artifact_count_after': after['count'],
        'inventory_digest_before': before['digest'],
        'inventory_digest_after': after['digest'],
        'unchanged': before['digest'] == after['digest'],
        'changed_entries': changed[:MAX_CHANGED_ENTRIES],
        'changed_entries_truncated': len(changed) > MAX_CHANGED_ENTRIES,
    }


# ---------------------------------------------------------------------------
# What Changed — current publication scan and the historical boundary
# ---------------------------------------------------------------------------


def scan_what_changed(block) -> dict:
    """Record the frozen What Changed payload and scan it for Team State vocabulary.

    The block is read from the published snapshot payload where the publication
    already froze it — no recomputation, and What Changed itself is untouched.
    """
    import json

    if not isinstance(block, Mapping):
        return {'available': False, 'reason': 'what_changed_block_absent'}
    serialized = json.dumps(_json_safe(block), sort_keys=True)
    changes = block.get('changes')
    changes = changes if isinstance(changes, (list, tuple)) else ()
    change_types = sorted({
        str(_mapping(change).get('change_type'))
        for change in changes if isinstance(change, Mapping)
    } - {'None'})
    return {
        'available': True,
        'source': 'dashboard_snapshot.payload.what_changed_since_yesterday',
        'state': block.get('state'),
        'change_count': block.get('change_count'),
        'change_types': change_types,
        'team_state_change_types_present': [
            change_type for change_type in change_types if 'team_state' in change_type
        ],
        'team_state_vocabulary_hits': [
            token for token in TEAM_STATE_TOKENS if token in serialized
        ],
        'scanned_tokens': list(TEAM_STATE_TOKENS),
    }


def _cross_version_block(current_block, boundary_snapshot_id, *, boundary_loader=None) -> dict:
    """The forward scan, the applicability verdict, and the historical boundary.

    The v3_phase_4 -> v3_phase_5 transition happened once, at the publication that
    first ran the new classifier. A later publication is v3_phase_5 -> v3_phase_5 and
    is NOT that boundary, so it reports ``applicable: false`` and resolves
    INCONCLUSIVE. Reporting PASS for a transition that did not occur would be the
    proof lying in the reassuring direction.

    No prior publication's method version is persisted anywhere, so applicability
    cannot be derived from production data; that is stated on the artifact rather
    than guessed at.
    """
    block = {
        'current_publication': scan_what_changed(current_block),
        'method_version_transition': {
            'applicable': False,
            'reason': 'no_method_version_transition_at_this_publication',
            'previous_publication_method_version': None,
            'previous_method_version_persisted': False,
        },
    }
    if boundary_snapshot_id is None:
        block['boundary_reference'] = {
            'available': False, 'reason': 'boundary_snapshot_not_supplied',
        }
        return block

    loader = boundary_loader or _load_snapshot
    try:
        boundary = loader(boundary_snapshot_id)
    except Exception:
        boundary = None
    if boundary is None:
        block['boundary_reference'] = {
            'available': False, 'reason': 'boundary_snapshot_not_found',
            'boundary_snapshot_id': boundary_snapshot_id,
        }
        return block

    payload = _mapping(getattr(boundary, 'payload', None))
    block['boundary_reference'] = {
        'available': True,
        'read_mode': 'frozen_published_snapshot_payload',
        'boundary_snapshot_id': getattr(boundary, 'id', None),
        'boundary_sync_run_id': getattr(boundary, 'sync_run_id', None),
        'boundary_data_through': _iso(getattr(boundary, 'data_through', None)),
        'scan': scan_what_changed(payload.get('what_changed_since_yesterday')),
    }
    return block


def _load_snapshot(snapshot_id):
    from models.dashboard_snapshot import DashboardSnapshot
    from utils.db import db

    return db.session.get(DashboardSnapshot, int(snapshot_id))


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def _invariant(result, detail, **extra) -> dict:
    return {'result': result, 'detail': detail, **extra}


def _evaluate_invariants(teams, *, expected_team_count, distribution, historical,
                         cross_version) -> dict:
    team_ids = [team['team_id'] for team in teams]
    duplicates = sorted({tid for tid in team_ids if team_ids.count(tid) > 1})
    complete = len(teams) == expected_team_count and not duplicates

    version_ok = [team for team in teams if team['method_version_matches_expected']]
    reproduced = [team for team in teams if team['contract_a_reproduction']['reproduced'] is True]
    evaluated = [team for team in teams if team['partition_invariant_state'] == 'evaluated']
    violations = [team for team in teams if team['partition_invariant_holds'] is False]
    not_applicable = [team for team in teams if team['partition_invariant_state'] == 'not_applicable']
    evidence_ok = [team for team in teams if team['evidence_complete']]
    aligned = [team for team in teams if team['reference_date_alignment'].get('aligned') is True]
    misaligned = [team for team in teams
                  if team['reference_date_alignment'].get('aligned') is not True]
    state_matches = [team for team in teams
                     if team['final_team_state']['public_state_matches_status_code'] is not False]

    current = cross_version.get('current_publication') or {}
    forward_clean = (
        current.get('available') is True
        and not current.get('team_state_change_types_present')
        and not current.get('team_state_vocabulary_hits')
    )

    return {
        'all_teams_published': _invariant(
            RESULT_PASS if complete else RESULT_FAIL,
            f'{len(teams)}/{expected_team_count} teams, {len(duplicates)} duplicate(s)',
            duplicate_team_ids=duplicates,
        ),
        'method_version_observed': _invariant(
            RESULT_PASS if teams and len(version_ok) == len(teams)
            and len(reproduced) == len(teams) else RESULT_FAIL,
            f'{len(version_ok)}/{len(teams)} stamped {EXPECTED_METHOD_VERSION}, '
            f'{len(reproduced)}/{len(teams)} reproduced from the recorded partition',
        ),
        'partition_integrity': _invariant(
            RESULT_FAIL if violations else (RESULT_PASS if evaluated else RESULT_INCONCLUSIVE),
            f'{len(evaluated)} evaluated, {len(not_applicable)} not_applicable, '
            f'{len(violations)} violation(s)',
            violating_team_ids=[team['team_id'] for team in violations],
        ),
        'team_state_evidence_complete': _invariant(
            RESULT_PASS if teams and len(evidence_ok) == len(teams) else RESULT_FAIL,
            f'{len(evidence_ok)}/{len(teams)} carry every required evidence key',
        ),
        'reference_date_alignment': _invariant(
            RESULT_PASS if teams and not misaligned else RESULT_FAIL,
            f'{len(aligned)}/{len(teams)} used membership=data_through and '
            f'availability=canonical next day (D-056)',
            misaligned_team_ids=[team['team_id'] for team in misaligned],
        ),
        'distribution_consistent': _invariant(
            RESULT_PASS if teams and len(state_matches) == len(teams) else RESULT_FAIL,
            f'{len(state_matches)}/{len(teams)} published states match their status code; '
            f'{distribution["fresh"]} Fresh / {distribution["stretched"]} Stretched / '
            f'{distribution["vulnerable"]} Vulnerable',
        ),
        'no_historical_rewrite': _invariant(
            {True: RESULT_PASS, False: RESULT_FAIL}.get(
                historical.get('unchanged'), RESULT_INCONCLUSIVE
            ),
            'prior published Team State artifacts unchanged across the publication'
            if historical.get('unchanged') else str(historical.get('reason') or 'inventory moved'),
        ),
        'no_false_cross_version_change': _invariant(
            RESULT_INCONCLUSIVE if forward_clean else RESULT_FAIL,
            'not a cross-version publication; forward scan found no Team State change '
            'type and no Team State vocabulary'
            if forward_clean else 'Team State vocabulary or change type present in the '
                                  'published change payload, or the block was unreadable',
        ),
    }


def _distribution(teams) -> dict:
    counts = {state: 0 for state in PUBLIC_STATES}
    withheld = 0
    for team in teams:
        state = team['final_team_state']['published_public_state']
        if state in counts:
            counts[state] += 1
        else:
            withheld += 1
    counts['withheld'] = withheld
    counts['total'] = len(teams)
    counts['source'] = 'published_artifact_public_copy'
    # A league in which no team is Fresh is a strong claim. It is surfaced for human
    # review, not silently tallied and not treated as a classifier failure. No
    # baseball threshold is invented here.
    counts['distribution_degenerate'] = bool(teams) and counts['fresh'] == 0
    counts['degeneracy_note'] = (
        'No team published Fresh. Surfaced for human review; not an automatic failure.'
        if counts['distribution_degenerate'] else None
    )
    return counts


# ---------------------------------------------------------------------------
# The artifact
# ---------------------------------------------------------------------------


def build_proof(*, snapshot, teams, expected_team_count, historical_before=None,
                historical_after=None, boundary_snapshot_id=None, workflow=None,
                boundary_loader=None) -> dict:
    """Assemble the complete proof document for one publication."""
    from services.availability_reference_date import trusted_slate_reference_dates

    data_through = getattr(snapshot, 'data_through', None)
    _, expected_availability = trusted_slate_reference_dates(data_through)

    historical = _historical_block(historical_before, historical_after)
    payload = _mapping(getattr(snapshot, 'payload', None))
    cross_version = _cross_version_block(
        payload.get('what_changed_since_yesterday'), boundary_snapshot_id,
        boundary_loader=boundary_loader,
    )
    distribution = _distribution(teams)
    invariants = _evaluate_invariants(
        teams, expected_team_count=expected_team_count, distribution=distribution,
        historical=historical, cross_version=cross_version,
    )

    failed = sorted(
        name for name, block in invariants.items() if block['result'] == RESULT_FAIL
    )
    inconclusive = sorted(
        name for name, block in invariants.items() if block['result'] == RESULT_INCONCLUSIVE
    )
    if failed:
        verdict = VERDICT_FAIL
    elif inconclusive or distribution['distribution_degenerate']:
        verdict = VERDICT_PASS_WITH_INCONCLUSIVE
    else:
        verdict = VERDICT_PASS

    return {
        'capability': CAPABILITY,
        'contract': CONTRACT,
        'schema_version': SCHEMA_VERSION,
        'observation_mode': OBSERVATION_MODE,
        'reconstructed': False,
        'publication': {
            'dashboard_snapshot_id': getattr(snapshot, 'id', None),
            'sync_run_id': getattr(snapshot, 'sync_run_id', None),
            'data_through': _iso(data_through),
            'published_at': _iso(getattr(snapshot, 'published_at', None)),
            'snapshot_status': getattr(snapshot, 'status', None),
            'snapshot_is_published': bool(getattr(snapshot, 'is_published', False)),
            'expected_method_version': EXPECTED_METHOD_VERSION,
            'expected_membership_reference_date': _iso(data_through),
            'expected_availability_reference_date': _iso(expected_availability),
            'workflow': workflow or _workflow_context(),
        },
        'batch': {
            'expected_team_count': expected_team_count,
            'captured_team_count': len(teams),
            'outcomes': _outcome_counts(teams),
        },
        'distribution': distribution,
        'teams': sorted(teams, key=lambda team: (team['team_id'] is None, team['team_id'])),
        'historical_immutability': historical,
        'cross_version_what_changed': cross_version,
        'invariants': invariants,
        'assertions_expected': len(INVARIANTS),
        'assertions_evaluated': len([name for name in INVARIANTS if name in invariants]),
        'failed_assertions': failed,
        'inconclusive_assertions': inconclusive,
        'overall_verdict': verdict,
    }


def _outcome_counts(teams) -> dict:
    counts = {}
    for team in teams:
        counts[str(team.get('outcome'))] = counts.get(str(team.get('outcome')), 0) + 1
    return dict(sorted(counts.items()))


def _workflow_context() -> dict:
    """GitHub Actions provenance. Traceability only — never accepted as proof."""
    return {
        'run_id': os.environ.get('GITHUB_RUN_ID') or None,
        'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT') or None,
        'source_sha': os.environ.get('GITHUB_SHA') or None,
        'note': 'provenance only; not accepted as method-version proof',
    }


# ---------------------------------------------------------------------------
# Orchestration from the publication hook
# ---------------------------------------------------------------------------


def proof_path() -> Optional[str]:
    return os.environ.get(PROOF_PATH_ENV) or None


def boundary_snapshot_id() -> Optional[int]:
    raw = os.environ.get(BOUNDARY_SNAPSHOT_ENV)
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def capture_publication_proof(snapshot, *, generator=None, path=None) -> Optional[dict]:
    """Run post-publication generation under observation and write the proof.

    Returns the proof document, or ``None`` when proof capture is off or could not
    run. Never raises: the publication has already committed and a proof problem
    must not become a publication problem. When ``TEAM_STATE_VNEXT_PROOF_PATH`` is
    unset this returns ``None`` without touching anything, which is the deployed
    default everywhere except the workflow step that asks for evidence.
    """
    from services.share_artifact_publication_hook import run_post_publication_generation

    destination = path or proof_path()
    if not destination:
        return None

    collector = ProofCollector()
    before = after = None
    snapshot_id = getattr(snapshot, 'id', None)
    try:
        before = historical_team_state_inventory(snapshot_id)
    except Exception:
        logger.exception('Team State proof: pre-publication inventory failed.')

    base_generator = generator
    if base_generator is None:
        from services.share_artifact_generation import generate_team_state_artifact
        base_generator = generate_team_state_artifact
    batch = run_post_publication_generation(snapshot, generator=collector.wrap(base_generator))

    try:
        after = historical_team_state_inventory(snapshot_id)
    except Exception:
        logger.exception('Team State proof: post-publication inventory failed.')

    try:
        from services.availability_reference_date import trusted_slate_reference_dates
        data_through = getattr(snapshot, 'data_through', None)
        _, expected_availability = trusted_slate_reference_dates(data_through)
        teams = [
            build_team_entry(
                team_id, result,
                expected_availability_reference_date=expected_availability,
                data_through=data_through,
            )
            for team_id, result in collector.results
            if result is not None
        ]
        expected_team_count = (
            getattr(batch, 'canonical_team_count', None)
            if batch is not None else None
        ) or len(teams)
        proof = build_proof(
            snapshot=snapshot, teams=teams, expected_team_count=expected_team_count,
            historical_before=before, historical_after=after,
            boundary_snapshot_id=boundary_snapshot_id(),
        )
        write_proof(proof, destination)
    except Exception:
        logger.exception('Team State proof capture failed non-fatally.')
        return None

    logger.info(
        'Team State vNext production proof written snapshot_id=%s teams=%s verdict=%s.',
        snapshot_id, len(proof['teams']), proof['overall_verdict'],
    )
    return proof


def write_proof(proof, path) -> None:
    """Write the proof deterministically, reusing the runners' evidence writer."""
    from utils.summary_output import write_summary

    write_summary(_json_safe(proof), path)
