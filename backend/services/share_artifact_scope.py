"""Scope-aware public labels for a Share Artifact's source authority.

A single, backend-owned source of the reader-facing publication scope copy. The
scope is derived from the artifact's DURABLE source-authority discriminator
(``subject_type``) — never from the collision-prone numeric ``source_snapshot_id``.
A team-progressive artifact is published after one team's completed game; a league
artifact comes from a synchronized BaseballOS league snapshot.

Both the public read projection (``services.share_artifact_public``) and the
immutable v1.2 card payload builder (``services.team_state_payload``) resolve scope
copy from here, so a frozen artifact and its public read describe the same scope in
the same words, and a numeric id collision can never change either.
"""

from __future__ import annotations

from typing import Optional

from models.share_artifact import (
    SOURCE_AUTHORITY_LEAGUE_SNAPSHOT,
    SOURCE_AUTHORITY_TEAM_PROGRESSIVE,
    SUBJECT_TYPE_TEAM_PROGRESSIVE,
)


# Keyed by the machine-readable source-authority type returned by
# ``models.share_artifact.source_authority_type``.
SCOPE_LABELS = {
    SOURCE_AUTHORITY_TEAM_PROGRESSIVE: {
        'publication_scope': SOURCE_AUTHORITY_TEAM_PROGRESSIVE,
        'display_label': 'Published Team Bullpen State',
        'context_label': "Updated after the team's completed game",
        'historical_note': (
            "This Team Bullpen State was published after the team's completed game "
            'and is preserved as a historical artifact.'
        ),
    },
    SOURCE_AUTHORITY_LEAGUE_SNAPSHOT: {
        'publication_scope': SOURCE_AUTHORITY_LEAGUE_SNAPSHOT,
        'display_label': 'Published BaseballOS Snapshot',
        'context_label': None,
        'historical_note': (
            'This Team Bullpen State comes from a synchronized BaseballOS league '
            'snapshot and is preserved as a historical artifact.'
        ),
    },
}


def scope_labels_for_authority(authority_type: str) -> dict:
    """Return a fresh scope-label dict for a machine-readable authority type."""
    return dict(SCOPE_LABELS[authority_type])


def scope_labels_for_subject_type(subject_type: Optional[str]) -> dict:
    """Return a fresh scope-label dict for a raw ``subject_type`` discriminator.

    Any subject_type that is not the team-progressive marker is a league snapshot —
    the same fail-safe mapping ``source_authority_type`` applies.
    """
    if subject_type == SUBJECT_TYPE_TEAM_PROGRESSIVE:
        return scope_labels_for_authority(SOURCE_AUTHORITY_TEAM_PROGRESSIVE)
    return scope_labels_for_authority(SOURCE_AUTHORITY_LEAGUE_SNAPSHOT)
