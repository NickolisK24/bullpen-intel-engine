from datetime import date, datetime, timedelta

from models.dashboard_snapshot import DashboardSnapshot
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.sync_run import SyncRun
from services.pitcher_performance import pitcher_performance
from services.share_artifacts import build_share_artifact_draft, publish_share_artifact
from services.team_performance_evidence import game_receipt
from tests.test_public_recent_work import client, _log, _pitcher
from tests.test_team_board_what_changed import TEAM_ID, _install_board_inputs, _snapshot
from utils.db import db


def test_two_performance_samples_and_incomplete_evidence(client):
    with client.application.app_context():
        pitcher = _pitcher()
        db.session.add(pitcher)
        db.session.flush()
        day = date(2026, 9, 28)
        rows = []
        for pk, days_ago, starts, game_type in [
            (1, 29, 0, 'R'), (2, 30, 0, 'R'), (3, 0, 1, 'R'), (4, 0, None, 'R'),
            (5, -1, 0, 'R'), (6, 0, 0, 'P'),
        ]:
            row = _log(pitcher.id, pk, day - timedelta(days=days_ago), strikeouts=2, walks=1)
            row.games_started, row.game_type = starts, game_type
            row.appearance_team_id, row.appearance_team_status = TEAM_ID, 'resolved'
            rows.append(row)
        db.session.add_all(rows)
        first = rows[0]
        stats = {'strikeOuts': 2, 'baseOnBalls': 1, 'homeRuns': 0, 'battersFaced': 4,
                 'earnedRuns': 0, 'inheritedRunners': 2, 'inheritedRunnersScored': 0}
        player = {'person': {'id': pitcher.mlb_id}, 'stats': {'pitching': stats}}
        box = {'teams': {'away': {'team': {'id': TEAM_ID}, 'players': {f'ID{pitcher.mlb_id}': player}}}}
        receipt = game_receipt(1, first.game_date, 'rev', box, [{
            'pitcher_mlb_id': pitcher.mlb_id, 'team_id': TEAM_ID, 'appearance_role': 'relief', 'side': 'away'}])
        item = GameIngestionWorkItem(mlb_game_pk=1, game_date=first.game_date, represented_date=first.game_date,
            game_type='R', status='completed', candidate_reason='newly_final', criticality='publication_critical',
            rows_expected=1, rows_reconciled=1, source_revision='rev', completed_at=datetime.now(),
            completion_proof={'performance_lines': receipt})
        db.session.add(item)
        result = pitcher_performance(pitcher, day)
        assert [result[k]['outings'] for k in ('recent', 'season')] == [1, 2]
        assert {k: v['value'] for k, v in result['recent']['metrics'].items()} == {
            'era': '0.00', 'whip': '1.00', 'hr9': '0.00', 'k_bb_percent': '25.00', 'inherited': '0 of 2'}
        assert result['season']['metrics']['era'] == {'covered': 1, 'value': None, 'denominator': None, 'unit': 'outs'}
        assert result['recent']['metrics']['k_bb_percent']['denominator'] == 4
        first.innings_pitched_outs, first.innings_pitched = 0, 0.0
        zero_outs = pitcher_performance(pitcher, day)['recent']['metrics']
        assert zero_outs['era'] == {'covered': 1, 'value': None, 'denominator': 0, 'unit': 'outs'}
        assert zero_outs['k_bb_percent']['value'] == '25.00'
        item.source_revision = 'superseded'
        first.walks = None
        assert all(m['value'] is None for m in pitcher_performance(pitcher, day)['recent']['metrics'].values())


def test_cited_labels_require_exact_published_editions_and_never_bridge_gaps(client):
    from api.bullpen import bullpen_bp
    from services.pitcher_public_labels import ROLE_PUBLIC_LABELS

    client.application.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with client.application.app_context():
        arm = _pitcher()
        arm.id = 7
        db.session.add(arm)
        run = SyncRun(status='success')
        db.session.add(run)
        db.session.flush()
        citations = {}
        for day, read, role in [(19, 'watch_arm', 'trust_arm'), (21, 'clean_option', 'bridge_arm'),
                                (22, 'watch_arm', 'trust_arm'), (23, 'clean_option', 'depth_arm')]:
            fake = _snapshot(day, f'2026-09-{day}')
            team = _install_board_inputs(fake, read, 0)
            team['records'][0]['public_role_read'] = ROLE_PUBLIC_LABELS[role]
            source = DashboardSnapshot(id=day, snapshot_type='bullpen_dashboard', status='ready', is_published=False,
                data_through=fake.data_through, availability_reference_date=fake.availability_reference_date,
                sync_run_id=run.id, payload=fake.payload, published_at=datetime(2026, 9, day))
            db.session.add(source)
            db.session.flush()
            draft = build_share_artifact_draft(artifact_type='team_state', team_id=TEAM_ID,
                source_snapshot_id=source.id, source_sync_run_id=run.id, product_date=fake.data_through,
                payload={'team': {'team_id': TEAM_ID}}, render_version='team-state-1.2.0', source='test')
            db.session.commit()
            if day != 23:
                published = publish_share_artifact(draft)
                citations[day] = '/share/' + published.public_id
        db.session.commit()
        response = client.get('/api/bullpen/pitchers/7/publication-history?through=2026-09-23')
        assert response.status_code == 200
        days = response.json['days']
        assert not days[0]['edition']
        assert days[1]['edition']['citation'] == citations[22]
        assert days[1]['edition']['read'] == 'Watch Arm'
        assert days[1]['changes'] == {
            'role': {'from': 'Setup Arm', 'citation': citations[21]},
            'read': {'from': 'Clean Option', 'citation': citations[21]}}
        assert days[2]['changes'] == {} and days[3]['edition'] is None
        assert client.get('/api/bullpen/pitchers/7/publication-history?through=foo').status_code == 400
