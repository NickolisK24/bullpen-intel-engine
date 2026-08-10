"""The routed `/team/{ABBR}` preview contract (DIST-003 / #594).

The old contract was "say something about tonight." These tests assert the new
one: a generated team representation states which baseball date it describes,
which trusted publication it came from, and what BaseballOS actually called that
bullpen — in the canonical public vocabulary — or it publishes no team claim at
all.
"""

import ast
import re
from pathlib import Path

import pytest

from services.team_bullpen_shape import TEAM_BULLPEN_PUBLIC_LABELS
from services.team_story_previews import (
    REPRESENTATION_DATED_READ,
    REPRESENTATION_WITHHELD,
    WITHHELD_AUTHORITY_MISMATCH,
    WITHHELD_NO_DATA_THROUGH,
    WITHHELD_NO_TRUSTED_PUBLICATION,
    build_team_story_preview,
    build_team_story_previews,
    render_invalid_team_html,
    render_team_story_html,
    write_team_story_pages,
)


# One trusted publication. The publication day is DELIBERATELY later than the
# baseball date it describes — that is the normal, correct case (the export runs
# in the morning, after the prior night's games completed), and every assertion
# about the two staying separate depends on the fixture actually differing.
SNAPSHOT_ID = 4821
SYNC_RUN_ID = 9107
DATA_THROUGH = '2026-08-08'
AVAILABILITY_REFERENCE_DATE = '2026-08-09'
SNAPSHOT_GENERATED_AT = '2026-08-09T10:04:00+00:00'
PUBLISHED_AT = '2026-08-09T10:12:00+00:00'
GENERATED_AT = '2026-08-09T10:31:00+00:00'

ISO_DATE = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')

# The in-product team-shape read labels. #594 removes them from the generated
# public metadata; it deliberately does NOT retire them from the Team Board.
SHAPE_LABELS = sorted({
    label
    for labels in TEAM_BULLPEN_PUBLIC_LABELS.values()
    for label in labels
})


def _team(team_id=1, name='Toronto Blue Jays', abbr='TOR'):
    return {
        'team_id': team_id,
        'team_name': name,
        'team_abbreviation': abbr,
    }


def _publication_authority(snapshot_id=SNAPSHOT_ID, data_through=DATA_THROUGH):
    return {
        'contract': 'trusted_dashboard_publication_v1',
        'authority_type': 'dashboard_snapshot',
        'snapshot_id': snapshot_id,
        'sync_run_id': SYNC_RUN_ID,
        'data_through': data_through,
        'availability_reference_date': AVAILABILITY_REFERENCE_DATE,
        'snapshot_generated_at': SNAPSHOT_GENERATED_AT,
        'published_at': PUBLISHED_AT,
    }


def _team_state(label='Stretched'):
    if label is None:
        return {
            'contract': 'team_state_public_v1',
            'available': False,
            'public_state': None,
            'public_label': None,
            'outcome': 'data_limited',
            'unavailable_message': (
                'A current Team State read is not available for this bullpen '
                'because the latest public workload and roster evidence is '
                'incomplete.'
            ),
            'reason_code': None,
            'data_through': DATA_THROUGH,
        }
    return {
        'contract': 'team_state_public_v1',
        'available': True,
        'public_state': label.lower(),
        'public_label': label,
        'outcome': 'available',
        'unavailable_message': None,
        'reason_code': None,
        'data_through': DATA_THROUGH,
    }


def _canonical_story(
    team=None,
    *,
    headline,
    share_title,
    share_summary,
    story_type='coverage_pressure',
    category='stressed',
    tone='stress',
    story_available=True,
):
    """A canonical story feed item (dashboard.stories.items shape)."""
    team = team or _team()
    return {
        'story_id': f"{team['team_id']}:2026-08-08",
        'team_id': team['team_id'],
        'team_name': team['team_name'],
        'team_abbreviation': team['team_abbreviation'],
        'date': '2026-08-08',
        'story_available': story_available,
        'story_type': story_type,
        'category': category,
        'tone': tone,
        'headline': headline,
        'narrative': (f'{headline}\n\nSupporting cause.' if headline else None),
        'share_title': share_title,
        'share_summary': share_summary,
        'continuity': {'state': 'new', 'reason': 'no_prior_canonical_story', 'compared': False},
    }


def _board(
    team=None,
    *,
    state_label='Stretched',
    shape_labels=None,
    reasons=None,
    health_label='The bullpen is short on rested arms right now.',
    publication_authority=-1,
    data_through=DATA_THROUGH,
):
    """A trusted published team board, in the shape build_published_team_board emits."""
    team = team or _team()
    shape_labels = shape_labels or {
        'trustAvailability': 'Stable Late-Inning Availability',
        'cleanOptions': 'Healthy Rested Bullpen',
        'bullpenPressure': 'Manageable Late-Inning Pressure',
    }
    if reasons is None:
        reasons = [
            'Five relievers are available from the latest completed workload data.',
            'Two relievers are in the On Watch group.',
            'Availability classifications are workload-based only.',
        ]
    if publication_authority == -1:
        publication_authority = _publication_authority(data_through=data_through)

    board = {
        'team': team,
        'team_state': _team_state(state_label),
        'freshness': {
            'data_through': data_through,
            'last_successful_sync': '2026-08-09T10:11:00+00:00',
            'is_current': True,
            'sync_status': 'success',
        },
        'context': {
            'metrics': {'total_relievers': 8, 'available': 5},
            'health': {
                'state': 'constrained',
                'label': health_label,
                'reasons': list(reasons),
            },
            'confidence': 'high',
            'limitations': [],
        },
        'team_shape': {
            'source': 'backend',
            'reads': [
                {
                    'key': key,
                    'label': label,
                    'summary': f'{label} fixture explanation.',
                    'explanation': f'{label} fixture explanation.',
                    'supportingCounts': {},
                }
                for key, label in shape_labels.items()
            ],
        },
        'served_from': 'trusted_dashboard_snapshot',
    }
    if publication_authority is not None:
        board['publication_authority'] = publication_authority
    return board


def _preview(team=None, **kwargs):
    team = team or _team()
    kwargs.setdefault('board', _board(team))
    kwargs.setdefault('generated_at', GENERATED_AT)
    kwargs.setdefault('expected_snapshot_id', SNAPSHOT_ID)
    return build_team_story_preview(team, **kwargs)


def _reader_facing_strings(page):
    """Every meaning-bearing string a reader or crawler sees on the page.

    Deliberately NOT a substring scan of the source: structured meta NAMES
    (`baseballos:snapshot-id`) are machine keys, not prose, and a vocabulary
    assertion that trips over them proves nothing.
    """
    values = []
    title = re.search(r'<title>(.*?)</title>', page, re.S)
    if title:
        values.append(title.group(1))
    for name in ('description', 'twitter:title', 'twitter:description'):
        for match in re.finditer(
            rf'<meta name="{re.escape(name)}" content="([^"]*)"', page
        ):
            values.append(match.group(1))
    for name in ('og:title', 'og:description'):
        for match in re.finditer(
            rf'<meta property="{re.escape(name)}" content="([^"]*)"', page
        ):
            values.append(match.group(1))
    body = re.search(r'<main>(.*?)</main>', page, re.S)
    if body:
        values.append(re.sub(r'<[^>]*>', ' ', body.group(1)))
    return values


def _body_text(page):
    body = re.search(r'<main>(.*?)</main>', page, re.S)
    assert body, f'page has no crawlable body: {page[:400]}'
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', body.group(1))).strip()


# ── canonical story previews keep their copy and gain a date ────────────────

def test_pressure_story_uses_canonical_share_copy_with_tension_framing():
    team = _team()
    share_title = 'Toronto Blue Jays bullpen: coverage pressure'
    share_summary = 'The Blue Jays are leaning on a small group of late-inning arms tonight.'
    story = _canonical_story(
        team,
        headline='The Blue Jays are carrying the late innings on a few arms',
        share_title=share_title,
        share_summary=share_summary,
    )

    preview = _preview(team, story=story)

    assert preview['has_story'] is True
    assert preview['source'] == 'canonical_story'
    assert preview['framing'] == 'tension'
    assert preview['og_title'] == share_title
    # The canonical sentence survives word for word; #594 only anchors it in time.
    assert preview['og_description'] == f'{share_summary} Data through {DATA_THROUGH}.'
    assert preview['og_title'] != preview['og_description']
    assert preview['og_url'] == 'https://baseballos.app/team/TOR'
    assert preview['story_type'] == 'coverage_pressure'
    assert preview['authority']['title'] == 'canonical_story.share_title'
    assert preview['authority']['description'] == 'canonical_story.share_summary+data_through'
    assert preview['redirect_path'] == '/bullpen?view=board&team=TOR&source=share'


def test_rested_story_uses_clean_framing():
    team = _team(2, 'Los Angeles Dodgers', 'LAD')
    story = _canonical_story(
        team,
        headline='The Dodgers have more rested options than most clubs today',
        share_title='Los Angeles Dodgers bullpen: availability depth',
        share_summary='Most of the Dodgers pen is available and rested tonight.',
        story_type='availability_depth',
        category='rested',
        tone='rest',
    )

    preview = _preview(team, story=story, board=_board(team, state_label='Fresh'))

    assert preview['framing'] == 'clean'
    assert preview['og_title'] == 'Los Angeles Dodgers bullpen: availability depth'
    assert preview['og_description'].startswith(
        'Most of the Dodgers pen is available and rested tonight.'
    )
    assert preview['og_description'].endswith(f'Data through {DATA_THROUGH}.')


def test_watch_tone_story_uses_tension_framing():
    team = _team(4, 'Chicago Cubs', 'CHC')
    story = _canonical_story(
        team,
        headline='The Cubs are settled at the back but fragile in the bridge',
        share_title='Chicago Cubs bullpen: bridge instability',
        share_summary='The Cubs have a trusted closer but a thin path to reach him.',
        story_type='bridge',
        category='watch',
        tone='watch',
    )

    preview = _preview(team, story=story, board=_board(team))

    assert preview['framing'] == 'tension'
    assert preview['og_title'] == 'Chicago Cubs bullpen: bridge instability'


def test_title_falls_back_to_headline_when_share_title_missing():
    team = _team(7, 'Fixture Club', 'FIX')
    story = _canonical_story(
        team,
        headline='The Fixture Club lean on a short bridge tonight',
        share_title=None,
        share_summary='Only two trusted arms are available late.',
    )

    preview = _preview(team, story=story, board=_board(team))

    assert preview['og_title'] == 'The Fixture Club lean on a short bridge tonight'
    assert preview['og_description'] == (
        f'Only two trusted arms are available late. Data through {DATA_THROUGH}.'
    )


def test_story_without_any_share_copy_raises():
    team = _team(8, 'Empty Club', 'EMP')
    story = _canonical_story(team, headline=None, share_title=None, share_summary=None)

    with pytest.raises(ValueError, match='missing a share title'):
        _preview(team, story=story, board=_board(team))


def test_story_preview_records_its_story_id():
    team = _team()
    story = _canonical_story(
        team,
        headline='A headline',
        share_title='A share title',
        share_summary='A share summary.',
    )

    preview = _preview(team, story=story)
    page = render_team_story_html(preview)

    assert preview['story_id'] == f"{team['team_id']}:2026-08-08"
    assert f'<meta name="baseballos:story-id" content="{preview["story_id"]}" />' in page


# ── neutral previews now speak canonical Team State ─────────────────────────

def test_neutral_team_leads_with_canonical_team_state_and_a_baseball_point():
    # The regression this locks: the neutral read used to be
    # "Tonight's board: <shape label>; <shape label>; <shape label>." — an undated
    # present-tense claim in a vocabulary that belongs to no canonical catalogue.
    team = _team(3, 'Quiet Club', 'QUT')

    preview = _preview(team, board=_board(team, state_label='Stretched'))

    assert preview['has_story'] is False
    assert preview['source'] == 'trusted_team_board'
    assert preview['team_state_label'] == 'Stretched'
    assert preview['og_title'] == 'Quiet Club Bullpen: Stretched'
    assert preview['og_description'] == (
        'Quiet Club bullpen state: Stretched. '
        'Five relievers are available from the latest completed workload data. '
        f'Data through {DATA_THROUGH}.'
    )
    assert preview['og_title'] != preview['og_description']
    assert "Tonight's board" not in preview['og_description']
    assert 'Stands Tonight' not in preview['og_title']


def test_every_canonical_state_label_is_rendered_verbatim():
    for label in ('Fresh', 'Stretched', 'Vulnerable'):
        team = _team(11, 'Vocab Club', 'VOC')
        preview = _preview(team, board=_board(team, state_label=label))
        assert preview['team_state_label'] == label
        assert preview['og_title'] == f'Vocab Club Bullpen: {label}'


def test_shape_read_labels_never_become_public_state_metadata():
    team = _team(12, 'Shape Club', 'SHP')
    board = _board(
        team,
        shape_labels={
            'trustAvailability': 'Thin Late-Inning Availability',
            'cleanOptions': 'Very Thin Rested Bullpen',
            'bullpenPressure': 'High Late-Inning Pressure',
        },
    )

    page = render_team_story_html(_preview(team, board=board))

    offenders = [
        (label, value)
        for value in _reader_facing_strings(page)
        for label in SHAPE_LABELS
        if re.search(rf'\b{re.escape(label)}\b', value)
    ]
    assert offenders == [], offenders


def test_governed_non_state_is_rendered_honestly_and_still_dated():
    team = _team(13, 'Limited Club', 'LIM')
    board = _board(team, state_label=None)

    preview = _preview(team, board=board)

    assert preview['team_state_label'] is None
    assert preview['non_state_message'].startswith(
        'A current Team State read is not available for this bullpen'
    )
    assert preview['og_title'] == 'Limited Club Bullpen Read'
    assert preview['og_description'].startswith(preview['non_state_message'])
    assert preview['og_description'].endswith(f'Data through {DATA_THROUGH}.')
    # A non-state is not a fourth state.
    for label in ('Fresh', 'Stretched', 'Vulnerable'):
        assert f'Bullpen: {label}' not in preview['og_title']


def test_a_limited_read_is_stated_rather_than_silently_dropped():
    # The old builder filtered `Limited Read` out of the label list and could
    # degrade to a generic sentence with no trace of the limitation.
    team = _team(14, 'Thin Club', 'THN')
    board = _board(
        team,
        reasons=[],
        health_label='',
        shape_labels={
            'trustAvailability': 'Limited Read',
            'cleanOptions': 'Limited Read',
            'bullpenPressure': 'Limited Read',
        },
    )

    preview = _preview(team, board=board)

    assert preview['baseball_point'] == 'Supporting bullpen reads are limited for this team.'
    assert preview['baseball_point'] in preview['og_description']


# ── one trusted publication per page ────────────────────────────────────────

def test_preview_records_the_snapshot_it_was_generated_from():
    preview = _preview()
    page = render_team_story_html(preview)

    assert preview['snapshot_id'] == str(SNAPSHOT_ID)
    assert preview['sync_run_id'] == str(SYNC_RUN_ID)
    assert preview['authority_contract'] == 'trusted_dashboard_publication_v1'
    assert f'<meta name="baseballos:snapshot-id" content="{SNAPSHOT_ID}" />' in page
    assert f'<meta name="baseballos:sync-run-id" content="{SYNC_RUN_ID}" />' in page
    assert (
        '<meta name="baseballos:authority-contract" '
        'content="trusted_dashboard_publication_v1" />'
    ) in page


def test_a_board_from_a_different_snapshot_cannot_be_published_with_this_story_feed():
    # AC-7: story copy and board copy on one page must resolve from ONE trusted
    # publication. A board that came from a later snapshot is withheld, not mixed.
    team = _team()
    story = _canonical_story(
        team,
        headline='A headline',
        share_title='A share title',
        share_summary='A share summary.',
    )
    board = _board(team, publication_authority=_publication_authority(snapshot_id=99999))

    preview = _preview(team, story=story, board=board)

    assert preview['representation'] == REPRESENTATION_WITHHELD
    assert preview['withheld_reason'] == WITHHELD_AUTHORITY_MISMATCH
    assert preview['data_through'] is None
    assert preview['snapshot_id'] is None
    assert 'A share summary.' not in preview['og_description']


def test_no_trusted_publication_publishes_no_present_tense_team_claim():
    # AC-8. A board with freshness but no publication authority did not come from
    # a trusted publication and must not be dressed as though it did.
    team = _team(15, 'Untrusted Club', 'UNT')
    board = _board(team, publication_authority=None)

    preview = _preview(team, board=board)

    assert preview['representation'] == REPRESENTATION_WITHHELD
    assert preview['withheld_reason'] == WITHHELD_NO_TRUSTED_PUBLICATION
    assert preview['team_state_label'] is None
    assert preview['data_through'] is None
    assert 'bullpen state:' not in preview['og_description']
    assert preview['og_description'].startswith(
        'A dated BaseballOS bullpen read is not published for this team right now.'
    )
    # Identity and the live handoff survive a withheld claim.
    assert preview['team_abbreviation'] == 'UNT'
    assert preview['redirect_path'] == '/bullpen?view=board&team=UNT&source=share'


def test_missing_data_through_publishes_no_present_tense_team_claim():
    team = _team(16, 'Undated Club', 'UND')
    board = _board(team, data_through=None)
    board['freshness']['data_through'] = None

    preview = _preview(team, board=board)

    assert preview['representation'] == REPRESENTATION_WITHHELD
    assert preview['withheld_reason'] == WITHHELD_NO_DATA_THROUGH


def test_a_withheld_page_carries_no_date_and_no_snapshot_receipt():
    team = _team(17, 'Silent Club', 'SIL')
    page = render_team_story_html(_preview(team, board=_board(team, publication_authority=None)))

    assert f'<meta name="baseballos:representation" content="{REPRESENTATION_WITHHELD}" />' in page
    assert 'baseballos:data-through' not in page
    assert 'baseballos:snapshot-id' not in page
    assert '<meta name="baseballos:generated-at"' in page
    assert not ISO_DATE.search(_body_text(page))


# ── temporal semantics stay four separate facts ─────────────────────────────

def test_publication_time_and_baseball_data_through_are_never_collapsed():
    # Published/generated 2026-08-09, describing baseball data through 2026-08-08.
    # That is correct, and it is only correct because the page says both.
    preview = _preview()
    page = render_team_story_html(preview)

    assert preview['data_through'] == '2026-08-08'
    assert preview['generated_at'] == '2026-08-09T10:31:00+00:00'
    assert preview['published_at'] == '2026-08-09T10:12:00+00:00'
    assert preview['snapshot_generated_at'] == '2026-08-09T10:04:00+00:00'
    assert preview['availability_reference_date'] == '2026-08-09'

    assert len({
        preview['data_through'],
        preview['generated_at'],
        preview['published_at'],
        preview['snapshot_generated_at'],
    }) == 4

    assert '<meta name="baseballos:data-through" content="2026-08-08" />' in page
    assert '<meta name="baseballos:generated-at" content="2026-08-09T10:31:00+00:00" />' in page
    assert '<meta name="baseballos:published-at" content="2026-08-09T10:12:00+00:00" />' in page
    # The claim-bearing description carries the BASEBALL date, not the publish time.
    assert 'Data through 2026-08-08.' in preview['og_description']
    assert '2026-08-09T' not in preview['og_description']


def test_published_at_is_omitted_only_when_it_is_the_same_fact_as_generated_at():
    team = _team(18, 'Same Club', 'SAM')
    authority = _publication_authority()
    authority['published_at'] = GENERATED_AT
    page = render_team_story_html(
        _preview(team, board=_board(team, publication_authority=authority))
    )

    assert 'baseballos:published-at' not in page
    assert f'<meta name="baseballos:generated-at" content="{GENERATED_AT}" />' in page


# ── rendered page contract ──────────────────────────────────────────────────

def test_static_html_keeps_the_og_contract_and_the_human_redirect():
    team = _team()
    story = _canonical_story(
        team,
        headline='The Blue Jays have more rested options than most clubs today',
        share_title='Toronto Blue Jays bullpen: availability depth',
        share_summary='Most of the Blue Jays pen is available and rested tonight.',
        story_type='availability_depth',
        category='rested',
        tone='rest',
    )
    page = render_team_story_html(_preview(team, story=story))

    assert (
        '<meta property="og:title" content="Toronto Blue Jays bullpen: availability depth" />'
        in page
    )
    assert (
        '<meta property="og:description" content="Most of the Blue Jays pen is available '
        f'and rested tonight. Data through {DATA_THROUGH}." />'
    ) in page
    assert '<meta property="og:url" content="https://baseballos.app/team/TOR" />' in page
    assert '<link rel="canonical" href="https://baseballos.app/team/TOR" />' in page
    assert 'window.location.replace("/bullpen?view=board&amp;team=TOR&amp;source=share")' not in page
    assert 'window.location.replace("/bullpen?view=board&team=TOR&source=share")' in page
    assert '<div id="root"></div>' not in page


def test_the_crawlable_body_states_team_state_point_date_and_the_current_board():
    team = _team(19, 'Crawl Club', 'CRW')
    page = render_team_story_html(_preview(team, board=_board(team, state_label='Vulnerable')))
    body = _body_text(page)

    assert 'Crawl Club Bullpen' in body
    assert 'BaseballOS Team State: Vulnerable.' in body
    assert 'Five relievers are available from the latest completed workload data.' in body
    assert 'Baseball data through' in body
    assert DATA_THROUGH in body
    # The date is marked up as a machine-readable time, not just prose.
    assert f'<time datetime="{DATA_THROUGH}">{DATA_THROUGH}</time>' in page
    assert f'published snapshot {SNAPSHOT_ID}' in body
    assert 'Open the current Crawl Club bullpen board' in body
    assert 'href="/bullpen?view=board&amp;team=CRW&amp;source=share"' in page
    # The body is a citation, not a product surface.
    assert '<div id="root"' not in page
    assert 'react' not in page.lower()


def test_every_claim_bearing_description_carries_a_parseable_date():
    teams = [_team(index, f'Club {index}', f'C{index:02d}') for index in range(1, 6)]
    previews = [_preview(team, board=_board(team)) for team in teams]

    for preview in previews:
        assert preview['representation'] == REPRESENTATION_DATED_READ
        assert ISO_DATE.search(preview['og_description']), preview['og_description']
        assert preview['data_through'] == DATA_THROUGH


# ── index construction ──────────────────────────────────────────────────────

def test_build_team_story_previews_consumes_canonical_stories_by_team_identity():
    tor = _team(141, 'Toronto Blue Jays', 'TOR')
    lad = _team(119, 'Los Angeles Dodgers', 'LAD')
    nym = _team(121, 'New York Mets', 'NYM')
    payload = {
        'stories': {
            'capability': 'baseballos_canonical_story_v1',
            'items': [
                _canonical_story(
                    tor,
                    headline='The Blue Jays are carrying the late innings on a few arms',
                    share_title='Toronto Blue Jays bullpen: coverage pressure',
                    share_summary='Toronto is leaning on a small late-inning group tonight.',
                ),
                # A suppressed canonical story is excluded from the index and
                # falls through to the neutral trusted-board read.
                _canonical_story(
                    nym,
                    headline=None,
                    share_title=None,
                    share_summary=None,
                    story_available=False,
                ),
            ],
        },
    }

    previews = build_team_story_previews(
        [lad, tor, nym],
        dashboard_payload=payload,
        boards=[_board(tor), _board(lad), _board(nym)],
        generated_at=GENERATED_AT,
        expected_snapshot_id=SNAPSHOT_ID,
    )
    by_abbr = {preview['team_abbreviation']: preview for preview in previews}

    assert by_abbr['TOR']['has_story'] is True
    assert by_abbr['TOR']['og_title'] == 'Toronto Blue Jays bullpen: coverage pressure'
    assert by_abbr['LAD']['has_story'] is False
    assert by_abbr['LAD']['source'] == 'trusted_team_board'
    assert by_abbr['NYM']['has_story'] is False
    assert by_abbr['NYM']['source'] == 'trusted_team_board'
    assert [preview['team_abbreviation'] for preview in previews] == ['LAD', 'NYM', 'TOR']
    # One publication for the whole run.
    assert {preview['snapshot_id'] for preview in previews} == {str(SNAPSHOT_ID)}
    assert {preview['generated_at'] for preview in previews} == {GENERATED_AT}


def test_pages_contain_canonical_story_content_not_board_only(tmp_path):
    team = _team(141, 'Toronto Blue Jays', 'TOR')
    story = _canonical_story(
        team,
        headline='The Blue Jays are carrying the late innings on a few arms',
        share_title='Toronto Blue Jays bullpen: coverage pressure',
        share_summary='Toronto is leaning on a small late-inning group tonight.',
    )
    previews = build_team_story_previews(
        [team],
        dashboard_payload={'stories': {'items': [story]}},
        boards=[_board(team)],
        generated_at=GENERATED_AT,
        expected_snapshot_id=SNAPSHOT_ID,
    )

    write_team_story_pages(previews, tmp_path)
    page = (tmp_path / 'team' / 'TOR' / 'index.html').read_text(encoding='utf-8')

    assert 'Toronto Blue Jays bullpen: coverage pressure' in page
    assert 'Toronto is leaning on a small late-inning group tonight.' in page
    assert 'Toronto Blue Jays Bullpen: ' not in page


def test_writer_emits_one_page_per_team_plus_a_fallback_that_makes_no_team_claim(tmp_path):
    teams = [_team(index, f'Team {index}', f'T{index:02d}') for index in range(1, 31)]
    previews = [
        build_team_story_preview(
            team,
            board=_board(team),
            generated_at=GENERATED_AT,
            expected_snapshot_id=SNAPSHOT_ID,
        )
        for team in teams
    ]

    result = write_team_story_pages(previews, tmp_path)

    assert result['count'] == 30
    assert result['withheld_count'] == 0
    for team in teams:
        path = tmp_path / 'team' / team['team_abbreviation'] / 'index.html'
        assert path.exists(), path
        page = path.read_text(encoding='utf-8')
        assert '<meta property="og:title"' in page
        assert f'<meta name="baseballos:data-through" content="{DATA_THROUGH}" />' in page
        assert f'<meta name="baseballos:snapshot-id" content="{SNAPSHOT_ID}" />' in page
        assert '<meta name="baseballos:generated-at"' in page
        assert (
            f'<meta name="baseballos:representation" content="{REPRESENTATION_DATED_READ}" />'
            in page
        )

    fallback = Path(result['fallback'])
    fallback_html = fallback.read_text(encoding='utf-8')
    assert '<meta property="og:url" content="https://baseballos.app/team/" />' in fallback_html
    assert '<link rel="canonical" href="https://baseballos.app/team/" />' in fallback_html
    assert 'window.location.replace("/")' in fallback_html
    # The fallback names no team, states no state, and claims no baseball date.
    assert '<meta name="baseballos:representation" content="invalid_team" />' in fallback_html
    assert 'baseballos:data-through' not in fallback_html
    assert not ISO_DATE.search(fallback_html)
    for label in ('Fresh', 'Stretched', 'Vulnerable'):
        assert f'Bullpen: {label}' not in fallback_html


def test_the_writer_reports_which_teams_were_withheld(tmp_path):
    good = _team(20, 'Good Club', 'GDC')
    bad = _team(21, 'Withheld Club', 'WHC')
    previews = [
        build_team_story_preview(
            good, board=_board(good), generated_at=GENERATED_AT,
            expected_snapshot_id=SNAPSHOT_ID,
        ),
        build_team_story_preview(
            bad, board=_board(bad, publication_authority=None), generated_at=GENERATED_AT,
            expected_snapshot_id=SNAPSHOT_ID,
        ),
    ]

    result = write_team_story_pages(previews, tmp_path)

    assert result['count'] == 2
    assert result['withheld_count'] == 1
    assert result['withheld_teams'] == ['WHC']


def test_the_exporter_takes_the_trusted_published_board_and_never_the_live_builder():
    """AC-7 at the source: one publication authority, no live fallback.

    The exporter used to import ``api.bullpen._build_team_board`` and run it
    against mutable acquisition tables while taking its story copy from the
    published snapshot. Asserting the source directly is the cheapest honest
    proof, because the alternative needs a populated production database.
    """
    raw = (
        Path(__file__).resolve().parents[2]
        / 'backend/scripts/export_team_story_pages.py'
    ).read_text(encoding='utf-8')
    # The guard is about executable source. The module docstring names the old
    # builder on purpose, to record what changed and why.
    tree = ast.parse(raw)
    docstring = ast.get_docstring(tree) or ''
    source = raw.replace(docstring, '')

    assert 'build_published_team_board' in source
    assert '_build_team_board' not in source
    assert 'build_bullpen_dashboard_payload' not in source
    # Fail closed with no trusted publication: distinct exit code, nothing written.
    assert 'EXIT_NO_TRUSTED_PUBLICATION' in source
    assert 'expected_snapshot_id=snapshot_id' in source
    # The generated-at stamp is one value for the whole run, taken once.
    assert 'generated_at = datetime.now(timezone.utc)' in source


def test_invalid_team_page_makes_no_team_claim():
    page = render_invalid_team_html()
    body = _body_text(page)

    assert 'Open BaseballOS for current bullpen availability and trust reads.' in body
    assert not ISO_DATE.search(page)
    offenders = [
        label
        for value in _reader_facing_strings(page)
        for label in SHAPE_LABELS
        if re.search(rf'\b{re.escape(label)}\b', value)
    ]
    assert offenders == []
