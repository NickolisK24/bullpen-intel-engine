"""Public, read-only Share Artifact read service (Share Cards SC-04).

The single canonical backend boundary that turns a published immutable Share
Artifact into a public-safe, integrity-verified, lifecycle-aware view model for
the permanent public citation page at ``/share/{public_id}``.

It NEVER recalculates baseball intelligence, invokes generation, mutates an
artifact, exposes internal-only fields, or falls back to live/current team data.
It reuses the existing repository, integrity verifier, lifecycle vocabulary, and
the immutable ``payload`` document — it owns none of those. The canonical
immutable artifact remains the sole source of meaning; this module only projects
a whitelisted public subset of it.

Lifecycle → outcome (one documented contract, shared by API + frontend):

* published  → ``ok`` (200) full public view
* superseded → ``superseded`` (200) original frozen view + replacement pointer
* withdrawn  → ``withdrawn`` (410) minimal audit-safe response, no meaning-bearing
               claim
* draft / unknown / malformed public_id → ``not_found`` (404); a draft is never
  publicly discoverable
* integrity mismatch / verifier error → ``integrity_error`` (503) fail closed; no
  altered meaning-bearing content is ever served
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from models.share_artifact import (
    LIFECYCLE_DRAFT,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_SUPERSEDED,
    LIFECYCLE_WITHDRAWN,
    ShareArtifactRelation,
)
from services.share_artifact_repository import get_share_artifact_by_public_id
from services.share_artifacts import verify_share_artifact_integrity
from services.team_state_public_copy import build_evidence_receipts
from services.team_state_public_vocabulary import (
    is_publishable_state,
    public_state_for,
)
from utils.db import db


logger = logging.getLogger(__name__)


# Public outcome vocabulary + the single HTTP mapping the API and page share.
RESULT_OK = 'ok'
RESULT_SUPERSEDED = 'superseded'
RESULT_WITHDRAWN = 'withdrawn'
RESULT_NOT_FOUND = 'not_found'
RESULT_INTEGRITY_ERROR = 'integrity_error'

HTTP_STATUS = {
    RESULT_OK: 200,
    RESULT_SUPERSEDED: 200,
    RESULT_WITHDRAWN: 410,
    RESULT_NOT_FOUND: 404,
    RESULT_INTEGRITY_ERROR: 503,
}

# public_id is an opaque token (see models.share_artifact); accept only a bounded
# URL-safe shape so a malformed id fails fast and never reaches a query as junk.
_PUBLIC_ID_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')

# Approved, first-party BaseballOS destinations only (no artifact-provided URLs are
# ever trusted as navigation targets — routes are constructed here from constants).
METHODOLOGY_ROUTE = '/methodology'
DATA_TRUST_ROUTE = '/trust'
TEAM_SURFACE_ROUTE = '/bullpen'


@dataclass(frozen=True)
class PublicArtifactResult:
    """The public read outcome: a status, its HTTP mapping, and a public view."""

    status: str
    view: Optional[dict] = None

    @property
    def http_status(self) -> int:
        return HTTP_STATUS[self.status]

    @property
    def is_ok(self) -> bool:
        return self.status in (RESULT_OK, RESULT_SUPERSEDED)


def is_valid_public_id(public_id: Any) -> bool:
    return isinstance(public_id, str) and bool(_PUBLIC_ID_RE.match(public_id))


def load_public_share_artifact(public_id: Any, *, session=None) -> PublicArtifactResult:
    """Resolve a publicly-routable artifact into a lifecycle-aware public result."""
    session = session or db.session

    if not is_valid_public_id(public_id):
        return PublicArtifactResult(RESULT_NOT_FOUND)

    # verify=False: we fetch the raw record and control verification ourselves so a
    # draft is a 404 (not discoverable) and an integrity failure is a fail-closed 503.
    artifact = get_share_artifact_by_public_id(public_id, verify=False, session=session)
    if artifact is None:
        return PublicArtifactResult(RESULT_NOT_FOUND)

    state = artifact.lifecycle_state

    # Draft existence must not be publicly discoverable.
    if state == LIFECYCLE_DRAFT:
        return PublicArtifactResult(RESULT_NOT_FOUND)

    # Withdrawn: 410 Gone with a minimal, audit-safe response — never the claim.
    if state == LIFECYCLE_WITHDRAWN:
        return PublicArtifactResult(RESULT_WITHDRAWN, _withdrawn_view(artifact, session))

    if state not in (LIFECYCLE_PUBLISHED, LIFECYCLE_SUPERSEDED):
        # Unknown/unsupported lifecycle — fail closed as not discoverable.
        return PublicArtifactResult(RESULT_NOT_FOUND)

    # Verify integrity BEFORE returning any meaning-bearing content. Fail closed.
    try:
        verify_share_artifact_integrity(artifact)
    except Exception:
        logger.exception(
            'Public share artifact integrity verification failed public_id=%s '
            'lifecycle=%s.', artifact.public_id, state,
        )
        return PublicArtifactResult(RESULT_INTEGRITY_ERROR)

    view = _public_view(artifact, session)
    if state == LIFECYCLE_SUPERSEDED:
        return PublicArtifactResult(RESULT_SUPERSEDED, view)
    return PublicArtifactResult(RESULT_OK, view)


# ---------------------------------------------------------------------------
# View-model construction (public field whitelist — reads only the immutable
# payload document + a few artifact columns; never the raw payload/internal ids).
# ---------------------------------------------------------------------------


def share_route(public_id: str) -> str:
    return f'/share/{public_id}'


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _team_route(team_id) -> Optional[str]:
    # The current/live canonical team bullpen surface (approved first-party route).
    # A constant approved destination — never an artifact-provided URL.
    return TEAM_SURFACE_ROUTE


def _public_state(team_state: Mapping[str, Any], public_copy: Mapping[str, Any]) -> Optional[dict]:
    """Reader-facing public Team State (Fresh/Stretched/Vulnerable) for the view.

    Revised (v1.1.0) artifacts carry the stored public state. Legacy (v1.0.0)
    artifacts have their internal status_code deterministically mapped at read
    time via the single backend-owned public vocabulary — a version-aware display
    of coded metadata that never mutates the stored document. Returns ``None`` if
    the internal status has no public state (never fabricates one).
    """
    stored = _mapping(public_copy.get('state'))
    if stored.get('public_code') and stored.get('public_label'):
        return {'public_code': stored['public_code'], 'public_label': stored['public_label']}
    status_code = team_state.get('status_code')
    if is_publishable_state(status_code):
        return public_state_for(status_code)
    return None


def _evidence_items(team_state: Mapping[str, Any], public_copy: Mapping[str, Any]) -> list:
    """Ordered, frozen, reader-facing evidence receipts from the immutable document.

    Revised artifacts carry stored reader-facing receipts. Legacy artifacts get a
    deterministic, version-aware reader-facing presentation of their coded
    constraint rows (label + count) from the single backend-owned mapping — never
    the raw internal enum and never the engine ``message``. Composes no new
    evidence and trusts no artifact-provided URL as a navigation target.
    """
    stored = public_copy.get('evidence')
    if isinstance(stored, (list, tuple)):
        return [dict(_mapping(item)) for item in stored]
    return build_evidence_receipts(team_state.get('constraints') or ())


def _legacy_trust_line(confidence) -> str:
    if confidence == 'high':
        return 'Verified from the current active bullpen and completed recent appearances.'
    if confidence == 'medium':
        return 'Based on the current active bullpen and its completed recent appearances.'
    return 'Based on the available current bullpen evidence.'


def _public_view(artifact, session) -> dict:
    document = _mapping(artifact.payload)
    team = _mapping(document.get('team'))
    authority = _mapping(document.get('authority'))
    team_state = _mapping(document.get('team_state'))
    trust = _mapping(document.get('trust'))
    public_copy = _mapping(document.get('public_copy'))
    revised = bool(public_copy)

    public_state = _public_state(team_state, public_copy)
    public_label = public_state['public_label'] if public_state else None
    team_name = team.get('team_name')

    if revised:
        copy = {
            'headline': public_copy.get('headline'),
            'why': public_copy.get('why'),
            'summary': public_copy.get('why'),
            'freshness_line': public_copy.get('freshness_line'),
            'trust_line': public_copy.get('trust_line'),
            'alt_text': public_copy.get('alt_text'),
            'description': public_copy.get('description'),
        }
        limitations = [str(item) for item in (public_copy.get('limitations') or [])]
    else:
        # Legacy: preserve the original stored read verbatim (historical fidelity);
        # only coded labels are mapped for reader-facing presentation.
        original = team_state.get('summary')
        headline = f'{team_name} bullpen — {public_label}' if (team_name and public_label) else team_name
        copy = {
            'headline': headline,
            'why': original,
            'summary': original,
            'freshness_line': None,
            'trust_line': _legacy_trust_line(trust.get('confidence')),
            'alt_text': None,
            'description': original,
        }
        limitations = [str(item) for item in (trust.get('limitations') or [])]

    view = {
        'public_id': artifact.public_id,
        'artifact_type': artifact.artifact_type,
        'schema_version': artifact.schema_version,
        'render_version': artifact.render_version,
        'payload_version': document.get('payload_version'),
        'revised': revised,
        'lifecycle_state': artifact.lifecycle_state,
        'is_historical': True,
        'generated_at': _iso(artifact.created_at),
        'published_at': _iso(artifact.published_at),
        'product_date': _iso(artifact.product_date),
        'team': {
            'team_id': team.get('team_id'),
            'team_name': team_name,
            'team_abbreviation': team.get('team_abbreviation'),
        },
        'authority': {
            'source_snapshot_id': authority.get('source_snapshot_id'),
            'source_sync_run_id': authority.get('source_sync_run_id'),
            'data_through': authority.get('data_through'),
            'published_at': authority.get('published_at'),
        },
        'team_state': {
            # status_code is internal; it is exposed only as an opaque data hook,
            # never rendered as reader-facing prose.
            'status_code': team_state.get('status_code'),
            'public_state': public_state['public_code'] if public_state else None,
            'public_label': public_label,
            'summary': team_state.get('summary'),
            'contract_state': team_state.get('contract_state'),
        },
        'trust': {
            'confidence': trust.get('confidence'),
            'data_state': trust.get('data_state'),
            'freshness_state': trust.get('freshness_state'),
            'trust_state': trust.get('trust_state'),
        },
        'freshness': {
            'data_through': authority.get('data_through'),
            'published_at': _iso(artifact.published_at),
        },
        'evidence': _evidence_items(team_state, public_copy),
        'limitations': limitations,
        'copy': copy,
        'routes': {
            'share_url': share_route(artifact.public_id),
            'team_url': _team_route(team.get('team_id') or artifact.team_id),
            'methodology_url': METHODOLOGY_ROUTE,
            'data_trust_url': DATA_TRUST_ROUTE,
        },
    }
    if artifact.lifecycle_state == LIFECYCLE_SUPERSEDED:
        view['superseded'] = _replacement_pointer(artifact, session)
    return view


def _replacement_pointer(artifact, session) -> dict:
    """The public pointer to the newer artifact that superseded this one.

    A ``supersedes`` relation points source (newer) → target (older). For this
    superseded (older) artifact, the incoming supersedes relation's source is the
    replacement. Only a still-routable replacement public_id is exposed.
    """
    replacement_public_id = None
    relation = (
        session.query(ShareArtifactRelation)
        .filter(
            ShareArtifactRelation.target_artifact_id == artifact.id,
            ShareArtifactRelation.relation_type == ShareArtifactRelation.RELATION_SUPERSEDES,
        )
        .order_by(ShareArtifactRelation.id.desc())
        .first()
    )
    if relation is not None and relation.source_artifact is not None:
        source = relation.source_artifact
        if source.lifecycle_state in (LIFECYCLE_PUBLISHED, LIFECYCLE_SUPERSEDED):
            replacement_public_id = source.public_id
    return {
        'lifecycle_state': LIFECYCLE_SUPERSEDED,
        'superseded_at': _iso(artifact.superseded_at),
        'replacement_public_id': replacement_public_id,
        'replacement_url': share_route(replacement_public_id) if replacement_public_id else None,
        'notice': 'This is the original published artifact and remains unchanged; a newer artifact has since superseded it.',
    }


def _withdrawn_view(artifact, session) -> dict:
    """Minimal, audit-safe withdrawn response — never the meaning-bearing claim."""
    return {
        'public_id': artifact.public_id,
        'lifecycle_state': LIFECYCLE_WITHDRAWN,
        'withdrawn_reason': artifact.withdrawn_reason,
        'routes': {'home_url': '/'},
    }
