"""The read-only truth certification harness against a real trusted publication.

A disposable PostgreSQL publication is built through the canonical publisher
(the trusted-publication rehearsal). The harness must certify it without
writing anything, report every domain, and catch a planted contradiction
between a frozen fact and the canonical rows behind it.
"""

from datetime import timedelta

import pytest
from sqlalchemy import event

from models.game_log import GameLog
from models.roster_status_snapshot import RosterStatusSnapshot
from services import publication_truth_certification as certification
from services.mlb_club_directory import MLB_CLUBS
from tests.test_trusted_publication_rehearsal import _TonightRehearsal
from utils.db import db


def _rehearsed(monkeypatch):
    rehearsal = _TonightRehearsal(monkeypatch, name='truth certification')
    return rehearsal


def _no_writes(connection_owner):
    statements = []

    def record(_conn, _cursor, statement, *_args):
        verb = statement.lstrip().split(' ', 1)[0].upper()
        if verb in {'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'ALTER', 'DROP', 'CREATE'}:
            statements.append(statement)

    return statements, record


def test_certifies_a_real_publication_without_writing(monkeypatch):
    rehearsal = _rehearsed(monkeypatch)
    with rehearsal.app.app_context():
        try:
            rehearsal.setup()
            snapshot = rehearsal.publish('cert_base')
            engine = db.session.get_bind()
            writes, record = _no_writes(engine)
            event.listen(engine, 'before_cursor_execute', record)
            try:
                report = certification.certify_snapshot(snapshot)
            finally:
                event.remove(engine, 'before_cursor_execute', record)

            assert writes == []
            assert report['snapshot_id'] == snapshot.id
            assert report['contract'] == certification.CERTIFICATION_CONTRACT
            assert set(report['domains']) == {
                'roster', 'workload', 'team_state', 'schedule', 'tonight'}
            assert set(report['team_verdicts']) == {club.abbreviation for club in MLB_CLUBS}
            assert report['teams_passed'] + report['teams_conditional'] + report[
                'teams_failed'] == 30
            assert len(report['team_state']) == 30
            assert report['tonight'], 'the publication carries a tonight_v1 edition'
            for team in report['team_state'].values():
                assert team['receipt_present'] is True
        finally:
            db.session.rollback()
            db.session.remove()
            from tests.test_trusted_publication_rehearsal import drop_test_schema
            drop_test_schema(rehearsal.app)


def test_a_planted_workload_contradiction_fails_the_team(monkeypatch):
    rehearsal = _rehearsed(monkeypatch)
    with rehearsal.app.app_context():
        try:
            rehearsal.setup()
            snapshot = rehearsal.publish('cert_contradiction')
            baseline = certification.certify_workload(snapshot)
            team_id, arm = next(
                (int(team_id), item)
                for team_id, team_package in snapshot.payload['trusted_team_boards'][
                    'by_team_id'].items()
                for item in (team_package.get('recent_usage_rest') or {}).get(
                    'active_pitchers') or ()
                if (item.get('pitched_yesterday') or {}).get('status') == 'complete'
                and (item.get('pitched_yesterday') or {}).get('value') is False
            )
            # A relief appearance yesterday that the frozen fact never saw.
            db.session.add(GameLog(
                pitcher_id=arm['pitcher_id'], mlb_game_pk=99887766,
                game_date=snapshot.data_through, games_started=0,
                innings_pitched=1.0, innings_pitched_outs=3, pitches_thrown=15,
            ))
            db.session.flush()
            planted = certification.certify_workload(snapshot)
            assert baseline[team_id]['verdict'] != certification.FAIL
            assert planted[team_id]['verdict'] == certification.FAIL
            mismatch = next(m for m in planted[team_id]['mismatches']
                            if m['pitcher_id'] == arm['pitcher_id'])
            assert mismatch['diff']['pitched_yesterday'] == {
                'published': False, 'recount': True}
        finally:
            db.session.rollback()
            db.session.remove()
            from tests.test_trusted_publication_rehearsal import drop_test_schema
            drop_test_schema(rehearsal.app)


def test_a_roster_snapshot_on_another_club_fails_roster(monkeypatch):
    rehearsal = _rehearsed(monkeypatch)
    with rehearsal.app.app_context():
        try:
            rehearsal.setup()
            snapshot = rehearsal.publish('cert_roster')
            membership = snapshot.availability_reference_date
            roster = certification.certify_roster(snapshot, membership_date=membership)
            team_id = next(t for t, r in roster.items() if r['active_bullpen_count'])
            from services import tonight_read_model
            team_package = snapshot.payload['trusted_team_boards']['by_team_id'][str(team_id)]
            pitcher_id = tonight_read_model._active_arms(team_package)[0]['pitcher_id']
            row = RosterStatusSnapshot.query.filter_by(
                pitcher_id=pitcher_id, snapshot_date=membership).one_or_none()
            if row is None:
                pytest.skip('rehearsal seeds no roster snapshot on the membership date')
            row.team_id = 999
            db.session.flush()
            after = certification.certify_roster(snapshot, membership_date=membership)
            assert after[team_id]['verdict'] == certification.FAIL
            assert {i['issue'] for i in after[team_id]['issues']} == {
                'roster_snapshot_other_team'}
        finally:
            db.session.rollback()
            db.session.remove()
            from tests.test_trusted_publication_rehearsal import drop_test_schema
            drop_test_schema(rehearsal.app)


def test_script_runs_read_only_and_reports(monkeypatch, tmp_path):
    from scripts import certify_publication_truth as script

    rehearsal = _rehearsed(monkeypatch)
    with rehearsal.app.app_context():
        try:
            rehearsal.setup()
            snapshot = rehearsal.publish('cert_script')
            monkeypatch.setattr('app.app', rehearsal.app, raising=False)
            output = tmp_path / 'report.json'
            code = script.main(['--snapshot-id', str(snapshot.id), '--output', str(output)])
            assert code in (0, 1)
            assert output.exists()
        finally:
            db.session.rollback()
            db.session.remove()
            from tests.test_trusted_publication_rehearsal import drop_test_schema
            drop_test_schema(rehearsal.app)
