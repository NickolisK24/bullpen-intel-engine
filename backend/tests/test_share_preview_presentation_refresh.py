"""Presentation-only migration proof for the checked-in immutable share corpus."""

from scripts.refresh_share_preview_presentation import (
    preview_from_generated_html,
    refresh_page,
    semantic_receipt,
)
from services.share_artifact_previews import render_share_artifact_html


def _legacy_page(*, artifact_type='team_state', state='Stretched'):
    state_meta = (
        f'    <meta name="baseballos:team-state" content="{state}" />\n'
        if state else ''
    )
    title = (
        'Boston Red Sox bullpen — Stretched'
        if artifact_type == 'team_state'
        else 'The Boston Red Sox bullpen changed since yesterday.'
    )
    description = (
        "The Boston Red Sox's bullpen is Stretched. Data through September 1, 2026."
        if artifact_type == 'team_state'
        else 'Two frozen bullpen facts changed. Data through 2026-09-01.'
    )
    return f'''<!DOCTYPE html>
<html lang="en">
  <head>
    <title>{title}</title>
    <meta name="description" content="{description}" />
    <meta property="og:type" content="article" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:url" content="https://baseballos.app/share/frozen-1" />
    <meta property="og:image" content="https://baseballos.app/og/baseballos-card.png" />
    <meta name="baseballos:representation" content="immutable_share_artifact" />
    <meta name="baseballos:public-id" content="frozen-1" />
    <meta name="baseballos:artifact-type" content="{artifact_type}" />
    <meta name="baseballos:team" content="BOS" />
{state_meta}    <meta name="baseballos:live-destination" content="/bullpen?view=board&amp;team=BOS&amp;source=share" />
    <meta name="baseballos:data-through" content="2026-09-01" />
    <meta name="baseballos:generated-at" content="2026-09-02T10:00:00" />
    <meta name="baseballos:published-at" content="2026-09-02T10:01:00" />
    <meta name="baseballos:snapshot-id" content="1753" />
    <meta name="baseballos:sync-run-id" content="999" />
    <meta name="baseballos:schema-version" content="1.0.0" />
    <meta name="baseballos:render-version" content="frozen-1.0.0" />
    <meta name="baseballos:payload-version" content="frozen-1.0.0" />
    <link rel="canonical" href="https://baseballos.app/share/frozen-1" />
  </head>
  <body><main><h1>{title}</h1><p>{description}</p></main></body>
</html>
'''


def test_team_state_refresh_preserves_receipt_and_projects_frozen_claim(tmp_path):
    path = tmp_path / 'index.html'
    original = _legacy_page()
    path.write_text(original, encoding='utf-8')

    artifact_type, changed = refresh_page(path)
    refreshed = path.read_text(encoding='utf-8')

    assert artifact_type == 'team_state'
    assert changed is True
    assert semantic_receipt(refreshed) == semantic_receipt(original)
    assert '<h1>Boston Red Sox</h1>' in refreshed
    assert 'Team State: <strong>Stretched</strong>' in refreshed
    assert 'The Boston Red Sox&#x27;s bullpen is Stretched.' in refreshed
    assert '<script' not in refreshed.casefold()


def test_since_yesterday_refresh_uses_existing_fact_without_new_lookup():
    original = _legacy_page(artifact_type='since_yesterday_change', state=None)
    preview = preview_from_generated_html(original)
    refreshed = render_share_artifact_html(preview)

    assert semantic_receipt(refreshed) == semantic_receipt(original)
    assert '<h2 id="share-claim-title">The Boston Red Sox bullpen changed since yesterday.</h2>' in refreshed
    assert 'Two frozen bullpen facts changed.' in refreshed
    assert 'Open current Boston Red Sox bullpen' in refreshed
    assert '<script' not in refreshed.casefold()
