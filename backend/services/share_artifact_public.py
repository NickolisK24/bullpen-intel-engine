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
    source_authority_type,
)
from services.public_bullpen_copy import PUBLIC_AVAILABILITY_STATUSES
from services.share_artifact_repository import get_share_artifact_by_public_id
from services.share_artifact_scope import scope_labels_for_authority
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
TEAM_SURFACE_VIEW = 'board'

def _publication_scope(artifact) -> dict:
    """Scope-aware public labels from the durable source-authority discriminator.

    Backend-owned copy, resolved from the artifact's DURABLE source-authority
    discriminator (subject_type) — never from the numeric source_snapshot_id — via
    the single centralized scope authority also used by the immutable card payload.
    """
    return scope_labels_for_authority(source_authority_type(artifact))


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

    return project_public_share_artifact(artifact, session=session)


def project_public_share_artifact(artifact, *, session=None) -> PublicArtifactResult:
    """Project one already-resolved artifact through the canonical public contract.

    This is the shared boundary for the permanent public-id read and the lazy
    Team Board share entry. It performs the same lifecycle and integrity checks
    either way; callers cannot bypass the public whitelist by resolving the
    artifact through another repository query first.
    """
    session = session or db.session
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


def _team_route(team_abbreviation) -> Optional[str]:
    """The current/live canonical team bullpen surface for this artifact's team.

    An approved first-party destination, still CONSTRUCTED HERE from constants —
    never an artifact-provided URL. The only artifact-derived part is the team's
    own frozen abbreviation, sanitised to the board's team-reference charset and
    used as a query value, so a historical Brewers artifact hands the reader the
    Brewers board rather than the league surface. An artifact with no stored
    abbreviation falls back to the bare route.
    """
    if not isinstance(team_abbreviation, str):
        return TEAM_SURFACE_ROUTE
    abbreviation = re.sub(r'[^A-Z0-9-]', '', team_abbreviation.strip().upper())
    if not abbreviation:
        return TEAM_SURFACE_ROUTE
    return (
        f'{TEAM_SURFACE_ROUTE}?view={TEAM_SURFACE_VIEW}&team={abbreviation}'
        '&source=share'
    )


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
        # Scope-aware public identity from the DURABLE discriminator (never the id).
        'publication_scope': _publication_scope(artifact),
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
            'team_url': _team_route(team.get('team_abbreviation')),
            'methodology_url': METHODOLOGY_ROUTE,
            'data_trust_url': DATA_TRUST_ROUTE,
        },
    }
    card = _card_view(artifact, document)
    if card is not None:
        view['card'] = card

    if artifact.lifecycle_state == LIFECYCLE_SUPERSEDED:
        view['superseded'] = _replacement_pointer(artifact, session)
    return view


def _public_reliever_row(row) -> dict:
    """Project one frozen reliever-evidence row, withholding non-public availability.

    Artifacts published before the card metrics projected availability froze the
    ENGINE state into this field, so historical payloads can carry ``Monitor`` or
    ``Avoid`` — words the public vocabulary owner reserves as engine-only. This
    module's contract is that it never exposes an internal-only field, so a value
    outside the approved public vocabulary is withheld rather than translated.

    Withheld, not remapped, deliberately. Remapping would re-author at read time
    what an immutable artifact actually published, and this boundary does not get
    to decide retroactively what a frozen claim meant. The renderer already shows
    an absent availability as a neutral dash, so a historical row keeps its name,
    workload, and rest facts and simply carries no availability claim.

    The stored payload is untouched either way — this projects a whitelisted view
    of it and mutates nothing.
    """
    projected = dict(_mapping(row))
    if projected.get('availability') not in PUBLIC_AVAILABILITY_STATUSES:
        projected.pop('availability', None)
    return projected


def _card_view(artifact, document: Mapping[str, Any]) -> Optional[dict]:
    """Project the immutable v1.2 ``card`` block for the code-rendered card.

    Reads only the frozen card block and a few artifact columns. It enriches the
    frozen ``artifact_context`` (scope + data_through, all deterministic) with the
    artifact's OWN ``generated_at`` / ``published_at`` from columns — those are not
    frozen into the immutable payload (they are unknown at build time), so the read
    supplies them. It composes no baseball meaning and mutates nothing.
    """
    card = document.get('card')
    if not isinstance(card, Mapping):
        return None

    context = _mapping(card.get('artifact_context'))
    artifact_context = {
        'publication_scope': context.get('publication_scope'),
        'publication_label': context.get('publication_label'),
        'historical_note': context.get('historical_note'),
        'data_through': context.get('data_through'),
        # Not frozen in the immutable payload — supplied from the artifact columns.
        'generated_at': _iso(artifact.created_at),
        'published_at': _iso(artifact.published_at),
    }

    return {
        'card_version': card.get('card_version'),
        'artifact_context': artifact_context,
        'team': dict(_mapping(card.get('team'))),
        'state': dict(_mapping(card.get('state'))),
        'readiness_summary': dict(_mapping(card.get('readiness_summary'))),
        'reliever_evidence': [_public_reliever_row(row) for row in (card.get('reliever_evidence') or ())],
        'trust': dict(_mapping(card.get('trust'))),
        'limitations': [str(item) for item in (card.get('limitations') or ())],
    }


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
