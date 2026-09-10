"""Authoritative active-MLB club denominator and fallback identity.

D-054 gives this immutable registry exactly two responsibilities: preserve the
30-club denominator and supply fallback labels when the live team directory has
no row. It is not a source of Team State, roster membership, ordering quality,
or any other baseball intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MlbClub:
    team_id: int
    abbreviation: str
    team_name: str


MLB_CLUBS = (
    MlbClub(108, 'LAA', 'Los Angeles Angels'),
    MlbClub(109, 'AZ', 'Arizona Diamondbacks'),
    MlbClub(110, 'BAL', 'Baltimore Orioles'),
    MlbClub(111, 'BOS', 'Boston Red Sox'),
    MlbClub(112, 'CHC', 'Chicago Cubs'),
    MlbClub(113, 'CIN', 'Cincinnati Reds'),
    MlbClub(114, 'CLE', 'Cleveland Guardians'),
    MlbClub(115, 'COL', 'Colorado Rockies'),
    MlbClub(116, 'DET', 'Detroit Tigers'),
    MlbClub(117, 'HOU', 'Houston Astros'),
    MlbClub(118, 'KC', 'Kansas City Royals'),
    MlbClub(119, 'LAD', 'Los Angeles Dodgers'),
    MlbClub(120, 'WSH', 'Washington Nationals'),
    MlbClub(121, 'NYM', 'New York Mets'),
    MlbClub(133, 'ATH', 'Athletics'),
    MlbClub(134, 'PIT', 'Pittsburgh Pirates'),
    MlbClub(135, 'SD', 'San Diego Padres'),
    MlbClub(136, 'SEA', 'Seattle Mariners'),
    MlbClub(137, 'SF', 'San Francisco Giants'),
    MlbClub(138, 'STL', 'St. Louis Cardinals'),
    MlbClub(139, 'TB', 'Tampa Bay Rays'),
    MlbClub(140, 'TEX', 'Texas Rangers'),
    MlbClub(141, 'TOR', 'Toronto Blue Jays'),
    MlbClub(142, 'MIN', 'Minnesota Twins'),
    MlbClub(143, 'PHI', 'Philadelphia Phillies'),
    MlbClub(144, 'ATL', 'Atlanta Braves'),
    MlbClub(145, 'CWS', 'Chicago White Sox'),
    MlbClub(146, 'MIA', 'Miami Marlins'),
    MlbClub(147, 'NYY', 'New York Yankees'),
    MlbClub(158, 'MIL', 'Milwaukee Brewers'),
)

EXPECTED_CLUB_COUNT = len(MLB_CLUBS)
MLB_TEAM_IDS = tuple(club.team_id for club in MLB_CLUBS)
