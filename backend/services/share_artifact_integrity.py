"""Deterministic normalization, integrity hashing, and equivalence for share
artifacts (Share Cards — sprint SC-01).

Two derived fingerprints anchor the immutable domain:

* **equivalence_key** — a hash over an artifact's *shareable substance*
  (identity, normalized payload, cited evidence, render version, trust
  metadata). It is available from draft time and drives deduplication: two
  independently built artifacts with identical substance produce the same
  equivalence key.

* **integrity_hash** — a hash over the equivalence document *plus* the
  per-instance identity (``artifact_uid``) and the captured ``published_at``
  timestamp. It binds one published instance so that any later tampering with
  payload, evidence, timestamps, render version, or trust metadata is detected
  and fails closed at verification time.

Everything here is pure: no database, no models, no side effects. This keeps
hash stability trivially testable and independent of persistence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from utils.time import to_utc_iso


INTEGRITY_HASH_ALGORITHM = 'sha256'


class ShareArtifactIntegrityError(Exception):
    """Raised when an artifact's content does not match its integrity hash.

    Integrity is a fail-closed guarantee: callers verifying a published
    artifact must treat this exception as a refusal, never as a warning.
    """


def _normalize(value: Any) -> Any:
    """Recursively coerce a JSON-ish value into a canonical, ordered form.

    * ``Mapping`` keys are stringified and sorted (order-independent).
    * ``Sequence`` order is preserved — list position is meaningful content.
    * ``date`` / ``datetime`` become explicit-UTC ISO strings.

    The result is composed only of JSON-native primitives, so it is both safe
    to persist in a JSON column and stable to serialize.
    """
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (datetime, date)):
        return to_utc_iso(value)
    return value


def to_json_safe(value: Any) -> Any:
    """Public alias: normalize a value into a JSON-serializable canonical form."""
    return _normalize(value)


def canonical_json(value: Any) -> str:
    """Serialize a value into its canonical, deterministic JSON string."""
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        default=str,
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalize_evidence_entries(entries: Sequence[Mapping]) -> list:
    """Return the canonical, order-stable list of evidence entries for hashing.

    Only the fields that constitute an evidence citation's *meaning* are kept.
    Soft provenance pointers (e.g. ``evidence_object_id``) are intentionally
    excluded so that re-keying an upstream evidence row never changes an
    artifact's identity.
    """
    normalized = []
    for entry in entries or ():
        sort_index = entry.get('sort_index')
        normalized.append({
            'evidence_key': entry.get('evidence_key'),
            'role': entry.get('role'),
            'claim': entry.get('claim'),
            'completeness_state': entry.get('completeness_state'),
            'snapshot': _normalize(entry.get('snapshot')),
            'sort_index': sort_index if sort_index is not None else 0,
        })
    normalized.sort(
        key=lambda item: (
            item['sort_index'],
            str(item['evidence_key']),
            str(item['role']),
        )
    )
    return normalized


def build_equivalence_document(
    *,
    artifact_type: str,
    render_version: int,
    subject_type: str,
    subject_key: str,
    product_date,
    payload,
    evidence_entries: Sequence[Mapping],
    trust_metadata,
    schema_version: int,
) -> dict:
    """Assemble the canonical document that defines an artifact's equivalence."""
    return {
        'schema_version': schema_version,
        'artifact_type': artifact_type,
        'render_version': render_version,
        'subject_type': subject_type,
        'subject_key': subject_key,
        'product_date': to_utc_iso(product_date) if product_date is not None else None,
        'payload': _normalize(payload),
        'evidence': normalize_evidence_entries(evidence_entries),
        'trust_metadata': _normalize(trust_metadata or {}),
    }


def compute_equivalence_key(**kwargs) -> str:
    """Deterministic equivalence key over an artifact's shareable substance."""
    return _sha256(canonical_json(build_equivalence_document(**kwargs)))


def build_integrity_document(
    *,
    artifact_uid: str,
    published_at,
    **equivalence_kwargs,
) -> dict:
    """The equivalence document plus per-instance identity and publish time."""
    document = build_equivalence_document(**equivalence_kwargs)
    document['artifact_uid'] = artifact_uid
    document['published_at'] = (
        to_utc_iso(published_at) if published_at is not None else None
    )
    return document


def compute_integrity_hash(
    *,
    artifact_uid: str,
    published_at,
    **equivalence_kwargs,
) -> str:
    """Deterministic integrity hash binding one published artifact instance."""
    document = build_integrity_document(
        artifact_uid=artifact_uid,
        published_at=published_at,
        **equivalence_kwargs,
    )
    return _sha256(canonical_json(document))
