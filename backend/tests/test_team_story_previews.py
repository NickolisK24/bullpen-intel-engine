from pathlib import Path

from services.four_beat_stories import (
    BEAT_SIGNAL,
    LEAD_AVAILABILITY_DEEP,
    LEAD_TRUST_LANE_SHALLOW,
)
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


def _story(
    team=None,
    *,
    signal,
    lead_dimension,
    rule_label='Stress Transfer',
    computed=None,
    lead_fields=None,
):
    team = team or _team()
    return {
        'story_id': f"{team['team_id']}:fixture",
        'rule_key': 'fixture_rule',
        'rule_label': rule_label,
        'team_id': team['team_id'],
        'team_name': team['team_name'],
        'team_abbreviation': team['team_abbreviation'],
        'title': signal,
        'beats': [
            {
                'key': BEAT_SIGNAL,
                'label': 'Signal',
                'text': signal,
            },
            {
                'key': 'mechanism',
                'label': 'Mechanism',
                'text': 'Fixture mechanism text.',
            },
        ],
        'lead_dimension': lead_dimension,
        'lead_fields': lead_fields or {},
        'computed': computed or {},
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


def test_tension_story_uses_signal_as_honest_contrast_preview():
    team = _team()
    signal = 'The Toronto Blue Jays have room tonight, but the clean Trust Arm lane is narrow.'
    story = _story(
        team,
        signal=signal,
        lead_dimension=LEAD_TRUST_LANE_SHALLOW,
        rule_label='Stress Transfer',
        computed={'clean_option_count': 4},
        lead_fields={'clean_trust_count': 1},
    )

    preview = build_team_story_preview(team, story=story, board=_board(team))

    assert preview['framing'] == 'tension'
    assert preview['og_title'] == 'Stress Transfer — Toronto Blue Jays'
    assert preview['og_description'] == signal
    assert preview['og_title'] != preview['og_description']
    assert preview['og_url'] == 'https://baseballos.vercel.app/team/TOR'
    assert preview['rule_label'] == 'Stress Transfer'
    assert preview['authority']['title'] == 'four_beat_story.rule_label'
    assert preview['authority']['description'] == 'four_beat_story.signal'
    assert preview['redirect_path'] == '/bullpen?view=board&team=TOR&source=share'


def test_no_tension_story_stays_clean_and_does_not_manufacture_contrast():
    team = _team(2, 'Los Angeles Dodgers', 'LAD')
    signal = 'The Los Angeles Dodgers have actual room tonight: most of the pen is Available.'
    story = _story(
        team,
        signal=signal,
        lead_dimension=LEAD_AVAILABILITY_DEEP,
        rule_label='Pressure Distribution',
        computed={'clean_option_count': 6},
        lead_fields={'clean_trust_count': 2},
    )

    preview = build_team_story_preview(team, story=story, board=_board(team))

    assert preview['framing'] == 'clean'
    assert ' but ' not in preview['og_title'].lower()
    assert preview['og_title'] == 'Pressure Distribution — Los Angeles Dodgers'
    assert preview['og_description'] == signal
    assert preview['og_title'] != preview['og_description']


def test_no_story_team_uses_neutral_shape_preview_only():
    team = _team(3, 'Quiet Club', 'QUT')
    preview = build_team_story_preview(team, board=_board(team))

    assert preview['has_story'] is False
    assert preview['framing'] == 'neutral'
    assert preview['source'] == 'team_shape'
    assert preview['og_title'] == 'The Quiet Club bullpen tonight - current availability and trust read'
    assert preview['og_description'] == (
        'Current read: Stable Trust Arm Availability; Healthy Clean Options; '
        'Manageable Trust-Lane Pressure.'
    )
    assert 'story' not in preview['og_title'].lower()
    assert preview['og_title'] != preview['og_description']
    assert preview['og_url'] == 'https://baseballos.vercel.app/team/QUT'


def test_build_team_story_previews_consumes_story_and_board_by_team_identity():
    tor = _team(141, 'Toronto Blue Jays', 'TOR')
    lad = _team(119, 'Los Angeles Dodgers', 'LAD')
    signal = 'The Toronto Blue Jays have room tonight, but the clean Trust Arm lane is narrow.'
    payload = {
        'four_beat_stories': {
            'items': [
                _story(
                    tor,
                    signal=signal,
                    lead_dimension=LEAD_TRUST_LANE_SHALLOW,
                    rule_label='Stress Transfer',
                    computed={'clean_option_count': 3},
                    lead_fields={'clean_trust_count': 1},
                )
            ],
        },
    }

    previews = build_team_story_previews(
        [lad, tor],
        dashboard_payload=payload,
        boards=[_board(tor), _board(lad)],
    )
    by_abbr = {preview['team_abbreviation']: preview for preview in previews}

    assert by_abbr['TOR']['og_description'] == signal
    assert by_abbr['TOR']['og_title'] == 'Stress Transfer — Toronto Blue Jays'
    assert by_abbr['TOR']['has_story'] is True
    assert by_abbr['LAD']['has_story'] is False
    assert by_abbr['LAD']['source'] == 'team_shape'


def test_static_html_contains_og_tags_and_human_redirect():
    team = _team()
    signal = 'The Toronto Blue Jays have actual room tonight: most of the pen is Available.'
    preview = build_team_story_preview(
        team,
        story=_story(
            team,
            signal=signal,
            lead_dimension=LEAD_AVAILABILITY_DEEP,
            rule_label='Pressure Distribution',
        ),
        board=_board(team),
    )

    html = render_team_story_html(preview)

    assert '<meta property="og:title" content="Pressure Distribution — Toronto Blue Jays" />' in html
    assert '<meta property="og:description" content="The Toronto Blue Jays have actual room tonight: most of the pen is Available." />' in html
    assert '<meta property="og:url" content="https://baseballos.vercel.app/team/TOR" />' in html
    assert '<meta name="twitter:title" content="Pressure Distribution — Toronto Blue Jays" />' in html
    assert '<meta name="twitter:description" content="The Toronto Blue Jays have actual room tonight: most of the pen is Available." />' in html
    assert 'window.location.replace("/bullpen?view=board&amp;team=TOR&amp;source=share")' not in html
    assert 'window.location.replace("/bullpen?view=board&team=TOR&source=share")' in html
    assert '<div id="root"></div>' not in html


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
