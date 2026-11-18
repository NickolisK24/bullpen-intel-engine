"""Replay the production Team State engine for one team on one game day.

The replay calls production code unchanged, in the same order the nightly
pipeline and the Team Operations readiness route call it:

    role authority      services.role_authority.classify_role
    fatigue score       services.fatigue.calculate_fatigue
    availability        services.availability.classify_availability
    readiness record    api.team_operations._readiness_record
    coverage / trust    services.team_readiness_coverage.assess_team_coverage
                        api.team_operations._build_trust_metadata
    freshness           api.team_operations._team_operations_freshness_metadata
    Team State          team_operations.assemble_bullpen_readiness (Contract A)
    public vocabulary   services.team_state_public_vocabulary.INTERNAL_TO_PUBLIC_STATE

What the replay substitutes for production database reads (documented in the
report as assumptions):

* Appearance history comes from MLB boxscores instead of the stored gameLog
  rows. Same fields (outs, pitches, gamesStarted, saves/holds).
* Active-bullpen membership = MLB active roster as of the day before the game
  (production's slate-day convention), pitching positions only, filtered by the
  production role authority over each pitcher's last 10 appearances.
* Source freshness, appearance-ledger completeness and roster authority are
  treated as current/complete (a replay has the full completed-game record).
  The coverage gate itself still runs: an arm whose recent logs lack a pitch
  count is unresolved, exactly as in production.

NO LOOKAHEAD: the replay never receives appearances directly. It receives a
``HistoryView`` whose only accessor returns appearances dated strictly before
the game date. Roster input is the prior day's roster. See
tests/test_no_lookahead.py.
"""

from __future__ import annotations

import os
import sys
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Iterable

from . import config

os.environ.setdefault('AUTO_SYNC', 'false')
if str(config.BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(config.BACKEND_DIR))

from api.team_operations import (  # noqa: E402  (production, read-only reuse)
    _build_trust_metadata,
    _readiness_record,
    _team_operations_freshness_metadata,
)
from services.availability import ACTIVE_WINDOW_DAYS, classify_availability  # noqa: E402
from services.fatigue import calculate_fatigue  # noqa: E402
from services.role_authority import classify_role  # noqa: E402
from services.team_readiness_coverage import assess_team_coverage  # noqa: E402
from services.team_state_public_vocabulary import INTERNAL_TO_PUBLIC_STATE  # noqa: E402
from services.workload_appearance import workload_appearance_logs  # noqa: E402
from team_operations import assemble_bullpen_readiness  # noqa: E402

ROLE_HISTORY_APPEARANCES = 10   # services.bullpen_population.usage_logs_by_pitcher (include_stale)
FATIGUE_WINDOW_DAYS = 14        # services.sync.recalculate_all_fatigue
AVAILABILITY_WINDOW_DAYS = 4    # services.availability_snapshot.logs_for_availability_windows
STATE_DATA_LIMITED = 'data_limited'


# ── History with a hard date cutoff ──────────────────────────────────────────

class History:
    """All appearances, indexed by pitcher. Never handed to the engine directly."""

    def __init__(self, appearances: Iterable):
        by_pitcher = defaultdict(list)
        for app in appearances:
            by_pitcher[app.pitcher_mlb_id].append(app)
        self._logs = {}
        self._dates = {}
        for pid, apps in by_pitcher.items():
            apps.sort(key=lambda a: (a.game_date, a.game_number, a.game_pk))
            self._logs[pid] = apps
            self._dates[pid] = [a.game_date for a in apps]

    def view_before(self, cutoff: date) -> 'HistoryView':
        return HistoryView(self, cutoff)


class HistoryView:
    """Read-only window onto History: only appearances dated < cutoff exist."""

    def __init__(self, history: History, cutoff: date):
        self._history = history
        self.cutoff = cutoff

    def logs(self, pitcher_mlb_id: int) -> list:
        """Appearances strictly before the cutoff date, most recent first."""
        apps = self._history._logs.get(pitcher_mlb_id)
        if not apps:
            return []
        idx = bisect_left(self._history._dates[pitcher_mlb_id], self.cutoff)
        return list(reversed(apps[:idx]))


# ── Replay output ────────────────────────────────────────────────────────────

@dataclass
class RelieverRead:
    pitcher_mlb_id: int
    name: str
    availability_status: str
    availability_data_state: str
    fatigue_score: float | None
    pitch_count_unknown: bool       # a 7-day log lacked a pitch count -> component scored as 0
    days_rest: int | None
    role: str


@dataclass
class TeamDayState:
    team_id: int
    game_date: date
    public_state: str               # fresh / stretched / vulnerable / data_limited
    readiness_code: str
    decisive_rule: str | None
    active_count: int
    clean_count: int
    moderate_count: int
    severe_count: int
    unknown_count: int
    trust_confidence: str
    team_fatigue_mean: float | None
    roster_pitchers: int
    relievers: list = field(default_factory=list)


def _pitcher(entry) -> SimpleNamespace:
    person = entry.get('person') or {}
    pos = (entry.get('position') or {}).get('abbreviation') or ''
    return SimpleNamespace(
        id=int(person['id']),
        mlb_id=int(person['id']),
        full_name=person.get('fullName', ''),
        position=pos,
        throws=None,          # handedness is not read by Contract A
        active=True,
        team_abbreviation=None,
    )


def _sync_status(game_date: date) -> dict:
    data_through = (game_date - timedelta(days=1)).isoformat()
    stamp = datetime.combine(game_date, time(10, 17)).isoformat()
    return {
        'status': 'success',
        'sync_authority': 'backtest_replay',
        'metadata_source': 'backtest_replay',
        'last_successful_sync': stamp,
        'data': {
            'latest_game_date': data_through,
            'latest_workload_date': data_through,
            'latest_fatigue_calculated_at': stamp,
        },
        'freshness': {
            'is_current': True,
            'is_stale': False,
            'freshness_state': 'current',
            'reference_date': data_through,
            'availability_reference_date': game_date.isoformat(),
            'reason_codes': [],
            'limitations': [],
        },
    }


def replay_team_day(team_id: int, game_date: date, roster: list, view: HistoryView) -> TeamDayState:
    """Pre-game Team State for ``team_id`` on ``game_date``.

    ``roster`` is the MLB active-roster list as of the day before. ``view`` must
    be cut off at ``game_date``.
    """
    if view.cutoff != game_date:
        raise ValueError('history view must be cut off at the game date')
    ref = game_date
    records = []
    reads = []
    roster_pitchers = 0
    for entry in roster:
        status = (entry.get('status') or {}).get('code')
        if status not in (None, 'A'):
            continue
        pitcher = _pitcher(entry)
        all_logs = view.logs(pitcher.mlb_id)
        role = classify_role(pitcher, all_logs[:ROLE_HISTORY_APPEARANCES], reference_date=ref)
        if role.get('role') != 'NonPitcher':
            roster_pitchers += 1
        if not role.get('eligible'):
            continue

        fatigue_logs = [g for g in all_logs if g.game_date >= ref - timedelta(days=FATIGUE_WINDOW_DAYS)]
        score = calculate_fatigue(pitcher, fatigue_logs, reference_date=ref)
        avail_logs = [g for g in all_logs if g.game_date >= ref - timedelta(days=AVAILABILITY_WINDOW_DAYS)]
        latest = all_logs[0].game_date if all_logs else None
        availability = classify_availability(
            score,
            game_logs=avail_logs,
            reference_date=ref,
            latest_game_date=latest,
            active_window_days=ACTIVE_WINDOW_DAYS,
        )
        logs_7 = [g for g in workload_appearance_logs(fatigue_logs) if g.game_date >= ref - timedelta(days=7)]
        records.append({
            'pitcher': pitcher,
            'score': score,
            'availability': availability,
            'latest_game_date': latest,
        })
        reads.append(RelieverRead(
            pitcher_mlb_id=pitcher.mlb_id,
            name=pitcher.full_name,
            availability_status=availability['availability_status'],
            availability_data_state=availability['data_state'],
            fatigue_score=round(score.raw_score, 2) if score is not None else None,
            pitch_count_unknown=bool(logs_7) and score.pitches_last_7_days is None,
            days_rest=availability['inputs'].get('days_rest'),
            role=role.get('role'),
        ))

    sync_status = _sync_status(game_date)
    generated_at = sync_status['last_successful_sync']
    active = len(records)
    usable = sum(
        1 for r in records
        if r['availability'].get('data_state') in ('fresh', 'stale')
    )
    assessment = assess_team_coverage(
        authority_complete=active > 0,
        source_current=True,
        active_bullpen_count=active,
        usable_record_count=usable,
        unresolved_record_count=active - usable,
    )
    trust = _build_trust_metadata(
        confidence=assessment.confidence,
        data_state=assessment.data_state,
        confidence_reasons=[assessment.reason_code],
        sync_status=sync_status,
        generated_at=generated_at,
        has_records=bool(records),
    )
    freshness = _team_operations_freshness_metadata(
        records, sync_status=sync_status, generated_at=generated_at,
    )
    payload = assemble_bullpen_readiness(
        team={'team_id': team_id, 'team_name': None, 'team_abbreviation': None},
        pitcher_records=tuple(_readiness_record(r) for r in records),
        trust_metadata=trust,
        freshness=freshness,
        generated_at=generated_at,
    )
    evidence = payload.get('team_state_evidence') or {}
    code = evidence.get('readiness_status_code') or STATE_DATA_LIMITED
    scores = [r.fatigue_score for r in reads if r.fatigue_score is not None]
    return TeamDayState(
        team_id=team_id,
        game_date=game_date,
        public_state=INTERNAL_TO_PUBLIC_STATE.get(code, STATE_DATA_LIMITED),
        readiness_code=code,
        decisive_rule=evidence.get('decisive_rule'),
        active_count=int(evidence.get('active_pitcher_count') or 0),
        clean_count=int(evidence.get('clean_count') or 0),
        moderate_count=int(evidence.get('moderate_count') or 0),
        severe_count=int(evidence.get('severe_count') or 0),
        unknown_count=int(evidence.get('unknown_count') or 0),
        trust_confidence=assessment.confidence,
        team_fatigue_mean=round(sum(scores) / len(scores), 2) if scores else None,
        roster_pitchers=roster_pitchers,
        relievers=reads,
    )
