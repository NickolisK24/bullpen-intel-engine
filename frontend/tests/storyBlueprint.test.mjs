import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { StoryBlueprint, StoryPresentation } = await server.ssrLoadModule(
  '/src/components/home/BullpenStories.jsx',
)
const { getCanonicalStoryFeed } = await server.ssrLoadModule(
  '/src/components/stories/storiesCanonicalFeedView.js',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

const SECTIONS = [
  { key: 'what_everyone_saw', label: 'What everyone saw', text: 'On the surface, the pitching line says the bullpen did its job.' },
  { key: 'what_baseballos_noticed', label: 'What BaseballOS noticed', text: 'The bullpen entered before the sixth in recent games.' },
  { key: 'evidence', label: 'Evidence', text: 'That is earlier than usual.\n\nThe starters are not covering as many innings.' },
  { key: 'why_it_matters', label: 'Why it matters', text: 'Bullpen workload is borrowed, not free.' },
  { key: 'why_it_matters_tomorrow', label: 'Why it matters tomorrow', text: 'More middle innings keep landing on the bullpen.' },
]


test('StoryBlueprint renders each labeled teaching section', () => {
  const html = renderToStaticMarkup(React.createElement(StoryBlueprint, { sections: SECTIONS }))
  for (const section of SECTIONS) {
    assert.ok(htmlIncludes(html, section.label), section.label)
  }
  assert.ok(htmlIncludes(html, 'What everyone saw'))
  assert.ok(htmlIncludes(html, 'Bullpen workload is borrowed, not free.'))
  // The evidence section keeps both supporting paragraphs.
  assert.ok(htmlIncludes(html, 'That is earlier than usual.'))
  assert.ok(htmlIncludes(html, 'The starters are not covering as many innings.'))
})


test('StoryBlueprint renders nothing without usable sections', () => {
  assert.equal(renderToStaticMarkup(React.createElement(StoryBlueprint, { sections: [] })), '')
  assert.equal(renderToStaticMarkup(React.createElement(StoryBlueprint, { sections: null })), '')
  // A section with no text is dropped.
  assert.equal(
    renderToStaticMarkup(React.createElement(StoryBlueprint, { sections: [{ key: 'x', label: 'X', text: '' }] })),
    '',
  )
})


test('StoryPresentation renders the blueprint when present and falls back when absent', () => {
  const withBlueprint = renderToStaticMarkup(React.createElement(StoryPresentation, {
    story: { blueprint: SECTIONS, narrative: 'FLAT NARRATIVE FALLBACK' },
  }))
  assert.ok(htmlIncludes(withBlueprint, 'What everyone saw'))
  assert.ok(htmlIncludes(withBlueprint, 'Why it matters tomorrow'))
  // When the blueprint renders, the flat narrative is not also dumped.
  assert.equal(htmlIncludes(withBlueprint, 'FLAT NARRATIVE FALLBACK'), false)

  const withoutBlueprint = renderToStaticMarkup(React.createElement(StoryPresentation, {
    story: { blueprint: [], narrative: 'FLAT NARRATIVE FALLBACK' },
  }))
  assert.ok(htmlIncludes(withoutBlueprint, 'FLAT NARRATIVE FALLBACK'))
})


test('canonical feed adapter passes the backend blueprint through to the card', () => {
  const dashboard = {
    stories: {
      items: [{
        story_available: true,
        story_id: '118:2026-06-25',
        team_id: 118,
        team_abbreviation: 'KC',
        headline: 'The bullpen is carrying more of the game',
        narrative: 'N',
        story_type: 'coverage_pressure',
        blueprint: SECTIONS,
      }],
      league_context: null,
    },
  }
  const feed = getCanonicalStoryFeed(dashboard)
  assert.equal(feed.items.length, 1)
  assert.deepEqual(feed.items[0].blueprint, SECTIONS)
})


// ── V3-2: collapse / expand ───────────────────────────────────────────────────

test('collapsible StoryBlueprint collapses to the lead-in with a Read the full read control', () => {
  const html = renderToStaticMarkup(React.createElement(StoryBlueprint, {
    sections: SECTIONS,
    collapsible: true,
  }))
  // The lead-in (what everyone saw + what BaseballOS noticed) stays visible.
  assert.ok(htmlIncludes(html, 'What everyone saw'))
  assert.ok(htmlIncludes(html, 'What BaseballOS noticed'))
  // Evidence / why it matters / why it matters tomorrow are hidden until expanded.
  assert.equal(htmlIncludes(html, 'Evidence'), false)
  assert.equal(htmlIncludes(html, 'Why it matters'), false)
  assert.equal(htmlIncludes(html, 'Bullpen workload is borrowed, not free.'), false)
  // Accessible, collapsed expand control.
  assert.ok(htmlIncludes(html, 'Read the full read'))
  assert.ok(htmlIncludes(html, 'type="button"'))
  assert.ok(htmlIncludes(html, 'aria-expanded="false"'))
})

test('collapsible StoryBlueprint with initialExpanded shows every section and Show less', () => {
  const html = renderToStaticMarkup(React.createElement(StoryBlueprint, {
    sections: SECTIONS,
    collapsible: true,
    initialExpanded: true,
  }))
  for (const section of SECTIONS) {
    assert.ok(htmlIncludes(html, section.label), section.label)
  }
  assert.ok(htmlIncludes(html, 'Bullpen workload is borrowed, not free.'))
  assert.ok(htmlIncludes(html, 'Show less'))
  assert.ok(htmlIncludes(html, 'aria-expanded="true"'))
})

test('non-collapsible StoryBlueprint shows every section with no toggle', () => {
  const html = renderToStaticMarkup(React.createElement(StoryBlueprint, { sections: SECTIONS }))
  assert.ok(htmlIncludes(html, 'Why it matters tomorrow'))
  assert.equal(htmlIncludes(html, 'Read the full read'), false)
  assert.equal(htmlIncludes(html, 'aria-expanded'), false)
})
