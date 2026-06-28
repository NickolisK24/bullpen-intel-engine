"""Static per-team story previews for shareable bullpen links."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import quote


DEFAULT_SITE_URL = 'https://baseballos.app'
DEFAULT_OG_IMAGE_PATH = '/og/baseballos-card.svg'
TEAM_PAGE_ROOT = '/team'
TEAM_SHARE_SOURCE = 'share'
TWITTER_CARD = 'summary'

# Canonical story tones that warrant a tension framing on the share card.
TENSION_TONES = {'stress', 'watch'}


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


def _story_title(story):
    """Share-card title: the canonical share title, falling back to the headline."""
    for key in ('share_title', 'headline'):
        text = _clean_text((story or {}).get(key))
        if text:
            return text
    return ''


def _story_description(story):
    """Share-card description: the canonical share summary, falling back to the headline."""
    for key in ('share_summary', 'headline'):
        text = _clean_text((story or {}).get(key))
        if text:
            return text
    return ''


def _story_framing(story):
    return 'tension' if (story or {}).get('tone') in TENSION_TONES else 'clean'


def build_story_index(dashboard_payload):
    # Canonical story feed (dashboard.stories). Only publishable stories carry
    # share-ready copy; suppressed entries fall through to the neutral board read.
    feed = (dashboard_payload or {}).get('stories') or {}
    stories = feed.get('items') or []
    return {
        _story_key(story): story
        for story in stories
        if isinstance(story, dict) and story.get('story_available') is True and _story_key(story)
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
        title = _story_title(story)
        if not title:
            raise ValueError(f'Canonical story for {abbr} is missing a share title.')
        description = _story_description(story)
        if not description:
            raise ValueError(f'Canonical story for {abbr} is missing a share summary.')
        return {
            'team_id': (team or {}).get('team_id') or story.get('team_id'),
            'team_abbreviation': abbr,
            'team_name': team_name,
            'has_story': True,
            'framing': _story_framing(story),
            'source': 'canonical_story',
            'story_id': story.get('story_id'),
            'story_type': story.get('story_type'),
            'category': story.get('category'),
            'tone': story.get('tone'),
            'og_title': title,
            'og_description': description,
            'og_url': team_page_url,
            'canonical_url': team_page_url,
            'og_image': og_image,
            'twitter_card': TWITTER_CARD,
            'redirect_path': redirect_path,
            'authority': {
                'title': 'canonical_story.share_title',
                'description': 'canonical_story.share_summary',
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
        'story_type': None,
        'category': None,
        'tone': None,
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
