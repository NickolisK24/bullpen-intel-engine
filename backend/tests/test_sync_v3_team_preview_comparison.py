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
