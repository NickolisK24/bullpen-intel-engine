from pathlib import Path

from services.team_story_previews import (
    build_team_story_preview,
    build_team_story_previews,
    render_team_story_html,
    write_team_story_pages,
)


def _team(team_id=1, name='Toronto Blue Jays', abbr='TOR'):
    return {
        'team_id': team_id,
        'team_name': name,
        'team_abbreviation': abbr,
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
        'story_id': f"{team['team_id']}:2026-06-22",
        'team_id': team['team_id'],
        'team_name': team['team_name'],
        'team_abbreviation': team['team_abbreviation'],
        'date': '2026-06-22',
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


def _board(team=None, labels=None):
    team = team or _team()
    labels = labels or {
        'trustAvailability': 'Stable Trust Arm Availability',
        'cleanOptions': 'Healthy Clean Options',
        'bullpenPressure': 'Manageable Trust-Lane Pressure',
    }
    return {
        'team': team,
        'team_shape': {
            'source': 'backend',
            'reads': [
                {
                    'key': key,
                    'label': label,
                    'explanation': f'{label} fixture explanation.',
                    'supportingCounts': {},
                }
                for key, label in labels.items()
            ],
        },
    }


def test_pressure_story_uses_canonical_share_copy_with_tension_framing():
    team = _team()
    share_title = 'Toronto Blue Jays bullpen: coverage pressure'
    share_summary = 'The Blue Jays are leaning on a small group of late-inning arms tonight.'
    story = _canonical_story(
        team,
        headline='The Blue Jays are carrying the late innings on a few arms',
        share_title=share_title,
        share_summary=share_summary,
        story_type='coverage_pressure',
        category='stressed',
        tone='stress',
    )

    preview = build_team_story_preview(team, story=story, board=_board(team))

    assert preview['has_story'] is True
    assert preview['source'] == 'canonical_story'
    assert preview['framing'] == 'tension'
    assert preview['og_title'] == share_title
    assert preview['og_description'] == share_summary
    assert preview['og_title'] != preview['og_description']
    assert preview['og_url'] == 'https://baseballos.vercel.app/team/TOR'
    assert preview['story_type'] == 'coverage_pressure'
    assert preview['category'] == 'stressed'
    assert preview['tone'] == 'stress'
    assert preview['authority']['title'] == 'canonical_story.share_title'
    assert preview['authority']['description'] == 'canonical_story.share_summary'
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

    preview = build_team_story_preview(team, story=story, board=_board(team))

    assert preview['has_story'] is True
    assert preview['framing'] == 'clean'
    assert preview['og_title'] == 'Los Angeles Dodgers bullpen: availability depth'
    assert preview['og_description'] == 'Most of the Dodgers pen is available and rested tonight.'


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

    preview = build_team_story_preview(team, story=story, board=_board(team))

    assert preview['framing'] == 'tension'
    assert preview['tone'] == 'watch'
    assert preview['og_title'] == 'Chicago Cubs bullpen: bridge instability'


def test_title_falls_back_to_headline_when_share_title_missing():
    team = _team(7, 'Fixture Club', 'FIX')
    story = _canonical_story(
        team,
        headline='The Fixture Club lean on a short bridge tonight',
        share_title=None,
        share_summary='Only two trusted arms are available late.',
        tone='stress',
    )

    preview = build_team_story_preview(team, story=story, board=_board(team))

    assert preview['og_title'] == 'The Fixture Club lean on a short bridge tonight'  # headline fallback
    assert preview['og_description'] == 'Only two trusted arms are available late.'  # share_summary


def test_story_without_any_share_copy_raises():
    team = _team(8, 'Empty Club', 'EMP')
    story = _canonical_story(
        team,
        headline=None,
        share_title=None,
        share_summary=None,
    )

    try:
        build_team_story_preview(team, story=story, board=_board(team))
    except ValueError as error:
        assert 'missing a share title' in str(error)
    else:
        raise AssertionError('Expected a story with no share copy to fail.')


def test_no_story_team_uses_neutral_shape_preview_only():
    team = _team(3, 'Quiet Club', 'QUT')
    preview = build_team_story_preview(team, board=_board(team))

    assert preview['has_story'] is False
    assert preview['framing'] == 'neutral'
    assert preview['source'] == 'team_shape'
    assert preview['og_title'] == 'Where the Quiet Club Bullpen Stands Tonight'
    assert preview['og_description'] == (
        'Tonight\'s board: Stable Trust Arm Availability; Healthy Clean Options; '
        'Manageable Trust-Lane Pressure.'
    )
    assert 'story' not in preview['og_title'].lower()
    assert preview['og_title'] != preview['og_description']
    assert preview['og_url'] == 'https://baseballos.vercel.app/team/QUT'


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
                    tone='stress',
                    category='stressed',
                ),
                # A suppressed canonical story is excluded from the index and
                # falls through to the neutral board read.
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
    )
    by_abbr = {preview['team_abbreviation']: preview for preview in previews}

    assert by_abbr['TOR']['has_story'] is True
    assert by_abbr['TOR']['og_title'] == 'Toronto Blue Jays bullpen: coverage pressure'
    assert by_abbr['TOR']['og_description'] == 'Toronto is leaning on a small late-inning group tonight.'
    # No story present in the feed.
    assert by_abbr['LAD']['has_story'] is False
    assert by_abbr['LAD']['source'] == 'team_shape'
    # Suppressed story excluded -> neutral preview.
    assert by_abbr['NYM']['has_story'] is False
    assert by_abbr['NYM']['source'] == 'team_shape'
    # Sorting is alphabetical by abbreviation.
    assert [preview['team_abbreviation'] for preview in previews] == ['LAD', 'NYM', 'TOR']


def test_static_html_contains_canonical_story_og_tags_and_human_redirect():
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
    preview = build_team_story_preview(team, story=story, board=_board(team))

    html = render_team_story_html(preview)

    assert '<meta property="og:title" content="Toronto Blue Jays bullpen: availability depth" />' in html
    assert (
        '<meta property="og:description" content="Most of the Blue Jays pen is available and rested tonight." />'
        in html
    )
    assert '<meta property="og:url" content="https://baseballos.vercel.app/team/TOR" />' in html
    assert '<meta name="twitter:title" content="Toronto Blue Jays bullpen: availability depth" />' in html
    assert 'window.location.replace("/bullpen?view=board&amp;team=TOR&amp;source=share")' not in html
    assert 'window.location.replace("/bullpen?view=board&team=TOR&source=share")' in html
    assert '<div id="root"></div>' not in html


def test_pages_contain_canonical_story_content_not_board_only(tmp_path):
    team = _team(141, 'Toronto Blue Jays', 'TOR')
    story = _canonical_story(
        team,
        headline='The Blue Jays are carrying the late innings on a few arms',
        share_title='Toronto Blue Jays bullpen: coverage pressure',
        share_summary='Toronto is leaning on a small late-inning group tonight.',
        tone='stress',
    )
    previews = build_team_story_previews(
        [team],
        dashboard_payload={'stories': {'items': [story]}},
        boards=[_board(team)],
    )

    write_team_story_pages(previews, tmp_path)
    page = (tmp_path / 'team' / 'TOR' / 'index.html').read_text(encoding='utf-8')

    # Real canonical story copy is present (no longer the neutral board fallback).
    assert 'Toronto Blue Jays bullpen: coverage pressure' in page
    assert 'Toronto is leaning on a small late-inning group tonight.' in page
    assert 'Where the Toronto Blue Jays Bullpen Stands Tonight' not in page


def test_writer_emits_one_static_page_per_team_and_invalid_team_fallback(tmp_path):
    teams = [
        _team(idx, f'Team {idx}', f'T{idx:02d}')
        for idx in range(1, 31)
    ]
    previews = [
        build_team_story_preview(team, board=_board(team))
        for team in teams
    ]

    result = write_team_story_pages(previews, tmp_path)

    assert result['count'] == 30
    for team in teams:
        path = tmp_path / 'team' / team['team_abbreviation'] / 'index.html'
        assert path.exists(), path
        assert '<meta property="og:title"' in path.read_text(encoding='utf-8')

    fallback = Path(result['fallback'])
    assert fallback.exists()
    fallback_html = fallback.read_text(encoding='utf-8')
    assert '<meta property="og:url" content="https://baseballos.vercel.app/team" />' in fallback_html
    assert 'window.location.replace("/")' in fallback_html
