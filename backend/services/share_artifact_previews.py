"""Crawler-visible metadata pages for immutable public Share Artifacts.

This module is a distribution projection only.  It consumes the same
integrity-verified public view used by ``/share/{public_id}`` and never consults
current Team Board, roster, workload, or Team State builders.  A generated page
therefore remains a projection of the frozen artifact for its entire lifetime.
"""

from __future__ import annotations

import html
import shutil
from datetime import date
from pathlib import Path
from typing import Mapping

from services.share_artifact_public import (
    RESULT_OK,
    RESULT_SUPERSEDED,
    is_valid_public_id,
    project_public_share_artifact,
)


DEFAULT_SITE_URL = 'https://baseballos.app'
DEFAULT_OG_IMAGE_PATH = '/og/baseballos-card.png'
OG_IMAGE_WIDTH = 1200
OG_IMAGE_HEIGHT = 630
OG_IMAGE_TYPE = 'image/png'
TWITTER_CARD = 'summary_large_image'
REPRESENTATION = 'immutable_share_artifact'
INVALID_REPRESENTATION = 'invalid_share_artifact'
SHARE_STYLESHEET_PATH = '/share-preview.css'


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _clean_text(value):
    return str(value).strip() if value not in (None, '') else None


def _site_url(value):
    return (_clean_text(value) or DEFAULT_SITE_URL).rstrip('/')


def _absolute_url(path, *, site_url=DEFAULT_SITE_URL):
    value = _clean_text(path) or DEFAULT_OG_IMAGE_PATH
    if value.startswith(('https://', 'http://')):
        return value
    return f'{_site_url(site_url)}/{value.lstrip("/")}'


def _data_through(view):
    freshness = _mapping(view.get('freshness'))
    authority = _mapping(view.get('authority'))
    return _clean_text(
        freshness.get('data_through')
        or freshness.get('current_data_through')
        or authority.get('data_through')
        or authority.get('current_data_through')
        or view.get('product_date')
    )


def _description(view, title, data_through):
    copy = _mapping(view.get('copy'))
    value = _clean_text(
        copy.get('description')
        or copy.get('summary')
        or copy.get('why')
        or title
    )
    if not value:
        raise ValueError('Published share artifact has no frozen public description.')
    if data_through and 'data through' not in value.casefold():
        value = f'{value.rstrip()} Data through {data_through}.'
    return value


def _live_destination(view, share_route):
    """Return the backend-owned live product route, never the citation itself."""
    routes = _mapping(view.get('routes'))
    for key in ('team_url', 'matchup_url', 'history_url'):
        value = _clean_text(routes.get(key))
        if (
            value
            and value.startswith('/')
            and not value.startswith('//')
            and not value.startswith('/share/')
            and value.rstrip('/') != share_route
        ):
            return value
    raise ValueError('Published share artifact has no distinct live destination.')


def _evidence_rows(view):
    rows = view.get('evidence')
    if not isinstance(rows, (list, tuple)):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _unique_texts(*values):
    unique = []
    seen = set()
    for value in values:
        clean = _clean_text(value)
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        unique.append(clean)
    return unique


def _presentation_copy(view, artifact_type, title):
    """Select frozen copy for layout without composing new baseball meaning."""
    copy = _mapping(view.get('copy'))
    if artifact_type == 'since_yesterday_change':
        primary = title
        supporting = _unique_texts(
            copy.get('summary'), copy.get('why'), copy.get('description'),
        )
    else:
        primary = _clean_text(
            copy.get('why')
            or copy.get('summary')
            or copy.get('description')
            or title
        )
        supporting = []
    return primary, [value for value in supporting if value != primary]


def _parse_date(value):
    clean = _clean_text(value)
    if not clean:
        return None
    try:
        return date.fromisoformat(clean[:10])
    except ValueError:
        return None


def _month_day(value):
    return value.strftime('%b %d').replace(' 0', ' ')


def _long_date(value):
    return value.strftime('%B %d, %Y').replace(' 0', ' ')


def _date_presentation(current_value, previous_value=None):
    current = _parse_date(current_value)
    previous = _parse_date(previous_value)
    if current and previous:
        if current.year == previous.year:
            return {
                'label': f'{_month_day(previous)} → {_month_day(current)}, {current.year}',
                'current': current.isoformat(),
                'previous': previous.isoformat(),
                'kind': 'comparison',
            }
        return {
            'label': f'{_long_date(previous)} → {_long_date(current)}',
            'current': current.isoformat(),
            'previous': previous.isoformat(),
            'kind': 'comparison',
        }
    if current:
        return {
            'label': _long_date(current),
            'current': current.isoformat(),
            'previous': None,
            'kind': 'data_through',
        }
    return None


def _copy_contains_date(copy_rows, date_presentation):
    if not date_presentation:
        return False
    haystack = ' '.join(_clean_text(value) or '' for value in copy_rows).casefold()
    current = _clean_text(date_presentation.get('current'))
    previous = _clean_text(date_presentation.get('previous'))
    label = _clean_text(date_presentation.get('label'))
    if date_presentation.get('kind') == 'comparison':
        return bool(
            (label and label.casefold() in haystack)
            or (
                current and previous
                and current.casefold() in haystack
                and previous.casefold() in haystack
            )
        )
    return any(value and value.casefold() in haystack for value in (current, label))


def _destination_label(path, team_name):
    if path.startswith('/bullpen') and team_name:
        return f'Open current {team_name} bullpen'
    if path.startswith('/matchup'):
        return 'Open matchup in BaseballOS'
    if path.startswith('/history'):
        return 'View team history in BaseballOS'
    return 'Open BaseballOS'


def build_share_artifact_preview(
    artifact,
    *,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    """Build one preview exclusively from an immutable public artifact view."""
    result = project_public_share_artifact(artifact)
    if result.status not in (RESULT_OK, RESULT_SUPERSEDED) or not result.view:
        raise ValueError(
            f'Share artifact is not safely previewable (status={result.status!r}).'
        )

    return build_share_artifact_preview_from_public_view(
        result.view,
        source_snapshot_id=getattr(artifact, 'source_snapshot_id', None),
        source_sync_run_id=getattr(artifact, 'source_sync_run_id', None),
        site_url=site_url,
        og_image_path=og_image_path,
    )


def build_share_artifact_preview_from_public_view(
    view,
    *,
    source_snapshot_id=None,
    source_sync_run_id=None,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    """Build from the canonical public projection without reinterpreting it."""
    if not isinstance(view, Mapping):
        raise ValueError('Share artifact public view is unavailable.')

    public_id = _clean_text(view.get('public_id'))
    if not is_valid_public_id(public_id) or public_id in {'.', '..'}:
        raise ValueError('Share artifact has an unsafe public_id for static output.')

    route = f'/share/{public_id}'
    routes = _mapping(view.get('routes'))
    if routes.get('share_url') != route:
        raise ValueError('Share artifact public route does not match its frozen public_id.')

    copy = _mapping(view.get('copy'))
    title = _clean_text(copy.get('headline'))
    if not title:
        raise ValueError('Published share artifact has no frozen public headline.')

    artifact_type = _clean_text(view.get('artifact_type'))
    data_through = _data_through(view)
    team = _mapping(view.get('team'))
    team_state = _mapping(view.get('team_state'))
    publication_scope = _mapping(view.get('publication_scope'))
    freshness = _mapping(view.get('freshness'))
    primary_claim, supporting_copy = _presentation_copy(view, artifact_type, title)
    previous_data_through = _clean_text(freshness.get('previous_data_through'))
    date_presentation = _date_presentation(data_through, previous_data_through)
    live_destination_path = _live_destination(view, route)
    team_name = _clean_text(team.get('team_name'))
    canonical_url = f'{_site_url(site_url)}{route}'
    return {
        'public_id': public_id,
        'artifact_type': artifact_type,
        'schema_version': _clean_text(view.get('schema_version')),
        'render_version': _clean_text(view.get('render_version')),
        'payload_version': _clean_text(view.get('payload_version')),
        'lifecycle_state': _clean_text(view.get('lifecycle_state')),
        'representation': REPRESENTATION,
        'title': title,
        'description': _description(view, title, data_through),
        'canonical_url': canonical_url,
        'og_image': _absolute_url(og_image_path, site_url=site_url),
        'twitter_card': TWITTER_CARD,
        'team_abbreviation': _clean_text(team.get('team_abbreviation')),
        'team_name': team_name,
        'team_state_label': _clean_text(team_state.get('public_label')),
        'evidence': _evidence_rows(view),
        'historical_context': _clean_text(publication_scope.get('historical_note')),
        'data_through': data_through,
        'previous_data_through': previous_data_through,
        'date_presentation': date_presentation,
        'date_embedded_in_copy': _copy_contains_date(
            [primary_claim, *supporting_copy], date_presentation,
        ),
        'primary_claim': primary_claim,
        'supporting_copy': supporting_copy,
        'generated_at': _clean_text(view.get('generated_at')),
        'published_at': _clean_text(view.get('published_at')),
        'snapshot_id': source_snapshot_id or authority_snapshot_id(view),
        'sync_run_id': source_sync_run_id or authority_sync_run_id(view),
        'live_destination_path': live_destination_path,
        'live_destination_label': _destination_label(live_destination_path, team_name),
    }


def authority_snapshot_id(view):
    return _mapping(view.get('authority')).get('source_snapshot_id')


def authority_sync_run_id(view):
    return _mapping(view.get('authority')).get('source_sync_run_id')


def _meta_property(name, content):
    return (
        f'    <meta property="{html.escape(name)}" '
        f'content="{html.escape(str(content), quote=True)}" />'
    )


def _meta_name(name, content):
    return (
        f'    <meta name="{html.escape(name)}" '
        f'content="{html.escape(str(content), quote=True)}" />'
    )


def _authority_meta(preview):
    fields = (
        ('representation', preview.get('representation')),
        ('public-id', preview.get('public_id')),
        ('artifact-type', preview.get('artifact_type')),
        ('team', preview.get('team_abbreviation')),
        ('team-state', preview.get('team_state_label')),
        ('evidence-count', len(preview.get('evidence') or [])),
        ('live-destination', preview.get('live_destination_path')),
        ('data-through', preview.get('data_through')),
        ('generated-at', preview.get('generated_at')),
        ('published-at', preview.get('published_at')),
        ('snapshot-id', preview.get('snapshot_id')),
        ('sync-run-id', preview.get('sync_run_id')),
        ('schema-version', preview.get('schema_version')),
        ('render-version', preview.get('render_version')),
        ('payload-version', preview.get('payload_version')),
    )
    return [
        _meta_name(f'baseballos:{name}', value)
        for name, value in fields
        if value not in (None, '')
    ]


def render_share_artifact_html(preview):
    title = preview['title']
    description = preview['description']
    browser_title = title if 'baseballos' in title.casefold() else f'{title} | BaseballOS'
    team_name = preview.get('team_name') or 'MLB bullpen observation'
    team_abbreviation = preview.get('team_abbreviation')
    state = preview.get('team_state_label')
    state_class = (state or 'limited-read').casefold().replace(' ', '-')
    primary_claim = preview.get('primary_claim') or title
    supporting_copy = preview.get('supporting_copy') or []
    artifact_type = preview.get('artifact_type')
    evidence_title = (
        'What changed' if artifact_type == 'since_yesterday_change'
        else 'Evidence behind the read'
    )
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '  <head>',
        '    <meta charset="UTF-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f'    <title>{html.escape(browser_title)}</title>',
        _meta_name('description', description),
        _meta_property('og:type', 'article'),
        _meta_property('og:site_name', 'BaseballOS'),
        _meta_property('og:title', title),
        _meta_property('og:description', description),
        _meta_property('og:url', preview['canonical_url']),
        _meta_property('og:image', preview['og_image']),
        _meta_property('og:image:width', OG_IMAGE_WIDTH),
        _meta_property('og:image:height', OG_IMAGE_HEIGHT),
        _meta_property('og:image:type', OG_IMAGE_TYPE),
        _meta_name('twitter:card', preview['twitter_card']),
        _meta_name('twitter:title', title),
        _meta_name('twitter:description', description),
        _meta_name('twitter:image', preview['og_image']),
        *_authority_meta(preview),
        f'    <link rel="canonical" href="{html.escape(preview["canonical_url"], quote=True)}" />',
        f'    <link rel="stylesheet" href="{SHARE_STYLESHEET_PATH}" />',
        '  </head>',
        '  <body class="share-artifact-page">',
        '    <main class="share-artifact-shell">',
        '      <header class="share-artifact-header">',
        '        <a class="share-brand" href="/" aria-label="BaseballOS home">',
        '          <span class="share-brand-mark" aria-hidden="true">B</span>',
        '          <span><strong>BaseballOS</strong><small>MLB bullpen intelligence</small></span>',
        '        </a>',
        '        <p class="share-kicker">Published BaseballOS observation</p>',
        '        <div class="share-team-identity">',
    ]
    if team_abbreviation:
        lines.append(f'          <p class="share-team-abbreviation">{html.escape(team_abbreviation)}</p>')
    lines.append(f'          <h1>{html.escape(team_name)}</h1>')
    if state:
        lines.append(
            f'          <p class="share-state share-state--{html.escape(state_class)}">'
            '<span class="share-state-dot" aria-hidden="true"></span>'
            f'<span>Team State: <strong>{html.escape(state)}</strong></span></p>'
        )
    lines.extend([
        '        </div>',
        '      </header>',
        '      <article class="share-artifact-card">',
        '        <section class="share-claim" aria-labelledby="share-claim-title">',
        '          <p class="share-section-label">Historical snapshot</p>',
        f'          <h2 id="share-claim-title">{html.escape(primary_claim)}</h2>',
    ])
    for paragraph in supporting_copy:
        lines.append(f'          <p>{html.escape(paragraph)}</p>')
    lines.extend(['        </section>'])
    evidence = preview.get('evidence') or []
    if evidence:
        lines.extend([
            '        <section class="share-evidence" aria-labelledby="share-evidence-title">',
            f'          <h2 id="share-evidence-title">{evidence_title}</h2>',
            '          <dl>',
        ])
        for row in evidence:
            label = _clean_text(row.get('label')) or 'Bullpen evidence'
            detail = _clean_text(row.get('detail'))
            if detail:
                value = detail
            elif row.get('yesterday') is not None and row.get('today') is not None:
                value = f'{row["yesterday"]} → {row["today"]}'
            elif row.get('count') is not None:
                value = str(row['count'])
            else:
                value = None
            lines.append('            <div class="share-evidence-row">')
            lines.append(f'              <dt>{html.escape(label)}</dt>')
            if value is not None:
                lines.append(f'              <dd>{html.escape(value)}</dd>')
            lines.append('            </div>')
        lines.extend(['          </dl>', '        </section>'])
    lines.extend([
        '        <footer class="share-artifact-context">',
    ])
    date_presentation = preview.get('date_presentation')
    if date_presentation and not preview.get('date_embedded_in_copy'):
        label = date_presentation['label']
        current = date_presentation['current']
        if date_presentation.get('kind') == 'comparison':
            lines.append(
                '          <p><span>Comparison</span>'
                f'<strong>{html.escape(label)}</strong></p>'
            )
        else:
            lines.append(
                '          <p><span>Data through</span>'
                f'<strong><time datetime="{html.escape(current, quote=True)}">'
                f'{html.escape(label)}</time></strong></p>'
            )
    lines.append(
        '          <p><span>Artifact</span><strong>Frozen historical observation</strong></p>'
    )
    if preview.get('historical_context'):
        lines.append(
            f'          <p class="share-historical-note">{html.escape(preview["historical_context"])}</p>'
        )
    lines.extend([
        '        </footer>',
        f'        <a class="share-live-cta" href="{html.escape(preview["live_destination_path"], quote=True)}">'
        f'{html.escape(preview.get("live_destination_label") or "Open BaseballOS")}<span aria-hidden="true">→</span></a>',
        '      </article>',
        '      <p class="share-live-note">The observation above is frozen. The destination opens the current BaseballOS view.</p>',
        '    </main>',
        '  </body>',
        '</html>',
        '',
    ])
    return '\n'.join(lines)


def render_invalid_share_html():
    title = 'Shared artifact not found · BaseballOS'
    description = 'No published BaseballOS artifact exists for this link.'
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '  <head>',
        '    <meta charset="UTF-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f'    <title>{title}</title>',
        _meta_name('description', description),
        _meta_name('robots', 'noindex,nofollow'),
        _meta_name('baseballos:representation', INVALID_REPRESENTATION),
        f'    <link rel="stylesheet" href="{SHARE_STYLESHEET_PATH}" />',
        '  </head>',
        '  <body class="share-artifact-page">',
        '    <main class="share-artifact-shell share-not-found">',
        '      <p class="share-kicker">BaseballOS</p>',
        f'      <h1>{title}</h1><p>{description}</p>',
        '      <a class="share-live-cta" href="/">Return to BaseballOS <span aria-hidden="true">→</span></a>',
        '    </main>',
        '  </body>',
        '</html>',
        '',
    ]
    return '\n'.join(lines)


def _safe_artifact_directory(share_root: Path, public_id: str) -> Path:
    if not is_valid_public_id(public_id) or public_id in {'.', '..'}:
        raise ValueError('Unsafe public_id for generated share preview path.')
    target = share_root / public_id
    root_resolved = share_root.resolve()
    target_resolved = target.resolve()
    if target_resolved.parent != root_resolved:
        raise ValueError('Generated share preview path escaped its output root.')
    return target


def _write_if_changed(path: Path, content: str) -> bool:
    if path.is_file() and path.read_text(encoding='utf-8') == content:
        return False
    path.write_text(content, encoding='utf-8')
    return True


def write_share_artifact_pages(
    previews,
    output_root,
    *,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    """Write the exact public/superseded artifact set under ``share/**`` only."""
    root = Path(output_root)
    share_root = root / 'share'
    share_root.mkdir(parents=True, exist_ok=True)

    ordered = sorted(previews, key=lambda row: row['public_id'])
    ids = [row['public_id'] for row in ordered]
    if len(ids) != len(set(ids)) or len(ids) != len({value.casefold() for value in ids}):
        raise ValueError('Duplicate generated share public_id.')

    expected_dirs = set()
    files = []
    changed = []
    for preview in ordered:
        target_dir = _safe_artifact_directory(share_root, preview['public_id'])
        expected_dirs.add(target_dir.resolve())
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / 'index.html'
        if _write_if_changed(target, render_share_artifact_html(preview)):
            changed.append(target)
        files.append(target)

    removed = []
    for child in share_root.iterdir():
        if not child.is_dir() or child.resolve() in expected_dirs:
            continue
        # Only generator-shaped directories are removable.  A foreign path in
        # the governed output root is a hard refusal, never collateral cleanup.
        if not is_valid_public_id(child.name) or child.name in {'.', '..'}:
            raise ValueError(f'Unexpected path in generated share root: {child.name!r}.')
        entries = list(child.iterdir())
        if len(entries) != 1 or entries[0].name != 'index.html' or not entries[0].is_file():
            raise ValueError(f'Refusing to remove non-generator directory: {child}.')
        removed.append(entries[0])
        shutil.rmtree(child)

    legacy_fallback = share_root / 'index.html'
    if legacy_fallback.is_file():
        legacy_fallback.unlink()
        removed.append(legacy_fallback)

    # F-016 owns the site-wide ``404.html`` contract. Share generation may only
    # refresh the scoped invalid-artifact document selected by Vercel.
    fallback = root / 'share-404.html'
    if _write_if_changed(
        fallback,
        render_invalid_share_html(),
    ):
        changed.append(fallback)

    return {
        'count': len(files),
        'share_page_root': str(share_root),
        'files': [str(path) for path in files],
        'fallback': str(fallback),
        'changed': [str(path) for path in changed],
        'removed': [str(path) for path in removed],
    }
