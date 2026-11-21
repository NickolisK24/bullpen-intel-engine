from datetime import date, datetime, timezone

import pytest

from sync_v3.canonical import Refused
from sync_v3.discovery import Request
from sync_v3.rosters import roster_facts
from sync_v3.sources import inspect_response


def view(team, members, kind='active'):
    req = Request(f'/teams/{team}/roster', (('date','2026-09-26'), ('rosterType',kind)), 0)
    return inspect_response(req, {'teamId': team, 'rosterType':kind, 'roster':members},
                            datetime(2026,10,3,tzinfo=timezone.utc))


def test_old_club_evidence_is_scoped_by_represented_day_and_membership_class():
    person = {'person': {'id': 670103}}
    assert roster_facts(view(111, []))['represented'] == date(2026,9,26).isoformat()
    assert roster_facts(view(111, [person], '40Man'))['members'][0]['id'] == 670103
    with pytest.raises(Refused, match='Affiliate'):
        roster_facts(view(999, [person]))
    conflicted = roster_facts(view(111, [dict(person,status={'code':'A'}),dict(person,status={'code':'D60'})]))
    assert len(conflicted['members']) == 1
    assert conflicted['members'][0]['status'] is None
    assert conflicted['members'][0]['source_statuses'] == ['A','D60']
    with pytest.raises(Refused, match='scope conflict'):
        roster_facts(view(111, [dict(person,parentTeamId=6052)]))
