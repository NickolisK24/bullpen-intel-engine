"""Crawler-visible metadata pages for immutable public Share Artifacts.

This module is a distribution projection only.  It consumes the same
integrity-verified public view used by ``/share/{public_id}`` and never consults
current Team Board, roster, workload, or Team State builders.  A generated page
therefore remains a projection of the frozen artifact for its entire lifetime.
"""

from __future__ import annotations

import html
import json
import shutil
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

    data_through = _data_through(view)
    team = _mapping(view.get('team'))
    team_state = _mapping(view.get('team_state'))
    canonical_url = f'{_site_url(site_url)}{route}'
    return {
        'public_id': public_id,
        'artifact_type': _clean_text(view.get('artifact_type')),
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
        'team_name': _clean_text(team.get('team_name')),
        'team_state_label': _clean_text(team_state.get('public_label')),
        'data_through': data_through,
        'generated_at': _clean_text(view.get('generated_at')),
        'published_at': _clean_text(view.get('published_at')),
        'snapshot_id': source_snapshot_id or authority_snapshot_id(view),
        'sync_run_id': source_sync_run_id or authority_sync_run_id(view),
        # The no-slash form serves this static document.  The trailing-slash
        # form misses the route-specific rewrite and hands the human reader to
        # the existing SPA route; the page then restores the canonical URL.
        'handoff_path': f'{route}/',
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
    handoff_json = json.dumps(preview['handoff_path'])
    title = preview['title']
    description = preview['description']
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '  <head>',
        '    <meta charset="UTF-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f'    <title>{html.escape(title)}</title>',
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
        '  </head>',
        '  <body>',
        '    <main>',
        f'      <h1>{html.escape(title)}</h1>',
        f'      <p>{html.escape(description)}</p>',
    ]
    if preview.get('data_through'):
        date_value = html.escape(preview['data_through'], quote=True)
        lines.append(
            f'      <p>Baseball data through <time datetime="{date_value}">'
            f'{html.escape(preview["data_through"])}</time>.</p>'
        )
    lines.extend([
        f'      <p><a href="{html.escape(preview["handoff_path"], quote=True)}">Open this published BaseballOS artifact</a></p>',
        '    </main>',
        f'    <script>window.location.replace({handoff_json});</script>',
        '  </body>',
        '</html>',
        '',
    ])
    return '\n'.join(lines)


def render_invalid_share_html(
    *, site_url=DEFAULT_SITE_URL, og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    title = 'Shared BaseballOS artifact'
    description = 'Open BaseballOS for published bullpen intelligence.'
    canonical_url = f'{_site_url(site_url)}/share/'
    image_url = _absolute_url(og_image_path, site_url=site_url)
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '  <head>',
        '    <meta charset="UTF-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f'    <title>{title}</title>',
        _meta_name('description', description),
        _meta_name('robots', 'noindex,nofollow'),
        _meta_property('og:type', 'website'),
        _meta_property('og:site_name', 'BaseballOS'),
        _meta_property('og:title', title),
        _meta_property('og:description', description),
        _meta_property('og:url', canonical_url),
        _meta_property('og:image', image_url),
        _meta_property('og:image:width', OG_IMAGE_WIDTH),
        _meta_property('og:image:height', OG_IMAGE_HEIGHT),
        _meta_property('og:image:type', OG_IMAGE_TYPE),
        _meta_name('twitter:card', TWITTER_CARD),
        _meta_name('twitter:title', title),
        _meta_name('twitter:description', description),
        _meta_name('twitter:image', image_url),
        _meta_name('baseballos:representation', INVALID_REPRESENTATION),
        f'    <link rel="canonical" href="{canonical_url}" />',
        '  </head>',
        '  <body>',
        '    <main><p>No published BaseballOS artifact exists for this link.</p></main>',
        '    <script>window.location.replace("/");</script>',
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

    fallback = share_root / 'index.html'
    if _write_if_changed(
        fallback,
        render_invalid_share_html(site_url=site_url, og_image_path=og_image_path),
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
