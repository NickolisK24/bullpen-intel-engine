"""Compare the two Team State populations at one moment. READ-ONLY.

Team State depends on two populations that have never been proven identical: the
governed board population the Team Board builder freezes as
``trusted_team_boards.default_pitcher_ids``, and the canonical active bullpen
``resolve_active_bullpen_membership`` resolves for the readiness distributions.
Historical membership is unrecoverable — the readiness path reads live
``Pitcher`` rows and roster status is overwritten in place — so the only honest
comparison is a current one, with both populations resolved in one process
against one database state at one captured reference date.

This script issues SELECT queries only. It never adds, updates, deletes,
commits, publishes, recalculates, repairs, syncs, or calls a source API. It
asserts the ORM session stayed clean, rolls back, and writes a JSON artifact.

    python -m scripts.compare_team_state_populations \
      --output /tmp/team_state_population_comparison.json

The shadow Contract A states in the artifact are offline arithmetic used to judge
whether a population difference has consequence. They are not published, not
written to any table, and not a Team State.

Exit codes: 0 success, 2 a population could not be resolved fairly, 3 the
session unexpectedly staged ORM changes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


class ComparisonError(RuntimeError):
    """Raised so the operator sees a loud failure instead of a partial artifact."""


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Read-only same-moment comparison of the Team Board population and '
            'the readiness population, for all 30 canonical MLB clubs.'
        ),
    )
    parser.add_argument(
        '--output',
        default='team_state_population_comparison.json',
        help='Destination path for the JSON artifact.',
    )
    return parser.parse_args(argv)


def _repository_sha():
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=str(BACKEND_DIR.parent), capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    sha = result.stdout.strip()
    return sha or None


def _reference_date():
    """The single anchor both populations are resolved against.

    Reproduces the production readiness anchor exactly — the same two public
    helpers ``api.team_operations`` uses — so the comparison is not run at a date
    production never uses. Captured once and passed explicitly to both
    resolvers, so neither can fall back to a different default.
    """
    from services import sync_metadata
    from services.availability_reference_date import (
        product_availability_reference_date_from_sync_status,
        product_current_date,
    )

    try:
        sync_status = sync_metadata.build_sync_status_payload()
    except Exception:
        sync_status = {}
    return (
        product_availability_reference_date_from_sync_status(sync_status)
        or product_current_date()
    )


def _board_population(reference_date):
    """Population A — the current candidate board population, read-only.

    These are the same two calls ``services.public_serving_authority`` makes when
    it builds ``trusted_team_boards.default_pitcher_ids``: the governed
    current-availability record set, grouped by ``pitcher.team_id``. Nothing is
    persisted and no snapshot is created.
    """
    from services.availability_population import current_availability_records
    from services.availability_snapshot import latest_fatigue_rows

    scored_rows = list(latest_fatigue_rows())
    records = current_availability_records(scored_rows, reference_date=reference_date)

    records_by_team = defaultdict(list)
    statuses = {}
    record_facts = {}
    for record in records:
        pitcher = record.get('pitcher')
        if pitcher is None or pitcher.team_id is None:
            continue
        pitcher_id = int(pitcher.id)
        records_by_team[int(pitcher.team_id)].append(record)
        availability = record.get('availability') or {}
        statuses[pitcher_id] = availability.get('availability_status')
        score = record.get('score')
        raw_score = getattr(score, 'raw_score', None) if score is not None else None
        record_facts[pitcher_id] = {
            'availability_data_state': availability.get('data_state'),
            'raw_score': float(raw_score) if raw_score is not None else None,
        }

    if not records:
        raise ComparisonError(
            'The current-availability population resolved no records; Population A '
            'cannot be resolved fairly.'
        )
    return records_by_team, statuses, record_facts


def _published_board_reference(reference_date):
    """Read-only metadata for the currently published board, plus its frozen ids.

    Reference only. The published ids were frozen at an earlier moment, so they
    are never used as Population A — using them would break the same-moment
    guarantee this comparison exists to provide. They are carried so the report
    can say whether the served board membership still matches the current
    candidate, instead of asserting it.
    """
    from models.dashboard_snapshot import DashboardSnapshot
    from services.dashboard_snapshot import (
        SNAPSHOT_STATUS_READY,
        SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
    )
    from services.public_serving_authority import (
        TEAM_BOARD_PACKAGE_CONTRACT,
        TEAM_BOARD_PACKAGE_KEY,
    )

    snapshot = (
        DashboardSnapshot.query
        .filter(
            DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
            DashboardSnapshot.status == SNAPSHOT_STATUS_READY,
            DashboardSnapshot.is_published == True,  # noqa: E712 - SQL boolean
        )
        .order_by(DashboardSnapshot.id.desc())
        .first()
    )
    if snapshot is None:
        return {'snapshot_id': None, 'eligible_for_comparison': False,
                'reason': 'no_published_snapshot'}, {}

    reference = {
        'snapshot_id': snapshot.id,
        'sync_run_id': snapshot.sync_run_id,
        'published_at': snapshot.published_at.isoformat() if snapshot.published_at else None,
        'data_through': str(snapshot.data_through) if snapshot.data_through else None,
        'availability_reference_date': (
            str(snapshot.availability_reference_date)
            if snapshot.availability_reference_date else None
        ),
        'used_as_population_a': False,
    }

    if snapshot.availability_reference_date != reference_date:
        reference['eligible_for_comparison'] = False
        reference['reason'] = 'published_board_anchored_to_a_different_reference_date'
        return reference, {}

    payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}
    package = payload.get(TEAM_BOARD_PACKAGE_KEY)
    if (
        not isinstance(package, dict)
        or package.get('contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or not isinstance(package.get('by_team_id'), dict)
    ):
        reference['eligible_for_comparison'] = False
        reference['reason'] = 'frozen_board_package_missing_or_unsupported'
        return reference, {}

    by_team = package['by_team_id']
    ids_by_team = {}
    for team_id, team_package in by_team.items():
        if not isinstance(team_package, dict):
            raise ComparisonError(
                f'Published board package for team {team_id!r} has an unsupported '
                'payload shape; refusing to report it as comparable.'
            )
        ids_by_team[int(team_id)] = {
            int(value) for value in (team_package.get('default_pitcher_ids') or [])
        }

    reference['eligible_for_comparison'] = True
    reference['reason'] = None
    return reference, ids_by_team


def _pitcher_details(pitcher_ids):
    """Roster facts for the differing arms only. One bounded query."""
    if not pitcher_ids:
        return {}
    from models.pitcher import Pitcher

    rows = Pitcher.query.filter(Pitcher.id.in_(sorted(pitcher_ids))).all()
    return {
        int(pitcher.id): {
            'active': pitcher.active,
            'team_id': pitcher.team_id,
            'roster_status': pitcher.roster_status,
        }
        for pitcher in rows
    }


def collect_rows(reference_date):
    """Resolve both populations for all 30 clubs inside one moment."""
    from api.team_operations import resolve_readiness_population
    from services.mlb_club_directory import EXPECTED_CLUB_COUNT, MLB_CLUBS
    from services.readiness_population_comparison import compare_team

    if EXPECTED_CLUB_COUNT != 30 or len(MLB_CLUBS) != 30:
        raise ComparisonError(
            f'Canonical club directory resolved {len(MLB_CLUBS)} clubs, expected 30.'
        )

    records_by_team, statuses, record_facts = _board_population(reference_date)
    published_reference, published_ids_by_team = _published_board_reference(reference_date)

    resolved = []
    for club in MLB_CLUBS:
        team_records = records_by_team.get(club.team_id, [])
        # One resolution per team, through the actual runtime entrypoint. The
        # membership it returns is resolved by the roster authority and does not
        # depend on the records passed; the records only decide which members
        # carry a governed status.
        #
        # Verified by running this locally: when public_roster_readiness reports
        # claims_available False it withholds bullpen_arms, the roster authority
        # publishes no arms, and resolve_active_bullpen_membership fails closed to
        # an empty set with authority_complete False. So the readiness population
        # is gated on roster_status_snapshots coverage even though the membership
        # list itself comes from live Pitcher rows. A team in that state is
        # reported with readiness_authority_incomplete rather than as a genuine
        # zero-arm bullpen — an inconclusive team must never read as a match.
        consumed_records, membership = resolve_readiness_population(
            team_records, team_id=club.team_id, reference_date=reference_date,
        )
        readiness_ids, authority_complete = membership
        resolved.append({
            'club': club,
            'board_ids': frozenset(
                int(record['pitcher'].id) for record in team_records
            ),
            'readiness_ids': frozenset(int(value) for value in readiness_ids),
            'authority_complete': bool(authority_complete),
            'consumed_ids': frozenset(
                int(record['pitcher'].id) for record in consumed_records
            ),
        })

    if not any(entry['readiness_ids'] for entry in resolved):
        raise ComparisonError(
            'The roster authority resolved no active bullpen for any club; '
            'Population B cannot be resolved.'
        )

    differing = set()
    for entry in resolved:
        differing |= entry['board_ids'] ^ entry['readiness_ids']

    roster_facts = _pitcher_details(differing)
    # Merged by unpacking rather than dict.update, so the read-only guard on this
    # script can forbid ``.update(`` and ``.delete(`` outright and no bulk ORM
    # write can hide behind a legitimate-looking dictionary call.
    arm_details = {
        pitcher_id: {
            **(record_facts.get(pitcher_id) or {}),
            **(roster_facts.get(pitcher_id) or {}),
        }
        for pitcher_id in differing
    }

    rows = [
        compare_team(
            club=entry['club'],
            reference_date=reference_date,
            board_ids=entry['board_ids'],
            readiness_ids=entry['readiness_ids'],
            statuses=statuses,
            arm_details=arm_details,
            authority_complete=entry['authority_complete'],
            consumed_ids=entry['consumed_ids'],
            published_board_ids=(
                published_ids_by_team.get(entry['club'].team_id, set())
                if published_reference.get('eligible_for_comparison')
                else None
            ),
        )
        for entry in resolved
    ]
    return rows, published_reference


def main(argv=None):
    args = _parse_args(argv)

    from sqlalchemy.exc import SQLAlchemyError

    from app import app
    from services.readiness_population_comparison import build_comparison
    from utils.db import db

    with app.app_context():
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            reference_date = _reference_date()
            rows, published_reference = collect_rows(reference_date)
            comparison = build_comparison(
                rows,
                generated_at=datetime.now(timezone.utc).isoformat(),
                comparison_started_at=started_at,
                reference_date=str(reference_date),
                repository_sha=_repository_sha(),
                board_population_source=(
                    'current_candidate_board_population '
                    '(availability_population.current_availability_records over '
                    'availability_snapshot.latest_fatigue_rows, grouped by '
                    'pitcher.team_id) — the same recipe '
                    'public_serving_authority uses for '
                    'trusted_team_boards.default_pitcher_ids'
                ),
                readiness_population_source=(
                    'api.team_operations.resolve_readiness_population -> '
                    'team_readiness_coverage.resolve_active_bullpen_membership'
                ),
                published_board_reference=published_reference,
            )
        except (ComparisonError, ValueError) as exc:
            db.session.rollback()
            print(f'error: {exc}', file=sys.stderr)
            return 2
        except SQLAlchemyError as exc:
            # Roll back rather than leaving a failed transaction open, and report
            # only the exception class: a driver-level message can carry the SQL
            # and, for some drivers, the connection string.
            db.session.rollback()
            print(
                f'error: a read failed against the database '
                f'({exc.__class__.__name__}); no artifact was written.',
                file=sys.stderr,
            )
            return 2

        # Read-only guarantee, asserted rather than assumed: a SELECT-only pass
        # leaves the session clean. Roll back regardless so nothing can escape.
        dirty = bool(db.session.new or db.session.dirty or db.session.deleted)
        db.session.rollback()
        if dirty:
            print('error: comparison unexpectedly staged ORM changes; aborting.',
                  file=sys.stderr)
            return 3

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(comparison, indent=2, sort_keys=True, default=str))
    summary = comparison['summary']
    print(
        f"Compared {comparison['team_count']} clubs at reference date "
        f"{comparison['reference_date']}: {summary['exact_match_count']} exact matches, "
        f"{summary['teams_with_differences']} with differences, "
        f"{summary['teams_with_clean_axis_differences']} with clean-axis differences, "
        f"{summary['teams_with_shadow_state_differences']} with shadow-state differences "
        f"-> {output}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
