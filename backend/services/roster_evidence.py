"""
Run-scoped official MLB roster evidence shared by the roster consumers.

Team assignment and roster status derive different governed facts from the same
official roster feeds: team assignment answers which organization owns a player,
roster status answers which roster category the player sits in. Both used to
fetch the same four roster views for the same thirty clubs, so one daily run
issued the roster endpoint twice for every team.

This module owns neither classification. It owns the *evidence*: it fetches team
metadata and each ``(team_id, roster_type)`` roster view at most once per run and
hands both consumers the same official response. Evidence is fetched lazily on
first ask, so nothing is requested that no consumer needs, and the fetch still
happens inside the stage that asks for it first.

Deliberate properties:

- Run scoped. A ``RunRosterEvidence`` instance lives for exactly one sync run and
  is passed explicitly; there is no module-level cache and nothing is persisted,
  so a later run can never observe an earlier run's roster feeds.
- Fail closed. A failed fetch is memoized as a *failure*, never as an empty
  roster. Every consumer that asks for that view observes the same failure, so a
  partial fetch failure can never be reused as successful evidence.
- Read only. Every accessor returns a defensive copy, so one consumer can never
  mutate what the other observes.
"""

import copy
from collections import namedtuple

from models.pitcher import Pitcher
from services.mlb_api import mlb_client
from utils.db import db


ROSTER_TYPE_ACTIVE = 'active'
ROSTER_TYPE_40_MAN = '40Man'
ROSTER_TYPE_FULL = 'fullRoster'
ROSTER_TYPE_NON_ROSTER = 'nonRosterInvitees'

ROSTER_TYPES = (
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
)

CONSUMER_TEAM_ASSIGNMENT = 'team_assignment_sync'
CONSUMER_ROSTER_STATUS = 'roster_status_sync'


TeamMetadata = namedtuple('TeamMetadata', ('team_map', 'error'))
RosterView = namedtuple('RosterView', ('team_id', 'roster_type', 'entries', 'error'))


def _stored_team_map():
    """Team identity already proven by stored pitcher rows."""
    rows = (
        db.session.query(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .filter(Pitcher.team_id.isnot(None))
        .distinct()
        .all()
    )
    return {
        row.team_id: {
            'id': row.team_id,
            'name': row.team_name,
            'abbreviation': row.team_abbreviation,
        }
        for row in rows
    }


class RunRosterEvidence:
    """One run's official roster evidence, fetched once and reused."""

    def __init__(self, client=None, roster_types=ROSTER_TYPES):
        self._client = client or mlb_client
        self._roster_types = tuple(roster_types)
        self._team_metadata = None
        self._rosters = {}
        self._consumers = []
        self._requests = 0

    @property
    def roster_types(self):
        """The roster views this run intends to read."""
        return self._roster_types

    # ── Team metadata ────────────────────────────────────────

    def team_metadata(self):
        """Team identity for the run: stored identity overlaid with ``/teams``."""
        if self._team_metadata is None:
            team_map = _stored_team_map()
            error = None
            try:
                teams = self._client.get_all_teams()
            except Exception as exc:  # noqa: BLE001 - reported to the consumer verbatim
                teams = []
                error = str(exc)

            for team in teams or []:
                team_id = team.get('id')
                if team_id is None:
                    continue
                team_map[team_id] = {
                    'id': team_id,
                    'name': team.get('name'),
                    'abbreviation': team.get('abbreviation'),
                }
            self._team_metadata = TeamMetadata(team_map=team_map, error=error)
        metadata = self._team_metadata
        return TeamMetadata(
            team_map={
                team_id: dict(team)
                for team_id, team in metadata.team_map.items()
            },
            error=metadata.error,
        )

    # ── Roster evidence ──────────────────────────────────────

    def roster_view(self, team_id, roster_type):
        """
        The official roster feed for one ``(team_id, roster_type)``.

        Fetched on first ask and reused for the rest of the run. A fetch failure
        is memoized as a failure, so every later consumer of the same view
        observes the same failure instead of an empty roster.
        """
        key = (team_id, roster_type)
        if key not in self._rosters:
            self._requests += 1
            try:
                roster = self._client.get_team_roster(team_id, roster_type=roster_type)
            except Exception as exc:  # noqa: BLE001 - reported to the consumer verbatim
                self._rosters[key] = (None, str(exc))
            else:
                self._rosters[key] = (tuple(roster or ()), None)

        entries, error = self._rosters[key]
        return RosterView(
            team_id=team_id,
            roster_type=roster_type,
            entries=() if entries is None else tuple(copy.deepcopy(entry) for entry in entries),
            error=error,
        )

    # ── Observability ────────────────────────────────────────

    def note_consumer(self, consumer):
        """Record which governed consumer read this run's evidence."""
        if consumer not in self._consumers:
            self._consumers.append(consumer)

    def summary(self):
        """Run-level reuse counters for the daily sync log."""
        fetched_team_ids = {team_id for team_id, _ in self._rosters}
        fetched_roster_types = {roster_type for _, roster_type in self._rosters}
        failures = [
            {'team_id': team_id, 'roster_type': roster_type, 'error': error}
            for (team_id, roster_type), (_, error) in self._rosters.items()
            if error is not None
        ]
        return {
            'teams_fetched': len(fetched_team_ids),
            'roster_types_declared': list(self._roster_types),
            'roster_types_fetched': sorted(fetched_roster_types),
            'roster_requests': self._requests,
            'team_metadata_fetched': self._team_metadata is not None,
            'fetch_failures': len(failures),
            'fetch_failure_details': failures,
            'consumers': list(self._consumers),
        }


def build_run_roster_evidence(client=None, roster_types=ROSTER_TYPES):
    """Create the roster evidence for exactly one sync run."""
    return RunRosterEvidence(client=client, roster_types=roster_types)
