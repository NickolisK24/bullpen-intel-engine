// Contract tests for the BaseballOS product experience foundation: the design
// token layer, the reusable intelligence primitives, the Today edition
// hierarchy, and the accessibility guarantees the redesign depends on.
//
// These tests exist to stop the foundation drifting back into a generic
// dashboard: they pin that Team State stays backend-owned, that the brief never
// invents a fact, that no synthetic score or ranking appears, and that the
// Today edition keeps its authored section order.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import tailwindConfig from '../tailwind.config.js'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { IntelligenceSurfaceView } = await server.ssrLoadModule('/src/components/home/IntelligenceSurface.jsx')
const {
  ConceptCard,
  ConceptGlossary,
  EditionHeader,
  EvidenceList,
  IntelNotice,
  IntelSection,
  TeamStateChip,
  TeamStateRead,
  TrustFact,
  TrustStrip,
} = await server.ssrLoadModule('/src/components/intel/index.js')
const { readPublicTeamState } = await server.ssrLoadModule('/src/adapters/publicTeamState.js')

const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = (html) => html
  .replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

const indexCss = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')
const surfaceSource = readFileSync(new URL('../src/components/home/IntelligenceSurface.jsx', import.meta.url), 'utf8')
const intelSources = [
  'EditionHeader',
  'TeamStateChip',
  'EvidenceReceipt',
  'TrustStrip',
  'ConceptCard',
  'IntelNotice',
  'IntelSection',
].map(name => readFileSync(new URL(`../src/components/intel/${name}.jsx`, import.meta.url), 'utf8')).join('\n')

// ── Layer A: design tokens ──────────────────────────────────────────────────

test('the product experience colour tokens exist in both token systems', () => {
  const colors = tailwindConfig.theme.extend.colors
  for (const token of [
    'ink', 'panel', 'panel-2', 'line', 'line-strong',
    'signal', 'signal-deep', 'signal-well', 'brass', 'brass-deep', 'focus',
  ]) {
    assert.match(colors[token] || '', /^#[0-9a-f]{6}$/i, `${token} is a hex token`)
    assert.ok(
      indexCss.includes(`--bos-${token}:`),
      `${token} is also exposed as a CSS custom property`,
    )
  }
})

test('spacing, radii, shadow, and breakpoint scales are deliberate rather than ad hoc', () => {
  const extend = tailwindConfig.theme.extend
  for (const step of ['gutter', 'rhythm', 'section']) {
    assert.ok(extend.spacing[step], `spacing.${step}`)
  }
  assert.deepEqual(Object.keys(extend.borderRadius), ['edge', 'panel', 'control'])
  assert.deepEqual(Object.keys(extend.boxShadow), ['panel', 'edition'])
  assert.equal(extend.screens.xs, '390px')
})

test('the typographic scale covers every level the surfaces use', () => {
  for (const level of [
    '.bos-eyebrow', '.bos-hero', '.bos-lead-headline', '.bos-section-title',
    '.bos-card-title', '.bos-body', '.bos-support', '.bos-evidence',
    '.bos-meta', '.bos-micro',
  ]) {
    assert.ok(indexCss.includes(`${level} {`), level)
  }
})

test('motion respects the reduced-motion preference and focus is always visible', () => {
  assert.ok(indexCss.includes('@media (prefers-reduced-motion: reduce)'))
  assert.match(indexCss, /animation-duration: 0\.001ms !important/)
  assert.match(indexCss, /transition-duration: 0\.001ms !important/)
  assert.ok(indexCss.includes('outline: 2px solid var(--bos-focus)'))
})

// ── Layer B: intelligence primitives ────────────────────────────────────────

test('Team State renders the canonical backend label and never a fourth state', () => {
  for (const [code, label] of [['fresh', 'Fresh'], ['stretched', 'Stretched'], ['vulnerable', 'Vulnerable']]) {
    const state = readPublicTeamState({ available: true, public_state: code, public_label: label })
    const html = render(React.createElement(TeamStateChip, { teamState: state }))
    assert.ok(htmlIncludes(html, label), label)
    // State is text plus a decorative dot — it never depends on colour alone.
    assert.ok(htmlIncludes(html, 'Team State: '))
  }
})

test('an unsupported Team State fails closed to the governed non-state message', () => {
  const unsupported = readPublicTeamState({
    available: true,
    public_state: 'neutral',
    public_label: 'Neutral',
    unavailable_message: 'A current Team State read is not available for this bullpen.',
  })
  const html = render(React.createElement(TeamStateRead, { teamState: unsupported }))

  assert.equal(htmlIncludes(html, 'Neutral'), false)
  assert.ok(htmlIncludes(html, 'No current state'))
  assert.ok(htmlIncludes(html, 'A current Team State read is not available for this bullpen.'))
})

test('a missing Team State block renders nothing rather than a guessed label', () => {
  assert.equal(render(React.createElement(TeamStateChip, { teamState: null })), '')
  const empty = readPublicTeamState(null)
  const html = render(React.createElement(TeamStateChip, { teamState: empty }))
  assert.ok(htmlIncludes(html, 'No current state'))
  for (const label of ['Fresh', 'Stretched', 'Vulnerable']) {
    assert.equal(htmlIncludes(html, label), false, label)
  }
})

test('trust facts and stamps disappear when the application has no value', () => {
  assert.equal(render(React.createElement(TrustFact, { label: 'Data through', value: null })), '')
  assert.equal(render(React.createElement(TrustStrip, {})), '')

  const populated = render(React.createElement(TrustStrip, {
    dataThrough: '2026-08-05',
    lastSync: '2026-08-06T10:04:00Z',
  }))
  assert.ok(htmlIncludes(populated, 'Data through Aug 5'))
  assert.ok(htmlIncludes(populated, 'Last synced'))
})

test('evidence lists render supplied receipts and nothing when there are none', () => {
  assert.equal(render(React.createElement(EvidenceList, { items: [] })), '')
  const html = render(React.createElement(EvidenceList, {
    label: 'Usage Notes',
    items: ['Clean options are limited', 'One arm is on watch after recent work'],
  }))
  assert.ok(htmlIncludes(html, 'Usage Notes'))
  assert.ok(htmlIncludes(html, 'Clean options are limited'))
  assert.ok(htmlIncludes(html, '<li'))
})

test('limited and quiet states are designed states with a live region', () => {
  const html = render(React.createElement(IntelNotice, {
    eyebrow: 'Limited read',
    title: 'This read is being held.',
    message: 'BaseballOS is withholding it rather than guessing.',
    tone: 'limited',
  }))
  assert.ok(htmlIncludes(html, 'role="status"'))
  assert.ok(htmlIncludes(html, 'aria-live="polite"'))
  assert.ok(htmlIncludes(html, 'This read is being held.'))
})

test('concept cards teach vocabulary without attaching a value to it', () => {
  const html = render(React.createElement(ConceptCard, {
    name: 'Bullpen Pressure',
    definition: 'How much workload strain the bullpen is carrying today.',
    to: '/methodology',
  }))
  const text = visibleText(html)
  assert.ok(text.includes('Bullpen Pressure'))
  // A concept never carries a number, a tier, a percentage, or a grade.
  assert.equal(/\d/.test(text), false, text)
  assert.equal(/\b(score|rating|rank|grade|index|percentile)\b/i.test(text), false, text)
})

test('the concept glossary renders only complete term/definition pairs', () => {
  const html = render(React.createElement(ConceptGlossary, {
    terms: [
      { name: 'Coverage Safety', definition: 'Whether the bullpen can cover the late innings if the game runs long.' },
      { name: 'Missing Definition' },
      { definition: 'Missing name' },
    ],
  }))
  assert.ok(htmlIncludes(html, 'Coverage Safety'))
  assert.equal(htmlIncludes(html, 'Missing Definition'), false)
  assert.equal(htmlIncludes(html, 'Missing name'), false)
})

test('the edition header omits every fact the application could not supply', () => {
  const html = render(React.createElement(EditionHeader, {
    eyebrow: 'Today',
    editionLabel: 'Edition',
    title: 'A lead statement.',
    facts: [
      { label: 'Bullpen data through', value: 'Aug 5, 2026' },
      { label: 'Coverage', value: null },
      { label: 'Verified teams', value: '' },
    ],
  }))
  assert.ok(htmlIncludes(html, 'Bullpen data through'))
  assert.equal(htmlIncludes(html, 'Coverage'), false)
  assert.equal(htmlIncludes(html, 'Verified teams'), false)
  // Exactly one H1 per surface.
  assert.equal((html.match(/<h1/g) || []).length, 1)
})

test('sections expose a labelled region and a single H2', () => {
  const html = render(React.createElement(
    IntelSection,
    { id: 'example', eyebrow: 'Eyebrow', title: 'Section title', subtitle: 'Orientation.' },
    React.createElement('p', null, 'body'),
  ))
  assert.ok(htmlIncludes(html, 'id="example"'))
  assert.ok(htmlIncludes(html, 'aria-labelledby="example-title"'))
  assert.ok(htmlIncludes(html, 'id="example-title"'))
  assert.equal((html.match(/<h2/g) || []).length, 1)
})

// ── Layer C: application shell ──────────────────────────────────────────────

test('the shell offers a skip link into the main landmark', () => {
  assert.ok(appSource.includes('href="#main-content"'))
  assert.ok(appSource.includes('id="main-content"'))
  assert.ok(indexCss.includes('.bos-skip-link'))
})

// ── Layer D: the Today edition ──────────────────────────────────────────────

const teams = [
  { team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF' },
  { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR' },
  { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL' },
]

const freshness = {
  data_through: '2026-08-05',
  last_successful_sync: '2026-08-06T10:04:00Z',
  is_current: true,
  sync_status: 'success',
}

const landscape = {
  capability: 'tonights_bullpen_landscape',
  reference_date: '2026-08-06',
  teams_evaluated: 30,
  games: { available: true, data_state: 'historical', as_of_date: '2026-08-05', as_of_count: 14 },
  available_bullpens: [{
    team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF',
    total_relievers: 8, available: 6, monitor: 1, restricted: 1,
    team_state: { available: true, public_state: 'fresh', public_label: 'Fresh', data_through: '2026-08-05' },
  }],
  monitoring_concentration: [{
    team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR',
    total_relievers: 8, available: 3, monitor: 4, restricted: 1,
    team_state: { available: false, unavailable_message: 'A current Team State read is not available for this bullpen.' },
  }],
  constrained_bullpens: [{
    team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL',
    total_relievers: 8, available: 2, monitor: 2, restricted: 4,
  }],
  notes: [],
}

test('Today opens with one edition brief carrying only governed facts', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [] },
    teams,
  }))

  assert.equal((html.match(/<h1/g) || []).length, 1, 'exactly one H1')
  assert.ok(htmlIncludes(html, "Today&#x27;s Intelligence Brief"))
  assert.ok(htmlIncludes(html, 'Bullpen data through'))
  assert.ok(htmlIncludes(html, 'Aug 5, 2026'))
  assert.ok(htmlIncludes(html, 'Tonight slate'))
  assert.ok(htmlIncludes(html, 'Teams tracked'))
  assert.ok(htmlIncludes(html, '30'))
})

test('the edition brief withholds every temporal fact when nothing is served', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, { teams: [] }))

  assert.equal(htmlIncludes(html, 'Bullpen data through'), false)
  assert.equal(htmlIncludes(html, 'Last updated'), false)
  assert.equal(htmlIncludes(html, 'Published view'), false)
  assert.equal(htmlIncludes(html, 'Teams tracked'), false)
  // The lead statement and the boundary survive; only unsupported facts drop.
  assert.ok(htmlIncludes(html, 'See which bullpens are fresh, stretched, or vulnerable tonight — and why.'))
})

test('the brief reports a non-current published view honestly instead of hiding it', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness: { ...freshness, is_current: false, is_stale: true, freshness_state: 'stale' } },
    teams: [],
  }))
  assert.ok(htmlIncludes(html, 'Published view'))
  assert.ok(htmlIncludes(html, 'Not current'))
})

test('the league overview renders backend Team State and fails closed without one', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    teams,
  }))

  // Scope to the league overview so the vocabulary glossary further down the
  // page (which defines all three states) cannot satisfy these assertions.
  const overview = html.slice(
    html.indexOf('id="bullpen-picture"'),
    html.indexOf('id="explore-baseballos"'),
  )

  // Supplied canonical state renders with its canonical label.
  assert.ok(htmlIncludes(overview, 'Fresh'))
  // A team whose backend block says "unavailable" gets the governed non-state.
  assert.ok(htmlIncludes(overview, 'No current state'))
  // A team with no Team State block at all gets no state chip invented for it.
  // (The lane heading "Limited Late-Inning Margin" is league orientation, not a
  // Team State, so only the canonical state labels are checked here.)
  assert.equal(htmlIncludes(overview, 'Vulnerable'), false)
  assert.equal(htmlIncludes(overview, 'Team State: Stretched'), false)
  // Full team names, never a bare abbreviation as the only identity.
  assert.ok(htmlIncludes(overview, 'San Francisco Giants'))
  assert.ok(htmlIncludes(overview, 'Milwaukee Brewers'))
})

test('Today keeps its authored section order across the whole edition', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [] },
    teams,
  }))

  const ordered = [
    'id="bullpen-picture"',
    'id="explore-baseballos"',
    'id="tonight"',
    'id="vocabulary"',
    'id="data-and-trust"',
    'id="what-baseballos-is-for"',
    'id="explore"',
  ]
  let previous = -1
  for (const marker of ordered) {
    const index = html.indexOf(marker)
    assert.ok(index > previous, marker)
    previous = index
  }
})

test('Today never renders a synthetic score, ranking, or predictive framing', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [] },
    teams,
  }))
  const text = visibleText(html)

  for (const banned of [
    'score', 'rating', 'ranked', 'ranking', 'power index', 'percentile',
    'grade', 'odds', 'edge', 'advantage', 'projection', 'prediction',
    'favourite', 'favorite', 'pick of the day',
  ]) {
    assert.equal(new RegExp(`\\b${escapeRegExp(banned)}\\b`, 'i').test(text), false, banned)
  }
})

test('the new surfaces never rewrite, filter, or invent backend-owned copy', () => {
  // The presentation primitives are pure presentation: no regex rewriting of
  // governed public text, and no locally authored replacement for it.
  for (const pattern of [/\.replace\(\s*\//, /publicTerminology/, /INTERNAL_[A-Z_]*_COPY_PATTERN/]) {
    assert.equal(pattern.test(intelSources), false, String(pattern))
  }
  // The Today surface adds no new copy-rewriting rules on top of the two the
  // backend-owned-copy package (#591) already owns.
  assert.equal((surfaceSource.match(/_COPY_PATTERN\s*=/g) || []).length, 2)
})

// ── Visual refinement contracts ─────────────────────────────────────────────
//
// These pin the design decisions that carry the most product risk if they drift
// back. They deliberately assert behaviour and vocabulary rather than freezing
// class names, so ordinary CSS work stays cheap.

test('editorial levels use the interface face; only metadata keeps the mono face', () => {
  const level = name => {
    const start = indexCss.indexOf(`${name} {`)
    return start < 0 ? '' : indexCss.slice(start, indexCss.indexOf('}', start))
  }
  // Reading content is never condensed and never monospaced.
  for (const name of ['.bos-hero', '.bos-lead-headline', '.bos-section-title', '.bos-card-title']) {
    assert.ok(level(name).includes('font-body'), `${name} uses the interface face`)
    assert.equal(level(name).includes('font-display'), false, `${name} is not condensed`)
    assert.equal(level(name).includes('font-mono'), false, `${name} is not monospaced`)
  }
  // The condensed face survives only as a named accent.
  assert.ok(level('.bos-kicker').includes('font-display'))
  // Precision values keep the mono face.
  for (const name of ['.bos-meta', '.bos-value']) {
    assert.ok(level(name).includes('font-mono'), name)
  }
  // Buttons are application controls, not console controls.
  assert.equal(level('.bos-action').includes('font-mono'), false)
  assert.equal(level('.bos-action').includes('uppercase'), false)
})

test('background depth is decorative only and cannot intercept interaction', () => {
  const start = indexCss.indexOf('.bos-depth::before,')
  assert.ok(start > -1, 'the depth layer exists')
  const block = indexCss.slice(start, start + 400)
  assert.ok(block.includes('pointer-events: none'))
  assert.ok(block.includes('z-index: -1'))
  // Depth is drawn, never animated.
  assert.equal(/\.bos-depth[^{]*\{[^}]*animation/.test(indexCss), false)
})

test('Today never uses superlative or extreme lane framing', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [] },
    teams,
  }))
  const text = visibleText(html)

  for (const banned of [
    'Most Available', 'Most Stretched', 'most available', 'most stretched',
    'fewest', 'strongest', 'weakest', 'best bullpen', 'worst bullpen',
    'top bullpen', 'bottom bullpen', 'league leader',
  ]) {
    assert.equal(
      new RegExp(escapeRegExp(banned), 'i').test(text),
      false,
      banned,
    )
  }
  // The lanes still read as descriptive league orientation.
  assert.ok(text.includes('Room to Maneuver'))
  assert.ok(text.includes('On Watch'))
  assert.ok(text.includes('Limited Late-Inning Margin'))
})

test('a supported Today payload always shows its data-through date', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [] },
    teams,
  }))
  assert.ok(htmlIncludes(html, 'Bullpen data through'))
  assert.ok(htmlIncludes(html, 'Aug 5, 2026'))
})

test('Tonight keeps the answer, evidence, freshness, and limitations outside any disclosure', () => {
  const card = {
    key: 'CHC', team_id: 112, team_name: 'Chicago Cubs', team_abbreviation: 'CHC',
    pregame_story: {
      headline: 'Narrow bullpen margin before first pitch',
      team_context: 'Schedule context sentence.',
      watching: 'The supported summary sentence.',
      why_it_matters: 'The deeper why sentence.',
      key_note: 'The deeper key note sentence.',
      watch_point: 'The watch point sentence.',
    },
    evidence: ['One arm is on watch after recent work'],
    limitations: ['Schedule context can change before lineup lock.'],
  }
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [card] },
    teams: [{ team_id: 112, team_name: 'Chicago Cubs', team_abbreviation: 'CHC' }],
  }))

  const beforeDisclosure = html.slice(0, html.indexOf('<details'))
  // The answer, its evidence, and the watch point are immediate.
  for (const immediate of [
    'Narrow bullpen margin before first pitch',
    'The supported summary sentence.',
    'The watch point sentence.',
    'One arm is on watch after recent work',
  ]) {
    assert.ok(htmlIncludes(beforeDisclosure, immediate), immediate)
  }
  // Supporting rows move behind one native, keyboard-operable disclosure.
  assert.ok(htmlIncludes(html, '<summary'))
  assert.ok(htmlIncludes(html, 'The deeper why sentence.'))
  assert.ok(htmlIncludes(html, 'The deeper key note sentence.'))
  // A limitation that could change interpretation is never hidden.
  const afterDisclosure = html.slice(html.indexOf('</details>'))
  assert.ok(htmlIncludes(afterDisclosure, 'Schedule context can change before lineup lock.'))
  // Freshness is never hidden either.
  assert.ok(htmlIncludes(html, 'Published view through'))
})

test('Team State stays readable without colour and without the mono face', () => {
  const state = readPublicTeamState({ available: true, public_state: 'fresh', public_label: 'Fresh' })
  const html = render(React.createElement(TeamStateChip, { teamState: state }))
  // The label is real text with a screen-reader prefix, not a colour or an icon.
  assert.ok(htmlIncludes(html, 'Team State: '))
  assert.ok(htmlIncludes(html, 'Fresh'))
  assert.equal(htmlIncludes(html, 'font-mono'), false)
})

test('the Today edition exposes one landmark-labelled section per region', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    teams,
  }))
  const sections = html.match(/<section[^>]*aria-labelledby="([^"]+)"/g) || []
  assert.ok(sections.length >= 6, `expected labelled sections, saw ${sections.length}`)
  for (const section of sections) {
    const id = /aria-labelledby="([^"]+)"/.exec(section)[1]
    assert.ok(html.includes(`id="${id}"`), `${id} target exists`)
  }
  // Every section heading is an H2 under the single page H1.
  assert.equal((html.match(/<h1/g) || []).length, 1)
})
