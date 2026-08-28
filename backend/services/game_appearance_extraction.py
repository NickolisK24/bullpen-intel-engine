"""Canonical game -> pitcher-appearance extraction (Foundation 3C).

One final game payload in, a deterministic set of pitcher appearance records
out. This module owns the *appearance* shape and the game-level role decision;
it deliberately does NOT own box-score parsing or MLB transport:

  * box-score pitching lines are produced by the single existing parser,
    ``services.sync._extract_pitching_lines_from_boxscore``, and are passed in
    here — there is no second box-score parser and no second MLB client;
  * innings are converted by the canonical ``utils.innings`` helpers, so
    recorded outs remain the integer authority and decimal innings stay a
    derived display value.

Game-level role authority
-------------------------
Role is decided per APPEARANCE from the official per-game ``gamesStarted``
signal (falling back to "first pitcher listed for this side" exactly as
``services.sync._line_games_started`` already does). Season role and roster
role are never consulted here:

  * ``games_started == 1``  -> this appearance is a START
  * otherwise               -> this appearance is RELIEF

That is the repository's existing canonical start signal (Role Authority V1 is
built on the same per-appearance ``GameLog.games_started`` column), so an
OPENER — who is officially credited with the start — records a start
appearance, and the bulk arm who follows records a relief appearance. No new
role heuristic is introduced here, and nothing overrides the official signal.

Source revision
---------------
MLB publishes no boxscore revision number. Rather than invent one, this module
derives an ``appearance_set_fingerprint`` from the canonical extracted fields
themselves. It is an OBSERVED-CONTENT marker: identical extracted appearances
produce an identical fingerprint, and any governed field changing produces a
different one. That is exactly the signal correction detection needs — "did the
official line for this game change?" — without asserting semantics the source
does not provide.
"""

from __future__ import annotations

import hashlib
import json

from utils.games_started import parse_games_started
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs


SOURCE_AUTHORITY = 'completed_game_boxscore_pitching_section'

APPEARANCE_ROLE_START = 'start'
APPEARANCE_ROLE_RELIEF = 'relief'

# Fields that participate in the observed-content revision marker. Restricted
# to canonical, governed fields so cosmetic payload churn (display names,
# ordering, unrelated hydrations) can never look like a stat correction.
FINGERPRINT_FIELDS = (
    'pitcher_mlb_id',
    'team_id',
    'opponent_team_id',
    'appearance_role',
    'games_started',
    'outs_recorded',
    'earned_runs',
    'runs_allowed',
    'hits_allowed',
    'walks',
    'strikeouts',
    'home_runs_allowed',
    'batters_faced',
    'pitches_thrown',
    'strikes',
    'balls',
    'games_finished',
    'hit_batters',
    'wild_pitches',
    'inherited_runners',
    'inherited_runners_scored',
    'save_situation',
    'hold',
    'blown_save',
    'win',
    'loss',
    'save',
)


class AppearanceExtractionError(ValueError):
    """The game payload cannot yield a deterministic appearance set."""

    def __init__(self, error_class: str, message: str):
        super().__init__(message)
        self.error_class = error_class


def extract_game_appearances(
    *,
    game: dict,
    pitching_lines,
    pitcher_order: dict,
    game_date,
) -> list[dict]:
    """Return the deterministic appearance set for one final game.

    ``pitching_lines`` / ``pitcher_order`` come from the existing canonical
    box-score parser. Raises :class:`AppearanceExtractionError` when the payload
    cannot produce an unambiguous set — a duplicate pitcher within one game, an
    unidentifiable pitcher, or an unparsable innings value. Failing closed here
    is deliberate: a half-extracted game must never be able to reconcile.
    """
    game_pk = _positive_int((game or {}).get('gamePk'))
    if game_pk is None:
        raise AppearanceExtractionError('payload_invalid', 'missing game identifier')

    teams = ((game or {}).get('teams') or {})
    side_team_ids = {
        side: _positive_int((((teams.get(side) or {}).get('team')) or {}).get('id'))
        for side in ('home', 'away')
    }

    records: list[dict] = []
    seen_pitchers: set[int] = set()
    for line in pitching_lines or []:
        stats = line.get('stats') or {}
        if not stats:
            continue

        pitcher_mlb_id = _positive_int(
            line.get('person_id') if line.get('person_id') else line.get('player_id')
        )
        if pitcher_mlb_id is None:
            raise AppearanceExtractionError(
                'starter_identity_unresolved',
                'box-score pitching line without a usable pitcher identity',
            )
        if pitcher_mlb_id in seen_pitchers:
            # One pitcher has exactly one pitching line per MLB game — the same
            # invariant the game_logs unique key encodes. Two lines for one
            # pitcher means the payload is ambiguous, not that the pitcher
            # appeared twice; reject rather than silently pick one.
            raise AppearanceExtractionError(
                'payload_invalid',
                'duplicate pitching line for one pitcher in one game',
            )
        seen_pitchers.add(pitcher_mlb_id)

        side = line.get('side')
        opponent_side = 'away' if side == 'home' else 'home'
        team_id = _positive_int(line.get('team_id')) or side_team_ids.get(side)
        opponent_team_id = side_team_ids.get(opponent_side)

        try:
            outs_recorded = parse_mlb_innings_to_outs(stats.get('inningsPitched'))
        except Exception as exc:  # noqa: BLE001 - normalized to a safe class
            raise AppearanceExtractionError(
                'payload_invalid', 'unparsable innings pitched'
            ) from exc
        if outs_recorded is None or outs_recorded < 0:
            raise AppearanceExtractionError(
                'payload_invalid', 'unusable innings pitched'
            )

        try:
            games_started = _games_started_for_line(line, pitcher_order)
        except AppearanceExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalized to a safe class
            raise AppearanceExtractionError(
                'payload_invalid', 'unusable gamesStarted signal'
            ) from exc
        appearance_role = (
            APPEARANCE_ROLE_START if games_started == 1 else APPEARANCE_ROLE_RELIEF
        )

        records.append({
            'game_pk': game_pk,
            'game_date': game_date,
            'pitcher_mlb_id': pitcher_mlb_id,
            'team_id': team_id,
            'opponent_team_id': opponent_team_id,
            'side': side,
            'appearance_role': appearance_role,
            'games_started': games_started,
            'is_starter': appearance_role == APPEARANCE_ROLE_START,
            'is_reliever': appearance_role == APPEARANCE_ROLE_RELIEF,
            'outs_recorded': outs_recorded,
            'innings_pitched': outs_to_decimal_innings(outs_recorded),
            'earned_runs': _int_or_none(stats.get('earnedRuns')),
            'runs_allowed': _int_or_none(stats.get('runs')),
            'hits_allowed': _int_or_none(stats.get('hits')),
            'walks': _int_or_none(stats.get('baseOnBalls')),
            'strikeouts': _int_or_none(stats.get('strikeOuts')),
            'home_runs_allowed': _int_or_none(stats.get('homeRuns')),
            'batters_faced': _int_or_none(stats.get('battersFaced')),
            'pitches_thrown': _int_or_none(stats.get('numberOfPitches')),
            'strikes': _int_or_none(stats.get('strikes')),
            'balls': _int_or_none(stats.get('balls')),
            'games_finished': _int_or_none(stats.get('gamesFinished')),
            'hit_batters': _first_int(stats, 'hitBatsmen', 'hitByPitch'),
            'wild_pitches': _int_or_none(stats.get('wildPitches')),
            'inherited_runners': _int_or_none(stats.get('inheritedRunners')),
            'inherited_runners_scored': _int_or_none(
                stats.get('inheritedRunnersScored')
            ),
            'save_situation': _positive_or_none(stats, 'saveOpportunities'),
            'hold': _positive_or_none(stats, 'holds'),
            'blown_save': _positive_or_none(stats, 'blownSaves'),
            'win': _positive_or_none(stats, 'wins'),
            'loss': _positive_or_none(stats, 'losses'),
            'save': _positive_or_none(stats, 'saves'),
            'source_authority': SOURCE_AUTHORITY,
        })

    # Deterministic order, independent of payload/dict iteration order.
    records.sort(key=lambda record: (
        0 if record['side'] == 'away' else 1,
        0 if record['is_starter'] else 1,
        record['pitcher_mlb_id'],
    ))
    return records


def starter_identity(appearances) -> dict:
    """Return the per-side starter mlb ids, or ``None`` for a side without one."""
    starters = {'home': None, 'away': None}
    for record in appearances or []:
        if record.get('is_starter') and record.get('side') in starters:
            starters[record['side']] = record['pitcher_mlb_id']
    return starters


def appearance_set_fingerprint(appearances) -> str:
    """Observed-content revision marker for one game's appearance set."""
    payload = [
        [record.get(field) for field in FINGERPRINT_FIELDS]
        for record in sorted(
            appearances or [], key=lambda item: item.get('pitcher_mlb_id') or 0
        )
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def relief_appearance_count(appearances) -> int:
    return sum(1 for record in appearances or [] if record.get('is_reliever'))


def _games_started_for_line(line: dict, pitcher_order: dict) -> int:
    """Official per-game start signal, with the existing positional fallback."""
    stats = line.get('stats') or {}
    parsed = parse_games_started(stats.get('gamesStarted'))
    if parsed is not None:
        return parsed
    side_pitchers = list((pitcher_order or {}).get(line.get('side')) or [])
    first = side_pitchers[0] if side_pitchers else None
    return 1 if first is not None and first == line.get('player_id') else 0


def _int_or_none(value):
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_int(stats, *keys):
    for key in keys:
        if key in (stats or {}):
            return _int_or_none(stats.get(key))
    return None


def _positive_or_none(stats, key):
    if key not in (stats or {}) or stats.get(key) in (None, ''):
        return None
    value = _int_or_none(stats.get(key))
    return None if value is None else value > 0


def _positive_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
