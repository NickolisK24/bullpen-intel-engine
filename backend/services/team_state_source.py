"""Governed evidence gatherer for the Team State V1 Share Card (SC-02).

SC-01 created the immutable Share Artifact domain. SC-02 decides *whether* a Team
State artifact deserves to exist and builds the canonical payload — it does not
publish or render anything.

This module gathers only governed BaseballOS evidence and packages it into an
immutable ``TeamStateSource``. It reuses the existing trusted engines rather than
recomputing intelligence:

* the trusted, published daily snapshot authority via
  ``services.dashboard_snapshot`` (``snapshot_unavailable_reason`` is the
  authoritative trust verdict; the snapshot's id / sync_run_id / data_through /
  published_at become the artifact's SC-01 authority fields), and
* the governed team operating-state payload produced by the existing
  ``team_operations.bullpen_readiness`` engine (consumed as a governed input,
  never re-derived here), and
* the authoritative team universe via ``services.team_directory``.

Gathering fails closed: a missing or untrusted snapshot, an unrecognized team,
or an absent readiness payload are represented as explicit gaps on the source so
the eligibility engine can refuse deterministically. No trust decision is made
here — that is the eligibility engine's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Optional

from services.dashboard_snapshot import (
    get_latest_dashboard_snapshot,
    snapshot_unavailable_reason,
)
from services.team_directory import is_valid_team_id
from utils.db import db


SNAPSHOT_MISSING_REASON = 'snapshot_missing'


@dataclass(frozen=True)
class TeamStateSnapshotAuthority:
    """The trusted published snapshot that would authorize generation.

    ``unavailable_reason`` is the verdict from
    ``dashboard_snapshot.snapshot_unavailable_reason``: ``None`` means the
    snapshot is trustworthy; any string is the reason it is not.
    """

    snapshot_id: Optional[int]
    sync_run_id: Optional[int]
    data_through: Optional[date]
    published_at: Optional[datetime]
    unavailable_reason: Optional[str]

    @property
    def is_present(self) -> bool:
        return self.snapshot_id is not None

    @property
    def is_trusted(self) -> bool:
        return self.is_present and self.unavailable_reason is None


@dataclass(frozen=True)
class TeamStateSource:
    """The governed inputs an eligibility decision and payload are built from."""

    team_id: int
    team_valid: bool
    snapshot: TeamStateSnapshotAuthority
    readiness: Optional[Mapping[str, Any]]
    requested_date: Optional[date] = None

    @property
    def data_through(self) -> Optional[date]:
        return self.snapshot.data_through


def _snapshot_authority(snapshot) -> TeamStateSnapshotAuthority:
    if snapshot is None:
        return TeamStateSnapshotAuthority(
            snapshot_id=None,
            sync_run_id=None,
            data_through=None,
            published_at=None,
            unavailable_reason=SNAPSHOT_MISSING_REASON,
        )
    return TeamStateSnapshotAuthority(
        snapshot_id=snapshot.id,
        sync_run_id=snapshot.sync_run_id,
        data_through=snapshot.data_through,
        published_at=snapshot.published_at,
        unavailable_reason=snapshot_unavailable_reason(snapshot),
    )


def _safe_is_valid_team_id(team_id) -> bool:
    try:
        return bool(is_valid_team_id(team_id))
    except Exception:
        # Fail closed: an unreadable team directory is treated as "unknown team".
        return False


def gather_team_state_source(
    team_id: int,
    *,
    readiness_payload: Optional[Mapping[str, Any]] = None,
    snapshot=None,
    requested_date: Optional[date] = None,
    session=None,
) -> TeamStateSource:
    """Package the governed evidence for a team into a ``TeamStateSource``.

    ``readiness_payload`` is the governed team operating-state payload produced by
    ``team_operations.bullpen_readiness.assemble_bullpen_readiness`` — SC-02
    consumes it, it does not assemble it. ``snapshot`` may be supplied for
    testing / explicit authorization; otherwise the latest published daily
    snapshot is resolved and its trust verdict computed. This function never
    raises for "not eligible": gaps are represented on the returned source and
    the eligibility engine refuses deterministically.
    """
    session = session or db.session

    team_valid = _safe_is_valid_team_id(team_id)

    if snapshot is None:
        try:
            snapshot = get_latest_dashboard_snapshot()
        except Exception:
            # Fail closed: an unreadable snapshot store is treated as missing.
            snapshot = None

    return TeamStateSource(
        team_id=int(team_id),
        team_valid=team_valid,
        snapshot=_snapshot_authority(snapshot),
        readiness=readiness_payload,
        requested_date=requested_date,
    )
