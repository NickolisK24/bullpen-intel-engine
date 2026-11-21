import pytest

from services.mlb_club_directory import MLB_CLUBS
from services.team_story_previews import render_team_story_html
from sync_v3.team_preview_comparison import compare_team_page
from tests.test_team_story_previews import _preview, DATA_THROUGH, SNAPSHOT_ID, SYNC_RUN_ID


def test_dated_team_handoff_requires_the_club_and_exact_publication():
    club = next(club for club in MLB_CLUBS if club.abbreviation == 'TOR')
    page = render_team_story_html(_preview())
    publication = dict(data_through=DATA_THROUGH, publication_snapshot_id=SNAPSHOT_ID, sync_run_id=SYNC_RUN_ID)
    assert compare_team_page(page, club, publication=publication)['data_through'] == DATA_THROUGH
    with pytest.raises(ValueError, match='lacks publication'):
        compare_team_page(page, club)
    for key, value in [('data_through', '2026-08-09'), ('publication_snapshot_id', 4822), ('sync_run_id', 9108)]:
        with pytest.raises(ValueError, match='disagrees'):
            compare_team_page(page, club, publication=dict(publication, **{key: value}))
    switched = page.replace('team=TOR&amp;source=share', 'team=PIT&amp;source=share')
    with pytest.raises(ValueError, match='route differs'):
        compare_team_page(switched, club, publication=publication)


def test_withheld_page_cannot_carry_a_dated_receipt():
    club = next(club for club in MLB_CLUBS if club.abbreviation == 'TOR')
    page = render_team_story_html(_preview(board={}))
    checked = compare_team_page(page, club)
    assert checked['withheld_reason'] == 'no_trusted_publication' and checked['snapshot_id'] is None
    forged = page.replace('</head>', '<meta name="baseballos:snapshot-id" content="4821" /></head>')
    with pytest.raises(ValueError, match='carries a claim'):
        compare_team_page(forged, club)


def test_export_requires_the_full_club_denominator_even_when_counts_agree(tmp_path):
    from hashlib import sha256
    import json
    from zipfile import ZipFile
    from sync_v3.team_preview_comparison import compare_team_export

    report = tmp_path / 'report.zip'
    name = 'frontend/public/team/TOR/index.html'
    with ZipFile(report, 'w') as z:
        z.writestr('generated-digest.json', json.dumps([dict(path=name, sha256='a' * 64)]))
        z.writestr('export-result.json', json.dumps(dict(teams=1, previews=1, output=dict(files=[name], count=1))))
        z.writestr('publication.json', '{}')
    with pytest.raises(ValueError, match='30 clubs'):
        compare_team_export(report, sha256(report.read_bytes()).hexdigest(), tmp_path)


def test_competition_page_reproduction_requires_original_copy_and_complete_inputs():
    from services.team_story_previews import build_team_story_preview
    from sync_v3.team_preview_comparison import reproduce_competition_page
    from tests.test_team_story_previews import _team, _board, GENERATED_AT, PUBLISHED_AT

    club = next(club for club in MLB_CLUBS if club.abbreviation == 'TOR')
    team = _team(club.team_id, club.team_name, club.abbreviation)
    board = _board(team)
    state = dict(available=False, outcome='season_complete', public_label=None, unavailable_message='Season complete.')
    board['team_state'] = state
    preview = build_team_story_preview(team, board=board, generated_at=GENERATED_AT)
    body = render_team_story_html(preview).encode()
    pub = dict(publication_snapshot_id=SNAPSHOT_ID, sync_run_id=SYNC_RUN_ID, data_through=DATA_THROUGH, published_at=PUBLISHED_AT)
    export = dict(story_previews=0, generated_at=GENERATED_AT)
    page = compare_team_page(body.decode(), club, publication=pub)
    assert reproduce_competition_page(body, page, club, state, pub, export) == 'reproduced'
    with pytest.raises(ValueError, match='do not reproduce'):
        reproduce_competition_page(body.replace(b'Season complete.', b'Bullpen fresh.'), page, club, state, pub, export)
    for changed_export, changed_state in [(dict(export, story_previews=1), state), (export, dict(state, available=True))]:
        assert reproduce_competition_page(body, page, club, changed_state, pub, changed_export) == 'additional_story_or_board_inputs_required'
    assert reproduce_competition_page(body, dict(page, representation='withheld'), club, state, pub, export) == 'withheld_delivery'


def test_archived_available_read_keeps_uncounted_members_separate():
    from services.team_state_public_vocabulary import public_team_state
    from sync_v3.team_preview_comparison import reproduce_available_state
    from tests.test_team_state_vnext_production_proof import _evidence

    state = 'operationally_stressed'
    dist = dict(total=2, available=0, monitor=1, limited=1, avoid=0, unavailable=0, unknown=0)
    evidence = _evidence(0, 2, 0, 0, status_code=state, decisive_rule='margin_floor')
    dates = dict(membership_reference_date='2026-10-27', availability_reference_date='2026-10-28')
    group = dict(team_id=111, member_pitcher_ids=[1, 2, 3], missing_record_pitcher_ids=[3],
                 records=[dict(pitcher_id=1), dict(pitcher_id=2)], **dates)
    readiness = dict(team=dict(team_id=111), readiness=dict(status_code=state), availability_distribution=dist,
                     freshness=dict(data_through='2026-10-27'), team_state_evidence=evidence)
    inputs = dict(readiness=readiness, reference_dates=dates, arm_reads=group)
    observed = public_team_state(readiness)
    receipt = reproduce_available_state(inputs, observed, 111)
    assert receipt['team_state'] == 'Vulnerable' and receipt['current_partition_rule_matches']
    assert receipt['counted_pitchers'] == 2 and receipt['members_without_records'] == [3]
    assert reproduce_available_state({}, observed, 111)['status'] == 'missing_archived_readiness_inputs'
    with pytest.raises(ValueError, match='partition differs'):
        reproduce_available_state(dict(inputs, arm_reads=dict(group, missing_record_pitcher_ids=[2])), observed, 111)
    with pytest.raises(ValueError, match='observed state'):
        reproduce_available_state(inputs, dict(observed, public_label='Fresh'), 111)
    with pytest.raises(ValueError, match='decision differs'):
        reproduce_available_state(dict(inputs, readiness=dict(readiness, team_state_evidence=dict(
            evidence, decisive_rule='fresh_coverage'))), observed, 111)
