"""Roster membership evidence scoped to the Phase 0E reliever daily read."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re

from sqlalchemy import desc

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.roster_status_snapshot import RosterStatusSnapshot
from services.evidence_contract import EvidenceCitationInput, build_evidence_object
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleRegistry,
)
from utils.db import db


RULE_VERSION = 1
EVIDENCE_SOURCE = 'phase0e:roster_membership_evidence'
PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID = 'pitcher_roster_membership_context'
ROSTER_MEMBERSHIP_RULE_IDS = (PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID,)

REASON_SNAPSHOT_MISSING = 'snapshot_missing'
REASON_SNAPSHOT_STALE = 'snapshot_stale'
REASON_SOURCE_FAMILY_NOT_READY = 'source_family_not_ready'
REASON_ROSTER_MEMBERSHIP_CORRECTED = 'roster_membership_source_corrected'

_FORBIDDEN_MEMBERSHIP_CLAIM_TERMS = (
    'availability',
    'available',
    'health',
    'healthy',
    'readiness',
    'ready',
    'role',
    'manager intent',
    'pressure',
    'leverage',
    'bet',
    'betting',
    'prediction',
    'score',
    'grade',
    'rank',
)

_RULE_DEFINITION = (
    "The pitcher's current roster membership fact from the roster snapshot "
    'authority: on the active roster or not on the active roster per the '
    'latest snapshot on the evidence date, with team and snapshot date cited. '
    'A snapshot older than the evidence date, or missing, makes membership '
    'UNKNOWN - never a carried-forward answer. This is a membership fact only: '
    'it implies nothing about availability, readiness, or health.'
)


@dataclass(frozen=True)
class BuiltRosterMembershipEvidence:
    evidence: EvidenceObject
    rule_id: str
    subject_key: str


_LOCAL_RULE_REGISTRY: EvidenceRuleRegistry | None = None
_LOCAL_TEMPLATE_REGISTRY: ClaimTemplateRegistry | None = None


def roster_membership_rule_ids() -> tuple[str, ...]:
    return ROSTER_MEMBERSHIP_RULE_IDS


def register_roster_membership_rules(
    *,
    registry: EvidenceRuleRegistry | None = None,
    template_registry: ClaimTemplateRegistry | None = None,
) -> tuple[EvidenceRuleRegistry, ClaimTemplateRegistry]:
    rule_registry = registry or EvidenceRuleRegistry()
    claim_registry = template_registry or ClaimTemplateRegistry()
    rule_registry.register(EvidenceRule(
        rule_id=PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID,
        rule_version=RULE_VERSION,
        evidence_type=PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID,
        plain_language_definition=_RULE_DEFINITION,
        required_input_families=('roster_status_snapshots',),
        required_cited_fields=(
            'roster_status_snapshots.snapshot_date',
            'roster_status_snapshots.active_roster',
            'roster_status_snapshots.team_id',
        ),
        allowed_completeness=(
            EvidenceObject.COMPLETENESS_COMPLETE,
            EvidenceObject.COMPLETENESS_UNKNOWN,
            EvidenceObject.COMPLETENESS_WITHHELD,
        ),
        posture_default=EvidenceObject.POSTURE_INTERNAL_ONLY,
    ))
    claim_registry.register(ClaimTemplate(
        template_id=_template_id(PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID),
        template_version=RULE_VERSION,
        template_text='{claim}',
    ))
    return rule_registry, claim_registry


def build_roster_membership_evidence(
    product_date,
    *,
    pitcher_ids,
    sync_run_id=None,
    source='manual',
    commit=False,
    restrict_evidence_keys: set[str] | None = None,
) -> dict:
    """Build read-scoped roster membership evidence for explicit pitchers only."""
    ref = _as_date(product_date)
    population = tuple(_dedupe_ints(pitcher_ids or ()))
    registry, templates = _local_registries()
    emitted = []

    for pitcher_id in population:
        built = _build_for_pitcher(
            pitcher_id=pitcher_id,
            product_date=ref,
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
        )
        if restrict_evidence_keys is not None and built.evidence.evidence_key not in restrict_evidence_keys:
            continue
        emitted.append(_upsert_evidence(built.evidence, sync_run_id=sync_run_id))

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return {
        'status': 'built',
        'product_date': ref.isoformat(),
        'rules': list(ROSTER_MEMBERSHIP_RULE_IDS),
        'pitchers_considered': len(population),
        'objects_built': len(emitted),
        'objects_created': sum(1 for item in emitted if item == 'created'),
        'objects_refreshed': sum(1 for item in emitted if item == 'refreshed'),
    }


def mark_roster_snapshot_correction_for_membership(
    snapshot,
    *,
    sync_run_id=None,
    reason_code=REASON_ROSTER_MEMBERSHIP_CORRECTED,
    batch_size=100,
) -> dict:
    if snapshot is None or getattr(snapshot, 'id', None) is None:
        return {'marked_count': 0, 'evidence_ids': []}
    from services.evidence_contract import mark_dependent_evidence_for_recompute

    return mark_dependent_evidence_for_recompute(
        source_table='roster_status_snapshots',
        source_pk=snapshot.id,
        reason_code=reason_code,
        batch_size=batch_size,
        sync_run_id=sync_run_id,
    )


def rebuild_marked_roster_membership_evidence(
    *,
    sync_run_id=None,
    source='manual',
    batch_size=100,
) -> dict:
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.rule_id.in_(ROSTER_MEMBERSHIP_RULE_IDS))
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_NEEDED)
        .order_by(EvidenceObject.product_date.asc(), EvidenceObject.id.asc())
        .limit(batch_size)
        .all()
    )
    if not rows:
        return {'status': 'noop', 'objects_rebuilt': 0, 'dates_rebuilt': []}

    keys_by_date: dict[date, set[str]] = {}
    pitchers_by_date: dict[date, set[int]] = {}
    for row in rows:
        keys_by_date.setdefault(row.product_date, set()).add(row.evidence_key)
        if row.subject_id is not None:
            pitchers_by_date.setdefault(row.product_date, set()).add(int(row.subject_id))

    rebuilt = 0
    for evidence_date, keys in keys_by_date.items():
        result = build_roster_membership_evidence(
            evidence_date,
            pitcher_ids=sorted(pitchers_by_date.get(evidence_date, set())),
            sync_run_id=sync_run_id,
            source=source,
            restrict_evidence_keys=keys,
        )
        rebuilt += result['objects_created'] + result['objects_refreshed']

    db.session.flush()
    return {
        'status': 'rebuilt',
        'objects_rebuilt': rebuilt,
        'dates_rebuilt': [day.isoformat() for day in sorted(keys_by_date)],
    }


def _local_registries():
    global _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY
    if _LOCAL_RULE_REGISTRY is None or _LOCAL_TEMPLATE_REGISTRY is None:
        _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY = register_roster_membership_rules()
    return _LOCAL_RULE_REGISTRY, _LOCAL_TEMPLATE_REGISTRY


def _build_for_pitcher(
    *,
    pitcher_id,
    product_date,
    registry,
    templates,
    sync_run_id,
    source,
) -> BuiltRosterMembershipEvidence:
    snapshot = _latest_snapshot(pitcher_id, product_date)
    if snapshot is None:
        claim = f'Roster membership unknown: {REASON_SNAPSHOT_MISSING}.'
        citation = _missing_snapshot_citation(pitcher_id, product_date)
        return _build_object(
            pitcher_id=pitcher_id,
            product_date=product_date,
            claim=claim,
            cited_inputs=(citation,),
            input_values={
                'roster_status_snapshots.snapshot_date': None,
                'roster_status_snapshots.active_roster': None,
                'roster_status_snapshots.team_id': None,
            },
            trace={
                'steps': ['Checked latest roster snapshot on or before the product date.'],
                'snapshot_found': False,
            },
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=(REASON_SNAPSHOT_MISSING,),
        )

    snapshot_age_days = (product_date - snapshot.snapshot_date).days
    if snapshot.snapshot_date != product_date:
        claim = f'Roster membership unknown: {REASON_SNAPSHOT_STALE}.'
        return _build_object(
            pitcher_id=pitcher_id,
            product_date=product_date,
            claim=claim,
            cited_inputs=(_snapshot_citation(snapshot, product_date),),
            input_values=_snapshot_input_values(snapshot),
            trace={
                'steps': ['Checked latest roster snapshot on or before the product date.'],
                'snapshot_found': True,
                'snapshot_date': snapshot.snapshot_date.isoformat(),
                'snapshot_age_days': snapshot_age_days,
            },
            registry=registry,
            templates=templates,
            sync_run_id=sync_run_id,
            source=source,
            state=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=(REASON_SNAPSHOT_STALE,),
        )

    if snapshot.active_roster:
        claim = (
            f'On the active roster per the {snapshot.snapshot_date.isoformat()} '
            f'snapshot (team {snapshot.team_id}).'
        )
    else:
        claim = f'Not on the active roster per the {snapshot.snapshot_date.isoformat()} snapshot.'

    return _build_object(
        pitcher_id=pitcher_id,
        product_date=product_date,
        claim=claim,
        cited_inputs=(_snapshot_citation(snapshot, product_date),),
        input_values=_snapshot_input_values(snapshot),
        trace={
            'steps': ['Checked same-day roster snapshot active-roster flag.'],
            'snapshot_found': True,
            'snapshot_date': snapshot.snapshot_date.isoformat(),
            'snapshot_age_days': snapshot_age_days,
            'active_roster': bool(snapshot.active_roster),
        },
        registry=registry,
        templates=templates,
        sync_run_id=sync_run_id,
        source=source,
    )


def _build_object(
    *,
    pitcher_id,
    product_date,
    claim,
    cited_inputs,
    input_values,
    trace,
    registry,
    templates,
    sync_run_id,
    source,
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=(),
) -> BuiltRosterMembershipEvidence:
    _assert_text_has_no_membership_forbidden_terms(claim)
    rule = registry.get(PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID, RULE_VERSION)
    template = templates.get(_template_id(rule.rule_id), RULE_VERSION)
    evidence = build_evidence_object(
        rule_id=rule.rule_id,
        rule_version=RULE_VERSION,
        claim_template=template,
        claim_values={'claim': claim},
        subject_type='pitcher',
        subject_id=pitcher_id,
        subject_key=f'pitcher:{pitcher_id}:{product_date.isoformat()}:roster-membership',
        product_date=product_date,
        cited_inputs=tuple(cited_inputs),
        computation_trace=trace,
        input_values=dict(input_values or {}),
        readiness_payload=_readiness_payload(),
        registry=registry,
        sync_run_id=sync_run_id,
        source=EVIDENCE_SOURCE,
    )
    if state != EvidenceObject.COMPLETENESS_COMPLETE or reason_codes:
        evidence.completeness_state = state
        evidence.reason_codes = _dedupe(reason_codes or [])
        evidence.rendered_claim = claim
    return BuiltRosterMembershipEvidence(
        evidence=evidence,
        rule_id=rule.rule_id,
        subject_key=evidence.subject_key,
    )


def _latest_snapshot(pitcher_id, product_date):
    return (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.pitcher_id == pitcher_id)
        .filter(RosterStatusSnapshot.snapshot_date <= product_date)
        .order_by(desc(RosterStatusSnapshot.snapshot_date), desc(RosterStatusSnapshot.id))
        .first()
    )


def _snapshot_input_values(snapshot):
    return {
        'roster_status_snapshots.snapshot_date': _iso(snapshot.snapshot_date),
        'roster_status_snapshots.active_roster': snapshot.active_roster,
        'roster_status_snapshots.team_id': snapshot.team_id,
    }


def _snapshot_citation(snapshot, product_date):
    fields = ('snapshot_date', 'active_roster', 'team_id', 'roster_status')
    return EvidenceCitationInput(
        source_family='roster_status_snapshots',
        source_table='roster_status_snapshots',
        source_pk=snapshot.id,
        source_field_names=fields,
        cited_values={
            field: _citation_value(getattr(snapshot, field, None))
            for field in fields
        } | {
            'snapshot_age_days': (product_date - snapshot.snapshot_date).days,
        },
        provenance={
            'source': snapshot.source,
            'sync_run_id': snapshot.sync_run_id,
            'correction_count': snapshot.correction_count or 0,
            'last_corrected_at': _iso(snapshot.last_corrected_at),
            'correction_source': snapshot.correction_source,
        },
    )


def _missing_snapshot_citation(pitcher_id, product_date):
    return EvidenceCitationInput(
        source_family='roster_status_snapshots',
        source_table='roster_status_snapshots',
        source_pk=f'missing:{pitcher_id}:{product_date.isoformat()}',
        source_field_names=('snapshot_date', 'active_roster', 'team_id'),
        cited_values={
            'pitcher_id': pitcher_id,
            'snapshot_date': None,
            'active_roster': None,
            'team_id': None,
            'product_date': product_date.isoformat(),
        },
        provenance={'source': 'roster_status_snapshots', 'missing': True},
    )


def _readiness_payload():
    return {
        'families': {
            'roster_status_snapshots': {'status': 'ready', 'reason_codes': []},
        }
    }


def _upsert_evidence(new_evidence, *, sync_run_id=None):
    existing = EvidenceObject.query.filter_by(evidence_key=new_evidence.evidence_key).first()
    if existing is None:
        db.session.add(new_evidence)
        db.session.flush()
        return 'created'

    prior_trace = {
        'rendered_claim': existing.rendered_claim,
        'completeness_state': existing.completeness_state,
        'reason_codes': list(existing.reason_codes or []),
        'invalidated_at': _iso(existing.invalidated_at),
        'invalidated_by_source_table': existing.invalidated_by_source_table,
        'invalidated_by_source_pk': existing.invalidated_by_source_pk,
    }
    for field in (
        'evidence_type',
        'subject_type',
        'subject_id',
        'subject_key',
        'product_date',
        'claim_template_id',
        'rendered_claim',
        'rule_id',
        'rule_version',
        'rule_definition_hash',
        'typed_cited_inputs',
        'computation_trace',
        'completeness_state',
        'reason_codes',
        'limitations',
        'posture',
        'source',
        'sync_run_id',
    ):
        setattr(existing, field, getattr(new_evidence, field))
    existing.computation_trace = dict(existing.computation_trace or {})
    existing.computation_trace['superseded_prior'] = prior_trace
    existing.recompute_status = EvidenceObject.RECOMPUTE_CURRENT
    existing.recompute_reason_codes = []
    existing.citations = [
        EvidenceCitation(
            source_family=citation.source_family,
            source_table=citation.source_table,
            source_pk=citation.source_pk,
            source_field_names=list(citation.source_field_names or []),
            citation_role=citation.citation_role,
            cited_values=dict(citation.cited_values or {}),
            provenance=dict(citation.provenance or {}),
        )
        for citation in new_evidence.citations
    ]
    db.session.add(existing)
    db.session.flush()
    _mark_dependent_reads_for_recompute(existing.id, sync_run_id=sync_run_id)
    return 'refreshed'


def _mark_dependent_reads_for_recompute(evidence_object_id, *, sync_run_id=None):
    from services.composed_read import mark_dependent_reads_for_recompute

    return mark_dependent_reads_for_recompute(
        evidence_object_ids=(evidence_object_id,),
        reason_code='component_evidence_superseded',
        sync_run_id=sync_run_id,
        correction_source=EVIDENCE_SOURCE,
    )


def _assert_text_has_no_membership_forbidden_terms(text):
    lowered = text.lower()
    for term in _FORBIDDEN_MEMBERSHIP_CLAIM_TERMS:
        if re.search(rf'\b{re.escape(term)}\b', lowered):
            raise EvidenceLanguageError(
                f'roster membership claim uses forbidden term: {term}'
            )
    return True


def _template_id(rule_id):
    return f'{rule_id}_claim'


def _as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _citation_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _dedupe(values):
    result = []
    seen = set()
    for value in values or []:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _dedupe_ints(values):
    result = []
    seen = set()
    for value in values or []:
        item = int(value)
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
