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
  ConceptGlyph,
  CONCEPT_GLYPH_KEYS,
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
const countOccurrences = (html, text) => (html.match(new RegExp(escapeRegExp(text), 'g')) || []).length
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

test('the product experience tokens match the approved design reference', () => {
  const colors = tailwindConfig.theme.extend.colors
  assert.deepEqual(
    {
      ink: colors.ink,
      panel: colors.panel,
      elevated: colors['panel-2'],
      quietLine: colors['line-quiet'],
      line: colors.line,
      primary: colors.chalk100,
      secondary: colors.chalk200,
      tertiary: colors.chalk500,
      muted: colors.chalk600,
      blue: colors.signal,
      gold: colors.brass,
      fresh: colors.pine,
      stretched: colors.warning,
      vulnerable: colors.danger,
    },
    {
      ink: '#0B0F14', panel: '#10161E', elevated: '#141C26', quietLine: '#171E27', line: '#232C38',
      primary: '#E9EEF5', secondary: '#B4C0CE', tertiary: '#8592A3', muted: '#788698',
      blue: '#5B8CD6', gold: '#C9A96A', fresh: '#6FB6A0',
      stretched: '#D6A45C', vulnerable: '#C97F6E',
    },
  )
  assert.deepEqual(tailwindConfig.theme.extend.fontFamily, {
    display: ['"Archivo Narrow"', 'sans-serif'],
    mono: ['"IBM Plex Mono"', 'monospace'],
    body: ['"IBM Plex Sans"', 'sans-serif'],
  })
})

test('spacing, radii, shadow, and breakpoint scales are deliberate rather than ad hoc', () => {
  const extend = tailwindConfig.theme.extend
  assert.deepEqual(
    { gutter: extend.spacing.gutter, tight: extend.spacing['rhythm-tight'], rhythm: extend.spacing.rhythm, loose: extend.spacing['rhythm-loose'], section: extend.spacing.section },
    { gutter: '1.5rem', tight: '0.75rem', rhythm: '1.125rem', loose: '2.25rem', section: '2.75rem' },
  )
  for (const radius of ['DEFAULT', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', 'edge', 'panel', 'control']) {
    assert.equal(extend.borderRadius[radius], '0', `borderRadius.${radius}`)
  }
  assert.deepEqual(extend.boxShadow, { panel: 'none', edition: 'none' })
  assert.deepEqual(
    { shell: extend.maxWidth.shell, reading: extend.maxWidth.reading, measure: extend.maxWidth.measure, definition: extend.maxWidth.definition },
    { shell: '85rem', reading: '72.5rem', measure: '66ch', definition: '76ch' },
  )
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

const changedDashboard = {
  freshness: {
    data_through: '2026-08-05',
    last_successful_sync: '2026-08-06T10:04:00Z',
    is_current: true,
    sync_status: 'success',
  },
  what_changed_since_yesterday: {
    capability: 'what_changed_since_yesterday_public_v1',
    state: 'changes_detected',
    comparison: {
      comparison_available: true,
      previous_data_through: '2026-08-04',
      current_data_through: '2026-08-05',
    },
    ordering_basis: 'team_abbreviation_then_team_name',
    item_count: 1,
    summary: {
      meaningful_change_count: 1,
      more_breathing_room_count: 1,
      tighter_today_count: 0,
      structure_changed_count: 0,
      other_meaningful_change_count: 0,
      counts_complete: true,
    },
    items: [{
      key: 'NYM', team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM',
      movement_lane: 'more_breathing_room', movement_label: 'More breathing room',
      primary_delta: { label: 'Rested relievers', previous: 3, current: 5, net_delta: 2 },
      public_headline: 'Mets bullpen has more breathing room today.',
      public_summary: 'New York has more usable late-inning margin than yesterday.',
      public_context: 'That creates more ways through a close game tonight.',
      yesterday_rested_count: 3,
      today_rested_count: 5,
      workload_added: [{ name: 'Reed Garrett', pitches: 21 }],
    }],
  },
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
  assert.ok(htmlIncludes(html, 'BaseballOS · Today'))
  assert.ok(htmlIncludes(html, "Today&#x27;s Bullpen Edition"))
  assert.ok(htmlIncludes(html, 'Bullpen data through'))
  assert.ok(htmlIncludes(html, 'Aug 5, 2026'))
  assert.ok(htmlIncludes(html, 'Tonight slate'))
  assert.ok(htmlIncludes(html, 'Teams tracked'))
  assert.ok(htmlIncludes(html, '30'))
})

test('the masthead is a dated nameplate, not a product pitch', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [] },
    teams,
  }))

  // The edition is dated by the slate it represents, derived from the served
  // reference date and never from the reader's clock.
  assert.ok(htmlIncludes(html, 'Thursday, August 6, 2026'))

  // A masthead names the publication and dates the issue. The value
  // proposition, the how-it-works paragraph, and the two calls to action that
  // used to occupy this position are gone: they argued for the product where a
  // daily edition reports the day, and they pushed the first real read off the
  // opening screen.
  const head = html.slice(0, html.indexOf('id="bullpen-picture"'))
  for (const marketing of [
    'See which bullpens are fresh, stretched, or vulnerable tonight',
    'BaseballOS reads public MLB usage, rest, and roster context after every completed game',
    "Explore today&#x27;s bullpen picture",
    'View the league board',
  ]) {
    assert.equal(htmlIncludes(head, marketing), false, marketing)
  }

  // The first substantive region on the page is baseball, not positioning.
  assert.ok(
    html.indexOf('id="bullpen-picture"') < html.indexOf('id="what-baseballos-is-for"'),
    'the league picture outranks the product statement',
  )
})

test('the edition brief withholds every temporal fact when nothing is served', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, { teams: [] }))

  assert.equal(htmlIncludes(html, 'Bullpen data through'), false)
  assert.equal(htmlIncludes(html, 'Last updated'), false)
  assert.equal(htmlIncludes(html, 'Published view'), false)
  assert.equal(htmlIncludes(html, 'Teams tracked'), false)
  // The nameplate survives — it is identity, not a claim about data.
  assert.ok(htmlIncludes(html, "Today&#x27;s Bullpen Edition"))
  // The dateline does not: an undated edition is honest, a guessed date is not.
  assert.equal(/\b(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),/.test(visibleText(html)), false)
})

test('a stale edition is dated by the data it represents, not by the reader', () => {
  const staleFreshness = {
    ...freshness,
    is_current: false,
    is_stale: true,
    freshness_state: 'stale',
  }
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness: staleFreshness },
    landscape,
    teams,
  }))

  // With no slate served the edition falls back to the completed date the
  // bullpen picture is built from — and says so plainly. A prettier masthead
  // must never let a stale read wear today's date.
  assert.ok(htmlIncludes(html, 'Wednesday, August 5, 2026'))
  assert.ok(htmlIncludes(html, 'Not current'))
})

test('no date on Today can come from the reader’s clock', () => {
  // The only defence that survives refactoring: the Today rendering path never
  // reads the current time at all. Every date it shows is a value the
  // application was served, so there is no code path in which a stale read can
  // acquire a fresh-looking date.
  const clockSources = [
    surfaceSource,
    intelSources,
    readFileSync(new URL('../src/utils/dateDisplay.js', import.meta.url), 'utf8'),
    readFileSync(new URL('../src/components/UI/Freshness.jsx', import.meta.url), 'utf8'),
  ].join('\n')

  assert.equal(/\bnew Date\(\s*\)/.test(clockSources), false, 'new Date()')
  assert.equal(/\bDate\.now\(\s*\)/.test(clockSources), false, 'Date.now()')
})

test('Today renders no lead story and invents no headline for one', () => {
  // A public lead-story claim contract does not exist yet in the Bullpen
  // Intelligence Standard, and Phase 3 "Today lead authority" is unstarted, so
  // Today carries no lead region. What matters for this pass is that the
  // position is not filled with something manufactured instead: the surface
  // must not render a placeholder lead, a "nothing cleared the bar" notice that
  // implies an evaluation this surface did not run, or the raw backend empty
  // reason.
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: {
      status: 'empty',
      lead_story: null,
      empty_reason: 'no_publishable_coin_story',
      candidates_considered: 4,
      publishable_candidates: 0,
    },
    dashboard: { freshness },
    landscape,
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [] },
    teams,
  }))

  for (const fabricated of [
    'BaseballOS is watching this bullpen story',
    'No lead bullpen story has cleared the bar yet.',
    'No publishable bullpen story is available from the current completed-game context.',
    'candidates considered',
  ]) {
    assert.equal(htmlIncludes(html, fabricated), false, fabricated)
  }

  // The first substantive read is still the governed league picture.
  const head = html.slice(0, html.indexOf('id="bullpen-picture"'))
  assert.equal((head.match(/<h2/g) || []).length, 0, 'nothing outranks the league picture')
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
    html.indexOf('id="tonight"'),
  )

  // Supplied canonical state renders with its canonical label.
  assert.ok(htmlIncludes(overview, 'Fresh'))
  // A team whose backend block says "unavailable" gets the governed non-state.
  assert.ok(htmlIncludes(overview, 'No current state'))
  // A team with no Team State block at all gets no state chip invented for it.
  // (The lane heading "Where late-inning margin is thin" is league orientation, not a
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
    'id="tonight"',
    'id="vocabulary"',
    'id="data-and-trust"',
    'id="what-baseballos-is-for"',
    'id="continue-exploring"',
  ]
  let previous = -1
  for (const marker of ordered) {
    const index = html.indexOf(marker)
    assert.ok(index > previous, marker)
    previous = index
  }

  // Today's landmark sections are a closed, ordered set. "What changed" is the
  // one region that legitimately withholds itself when the dashboard supplies
  // no comparison, so the rendered ids must be a prefix-preserving subsequence
  // of the authored order — never a superset, and never reshuffled. This is
  // what stops a navigation block being reinserted between two reads.
  const AUTHORED_ORDER = [
    'bullpen-picture',
    'since-yesterday',
    'tonight',
    'vocabulary',
    'data-and-trust',
    'what-baseballos-is-for',
  ]
  const sectionIds = [...html.matchAll(/<section id="([^"]+)"/g)].map(match => match[1])
  assert.deepEqual(
    sectionIds,
    AUTHORED_ORDER.filter(id => sectionIds.includes(id)),
    `unexpected Today sections: ${sectionIds.join(', ')}`,
  )
  // Every region that is not conditionally withheld is present.
  for (const id of AUTHORED_ORDER.filter(candidate => candidate !== 'since-yesterday')) {
    assert.ok(sectionIds.includes(id), id)
  }
})

test('the Today vocabulary teaches three concepts and routes to the full set', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    teams,
  }))
  const vocabulary = html.slice(html.indexOf('id="vocabulary"'), html.indexOf('id="data-and-trust"'))

  // Exactly three concept features: how loaded the pen is, how it recovers,
  // and what is usable tonight.
  for (const name of ['Bullpen Pressure', 'Recovery Window', 'Clean Options']) {
    assert.ok(htmlIncludes(vocabulary, name), name)
  }
  // The remaining three are still canonical vocabulary — they are simply not
  // taught mid-edition. How to Read still owns the complete dictionary.
  for (const name of ['Workload Concentration', 'Coverage Safety', 'Trusted Arms']) {
    assert.equal(htmlIncludes(vocabulary, name), false, name)
  }
  // Three cards, three marks — not three names inside six cards.
  assert.equal(countOccurrences(vocabulary, 'bos-concept-title'), 3)
  assert.equal(countOccurrences(vocabulary, '<svg'), 3)

  // The three canonical Team State words are untouched by the trim.
  for (const label of ['Fresh', 'Stretched', 'Vulnerable']) {
    assert.ok(htmlIncludes(vocabulary, `>${label}<`), label)
  }

  // Exactly one path to everything that was removed.
  assert.ok(htmlIncludes(vocabulary, 'Explore all BaseballOS terms'))
  assert.ok(htmlIncludes(vocabulary, 'href="/how-to-read"'))
})

test('the full six-concept dictionary survives the Today trim', async () => {
  const { CONCEPT_DEFINITIONS: full, SUPPORTING_CONCEPT_DEFINITIONS: supporting } =
    await server.ssrLoadModule('/src/utils/bullpenConcepts.js')

  // Removing three concepts from Today removed nothing from the product: the
  // definitions, the glyph keys, and the card component are all still there.
  for (const key of ['pressure', 'recovery', 'concentration', 'cleanOptions']) {
    assert.ok(full[key]?.name, key)
    assert.ok(full[key]?.definition, key)
  }
  for (const key of ['coverageSafety', 'trustedArms']) {
    assert.ok(supporting[key]?.name, key)
    assert.ok(supporting[key]?.definition, key)
  }
  for (const key of ['concentration', 'coverageSafety', 'trustedArms']) {
    assert.ok(CONCEPT_GLYPH_KEYS.includes(key), key)
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

test('Today never leaks implementation vocabulary into public copy', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: changedDashboard,
    landscape,
    tonight: {
      status: 'ok',
      reference_date: '2026-08-06',
      cards: [{
        team_id: 137,
        team_name: 'San Francisco Giants',
        pregame_story: {
          headline: 'A narrower late-inning group tonight',
          watching: 'BaseballOS is watching how much usable margin is left.',
          watch_point: 'Whether the same arms cover the seventh and eighth again.',
        },
        evidence: ['Aug 5 vs SD: Camilo Doval, 18 pitches, 1.0 inning'],
        limitations: [],
      }],
    },
    teams,
  }))
  const text = visibleText(html)

  // Engine, storage, and transport words the reader has no way to check, plus
  // the advice framing the product refuses outright. "No picks, no betting"
  // style refusals are deliberately not in this list: naming what BaseballOS
  // does not do is a boundary statement, not a leak.
  for (const banned of [
    'recommendation', 'recommended', 'recommends',
    'COIN', 'endpoint', 'backend', 'snapshot', 'payload', 'adapter',
    'deterministic', 'signal_family', 'internal_strength', 'ranking_score',
    'story_priority', 'confidence', 'fatigue', 'model version', 'method version',
  ]) {
    assert.equal(new RegExp(`\\b${escapeRegExp(banned)}\\b`, 'i').test(text), false, banned)
  }

  // No bare version stamp ("v1", "V2") anywhere a reader can see it.
  assert.equal(/\bv\d+(\.\d+)*\b/i.test(text), false, 'version label')
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

test('editorial headings use the approved display face; only metadata keeps the mono face', () => {
  const level = name => {
    const start = indexCss.indexOf(`${name} {`)
    return start < 0 ? '' : indexCss.slice(start, indexCss.indexOf('}', start))
  }
  // Headings use Archivo Narrow through the display token and never mono.
  for (const name of ['.bos-hero', '.bos-lead-headline', '.bos-section-title', '.bos-card-title']) {
    assert.ok(level(name).includes('font-display'), `${name} uses the display face`)
    assert.equal(level(name).includes('font-mono'), false, `${name} is not monospaced`)
  }
  // Short kickers use the same display family.
  assert.ok(level('.bos-kicker').includes('font-display'))
  // Precision values keep the mono face.
  for (const name of ['.bos-meta', '.bos-value']) {
    assert.ok(level(name).includes('font-mono'), name)
  }
  // Buttons are application controls, not console controls.
  assert.equal(level('.bos-action').includes('font-mono'), false)
  assert.equal(level('.bos-action').includes('uppercase'), false)
})

test('Foundations remains flat: no contour art, radial glow, or component shadow', () => {
  assert.match(indexCss, /--bos-shadow-panel:\s+none/)
  assert.match(indexCss, /--bos-shadow-edition:\s+none/)
  const start = indexCss.indexOf('.bos-depth::before,')
  const block = indexCss.slice(start, start + 500)
  assert.ok(block.includes('content: none'))
  assert.equal(block.includes('radial-gradient'), false)
  assert.equal(block.includes('data:image/svg+xml'), false)
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
  assert.ok(text.includes('Where arms are rested'))
  assert.ok(text.includes('Where recent work is worth watching'))
  assert.ok(text.includes('Where late-inning margin is thin'))
})

test('no league lane label can be mistaken for a fourth Team State', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    tonight: { status: 'ok', reference_date: '2026-08-06', cards: [] },
    teams,
  }))
  const overview = html.slice(
    html.indexOf('id="bullpen-picture"'),
    html.indexOf('id="tonight"'),
  )

  // The retired lane titles were short capitalised noun phrases — the same
  // grammatical shape as Fresh / Stretched / Vulnerable — sitting one line
  // above a club's canonical state. They are gone from the league overview.
  for (const stateShaped of [
    'Room to Maneuver', 'Limited Late-Inning Margin',
    'Stable', 'Strong', 'Healthy', 'Safe',
  ]) {
    assert.equal(htmlIncludes(overview, stateShaped), false, stateShaped)
  }

  // "On Watch" stays canonical public vocabulary at the arm altitude, so it is
  // not banned outright — it simply no longer titles a league lane, where it
  // read as a peer of the three team states.
  assert.equal(/>\s*On Watch\s*</.test(overview), false, 'On Watch is not a lane heading')

  // Only the backend-owned Team State is presented as a state: it is the one
  // thing in the column carrying the screen-reader state prefix.
  assert.ok(htmlIncludes(overview, 'Team State:'))

  // Every lane label renders in the quiet label treatment, never in a heading
  // weight that competes with the club name and its state.
  for (const lane of [
    'Where arms are rested',
    'Where recent work is worth watching',
    'Where late-inning margin is thin',
  ]) {
    assert.ok(
      new RegExp(`class="bos-micro"[^>]*>\\s*${escapeRegExp(lane)}`).test(overview),
      lane,
    )
  }
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

// The collapsed Tonight read is the answer only. Everything inspectable sits
// behind one disclosure whose label names the supplied evidence count; the
// exact rows are inside, verbatim. Limitations, freshness, and the Team Board
// path never move behind it.
const tonightCard = {
  key: 'CHC', team_id: 112, team_name: 'Chicago Cubs', team_abbreviation: 'CHC',
  pregame_story: {
    headline: 'Narrow bullpen margin before first pitch',
    team_context: 'Schedule context sentence.',
    watching: 'The supported summary sentence.',
    why_it_matters: 'The deeper why sentence.',
    key_note: 'The deeper key note sentence.',
    watch_point: 'The watch point sentence.',
  },
  evidence: ['One arm is on watch after recent work', 'A long stretch before the next off day'],
  limitations: ['Schedule context can change before lineup lock.'],
}
const tonightTeams = [{ team_id: 112, team_name: 'Chicago Cubs', team_abbreviation: 'CHC' }]

const renderTonight = (card) => render(React.createElement(IntelligenceSurfaceView, {
  dashboard: { freshness },
  tonight: { status: 'ok', reference_date: '2026-08-06', cards: [card] },
  teams: tonightTeams,
}))

test('the collapsed Tonight read is the answer, and inspection sits behind one disclosure', () => {
  const html = renderTonight(tonightCard)
  const collapsed = html.slice(0, html.indexOf('<details'))

  // Club, headline, the supported summary, and the watch point are immediate.
  for (const immediate of [
    'Chicago Cubs',
    'Narrow bullpen margin before first pitch',
    'The supported summary sentence.',
    'Watch Point',
    'The watch point sentence.',
  ]) {
    assert.ok(htmlIncludes(collapsed, immediate), immediate)
  }

  // Evidence rows and supporting context are not in the collapsed read.
  for (const deferred of [
    'One arm is on watch after recent work',
    'A long stretch before the next off day',
    'Schedule context sentence.',
    'The deeper why sentence.',
    'The deeper key note sentence.',
  ]) {
    assert.equal(htmlIncludes(collapsed, deferred), false, deferred)
  }

  // Exactly one disclosure per card — no nested details.
  assert.equal((html.match(/<details/g) || []).length, 1)
  assert.equal(/<details[\s\S]*<details/.test(html), false, 'no nested disclosure')
})

test('the Tonight disclosure label reports only the supplied evidence count', () => {
  // Two supplied rows -> a count of two. The label is derived from the array
  // length alone; nothing is read out of the row contents.
  const two = renderTonight(tonightCard)
  assert.ok(htmlIncludes(two, 'View evidence and context (2)'))
  assert.ok(htmlIncludes(two, 'Hide evidence and context'))

  // One supplied row -> a count of one.
  const one = renderTonight({ ...tonightCard, evidence: ['One arm is on watch after recent work'] })
  assert.ok(htmlIncludes(one, 'View evidence and context (1)'))
  assert.equal(htmlIncludes(one, '(2)'), false)

  // No evidence at all -> no count is invented, and the disclosure still opens
  // the remaining backend-authored context.
  const none = renderTonight({ ...tonightCard, evidence: [] })
  assert.equal(/View evidence and context \(\d/.test(none), false)
  assert.ok(htmlIncludes(none, 'More on this read'))

  // Nothing to inspect at all -> no disclosure rather than an empty one.
  const bare = renderTonight({
    ...tonightCard,
    evidence: [],
    pregame_story: {
      headline: 'Narrow bullpen margin before first pitch',
      watching: 'The supported summary sentence.',
      watch_point: 'The watch point sentence.',
    },
  })
  assert.equal(htmlIncludes(bare, '<details'), false)
  assert.ok(htmlIncludes(bare, 'The watch point sentence.'))
})

test('Tonight never summarizes, ranks, or paraphrases the evidence it defers', () => {
  const html = renderTonight(tonightCard)

  // The exact supplied rows survive inside the disclosure, verbatim and in the
  // order they were served.
  const disclosure = html.slice(html.indexOf('<details'), html.indexOf('</details>'))
  const first = disclosure.indexOf('One arm is on watch after recent work')
  const second = disclosure.indexOf('A long stretch before the next off day')
  assert.ok(first > -1 && second > first, 'supplied rows render in order')

  // The count affordance is the only thing derived from the array, and no
  // ranking or quality language is attached to it.
  const text = visibleText(html)
  for (const banned of ['strongest', 'weakest', 'most important', 'key evidence', 'top', 'best', 'worst']) {
    assert.equal(new RegExp(`\\b${escapeRegExp(banned)}\\b`, 'i').test(text), false, banned)
  }
})

test('Tonight keeps limitations, freshness, and the Team Board path outside the disclosure', () => {
  const html = renderTonight(tonightCard)
  const afterDisclosure = html.slice(html.indexOf('</details>'))

  // A limitation that could change interpretation is never deferred.
  assert.ok(htmlIncludes(afterDisclosure, 'Schedule context can change before lineup lock.'))
  // The inspection path stays visible.
  assert.ok(htmlIncludes(afterDisclosure, 'View Team Bullpen State'))
  assert.ok(htmlIncludes(afterDisclosure, 'Open the bullpen board for Chicago Cubs'))
  // Freshness sits above the grid, outside every card.
  const beforeCards = html.slice(0, html.indexOf('<details'))
  assert.ok(htmlIncludes(beforeCards, 'Published view through'))
  assert.ok(htmlIncludes(beforeCards, 'Tonight slate'))
})

test('Team State stays readable without colour and without the mono face', () => {
  const state = readPublicTeamState({ available: true, public_state: 'fresh', public_label: 'Fresh' })
  const html = render(React.createElement(TeamStateChip, { teamState: state }))
  // The label is real text with a screen-reader prefix, not a colour or an icon.
  assert.ok(htmlIncludes(html, 'Team State: '))
  assert.ok(htmlIncludes(html, 'Fresh'))
  assert.equal(htmlIncludes(html, 'font-mono'), false)
})

// ── Third-pass art-direction contracts ──────────────────────────────────────

test('the concept glyphs are decorative marks that cannot carry a value', () => {
  const glyphSource = readFileSync(new URL('../src/components/intel/ConceptGlyph.jsx', import.meta.url), 'utf8')
  const code = glyphSource.replace(/^\s*\/\/.*$/gm, '')

  // Fixed geometry only. The component takes a concept name and a class, never
  // a number, so no glyph can become a gauge, meter, ring, or rating.
  assert.match(code, /function ConceptGlyph\(\{ name, className = '' \}\)/)
  // No path, radius, angle, or opacity is interpolated from anything.
  assert.equal(/(d|r|cx|cy|strokeOpacity|opacity)=\{/.test(code), false, 'geometry is never computed')
  assert.equal(/<text|textContent/.test(code), false, 'a glyph never renders text')
  // Hand-authored inline SVG — no icon library import.
  assert.equal(/^import .*(icon|lucide|heroicon|feather)/im.test(code), false)

  const html = render(React.createElement(ConceptCard, {
    name: 'Recovery Window',
    definition: 'How much clean rest the bullpen has available.',
    glyph: 'recovery',
    to: '/methodology',
  }))
  assert.ok(htmlIncludes(html, '<svg'))
  assert.ok(htmlIncludes(html, 'aria-hidden="true"'))
  assert.ok(htmlIncludes(html, 'focusable="false"'))
  // The name still carries the meaning as text.
  assert.ok(htmlIncludes(html, 'Recovery Window'))
  // And the card still holds no digit of any kind.
  assert.equal(/\d/.test(visibleText(html)), false, visibleText(html))
})

test('an unknown glyph name renders nothing rather than a placeholder mark', () => {
  assert.equal(render(React.createElement(ConceptGlyph, { name: 'not-a-concept' })), '')
  assert.equal(render(React.createElement(ConceptGlyph, {})), '')
  // Every named concept the vocabulary uses has a mark.
  for (const key of ['pressure', 'recovery', 'concentration', 'cleanOptions', 'coverageSafety', 'trustedArms']) {
    assert.ok(CONCEPT_GLYPH_KEYS.includes(key), key)
  }
})

test('the canonical Team State words stay text and stay out of the concept features', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    teams,
  }))
  const vocabulary = html.slice(html.indexOf('id="vocabulary"'), html.indexOf('id="data-and-trust"'))

  // The three reads are present as plain text definitions...
  for (const label of ['Fresh', 'Stretched', 'Vulnerable']) {
    assert.ok(htmlIncludes(vocabulary, `>${label}<`), label)
  }
  // ...and the state list itself is never dressed as a concept feature.
  const stateList = render(React.createElement(ConceptGlossary, {
    terms: [
      { name: 'Fresh', definition: 'The bullpen comes in mostly rested, with room to maneuver late.' },
      { name: 'Stretched', definition: 'The bullpen is thin on rested arms after recent work.' },
      { name: 'Vulnerable', definition: 'Little late-inning margin remains if the game runs long.' },
    ],
  }))
  assert.equal(htmlIncludes(stateList, '<svg'), false, 'state words carry no glyph')
  assert.ok(htmlIncludes(stateList, '<dl'), 'the three reads stay a definition list')
})

test('the descriptive-only boundary sits in the trust context, not the lead region', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: { freshness },
    landscape,
    teams,
  }))
  const boundary = 'Descriptive only'
  const brief = html.slice(0, html.indexOf('id="bullpen-picture"'))
  const trust = html.slice(html.indexOf('id="data-and-trust"'))

  // The governance statement stays on the page...
  assert.ok(htmlIncludes(html, boundary))
  // ...but not inside the opening reading path.
  assert.equal(htmlIncludes(brief, boundary), false)
  assert.ok(htmlIncludes(trust, boundary))
})

test('What Changed keeps its controls, evidence, and comparison contract', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: changedDashboard,
    landscape,
    teams,
  }))
  const changed = html.slice(html.indexOf('SINCE YESTERDAY'), html.indexOf('id="tonight"'))

  // Controls survive the visual quietening, including roving keyboard wiring.
  assert.ok(htmlIncludes(changed, 'role="tablist"'))
  assert.ok(htmlIncludes(changed, 'role="tabpanel"'))
  assert.ok(htmlIncludes(changed, 'aria-selected="true"'))
  assert.ok(htmlIncludes(changed, 'tabindex="-1"'))
  assert.ok(htmlIncludes(changed, 'type="search"'))
  assert.ok(htmlIncludes(changed, 'Find a team'))

  // The comparison contract is still stated, and both dates still render.
  assert.ok(htmlIncludes(changed, 'Previous view'))
  assert.ok(htmlIncludes(changed, 'Current view'))

  // Backend-authored change copy renders verbatim, and the delta keeps its
  // supplied label rather than a frontend recasing of it.
  assert.ok(htmlIncludes(changed, 'New York has more usable late-inning margin than yesterday.'))
  assert.ok(htmlIncludes(changed, 'Rested relievers'))
  assert.ok(htmlIncludes(changed, 'Reed Garrett'))
  assert.ok(htmlIncludes(changed, 'View evidence'))

  // Nothing infers a transition: only supplied previous/current values appear.
  const text = visibleText(changed)
  for (const banned of ['likely', 'expected', 'projected', 'trending', 'because of tomorrow']) {
    assert.equal(new RegExp(escapeRegExp(banned), 'i').test(text), false, banned)
  }
})

test('the Today edition exposes one landmark-labelled section per region', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    dashboard: {
      freshness,
      what_changed_since_yesterday: {
        state: 'no_meaningful_changes',
        comparison: { comparison_available: true },
      },
    },
    landscape,
    teams,
  }))
  const sections = html.match(/<section[^>]*aria-labelledby="([^"]+)"/g) || []
  // Six regions, each labelled by its own heading. Not "at least six": a
  // seventh landmark section on Today means a region was added back.
  assert.equal(sections.length, 6, `expected six labelled sections, saw ${sections.length}`)
  for (const section of sections) {
    const id = /aria-labelledby="([^"]+)"/.exec(section)[1]
    assert.ok(html.includes(`id="${id}"`), `${id} target exists`)
  }
  // Every section heading is an H2 under the single page H1.
  assert.equal((html.match(/<h1/g) || []).length, 1)
  // The one remaining navigation group on Today is a <nav> with its own label,
  // not a seventh section competing with the reads.
  assert.equal((html.match(/<nav[^>]*aria-label="Other bullpen views"/g) || []).length, 1)
})
