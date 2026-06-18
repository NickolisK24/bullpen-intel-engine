"""Static per-team story previews for shareable bullpen links."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import quote

from services.four_beat_stories import (
    BEAT_SIGNAL,
    LEAD_ERA_ORDINARY,
    LEAD_PARTICIPATION_NARROW,
    LEAD_TRUST_LANE_ABSENCE,
    LEAD_TRUST_LANE_SHALLOW,
    LEAD_WORKLOAD_HIGH,
    RULE_HIDDEN_CAPACITY_LOSS,
    RULE_PRESSURE_DISTRIBUTION,
    RULE_STRESS_TRANSFER,
    RULE_SUSTAINABILITY_QUESTION,
    RULES,
)


DEFAULT_SITE_URL = 'https://baseballos.vercel.app'
DEFAULT_OG_IMAGE_PATH = '/og/baseballos-card.svg'
TEAM_PAGE_ROOT = '/team'
TEAM_SHARE_SOURCE = 'share'
TWITTER_CARD = 'summary'

PLAIN_SHARE_TITLE_LABELS = {
    RULE_SUSTAINABILITY_QUESTION: 'Riding the Bullpen Hard',
    RULE_PRESSURE_DISTRIBUTION: 'Room to Maneuver',
    RULE_STRESS_TRANSFER: 'Short on Fresh Arms',
    RULE_HIDDEN_CAPACITY_LOSS: 'Not as Deep as It Looks',
    'thinning_trust_lane': 'Thin Where It Counts Late',
}

TENSION_LEAD_DIMENSIONS = {
    LEAD_TRUST_LANE_ABSENCE,
    LEAD_TRUST_LANE_SHALLOW,
    LEAD_WORKLOAD_HIGH,
    LEAD_PARTICIPATION_NARROW,
    LEAD_ERA_ORDINARY,
}


def _clean_text(value):
    return value.strip() if isinstance(value, str) else ''


def _strip_trailing_slash(value):
    return str(value or '').rstrip('/')


def _absolute_url(path, site_url=DEFAULT_SITE_URL):
    if not path:
        return ''
    if str(path).startswith(('http://', 'https://')):
        return str(path)
    return f'{_strip_trailing_slash(site_url)}{path if str(path).startswith("/") else f"/{path}"}'


def _team_abbreviation(team=None, story=None, board=None):
    candidates = [
        (team or {}).get('team_abbreviation'),
        (story or {}).get('team_abbreviation'),
        ((board or {}).get('team') or {}).get('team_abbreviation'),
    ]
    for candidate in candidates:
        text = _clean_text(candidate).upper()
        if text:
            return re.sub(r'[^A-Z0-9-]', '', text)
    return None


def _team_name(team=None, story=None, board=None):
    candidates = [
        (team or {}).get('team_name'),
        (story or {}).get('team_name'),
        ((board or {}).get('team') or {}).get('team_name'),
        _team_abbreviation(team=team, story=story, board=board),
    ]
    for candidate in candidates:
        text = _clean_text(candidate)
        if text:
            return text
    return 'This team'


def _story_key(story):
    if not isinstance(story, dict):
        return None
    if story.get('team_id') is not None:
        return str(story.get('team_id'))
    abbr = _clean_text(story.get('team_abbreviation')).upper()
    return abbr or None


def _board_key(board):
    team = (board or {}).get('team') or {}
    if team.get('team_id') is not None:
        return str(team.get('team_id'))
    abbr = _clean_text(team.get('team_abbreviation')).upper()
    return abbr or None


def _team_key(team):
    if not isinstance(team, dict):
        return None
    if team.get('team_id') is not None:
        return str(team.get('team_id'))
    abbr = _clean_text(team.get('team_abbreviation')).upper()
    return abbr or None


def _shape_reads(board):
    shape = (board or {}).get('team_shape') or {}
    reads = shape.get('reads')
    if isinstance(reads, list):
        return [read for read in reads if isinstance(read, dict)]
    return []


def _read_by_key(board):
    return {
        read.get('key'): read
        for read in _shape_reads(board)
        if read.get('key')
    }


def _neutral_shape_description(board):
    reads = _read_by_key(board)
    labels = [
        _clean_text((reads.get(key) or {}).get('label'))
        for key in ('trustAvailability', 'cleanOptions', 'bullpenPressure')
    ]
    labels = [label for label in labels if label and label != 'Limited Read']
    if labels:
        return f"Tonight's board: {'; '.join(labels)}."
    return 'Availability and trust details come from the team board.'


def _live_story_rule_keys():
    return {
        key
        for key, rule in RULES.items()
        if (rule or {}).get('status') == 'live'
    }


def unmapped_live_story_rule_keys():
    return sorted(_live_story_rule_keys() - set(PLAIN_SHARE_TITLE_LABELS))


def _plain_share_title_label(story, abbr):
    rule_key = _clean_text((story or {}).get('rule_key'))
    if not rule_key:
        raise ValueError(f'Team story for {abbr} is missing a rule key.')
    label = PLAIN_SHARE_TITLE_LABELS.get(rule_key)
    if not label:
        raise ValueError(f'Team story rule {rule_key} is missing a plain share title label.')
    return label


def _signal_beat(story):
    beats = story.get('beats') if isinstance(story, dict) else None
    if isinstance(beats, list):
        for beat in beats:
            if isinstance(beat, dict) and beat.get('key') == BEAT_SIGNAL:
                text = _clean_text(beat.get('text'))
                if text:
                    return text
    return _clean_text((story or {}).get('title'))


def _story_label(story):
    for key in ('rule_label', 'kicker'):
        text = _clean_text((story or {}).get(key))
        if text:
            return text
    return ''


def _story_supports_tension(story):
    signal = _signal_beat(story)
    if ' but ' not in signal.lower():
        return False
    dimension = (story or {}).get('lead_dimension')
    if dimension not in TENSION_LEAD_DIMENSIONS:
        return False

    lead_fields = (story or {}).get('lead_fields') or {}
    computed = (story or {}).get('computed') or {}
    clean_trust_count = lead_fields.get('clean_trust_count')
    if clean_trust_count is None:
        clean_trust_count = computed.get('clean_trust_count')
    clean_option_count = computed.get('clean_option_count')

    if dimension == LEAD_TRUST_LANE_ABSENCE:
        return (clean_option_count or 0) > 0 and int(clean_trust_count or 0) == 0
    if dimension == LEAD_TRUST_LANE_SHALLOW:
        return int(clean_trust_count or 0) == 1 and (clean_option_count or 0) > 1
    return True


def build_story_index(dashboard_payload):
    stories = (((dashboard_payload or {}).get('four_beat_stories') or {}).get('items') or [])
    return {
        _story_key(story): story
        for story in stories
        if _story_key(story)
    }


def build_board_index(boards):
    return {
        _board_key(board): board
        for board in boards or []
        if _board_key(board)
    }


def build_team_story_preview(
    team,
    *,
    story=None,
    board=None,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    abbr = _team_abbreviation(team=team, story=story, board=board)
    if not abbr:
        raise ValueError('Team preview requires a team abbreviation.')

    team_name = _team_name(team=team, story=story, board=board)
    team_page_path = f'{TEAM_PAGE_ROOT}/{quote(abbr)}'
    team_page_url = _absolute_url(team_page_path, site_url=site_url)
    redirect_path = f'/bullpen?view=board&team={quote(abbr)}&source={TEAM_SHARE_SOURCE}'
    og_image = _absolute_url(og_image_path, site_url=site_url)

    if story:
        signal = _signal_beat(story)
        if not signal:
            raise ValueError(f'Team story for {abbr} is missing a Signal beat.')
        internal_label = _story_label(story)
        if not internal_label:
            raise ValueError(f'Team story for {abbr} is missing a rule label.')
        share_label = _plain_share_title_label(story, abbr)
        framing = 'tension' if _story_supports_tension(story) else 'clean'
        return {
            'team_id': (team or {}).get('team_id') or story.get('team_id'),
            'team_abbreviation': abbr,
            'team_name': team_name,
            'has_story': True,
            'framing': framing,
            'source': 'four_beat_story',
            'story_id': story.get('story_id'),
            'rule_key': story.get('rule_key'),
            'rule_label': internal_label,
            'share_title_label': share_label,
            'lead_dimension': story.get('lead_dimension'),
            'og_title': f'{share_label} — {team_name}',
            'og_description': signal,
            'og_url': team_page_url,
            'canonical_url': team_page_url,
            'og_image': og_image,
            'twitter_card': TWITTER_CARD,
            'redirect_path': redirect_path,
            'authority': {
                'title': 'four_beat_story.rule_key.plain_share_title_label',
                'description': 'four_beat_story.signal',
                'redirect': 'tonights_bullpen_board.deep_link',
            },
        }

    return {
        'team_id': (team or {}).get('team_id') or ((board or {}).get('team') or {}).get('team_id'),
        'team_abbreviation': abbr,
        'team_name': team_name,
        'has_story': False,
        'framing': 'neutral',
        'source': 'team_shape',
        'story_id': None,
        'rule_key': None,
        'rule_label': None,
        'share_title_label': None,
        'lead_dimension': None,
        'og_title': f'Where the {team_name} Bullpen Stands Tonight',
        'og_description': _neutral_shape_description(board),
        'og_url': team_page_url,
        'canonical_url': team_page_url,
        'og_image': og_image,
        'twitter_card': TWITTER_CARD,
        'redirect_path': redirect_path,
        'authority': {
            'title': 'team_shape.neutral',
            'description': 'team_shape.reads',
            'redirect': 'tonights_bullpen_board.deep_link',
        },
    }


def build_team_story_previews(
    teams,
    *,
    dashboard_payload,
    boards,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    story_index = build_story_index(dashboard_payload)
    board_index = build_board_index(boards)
    previews = []
    for team in sorted(
        (teams or []),
        key=lambda item: (_clean_text(item.get('team_abbreviation')).upper(), item.get('team_id') or 0),
    ):
        key = _team_key(team)
        story = story_index.get(key)
        board = board_index.get(key)
        previews.append(
            build_team_story_preview(
                team,
                story=story,
                board=board,
                site_url=site_url,
                og_image_path=og_image_path,
            )
        )
    return previews


def _meta_property(name, content):
    return f'    <meta property="{html.escape(name)}" content="{html.escape(str(content), quote=True)}" />'


def _meta_name(name, content):
    return f'    <meta name="{html.escape(name)}" content="{html.escape(str(content), quote=True)}" />'


def render_team_story_html(preview):
    title = html.escape(preview['og_title'])
    redirect = preview['redirect_path']
    redirect_json = json.dumps(redirect)
    redirect_attr = html.escape(redirect, quote=True)
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '  <head>',
        '    <meta charset="UTF-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f'    <title>{title}</title>',
        _meta_name('description', preview['og_description']),
        _meta_property('og:type', 'website'),
        _meta_property('og:site_name', 'BaseballOS'),
        _meta_property('og:title', preview['og_title']),
        _meta_property('og:description', preview['og_description']),
        _meta_property('og:url', preview['og_url']),
        _meta_property('og:image', preview['og_image']),
        _meta_name('twitter:card', preview['twitter_card']),
        _meta_name('twitter:title', preview['og_title']),
        _meta_name('twitter:description', preview['og_description']),
        _meta_name('twitter:image', preview['og_image']),
        f'    <link rel="canonical" href="{html.escape(preview["canonical_url"], quote=True)}" />',
        '  </head>',
        '  <body>',
        f'    <script>window.location.replace({redirect_json});</script>',
        f'    <noscript><a href="{redirect_attr}">Open this team board</a></noscript>',
        '  </body>',
        '</html>',
        '',
    ]
    return '\n'.join(lines)


def render_invalid_team_html(site_url=DEFAULT_SITE_URL, og_image_path=DEFAULT_OG_IMAGE_PATH):
    preview = {
        'og_title': 'BaseballOS | Team Story Preview',
        'og_description': 'Open BaseballOS for current bullpen availability and trust reads.',
        'og_url': _absolute_url(TEAM_PAGE_ROOT, site_url=site_url),
        'canonical_url': _absolute_url('/', site_url=site_url),
        'og_image': _absolute_url(og_image_path, site_url=site_url),
        'twitter_card': TWITTER_CARD,
        'redirect_path': '/',
    }
    return render_team_story_html(preview)


def write_team_story_pages(
    previews,
    output_root,
    *,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    root = Path(output_root)
    team_root = root / 'team'
    team_root.mkdir(parents=True, exist_ok=True)
    written = []
    for preview in previews:
        abbr = preview['team_abbreviation']
        target_dir = team_root / abbr
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / 'index.html'
        target.write_text(render_team_story_html(preview), encoding='utf-8')
        written.append(target)

    fallback = team_root / 'index.html'
    fallback.write_text(
        render_invalid_team_html(site_url=site_url, og_image_path=og_image_path),
        encoding='utf-8',
    )
    return {
        'count': len(written),
        'team_page_root': str(team_root),
        'files': [str(path) for path in written],
        'fallback': str(fallback),
    }
