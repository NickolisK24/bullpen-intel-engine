import assert from 'node:assert/strict'
import test, { after, afterEach } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
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

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

const {
  IntelligenceSurfaceView,
  getAroundBaseballItems,
  getBullpenPictureView,
  getLeadStoryView,
  getTonightCards,
} = await server.ssrLoadModule('/src/components/home/IntelligenceSurface.jsx')
const {
  getTodayIntelligence,
  getTonightIntelligence,
} = await server.ssrLoadModule('/src/utils/api.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const countOccurrences = (html, text) => (html.match(new RegExp(escapeRegExp(text), 'g')) || []).length

const teams = [
  { team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF' },
  { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM' },
  { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL' },
  { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR' },
  { team_id: 112, team_name: 'Chicago Cubs', team_abbreviation: 'CHC' },
]

const intelligenceOk = {
  status: 'ok',
  reference_date: '2026-06-25',
  candidates_considered: 4,
  publishable_candidates: 4,
  errors: 0,
  empty_reason: null,
  lead_story: {
    team_id: 137,
    game_pk: 137000,
    package: {
      team_id: 137,
      primary_story: 'lost_game_shape',
      publish_reason: 'critical_narrative',
      completed_game_context: {
        team_id: 137,
        team_name: 'the Giants',
        late_runs_allowed: 7,
        largest_lead: 4,
      },
      availability_snapshot: {
        available_arms_count: 3,
        monitor_arms_count: 1,
        unavailable_arms_count: 1,
        optionality_band: 'thin',
      },
      workload_snapshot: {
        concentration_band: 'concentrated',
      },
      bullpen_snapshot: {
        clean_options_count: 1,
        clean_options: [{ name: 'Erik Miller' }],
        optionality_band: 'thin',
      },
    },
    drafts: {
      team_story: {
        writer: 'team_story',
        headline: 'Giants bullpen let a four-run lead get away',
        body: 'The Giants reached the seventh with a cushion, but the late innings changed the whole game shape.',
        observations: [
          'The relievers could not hold the lead.',
          'The starter went deep and set the bullpen up to finish the game.',
        ],
        evidence: [
          'Starter: Landen Roupp, 6.0 IP, 95 pitches',
          'Largest lead: 4',
          'Late runs allowed: 7',
        ],
      },
    },
    selection: {
      rank: 1,
      reason: 'critical_narrative',
      story_priority: 'CRITICAL',
      game_importance: 'HIGH',
      confidence: 'HIGH',
      primary_story: 'lost_game_shape',
      late_runs_allowed: 7,
      swing: 4,
    },
  },
}

const dashboard = {
  freshness: {
    data_through: '2026-06-25',
    last_successful_sync: '2026-06-26T10:04:00Z',
    is_current: true,
    sync_status: 'success',
  },
  what_changed_since_yesterday: {
    capability: 'what_changed_since_yesterday_public_v1',
    items: [
      {
        key: 'SF-what-changed',
        team_id: 137,
        team_name: 'San Francisco Giants',
        team_abbreviation: 'SF',
        public_headline: 'Giants bullpen moved from 4 to 2 rested relievers.',
        public_summary: 'San Francisco has 2 fewer rested relievers than it had yesterday.',
      },
      {
        key: 'NYM-what-changed',
        team_id: 121,
        team_name: 'New York Mets',
        team_abbreviation: 'NYM',
        public_headline: 'Mets bullpen moved from 3 to 5 rested relievers.',
        public_summary: 'New York has 2 more rested relievers than it had yesterday.',
      },
      {
        key: 'MIL-what-changed',
        team_id: 158,
        team_name: 'Milwaukee Brewers',
        team_abbreviation: 'MIL',
        public_headline: 'Brewers bullpen moved from 5 to 3 rested relievers.',
        public_summary: 'Milwaukee has 2 fewer rested relievers than it had yesterday.',
      },
      {
        key: 'TOR-what-changed',
        team_id: 141,
        team_name: 'Toronto Blue Jays',
        team_abbreviation: 'TOR',
        public_headline: 'Blue Jays bullpen moved from 4 to 4 rested relievers.',
        public_summary: 'Toronto still has 4 rested relievers today.',
      },
    ],
  },
}

const tonightOk = {
  status: 'ok',
  reference_date: '2026-06-25',
  card_count: 2,
  empty_reason: null,
  limitations: ['Schedule and bullpen context can still change before first pitch.'],
  cards: [
    {
      key: 'CHC-tonight',
      team_id: 112,
      team_name: 'Chicago Cubs',
      team_abbreviation: 'CHC',
      headline: 'Cubs have a narrow late-game path before first pitch',
      summary: 'Chicago has 2 clean bullpen paths available with another game on the schedule tonight.',
      evidence: [
        'Clean options: 2',
        'Games before next off day: 5',
      ],
      limitations: [],
      signal_family: 'schedule_pressure',
      internal_strength: 87,
      recommendation: 'Do not render this field.',
    },
    {
      key: 'SF-tonight',
      team_id: 137,
      team_name: 'San Francisco Giants',
      team_abbreviation: 'SF',
      headline: 'Giants are thinner than usual behind the first lane',
      summary: 'San Francisco has fewer clean options than a fully open bullpen entering tonight.',
      evidence: [
        'Clean options: 1',
        'On watch: 1',
      ],
      limitations: ['Schedule context can change before lineup lock.'],
      ranking_score: 91,
    },
  ],
}

const tonightEmpty = {
  status: 'empty',
  reference_date: '2026-06-25',
  card_count: 0,
  cards: [],
  empty_reason: 'no_cards_cleared_bar',
  limitations: [],
}

const landscape = {
  capability: 'tonights_bullpen_landscape',
  reference_date: '2026-06-25',
  teams_evaluated: 3,
  games: {
    available: true,
    data_state: 'historical',
    today_count: 0,
    as_of_date: '2026-06-25',
    as_of_count: 5,
    is_today: false,
    message: null,
  },
  constrained_bullpens: [
    { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL', total_relievers: 8, available: 2, monitor: 2, restricted: 4 },
  ],
  available_bullpens: [
    { team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF', total_relievers: 8, available: 6, monitor: 1, restricted: 1 },
  ],
  monitoring_concentration: [
    { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR', total_relievers: 8, available: 3, monitor: 4, restricted: 1 },
  ],
  notes: [],
}

test('getTodayIntelligence calls the Intelligence Surface endpoint', async () => {
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ status: 'empty' }),
    }
  }

  await getTodayIntelligence({ reference_date: '2026-06-25' })

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/bullpen/intelligence/today?reference_date=2026-06-25')
})

test('getTonightIntelligence calls the Tonight Intelligence endpoint', async () => {
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ status: 'empty', cards: [] }),
    }
  }

  await getTonightIntelligence({ reference_date: '2026-06-25' })

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/bullpen/intelligence/tonight?reference_date=2026-06-25')
})

test('lead story view resolves team, prose, evidence, metadata, and snapshot', () => {
  const view = getLeadStoryView(intelligenceOk, teams)

  assert.equal(view.hasStory, true)
  assert.equal(view.team.label, 'San Francisco Giants')
  assert.equal(view.headline, 'Giants bullpen let a four-run lead get away')
  assert.equal(view.observations.length, 2)
  assert.equal(view.evidence.length, 3)
  assert.ok(view.snapshot.includes('Available arms: 3'))
  assert.ok(view.snapshot.includes('Named clean options: Erik Miller'))
  assert.deepEqual(view.metadata.map(item => item.label), [
    'Priority',
    'Confidence',
  ])
})

test('Intelligence Surface shell and lead story skeleton render before data resolves', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligenceLoading: true,
    tonightLoading: true,
    dashboardLoading: true,
    landscapeLoading: true,
    teams: [],
  }))

  assert.ok(htmlIncludes(html, 'What BaseballOS Sees'))
  assert.ok(htmlIncludes(html, 'Today&#x27;s Story'))
  assert.ok(htmlIncludes(html, 'Reading the latest completed-game context...'))
  assert.ok(htmlIncludes(html, 'Loading today'))
  assert.ok(htmlIncludes(html, 'min-h-[28rem]'))
  assert.ok(htmlIncludes(html, 'Tonight'))
  assert.ok(htmlIncludes(html, 'Reading tonight&#x27;s bullpen context...'))
  assert.ok(htmlIncludes(html, 'Today&#x27;s Bullpen Picture'))
  assert.ok(htmlIncludes(html, 'Loading bullpen picture...'))
  assert.ok(htmlIncludes(html, 'href="/bullpen"'))
  assert.equal(htmlIncludes(html, 'No lead bullpen story has cleared the bar yet.'), false)
})

test('Intelligence Surface renders a populated StoryPackage without raw JSON fields', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'What BaseballOS Sees'))
  assert.ok(htmlIncludes(html, 'Every morning BaseballOS watches every bullpen in baseball'))
  assert.ok(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'))
  assert.ok(htmlIncludes(html, 'The Giants reached the seventh with a cushion'))
  assert.ok(htmlIncludes(html, 'Why BaseballOS Sees It'))
  assert.ok(htmlIncludes(html, 'The relievers could not hold the lead.'))
  assert.ok(htmlIncludes(html, 'Starter: Landen Roupp, 6.0 IP, 95 pitches'))
  assert.ok(htmlIncludes(html, 'Bullpen Read'))
  assert.ok(htmlIncludes(html, 'Priority'))
  assert.ok(htmlIncludes(html, 'Confidence'))
  assert.ok(htmlIncludes(html, 'Critical'))
  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Data through Jun 25'))
  assert.ok(htmlIncludes(html, 'Last synced 6:04 AM ET'))
  assert.ok(htmlIncludes(html, 'mt-5 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=SF&amp;source=intelligence-surface"'))
  assert.ok(htmlIncludes(html, 'Tonight'))
  assert.ok(htmlIncludes(html, 'Bullpen situations BaseballOS is watching before first pitch.'))
  assert.ok(htmlIncludes(html, 'Cubs have a narrow late-game path before first pitch'))
  for (const raw of ['lead_story', 'story_priority', 'lost_game_shape', 'public_headline', 'Primary story', 'Why selected']) {
    assert.equal(html.includes(raw), false, raw)
  }
  for (const implementationCopy of ['existing dashboard snapshot', 'existing landscape endpoint', 'internal adapter']) {
    assert.equal(html.includes(implementationCopy), false, implementationCopy)
  }
})

test('empty Intelligence Surface response shows a graceful story fallback', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: {
      status: 'empty',
      lead_story: null,
      empty_reason: 'no_publishable_coin_story',
      candidates_considered: 2,
      publishable_candidates: 0,
    },
    dashboard: {},
    landscape: null,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'No lead bullpen story has cleared the bar yet.'))
  assert.ok(htmlIncludes(html, 'will only surface a lead story when the evidence is strong enough.'))
  assert.ok(htmlIncludes(html, 'No publishable bullpen story is available from the current completed-game context.'))
})

test('Tonight renders endpoint cards without exposing internal fields', () => {
  const cards = getTonightCards(tonightOk, teams)
  assert.equal(cards.length, 2)
  assert.equal(cards[0].href, '/bullpen?view=board&team=CHC&source=intelligence-tonight')

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Tonight'))
  assert.ok(htmlIncludes(html, 'Bullpen situations BaseballOS is watching before first pitch.'))
  assert.ok(htmlIncludes(html, 'Chicago Cubs'))
  assert.ok(htmlIncludes(html, 'Cubs have a narrow late-game path before first pitch'))
  assert.ok(htmlIncludes(html, 'Chicago has 2 clean bullpen paths available with another game on the schedule tonight.'))
  assert.ok(htmlIncludes(html, 'Clean options: 2'))
  assert.ok(htmlIncludes(html, 'Schedule and bullpen context can still change before first pitch.'))
  assert.ok(htmlIncludes(html, 'Schedule context can change before lineup lock.'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=CHC&amp;source=intelligence-tonight"'))
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  for (const raw of ['signal_family', 'schedule_pressure', 'internal_strength', 'ranking_score', 'recommendation', 'Do not render this field.']) {
    assert.equal(html.includes(raw), false, raw)
  }
})

test('Tonight renders only returned cards and does not backfill from Around Baseball', () => {
  const oneCardTonight = {
    ...tonightOk,
    card_count: 1,
    cards: tonightOk.cards.slice(0, 1),
  }

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: oneCardTonight,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Cubs have a narrow late-game path before first pitch'))
  assert.equal(htmlIncludes(html, 'Giants are thinner than usual behind the first lane'), false)
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  assert.equal(htmlIncludes(html, 'New York Mets added 2 rested arms'), false)
  assert.equal(countOccurrences(html, 'source=intelligence-tonight'), 1)
})

test('Tonight empty response falls back to Around Baseball when dashboard observations exist', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Around Baseball'))
  assert.ok(htmlIncludes(html, 'Other bullpen movement BaseballOS is tracking across the league.'))
  assert.ok(htmlIncludes(html, 'New York Mets added 2 rested arms'))
  assert.equal(htmlIncludes(html, 'No Tonight bullpen read has cleared the bar yet.'), false)
})

test('Tonight empty response shows a muted empty state when fallback has no items', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard: {},
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'No Tonight bullpen read has cleared the bar yet.'))
  assert.ok(htmlIncludes(html, 'will only surface a pregame card when schedule context and bullpen evidence are strong enough.'))
  assert.equal(htmlIncludes(html, 'No other league bullpen movement is ready to show yet.'), false)
})

test('Tonight error falls back to Around Baseball when dashboard observations exist', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: null,
    tonightError: 'Tonight unavailable',
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'))
  assert.ok(htmlIncludes(html, 'Around Baseball'))
  assert.ok(htmlIncludes(html, 'Milwaukee Brewers lost 2 rested arms'))
  assert.equal(htmlIncludes(html, 'Tonight&#x27;s bullpen reads are temporarily unavailable.'), false)
})

test('Tonight error shows a graceful error state when fallback also fails', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: null,
    tonightError: 'Tonight unavailable',
    dashboard: null,
    dashboardError: 'Dashboard unavailable',
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'))
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s bullpen reads are temporarily unavailable.'))
  assert.ok(htmlIncludes(html, 'The rest of the Intelligence Surface can still be used.'))
  assert.ok(htmlIncludes(html, 'Most Available'))
})

test('Around Baseball editorializes dashboard observations, excludes the lead team, and caps at three', () => {
  const lead = getLeadStoryView(intelligenceOk, teams)
  const items = getAroundBaseballItems(dashboard, lead)

  assert.deepEqual(items.map(item => item.teamName), [
    'New York Mets',
    'Milwaukee Brewers',
    'Toronto Blue Jays',
  ])
  assert.deepEqual(items.map(item => item.title), [
    'New York Mets added 2 rested arms',
    'Milwaukee Brewers lost 2 rested arms',
    'Toronto Blue Jays held steady',
  ])

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Around Baseball'))
  assert.ok(htmlIncludes(html, 'Other bullpen movement BaseballOS is tracking across the league.'))
  assert.equal(htmlIncludes(html, 'Giants bullpen moved from 4 to 2 rested relievers.'), false)
  assert.equal(htmlIncludes(html, 'Mets bullpen moved from 3 to 5 rested relievers.'), false)
  assert.ok(htmlIncludes(html, 'New York Mets added 2 rested arms'))
  assert.ok(htmlIncludes(html, 'Toronto still has 4 rested relievers today.'))
})

test('Tonight empty state renders when neither Tonight nor fallback observations are available', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard: {},
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'No Tonight bullpen read has cleared the bar yet.'))
  assert.ok(htmlIncludes(html, 'will only surface a pregame card when schedule context and bullpen evidence are strong enough.'))
})

test('fallback dashboard failure does not prevent Today story rendering', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard: null,
    dashboardError: 'Dashboard unavailable',
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'))
  assert.ok(htmlIncludes(html, 'The Giants reached the seventh with a cushion'))
  assert.ok(htmlIncludes(html, 'No Tonight bullpen read has cleared the bar yet.'))
  assert.ok(htmlIncludes(html, 'Most Available'))
})

test('Bullpen Picture failure does not prevent Today story rendering', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape: null,
    landscapeError: 'Landscape unavailable',
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'))
  assert.ok(htmlIncludes(html, 'Why BaseballOS Sees It'))
  assert.ok(htmlIncludes(html, 'No current bullpen read available.'))
  assert.ok(htmlIncludes(html, 'Today&#x27;s bullpen picture is temporarily unavailable.'))
  assert.ok(htmlIncludes(html, 'Cubs have a narrow late-game path before first pitch'))
})

test('Bullpen Picture renders existing landscape lanes and handles missing data', () => {
  const picture = getBullpenPictureView(landscape)
  assert.equal(picture.hasLandscape, true)
  assert.deepEqual(picture.columns.map(column => column.title), [
    'Most Available',
    'Most Constrained',
    'Worth Watching',
  ])

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Today&#x27;s Bullpen Picture'))
  assert.ok(htmlIncludes(html, 'A quick look at which bullpens look rested, constrained, or worth monitoring.'))
  assert.ok(htmlIncludes(html, 'Most Available'))
  assert.ok(htmlIncludes(html, 'Most Constrained'))
  assert.ok(htmlIncludes(html, 'Worth Watching'))
  assert.ok(htmlIncludes(html, 'SF'))
  assert.ok(htmlIncludes(html, 'MIL'))
  assert.ok(htmlIncludes(html, 'TOR'))
  assert.ok(htmlIncludes(html, 'flex-col items-start gap-1'))
  assert.ok(htmlIncludes(html, 'max-w-full break-words font-mono text-xs'))

  const emptyLaneHtml = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape: {
      ...landscape,
      constrained_bullpens: [],
    },
    teams,
  }))
  assert.ok(htmlIncludes(emptyLaneHtml, 'No bullpen currently meets this threshold.'))
  assert.equal(htmlIncludes(emptyLaneHtml, 'No entries in this lane.'), false)

  const emptyHtml = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape: null,
    teams,
  }))
  assert.ok(htmlIncludes(emptyHtml, 'No league bullpen picture is available for the current view.'))
})

test('Explore links render to existing routes', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    dashboard,
    landscape,
    teams,
  }))

  for (const href of [
    'href="/bullpen"',
    'href="/bullpen?view=compare"',
    'href="/trust"',
    'href="/methodology"',
  ]) {
    assert.ok(htmlIncludes(html, href), href)
  }
})
