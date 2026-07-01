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
const clone = (value) => JSON.parse(JSON.stringify(value))

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
  snapshot: {
    served_from: 'snapshot',
    source: 'github_actions',
    generated_at: '2026-06-26T03:30:00',
  },
  limitations: ['Schedule and bullpen context can still change before first pitch.'],
  cards: [
    {
      key: 'CHC-tonight',
      team_id: 112,
      team_name: 'Chicago Cubs',
      team_abbreviation: 'CHC',
      headline: 'Cubs have a narrow late-game path before first pitch',
      summary: 'Chicago has a narrow set of clean bullpen paths with another game on the schedule tonight.',
      pregame_story: {
        story_type: 'pregame_bullpen_watch_v1',
        label: "Tonight's Bullpen Watch",
        headline: 'Narrow bullpen margin before first pitch',
        team_context: "Tonight's schedule has Chicago Cubs at home against Milwaukee Brewers.",
        watching: 'BaseballOS is watching how much usable bullpen margin is left before the next rest day.',
        why_it_matters: 'This matters because clean options are limited with a long stretch before the next off day.',
        key_note: 'Key bullpen note: clean options are limited, with several arms on watch after recent work.',
        watch_point: 'The key question is whether the bridge to the late innings stays manageable without leaning on the same arms again.',
      },
      evidence: [
        'Clean options are limited',
        'Long stretch before the next off day',
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
      pregame_story: {
        story_type: 'pregame_bullpen_watch_v1',
        label: "Tonight's Bullpen Watch",
        headline: 'Late-game path worth monitoring',
        team_context: "Tonight's schedule has San Francisco Giants on the road against Los Angeles Dodgers.",
        watching: 'BaseballOS is watching the late-game path if the game gets tight.',
        why_it_matters: 'This matters because clean late-game margin is limited tonight.',
        key_note: 'Key bullpen note: rested-enough arms include Erik Miller and Ryan Walker.',
        watch_point: 'The key question is how the shortest part of the bullpen handles the first tight inning.',
      },
      evidence: [
        'Clean options are limited',
        'One arm is on watch after recent work',
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
  assert.ok(calls[0].options.signal)
})

test('getTonightIntelligence times out a stuck Tonight request', async () => {
  globalThis.fetch = async (url, options = {}) => {
    assert.equal(url, '/api/bullpen/intelligence/tonight')
    assert.ok(options.signal)
    return new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        const err = new Error('aborted')
        err.name = 'AbortError'
        reject(err)
      })
    })
  }

  await assert.rejects(
    () => getTonightIntelligence({}, { timeoutMs: 5, silent: true }),
    /timed out after 5ms/,
  )
})

test('lead story view resolves team, prose, evidence, metadata, and snapshot', () => {
  const view = getLeadStoryView(intelligenceOk, teams)

  assert.equal(view.hasStory, true)
  assert.equal(view.team.label, 'San Francisco Giants')
  assert.equal(view.headline, 'Giants bullpen let a four-run lead get away')
  assert.equal(view.observations.length, 2)
  assert.equal(view.evidence.length, 3)
  assert.deepEqual(view.limitations, [])
  assert.ok(view.snapshot.includes('Available arms: 3'))
  assert.ok(view.snapshot.includes('Named Clean Options: Erik Miller'))
  assert.deepEqual(view.metadata.map(item => item.label), [
    'Priority',
    'Confidence',
  ])
})

test('lead story view renders payload limitations safely', () => {
  const intelligenceWithLimitations = clone(intelligenceOk)
  intelligenceWithLimitations.lead_story.drafts.team_story.limitations = [
    'Lineup cards and final availability can still change before first pitch.',
    'Backend snapshot detail should not be public.',
  ]

  const view = getLeadStoryView(intelligenceWithLimitations, teams)

  assert.deepEqual(view.limitations, [
    'Lineup cards and final availability can still change before first pitch.',
  ])

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceWithLimitations,
    tonight: tonightOk,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'Lineup cards and final availability can still change before first pitch.'))
  assert.equal(htmlIncludes(html, 'Backend snapshot detail should not be public.'), false)
})

test('Intelligence Surface shell and lead story skeleton render before data resolves', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligenceLoading: true,
    tonightLoading: true,
    dashboardLoading: true,
    landscapeLoading: true,
    teams: [],
  }))

  assert.ok(htmlIncludes(html, 'MLB BULLPEN INTELLIGENCE — UPDATED DAILY'))
  assert.ok(htmlIncludes(html, 'See which bullpens are fresh, stretched, or vulnerable tonight — and why.'))
  assert.ok(htmlIncludes(html, 'Explore today&#x27;s bullpen picture'))
  assert.ok(htmlIncludes(html, 'href="#bullpen-picture"'))
  assert.ok(htmlIncludes(html, 'Get the weekly Bullpen Report'))
  assert.ok(htmlIncludes(html, 'mailto:baseballoshq@gmail.com'))
  assert.ok(htmlIncludes(html, 'Favorite%20team%3A%20'))
  assert.ok(htmlIncludes(html, 'One email a week. No spam, no picks.'))
  assert.equal(htmlIncludes(html, 'mailto:nickoliskacludis@gmail.com'), false)
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

  assert.ok(htmlIncludes(html, 'MLB BULLPEN INTELLIGENCE — UPDATED DAILY'))
  assert.ok(htmlIncludes(html, 'See which bullpens are fresh, stretched, or vulnerable tonight — and why.'))
  assert.ok(htmlIncludes(html, 'BaseballOS reads public MLB usage and workload after every game, so you can tell which pens are gassed and which are loaded — and see the evidence behind each read.'))
  assert.ok(htmlIncludes(html, 'Descriptive only — we show what we see and what we can&#x27;t. No picks, no predictions.'))
  assert.ok(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'))
  assert.ok(htmlIncludes(html, 'The Giants reached the seventh with a cushion'))
  assert.ok(htmlIncludes(html, 'Why BaseballOS Sees It'))
  assert.ok(htmlIncludes(html, 'The relievers could not hold the lead.'))
  assert.ok(htmlIncludes(html, 'Starter: Landen Roupp, 6.0 IP, 95 pitches'))
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'BaseballOS does not know manager intent, bullpen phone activity, private medical availability, or final game-day decisions.'))
  assert.ok(htmlIncludes(html, 'Bullpen Read'))
  assert.ok(htmlIncludes(html, 'Priority'))
  assert.ok(htmlIncludes(html, 'Confidence'))
  assert.ok(htmlIncludes(html, 'Critical'))
  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Tonight watch generated 11:30 PM ET'))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 25'))
  assert.ok(htmlIncludes(html, 'Last synced 6:04 AM ET'))
  assert.ok(htmlIncludes(html, 'mt-5 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=SF&amp;source=intelligence-surface"'))
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Watch'))
  assert.ok(htmlIncludes(html, 'What BaseballOS is watching before first pitch.'))
  assert.ok(htmlIncludes(html, 'Narrow bullpen margin before first pitch'))
  for (const raw of ['lead_story', 'story_priority', 'lost_game_shape', 'public_headline', 'Primary story', 'Why selected']) {
    assert.equal(html.includes(raw), false, raw)
  }
  for (const raw of ['github_actions', 'served_from']) {
    assert.equal(html.includes(raw), false, raw)
  }
  for (const implementationCopy of ['existing dashboard snapshot', 'existing landscape endpoint', 'internal adapter']) {
    assert.equal(html.includes(implementationCopy), false, implementationCopy)
  }
})

test('Tonight generated timestamp treats timezone-less UTC as EDT before labeling ET', () => {
  const summerTonight = clone(tonightOk)
  summerTonight.snapshot.generated_at = '2026-06-29T03:30:00'

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: summerTonight,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Tonight watch generated 11:30 PM ET'))
  assert.equal(htmlIncludes(html, 'Tonight watch generated 3:30 AM ET'), false)
})

test('Tonight generated timestamp treats timezone-less UTC as EST before labeling ET', () => {
  const winterTonight = clone(tonightOk)
  winterTonight.snapshot.generated_at = '2026-12-15T03:30:00'

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: winterTonight,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Tonight watch generated 10:30 PM ET'))
  assert.equal(htmlIncludes(html, 'Tonight watch generated 3:30 AM ET'), false)
})

test('homepage freshness separates Tonight slate from completed-game bullpen data', () => {
  const slateTonight = {
    ...tonightOk,
    reference_date: '2026-06-27',
  }
  const completedDashboard = {
    ...dashboard,
    freshness: {
      ...dashboard.freshness,
      data_through: '2026-06-26',
      last_successful_sync: '2026-06-27T15:04:00Z',
    },
  }
  const completedLandscape = {
    ...landscape,
    reference_date: '2026-06-27',
    games: {
      ...landscape.games,
      as_of_date: '2026-06-26',
    },
  }

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: { ...intelligenceOk, reference_date: '2026-06-26' },
    tonight: slateTonight,
    dashboard: completedDashboard,
    landscape: completedLandscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Tonight slate: Jun 27'))
  assert.ok(htmlIncludes(html, 'Tonight watch generated 11:30 PM ET'))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 26'))
  assert.ok(htmlIncludes(html, 'Last synced 11:04 AM ET'))
  assert.equal(htmlIncludes(html, 'Data through Jun 27'), false)
  assert.equal(htmlIncludes(html, 'Bullpen data through Jun 27'), false)
})

test('Bullpen Picture omits data-through when no trusted completed-game date exists', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: {},
    landscape: {
      ...landscape,
      reference_date: '2026-06-27',
      games: {
        ...landscape.games,
        as_of_date: null,
      },
    },
    teams,
  }))

  const pictureStart = html.indexOf('Today&#x27;s Bullpen Picture')
  const exploreStart = html.indexOf('Explore', pictureStart)
  const pictureHtml = html.slice(pictureStart, exploreStart)

  assert.equal(htmlIncludes(pictureHtml, 'Bullpen data through'), false)
  assert.equal(htmlIncludes(pictureHtml, 'Data through Jun 27'), false)
  assert.equal(htmlIncludes(pictureHtml, 'Invalid Date'), false)
  assert.equal(htmlIncludes(pictureHtml, 'undefined'), false)
  assert.equal(htmlIncludes(pictureHtml, 'null'), false)
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
  assert.equal(cards[0].headline, 'Narrow bullpen margin before first pitch')
  assert.equal(cards[0].summary, 'BaseballOS is watching how much usable bullpen margin is left before the next rest day.')
  assert.equal(cards[0].whyItMatters, 'This matters because Clean Options are limited with a long stretch before the next off day.')
  assert.equal(cards[0].keyNote, 'Key bullpen note: Clean Options are limited, with several arms on watch after recent work.')
  assert.equal(cards[0].watchPoint, 'The key question is whether the bridge to the late innings stays manageable without leaning on the same arms again.')

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Watch'))
  assert.ok(htmlIncludes(html, 'What BaseballOS is watching before first pitch.'))
  assert.ok(htmlIncludes(html, 'Chicago Cubs'))
  assert.ok(htmlIncludes(html, 'Narrow bullpen margin before first pitch'))
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s schedule has Chicago Cubs at home against Milwaukee Brewers.'))
  assert.ok(htmlIncludes(html, 'BaseballOS is watching how much usable bullpen margin is left before the next rest day.'))
  assert.ok(htmlIncludes(html, 'Why It Matters Tonight'))
  assert.ok(htmlIncludes(html, 'This matters because Clean Options are limited with a long stretch before the next off day.'))
  assert.ok(htmlIncludes(html, 'Key Note'))
  assert.ok(htmlIncludes(html, 'Key bullpen note: Clean Options are limited, with several arms on watch after recent work.'))
  assert.ok(htmlIncludes(html, 'Watch Point'))
  assert.ok(htmlIncludes(html, 'The key question is whether the bridge to the late innings stays manageable without leaning on the same arms again.'))
  assert.ok(htmlIncludes(html, 'Clean Options are limited'))
  assert.ok(htmlIncludes(html, 'Schedule and bullpen context can still change before first pitch.'))
  assert.ok(htmlIncludes(html, 'Schedule context can change before lineup lock.'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=CHC&amp;source=intelligence-tonight"'))
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  for (const raw of ['signal_family', 'schedule_pressure', 'internal_strength', 'ranking_score', 'recommendation', 'Do not render this field.', 'fatigue score', 'confidence score']) {
    assert.equal(html.includes(raw), false, raw)
  }
})

test('Tonight qualitative story payload survives the public safety filter', () => {
  const cards = getTonightCards(tonightOk, teams)

  assert.equal(cards.length, 2)
  assert.equal(cards[0].headline, 'Narrow bullpen margin before first pitch')
  assert.equal(cards[0].whyItMatters, 'This matters because Clean Options are limited with a long stretch before the next off day.')
  assert.equal(cards[0].keyNote, 'Key bullpen note: Clean Options are limited, with several arms on watch after recent work.')
  assert.deepEqual(cards[0].evidence, [
    'Clean Options are limited',
    'Long stretch before the next off day',
  ])
})

test('Tonight missing pregame_story exits loading and renders safe legacy fields', () => {
  const legacyTonight = clone(tonightOk)
  legacyTonight.cards = [
    {
      ...legacyTonight.cards[0],
      pregame_story: null,
      headline: 'Bullpen margin worth watching before first pitch',
      summary: 'BaseballOS is watching whether the late-inning bridge stays manageable tonight.',
      evidence: [],
      limitations: [],
    },
  ]
  legacyTonight.card_count = 1

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: legacyTonight,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Bullpen margin worth watching before first pitch'))
  assert.ok(htmlIncludes(html, 'BaseballOS is watching whether the late-inning bridge stays manageable tonight.'))
  assert.equal(htmlIncludes(html, 'Reading tonight&#x27;s bullpen context...'), false)
  assert.equal(htmlIncludes(html, 'No standout bullpen watch point tonight.'), false)
})

test('Tonight story card drops unsafe scoring and prediction copy', () => {
  const unsafeTonight = clone(tonightOk)
  unsafeTonight.cards[0].pregame_story = {
    ...unsafeTonight.cards[0].pregame_story,
    why_it_matters: 'This projection is expected to happen.',
    key_note: 'fatigue score 91 and confidence score high',
    watch_point: 'This will happen late.',
  }

  const cards = getTonightCards(unsafeTonight, teams)
  assert.equal(cards.length, 2)
  assert.equal(cards[0].whyItMatters, null)
  assert.equal(cards[0].keyNote, null)
  assert.equal(cards[0].watchPoint, null)

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: unsafeTonight,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'BaseballOS is watching how much usable bullpen margin is left before the next rest day.'))
  for (const raw of ['fatigue score', 'confidence score', 'projection', 'expected to happen', 'will happen']) {
    assert.equal(new RegExp(escapeRegExp(raw), 'i').test(html), false, raw)
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

  assert.ok(htmlIncludes(html, 'Narrow bullpen margin before first pitch'))
  assert.equal(htmlIncludes(html, 'Late-game path worth monitoring'), false)
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  assert.equal(htmlIncludes(html, 'New York Mets added 2 rested arms'), false)
  assert.equal(countOccurrences(html, 'source=intelligence-tonight'), 1)
})

test('Tonight empty response shows honest empty state when dashboard observations exist', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Watch'))
  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight.'))
  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight based on the latest available usage data.'))
  assert.equal(htmlIncludes(html, 'Reading tonight&#x27;s bullpen context...'), false)
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  assert.equal(htmlIncludes(html, 'New York Mets added 2 rested arms'), false)
})

test('Tonight empty response shows a muted empty state when fallback has no items', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard: {},
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight.'))
  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight based on the latest available usage data.'))
  assert.equal(htmlIncludes(html, 'No other league bullpen movement is ready to show yet.'), false)
})

test('Tonight completed missing payload exits skeleton into empty state', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: null,
    tonightLoading: false,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight.'))
  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight based on the latest available usage data.'))
  assert.equal(htmlIncludes(html, 'Reading tonight&#x27;s bullpen context...'), false)
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
})

test('Tonight live build timeout reason renders unavailable state without fallback cards', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: {
      ...tonightEmpty,
      empty_reason: 'tonight_live_build_timeout',
      limitations: ['Tonight watch is temporarily unavailable.'],
      snapshot: {
        served_from: 'live_build_timeout',
        source: 'on_demand',
        generated_at: '2026-06-26T03:30:00',
      },
    },
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Tonight&#x27;s bullpen reads are temporarily unavailable.'))
  assert.ok(htmlIncludes(html, 'The rest of Today can still be used.'))
  assert.ok(htmlIncludes(html, 'Tonight watch generated 11:30 PM ET'))
  assert.equal(htmlIncludes(html, 'Reading tonight&#x27;s bullpen context...'), false)
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  assert.equal(htmlIncludes(html, 'New York Mets added 2 rested arms'), false)
})

test('Tonight error shows unavailable state when dashboard observations exist', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: null,
    tonightError: 'Tonight unavailable',
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'))
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s bullpen reads are temporarily unavailable.'))
  assert.ok(htmlIncludes(html, 'The rest of Today can still be used.'))
  assert.equal(htmlIncludes(html, 'Reading tonight&#x27;s bullpen context...'), false)
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  assert.equal(htmlIncludes(html, 'Milwaukee Brewers lost 2 rested arms'), false)
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
  assert.ok(htmlIncludes(html, 'The rest of Today can still be used.'))
  assert.ok(htmlIncludes(html, 'Most Available'))
})

test('Around Baseball helper editorializes dashboard observations without replacing Tonight', () => {
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

  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Watch'))
  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight.'))
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  assert.equal(htmlIncludes(html, 'Giants bullpen moved from 4 to 2 rested relievers.'), false)
  assert.equal(htmlIncludes(html, 'Mets bullpen moved from 3 to 5 rested relievers.'), false)
  assert.equal(htmlIncludes(html, 'New York Mets added 2 rested arms'), false)
  assert.equal(htmlIncludes(html, 'Toronto still has 4 rested relievers today.'), false)
})

test('Tonight empty state renders when neither Tonight nor fallback observations are available', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard: {},
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight.'))
  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight based on the latest available usage data.'))
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
  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight.'))
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
  assert.ok(htmlIncludes(html, 'Narrow bullpen margin before first pitch'))
})

test('Bullpen Picture renders existing landscape lanes and handles missing data', () => {
  const picture = getBullpenPictureView(landscape)
  assert.equal(picture.hasLandscape, true)
  assert.deepEqual(picture.columns.map(column => column.title), [
    'Most Available',
    'Most Stretched',
    'On Watch',
  ])

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Today&#x27;s Bullpen Picture'))
  assert.ok(htmlIncludes(html, 'A quick look at which bullpens look rested and available, stretched, or on watch.'))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 25'))
  assert.ok(htmlIncludes(html, 'Most Available'))
  assert.ok(htmlIncludes(html, 'Most Stretched'))
  assert.ok(htmlIncludes(html, 'On Watch'))
  assert.ok(htmlIncludes(html, 'SF'))
  assert.ok(htmlIncludes(html, 'MIL'))
  assert.ok(htmlIncludes(html, 'TOR'))
  assert.ok(htmlIncludes(html, 'flex-col items-start gap-1'))
  assert.ok(htmlIncludes(html, 'max-w-full break-words font-mono text-xs'))
  assert.ok(htmlIncludes(html, 'href="/dashboard"'))
  assert.ok(htmlIncludes(html, 'View full league board'))

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
    'href="/dashboard"',
    'href="/bullpen"',
    'href="/stories"',
    'href="/trust"',
  ]) {
    assert.ok(htmlIncludes(html, href), href)
  }

  assert.ok(htmlIncludes(html, "See every team&#x27;s pen at a glance."))
  assert.ok(htmlIncludes(html, "Open any team&#x27;s bullpen board."))
  assert.ok(htmlIncludes(html, "Read today&#x27;s bullpen storylines."))
  assert.ok(htmlIncludes(html, 'Check freshness and how we know.'))
  assert.equal(countOccurrences(html, 'href="/bullpen"'), 1)
  assert.equal(htmlIncludes(html, 'href="/bullpen?view=compare"'), false)
})

test('Today visible text avoids internal platform terms', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape,
    teams,
  }))

  const visibleText = html
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')

  for (const term of [
    'COIN',
    'V2',
    'V3',
    'V4',
    'deterministic',
    'snapshot',
    'endpoint',
    'backend',
    'recommendation engine',
    'baseline distribution',
    'governance layer',
    'sample state',
  ]) {
    assert.equal(new RegExp(escapeRegExp(term), 'i').test(visibleText), false, term)
  }
})
