"""Canonical resolver for trusted current governed evidence by (subject, date)
(Share Cards SC-03B-01, Workstream A).

Before this module, the same governed ``EvidenceObject`` authority query was
spelled out inline in two internal readers that were byte-for-byte identical
except for the subject type:

  * ``services.internal_team_evidence._evidence_objects``      (subject_type 'team')
  * ``services.internal_pitcher_evidence._evidence_objects``   (subject_type 'pitcher')

Both also duplicated the identical "merge in the evidence cited by the composed
read, then re-sort by the governed key" step (``_cited_evidence_objects``). This
module owns exactly that one authority — nothing more:

  subject identity  : subject_type + subject_id == str(id)   (exact, no fallback)
  product date      : product_date == the trusted, caller-resolved reference date
                      (exact equality — never a different date's rows)
  trust / freshness : recompute_status == RECOMPUTE_CURRENT   (excludes stale /
                      superseded / needing-recompute rows)
  public eligibility: posture == the governed posture (today every stored row is
                      ``internal_only``; the classification -> public posture
                      mapping does not exist yet and is deliberately NOT invented
                      here)
  ordering          : (evidence_type, rule_id, id) ascending  (the governed order
                      both readers already used)

It intentionally does NOT own evidence *policy*: the rule -> classification
verdicts live in ``services.evidence_classification`` and are untouched. It moves
no presentation/formatting, invents no snapshot cross-check the readers never
had, and never substitutes a different date/subject/stale row for a missing one
(a no-match yields an empty list, the existing "no trusted evidence" outcome).

The two internal_* readers with *drifted* behavior on purpose
(``team_daily_read._team_evidence`` / ``reliever_daily_read._pitcher_evidence``,
which deliberately include superseded rows and flag them with a governed reason
code) are NOT migrated here — folding them in would silently drop that governed
nuance.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import asc
from sqlalchemy.orm import selectinload

from models.evidence_contract import EvidenceObject


# The governed posture for the stored evidence these readers surface. Today every
# EvidenceObject is registered ``internal_only`` (the rule -> public-candidate
# classification in services.evidence_classification is advisory rule metadata,
# not yet a stored-row posture), so this is the exact filter the readers used.
DEFAULT_EVIDENCE_POSTURE = EvidenceObject.POSTURE_INTERNAL_ONLY

# Known subject types for governed subject evidence.
SUBJECT_TYPE_TEAM = 'team'
SUBJECT_TYPE_PITCHER = 'pitcher'


class EvidenceAuthorityError(ValueError):
    """The evidence-authority request itself is malformed.

    Raised (rather than silently returning no rows) so a bad subject/date can
    never masquerade as "no trusted evidence".
    """


def _evidence_sort_key(row):
    return (row.evidence_type or '', row.rule_id or '', row.id or 0)


def cited_evidence_objects(read) -> list:
    """Distinct evidence objects cited by a composed read, in governed order.

    Deterministic: components by name, citations by id, first occurrence wins.
    Duck-typed on ``read`` (a ``ComposedRead`` or ``None``) so this module does
    not depend on the read model. Returns ``[]`` when ``read`` is ``None``.
    """
    if read is None:
        return []
    rows = []
    seen = set()
    for component in sorted(read.components or [], key=lambda row: row.component_name):
        for citation in sorted(component.evidence_citations or [], key=lambda row: row.id or 0):
            evidence = citation.evidence_object
            if evidence is None or evidence.id in seen:
                continue
            rows.append(evidence)
            seen.add(evidence.id)
    return rows


def resolve_subject_current_evidence(
    subject_type: str,
    subject_id,
    product_date: date,
    *,
    read=None,
    posture: str = DEFAULT_EVIDENCE_POSTURE,
) -> list:
    """Resolve the trusted, current governed evidence for one subject + date.

    This is the single canonical owner of the governed authority query. It
    returns the current in-posture rows for the exact ``(subject_type,
    subject_id, product_date)``, merged with any evidence cited by the supplied
    composed ``read`` (deduped), sorted by the governed ``(evidence_type,
    rule_id, id)`` key. A no-match returns an empty list — it never falls back to
    a different date, subject, or stale/superseded row.

    Fails closed on malformed input (``EvidenceAuthorityError``).
    """
    if not subject_type or not isinstance(subject_type, str):
        raise EvidenceAuthorityError('invalid_subject_type')
    if subject_id is None or str(subject_id) == '':
        raise EvidenceAuthorityError('invalid_subject_id')
    if not isinstance(product_date, date):
        raise EvidenceAuthorityError('invalid_product_date')

    rows = (
        EvidenceObject.query
        .options(selectinload(EvidenceObject.citations))
        .filter(EvidenceObject.subject_type == subject_type)
        .filter(EvidenceObject.subject_id == str(subject_id))
        .filter(EvidenceObject.product_date == product_date)
        .filter(EvidenceObject.posture == posture)
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(
            asc(EvidenceObject.evidence_type),
            asc(EvidenceObject.rule_id),
            asc(EvidenceObject.id),
        )
        .all()
    )
    by_id = {row.id: row for row in rows}
    for row in cited_evidence_objects(read):
        if row is not None:
            by_id.setdefault(row.id, row)
    return sorted(by_id.values(), key=_evidence_sort_key)


def resolve_current_team_evidence(
    team_id: int, product_date: date, *, read=None,
) -> list:
    """Trusted current governed evidence for a team + product date."""
    return resolve_subject_current_evidence(
        SUBJECT_TYPE_TEAM, team_id, product_date, read=read,
    )


def resolve_current_pitcher_evidence(
    pitcher_id: int, product_date: date, *, read=None,
) -> list:
    """Trusted current governed evidence for a pitcher + product date."""
    return resolve_subject_current_evidence(
        SUBJECT_TYPE_PITCHER, pitcher_id, product_date, read=read,
    )
