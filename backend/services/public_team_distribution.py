"""Canonical team universe for snapshot-bound public distribution.

Public team pages are distribution artifacts for one trusted Dashboard
publication.  Their denominator therefore comes from that publication's exact
Team Board accounting, while stable display identity comes from the immutable
MLB club directory.  Mutable player/roster organization rows are deliberately
not an input: those sources legitimately contain affiliates and other
noncanonical organizations.
"""

from collections.abc import Mapping

from services.mlb_club_directory import EXPECTED_CLUB_COUNT, MLB_CLUBS, MLB_TEAM_IDS
from services.team_board_snapshot_team_state import require_complete_team_accounting


def canonical_distribution_team_ids():
    """Return the immutable public MLB denominator in stable ID order."""
    team_ids = tuple(sorted(int(team_id) for team_id in MLB_TEAM_IDS))
    if len(team_ids) != EXPECTED_CLUB_COUNT or len(set(team_ids)) != EXPECTED_CLUB_COUNT:
        raise ValueError('public_distribution_team_universe_invalid')
    return team_ids


def snapshot_distribution_teams(payload, *, clubs=MLB_CLUBS):
    """Return the exact canonical MLB teams accounted for by ``payload``.

    The accounting validator fails closed on missing, duplicate, substituted,
    or noncanonical identities.  Club metadata is then taken from the same
    immutable directory that defines ``MLB_TEAM_IDS``; a missing label is an
    explicit contract failure rather than an invitation to substitute a
    mutable organization row.
    """
    if not isinstance(payload, Mapping):
        raise ValueError('public_distribution_snapshot_payload_invalid')
    package = payload.get('trusted_team_boards')
    if not isinstance(package, Mapping):
        raise ValueError('public_distribution_team_accounting_missing')

    canonical_team_ids = canonical_distribution_team_ids()
    require_complete_team_accounting(package, canonical_team_ids)

    rows = []
    seen = set()
    for club in sorted(clubs, key=lambda item: (item.abbreviation, item.team_id)):
        team_id = int(club.team_id)
        if (
            team_id in seen
            or team_id not in canonical_team_ids
            or not str(club.abbreviation or '').strip()
            or not str(club.team_name or '').strip()
        ):
            raise ValueError('public_distribution_team_metadata_invalid')
        seen.add(team_id)
        rows.append({
            'team_id': team_id,
            'team_name': club.team_name,
            'team_abbreviation': club.abbreviation,
        })

    if len(rows) != EXPECTED_CLUB_COUNT or seen != set(canonical_team_ids):
        raise ValueError('public_distribution_team_universe_invalid')
    return rows
