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
  resetAnalyticsDedupeForTests()
})

const {
  AUDIENCE_SIGNUP_ERROR,
  AUDIENCE_SIGNUP_IDLE,
  AUDIENCE_SIGNUP_INVALID,
  AUDIENCE_SIGNUP_LOADING,
  AUDIENCE_SIGNUP_SUCCESS,
  AudienceSignupFormView,
  IntelligenceSurfaceView,
  getBullpenPictureView,
  getLeadStoryView,
  getSinceYesterdayView,
  getTonightCards,
  submitAudienceSignup,
  trackSinceYesterdayItemOpened,
  trackSinceYesterdayTeamClicked,
  trackSinceYesterdayViewed,
} = await server.ssrLoadModule('/src/components/home/IntelligenceSurface.jsx')
const { resetAnalyticsDedupeForTests } = await server.ssrLoadModule('/src/utils/analytics.js')
const {
  getTodayIntelligence,
  getTonightIntelligence,
  signupAudience,
} = await server.ssrLoadModule('/src/utils/api.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const countOccurrences = (html, text) => (html.match(new RegExp(escapeRegExp(text), 'g')) || []).length
const clone = (value) => JSON.parse(JSON.stringify(value))
const sectionSlice = (html, startText, endText) => {
  const start = html.indexOf(startText)
  if (start < 0) return ''
  const end = endText ? html.indexOf(endText, start + startText.length) : -1
  return end > start ? html.slice(start, end) : html.slice(start)
}

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

const dashboardWithSinceYesterdayChanges = {
  ...dashboard,
  what_changed_since_yesterday: {
    capability: 'what_changed_since_yesterday_public_v1',
    state: 'changes_detected',
    comparison: {
      comparison_available: true,
      previous_data_through: '2026-06-24',
      current_data_through: '2026-06-25',
    },
    ordering_basis: 'team_abbreviation_then_team_name',
    item_count: 2,
    items: [
      {
        key: 'NYM-what-changed',
        team_id: 121,
        team_name: 'New York Mets',
        team_abbreviation: 'NYM',
        public_headline: 'Mets bullpen has more breathing room today.',
        public_summary: 'New York has more usable late-inning margin than yesterday.',
        public_context: 'That creates more ways through a close game tonight.',
        yesterday_rested_count: 3,
        today_rested_count: 5,
        workload_added: [
          { name: 'Reed Garrett', pitches: 21 },
        ],
        public_evidence: [
          {
            label: 'Resource pool',
            yesterday: 'tight',
            today: 'less tight',
          },
        ],
      },
      {
        key: 'SF-what-changed',
        team_id: 137,
        team_name: 'San Francisco Giants',
        team_abbreviation: 'SF',
        public_headline: 'Giants bullpen has a thinner cushion today.',
        public_summary: 'San Francisco has fewer rested relievers than yesterday.',
        public_context: 'That puts more weight on the middle innings.',
        yesterday_rested_count: 4,
        today_rested_count: 2,
        workload_added: [
          { name: 'Erik Miller', pitches: 18 },
        ],
      },
    ],
  },
}

const dashboardWithSinceYesterdayQuiet = {
  ...dashboard,
  what_changed_since_yesterday: {
    capability: 'what_changed_since_yesterday_public_v1',
    state: 'no_meaningful_changes',
    comparison: {
      comparison_available: true,
      previous_data_through: '2026-06-24',
      current_data_through: '2026-06-25',
    },
    reason_codes: [],
    limitations: [],
    items: [],
    item_count: 0,
  },
}

const dashboardWithSinceYesterdayInsufficient = {
  ...dashboard,
  what_changed_since_yesterday: {
    capability: 'what_changed_since_yesterday_public_v1',
    state: 'insufficient_context',
    comparison: {
      comparison_available: false,
      previous_data_through: '2026-06-24',
      current_data_through: '2026-06-26',
    },
    reason_codes: ['non_adjacent_data_through_dates'],
    limitations: ['Internal audit note should not render.'],
    items: [],
    item_count: 0,
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
        starter_dependency: 'Starters averaged 4.8 innings over the last seven days, requiring 21.0 bullpen innings.',
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

test('signupAudience posts the public audience signup payload', async () => {
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ success: true, message: 'ok' }),
    }
  }

  await signupAudience(' fan@example.com ', { source: 'homepage_hero' })

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/audience/signup')
  assert.equal(calls[0].options.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    email: ' fan@example.com ',
    source: 'homepage_hero',
  })
})

test('audience signup helper rejects invalid email before calling the API', async () => {
  const statuses = []
  let called = false

  const submitted = await submitAudienceSignup({
    email: 'not-an-email',
    signup: async () => {
      called = true
    },
    setStatus: status => statuses.push(status),
  })

  assert.equal(submitted, false)
  assert.equal(called, false)
  assert.deepEqual(statuses, [AUDIENCE_SIGNUP_INVALID])
})

test('audience signup helper handles success, duplicate success, and API failure', async () => {
  const successStatuses = []
  let requestedEmail = null
  const submitted = await submitAudienceSignup({
    email: ' fan@example.com ',
    signup: async (email) => {
      requestedEmail = email
      return { success: true, message: 'ok' }
    },
    setStatus: status => successStatuses.push(status),
  })

  assert.equal(submitted, true)
  assert.equal(requestedEmail, 'fan@example.com')
  assert.deepEqual(successStatuses, [AUDIENCE_SIGNUP_LOADING, AUDIENCE_SIGNUP_SUCCESS])

  const duplicateStatuses = []
  const duplicateSubmitted = await submitAudienceSignup({
    email: 'fan@example.com',
    signup: async () => ({ success: true, message: 'already ok' }),
    setStatus: status => duplicateStatuses.push(status),
  })
  assert.equal(duplicateSubmitted, true)
  assert.deepEqual(duplicateStatuses, [AUDIENCE_SIGNUP_LOADING, AUDIENCE_SIGNUP_SUCCESS])

  const errorStatuses = []
  let capturedError = null
  const failed = await submitAudienceSignup({
    email: 'fan@example.com',
    signup: async () => {
      throw new Error('network')
    },
    setStatus: status => errorStatuses.push(status),
    setError: error => {
      capturedError = error
    },
  })
  assert.equal(failed, false)
  assert.equal(capturedError.message, 'network')
  assert.deepEqual(errorStatuses, [AUDIENCE_SIGNUP_LOADING, AUDIENCE_SIGNUP_ERROR])
})

test('Audience signup form renders loading, invalid, success, and failure states', () => {
  const idleHtml = render(React.createElement(AudienceSignupFormView, {
    email: '',
    status: AUDIENCE_SIGNUP_IDLE,
    onEmailChange: () => {},
    onSubmit: () => {},
  }))
  const loadingHtml = render(React.createElement(AudienceSignupFormView, {
    email: 'fan@example.com',
    status: AUDIENCE_SIGNUP_LOADING,
    onEmailChange: () => {},
    onSubmit: () => {},
  }))
  const invalidHtml = render(React.createElement(AudienceSignupFormView, {
    email: 'bad',
    status: AUDIENCE_SIGNUP_INVALID,
    onEmailChange: () => {},
    onSubmit: () => {},
  }))
  const successHtml = render(React.createElement(AudienceSignupFormView, {
    email: 'fan@example.com',
    status: AUDIENCE_SIGNUP_SUCCESS,
    onEmailChange: () => {},
    onSubmit: () => {},
  }))
  const errorHtml = render(React.createElement(AudienceSignupFormView, {
    email: 'fan@example.com',
    status: AUDIENCE_SIGNUP_ERROR,
    onEmailChange: () => {},
    onSubmit: () => {},
  }))

  assert.ok(htmlIncludes(idleHtml, 'Get BaseballOS bullpen notes in your inbox.'))
  assert.ok(htmlIncludes(idleHtml, 'type="email"'))
  assert.ok(htmlIncludes(idleHtml, 'Get bullpen notes'))
  assert.ok(htmlIncludes(idleHtml, 'No picks. No betting. Just bullpen context and product updates.'))
  assert.ok(htmlIncludes(loadingHtml, 'Joining...'))
  assert.ok(/<button[^>]*disabled/.test(loadingHtml))
  assert.ok(htmlIncludes(invalidHtml, 'aria-invalid="true"'))
  assert.ok(htmlIncludes(invalidHtml, 'Enter a valid email address.'))
  assert.ok(htmlIncludes(successHtml, 'You are on the list for BaseballOS bullpen notes.'))
  assert.ok(htmlIncludes(errorHtml, 'We could not save that signup. Please try again.'))
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

test('lead story view resolves payload limitations safely', () => {
  const intelligenceWithLimitations = clone(intelligenceOk)
  intelligenceWithLimitations.lead_story.drafts.team_story.limitations = [
    'Lineup cards and final availability can still change before first pitch.',
    'Backend snapshot detail should not be public.',
  ]

  const view = getLeadStoryView(intelligenceWithLimitations, teams)

  assert.deepEqual(view.limitations, [
    'Lineup cards and final availability can still change before first pitch.',
  ])
})

test('Intelligence Surface shell renders before data resolves', () => {
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
  assert.ok(htmlIncludes(html, 'Get BaseballOS bullpen notes in your inbox.'))
  assert.ok(htmlIncludes(html, 'type="email"'))
  assert.ok(htmlIncludes(html, 'Get bullpen notes'))
  assert.ok(htmlIncludes(html, 'No picks. No betting. Just bullpen context and product updates.'))
  assert.equal(htmlIncludes(html, 'mailto:baseballoshq@gmail.com'), false)
  assert.equal(htmlIncludes(html, 'mailto:nickoliskacludis@gmail.com'), false)
  assert.equal(htmlIncludes(html, 'Upcoming Games'), false)
  assert.equal(htmlIncludes(html, 'Today&#x27;s Story'), false)
  assert.equal(htmlIncludes(html, 'Reading the latest completed-game context...'), false)
  assert.equal(htmlIncludes(html, 'Loading today'), false)
  assert.equal(htmlIncludes(html, 'min-h-[28rem]'), false)
  assert.ok(htmlIncludes(html, 'Tonight'))
  assert.ok(htmlIncludes(html, 'Reading tonight&#x27;s bullpen context...'))
  assert.ok(htmlIncludes(html, 'Today&#x27;s Bullpen Picture'))
  assert.ok(htmlIncludes(html, 'Loading bullpen picture...'))
  assert.equal(htmlIncludes(html, 'href="/bullpen"'), false)
  assert.equal(htmlIncludes(html, 'No lead bullpen story has cleared the bar yet.'), false)
})

test('homepage sections introduce the bullpen picture before Tonight watch', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardWithSinceYesterdayChanges,
    landscape,
    teams,
  }))

  const orderedSections = [
    'See which bullpens are fresh, stretched, or vulnerable tonight — and why.',
    'Today&#x27;s Bullpen Picture',
    'SINCE YESTERDAY',
    'What changed across MLB bullpens',
    'Tonight&#x27;s Bullpen Watch',
    'Learn &amp; Explore BaseballOS',
  ]
  let previousIndex = -1
  for (const section of orderedSections) {
    const index = html.indexOf(section)
    assert.ok(index > previousIndex, section)
    previousIndex = index
  }
})

test('Since Yesterday renders changes in stored order with public copy and team links', () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayChanges, teams)
  assert.equal(view.state, 'changes_detected')
  assert.equal(view.comparisonAvailable, true)
  assert.deepEqual(view.items.map(item => item.teamAbbr), ['NYM', 'SF'])
  assert.deepEqual(view.items[0].publicEvidence, [
    {
      key: 'Resource pool-tight-less tight-0',
      label: 'Resource pool',
      yesterday: 'tight',
      today: 'less tight',
    },
  ])
  assert.equal(view.footerCopy, 'Teams are listed alphabetically. 2 teams show meaningful, evidence-backed movement in this daily comparison.')

  const sourceOrderedDashboard = clone(dashboardWithSinceYesterdayChanges)
  sourceOrderedDashboard.what_changed_since_yesterday.ordering_basis = 'stored_payload_order'
  sourceOrderedDashboard.what_changed_since_yesterday.items.reverse()
  const sourceOrderView = getSinceYesterdayView(sourceOrderedDashboard, teams)
  assert.deepEqual(sourceOrderView.items.map(item => item.teamAbbr), ['SF', 'NYM'])
  assert.equal(sourceOrderView.footerCopy, '2 teams show meaningful, evidence-backed movement in this daily comparison.')

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardWithSinceYesterdayChanges,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')

  assert.ok(htmlIncludes(sinceHtml, 'What changed across MLB bullpens'))
  assert.ok(htmlIncludes(sinceHtml, 'Comparing complete, adjacent daily views only. Movement is descriptive, not predictive.'))
  assert.ok(htmlIncludes(sinceHtml, 'Previous view Jun 24'))
  assert.ok(htmlIncludes(sinceHtml, 'Current view Jun 25'))
  assert.ok(htmlIncludes(sinceHtml, 'Mets bullpen has more breathing room today.'))
  assert.ok(htmlIncludes(sinceHtml, 'New York has more usable late-inning margin than yesterday.'))
  assert.ok(htmlIncludes(sinceHtml, 'That creates more ways through a close game tonight.'))
  assert.ok(htmlIncludes(sinceHtml, 'Evidence shown'))
  assert.ok(htmlIncludes(sinceHtml, 'Resource pool'))
  assert.ok(htmlIncludes(sinceHtml, 'Yesterday tight'))
  assert.ok(htmlIncludes(sinceHtml, 'Today less tight'))
  assert.ok(htmlIncludes(sinceHtml, 'Giants bullpen has a thinner cushion today.'))
  assert.ok(htmlIncludes(sinceHtml, 'Reed Garrett'))
  assert.ok(htmlIncludes(sinceHtml, '21 pitches'))
  assert.ok(htmlIncludes(sinceHtml, 'Yesterday'))
  assert.ok(htmlIncludes(sinceHtml, 'Today'))
  assert.ok(htmlIncludes(sinceHtml, 'href="/bullpen?view=board&amp;team=NYM&amp;source=since-yesterday"'))
  assert.ok(htmlIncludes(sinceHtml, 'href="/bullpen?view=board&amp;team=SF&amp;source=since-yesterday"'))
  assert.equal(countOccurrences(sinceHtml, '<details'), 2)
  assert.equal(countOccurrences(sinceHtml, '<summary'), 2)
  assert.equal(/<details[^>]*\sopen(?:=|>|\s)/i.test(sinceHtml), false)
  assert.equal(htmlIncludes(sinceHtml, 'what_changed_item_opened'), false)
})

test('Since Yesterday analytics emit only the approved events and fields', async () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayChanges, teams)
  const calls = []
  const send = async payload => calls.push(payload)

  assert.equal(await trackSinceYesterdayViewed(view, { send }), true)
  assert.equal(await trackSinceYesterdayViewed(view, { send }), false)
  assert.equal(await trackSinceYesterdayItemOpened(view.items[0], { send }), true)
  assert.equal(await trackSinceYesterdayTeamClicked(view.items[1], { send }), true)

  assert.deepEqual(calls, [
    {
      event_name: 'what_changed_viewed',
      surface: 'home',
      route: '/',
      source: 'since_yesterday',
      state: 'changes_detected',
    },
    {
      event_name: 'what_changed_item_opened',
      surface: 'home',
      route: '/',
      source: 'since_yesterday',
      team_abbrev: 'NYM',
      team_id: 121,
    },
    {
      event_name: 'what_changed_team_clicked',
      surface: 'home',
      route: '/',
      source: 'since_yesterday',
      team_abbrev: 'SF',
      team_id: 137,
    },
  ])
})

test('Since Yesterday renders quiet comparable days without empty cards', async () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayQuiet, teams)
  assert.equal(view.state, 'no_meaningful_changes')
  assert.equal(view.comparisonAvailable, true)
  assert.deepEqual(view.items, [])
  assert.equal(view.itemCount, 0)
  assert.equal(view.quietCopy, 'No meaningful bullpen movement was found between Jun 24 and Jun 25. Quiet days are reported as quiet — nothing is padded.')

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardWithSinceYesterdayQuiet,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')
  assert.ok(htmlIncludes(sinceHtml, 'No meaningful bullpen movement was found between Jun 24 and Jun 25. Quiet days are reported as quiet — nothing is padded.'))
  assert.equal(countOccurrences(sinceHtml, '<details'), 0)

  const calls = []
  assert.equal(await trackSinceYesterdayViewed(view, { send: async payload => calls.push(payload) }), true)
  assert.deepEqual(calls.map(call => call.state), ['no_meaningful_changes'])
})

test('Since Yesterday renders withheld comparison safely without raw reason codes', async () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayInsufficient, teams)
  assert.equal(view.state, 'insufficient_context')
  assert.equal(view.comparisonAvailable, false)
  assert.deepEqual(view.items, [])

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardWithSinceYesterdayInsufficient,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')
  assert.ok(htmlIncludes(sinceHtml, 'Since-yesterday movement is unavailable because the two daily views could not be compared safely. BaseballOS only compares complete, adjacent days.'))
  assert.equal(htmlIncludes(sinceHtml, 'non_adjacent_data_through_dates'), false)
  assert.equal(htmlIncludes(sinceHtml, 'Internal audit note should not render.'), false)
  assert.equal(countOccurrences(sinceHtml, '<details'), 0)

  const calls = []
  assert.equal(await trackSinceYesterdayViewed(view, { send: async payload => calls.push(payload) }), true)
  assert.deepEqual(calls.map(call => call.state), ['insufficient_context'])
})

test('Since Yesterday hides legacy, missing, and fail-closed dashboard blocks', async () => {
  const legacyView = getSinceYesterdayView(dashboard, teams)
  const missingView = getSinceYesterdayView({ freshness: dashboard.freshness }, teams)
  const failClosedView = getSinceYesterdayView({
    status: 'error',
    what_changed_since_yesterday: dashboardWithSinceYesterdayChanges.what_changed_since_yesterday,
  }, teams)

  assert.equal(legacyView, null)
  assert.equal(missingView, null)
  assert.equal(failClosedView, null)

  for (const currentDashboard of [dashboard, { freshness: dashboard.freshness }]) {
    const html = render(React.createElement(IntelligenceSurfaceView, {
      intelligence: intelligenceOk,
      tonight: tonightOk,
      dashboard: currentDashboard,
      landscape,
      teams,
    }))
    assert.equal(htmlIncludes(html, 'SINCE YESTERDAY'), false)
    assert.equal(htmlIncludes(html, 'What changed across MLB bullpens'), false)
  }

  const calls = []
  assert.equal(await trackSinceYesterdayViewed(legacyView, { send: async payload => calls.push(payload) }), false)
  assert.deepEqual(calls, [])
})

test('Since Yesterday markup stays semantic, single-column, and free of internal fields', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardWithSinceYesterdayChanges,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')
  const visibleText = sinceHtml
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')

  assert.ok(htmlIncludes(sinceHtml, 'grid grid-cols-1'))
  assert.ok(htmlIncludes(sinceHtml, '<details'))
  assert.ok(htmlIncludes(sinceHtml, '<summary'))
  for (const raw of [
    'snapshot',
    'backend',
    'deterministic',
    'audit',
    'reason code',
    'engine',
    'reason_codes',
    'item_count',
    'public_headline',
    'ranking',
    'score',
    'projection',
    'prediction',
    'recommendation',
  ]) {
    assert.equal(new RegExp(escapeRegExp(raw), 'i').test(visibleText), false, raw)
  }
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
  assert.ok(htmlIncludes(html, 'BaseballOS reads public MLB usage and workload after every game, so you can tell which pens are gassed and which are loaded — with the data date and confidence always shown.'))
  assert.equal(htmlIncludes(html, 'see the evidence behind each read'), false)
  assert.ok(htmlIncludes(html, 'Descriptive only — we show what we see and what we can&#x27;t. No picks, no predictions.'))
  assert.equal(htmlIncludes(html, 'Upcoming Games'), false)
  assert.equal(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'), false)
  assert.equal(htmlIncludes(html, 'The Giants reached the seventh with a cushion'), false)
  assert.equal(htmlIncludes(html, 'Why BaseballOS Sees It'), false)
  assert.equal(htmlIncludes(html, 'The relievers could not hold the lead.'), false)
  assert.equal(htmlIncludes(html, 'Starter: Landen Roupp, 6.0 IP, 95 pitches'), false)
  assert.ok(htmlIncludes(html, 'Published view current'))
  assert.equal(htmlIncludes(html, 'Freshness: Current'), false)
  assert.ok(htmlIncludes(html, 'Tonight watch generated 11:30 PM ET'))
  assert.ok(htmlIncludes(html, 'Published view through Jun 25'))
  assert.ok(htmlIncludes(html, 'Last synced 6:04 AM ET'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=SF&amp;source=landscape"'))
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
  assert.ok(htmlIncludes(html, 'Published view through Jun 26'))
  assert.ok(htmlIncludes(html, 'Last synced 11:04 AM ET'))
  assert.equal(htmlIncludes(html, 'Data through Jun 27'), false)
  assert.equal(htmlIncludes(html, 'Published view through Jun 27'), false)
})

test('sample Today intelligence is not rendered as a current homepage story', () => {
  const sampleIntelligence = {
    ...intelligenceOk,
    freshness: {
      freshness_state: 'sample',
      sample: true,
      data_through: '2026-06-24',
    },
  }

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: sampleIntelligence,
    teams,
  }))

  assert.equal(htmlIncludes(html, 'Sample intelligence state'), false)
  assert.equal(htmlIncludes(html, 'Not live MLB data.'), false)
  assert.equal(htmlIncludes(html, 'Freshness: Current'), false)
})

test('stale homepage freshness does not imply current live data', () => {
  const staleDashboard = {
    ...dashboard,
    freshness: {
      ...dashboard.freshness,
      freshness_state: 'stale',
      is_current: false,
      is_stale: true,
    },
  }

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    dashboard: staleDashboard,
    landscape,
    teams,
  }))
  const pictureHtml = sectionSlice(html, 'Today&#x27;s Bullpen Picture', 'Tonight&#x27;s Bullpen Watch')

  assert.ok(htmlIncludes(pictureHtml, 'Refresh delayed'))
  assert.equal(htmlIncludes(pictureHtml, 'Freshness: Current'), false)
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
  const exploreStart = html.indexOf('Tonight&#x27;s Bullpen Watch', pictureStart)
  const pictureHtml = html.slice(pictureStart, exploreStart)

  assert.equal(htmlIncludes(pictureHtml, 'Bullpen data through'), false)
  assert.equal(htmlIncludes(pictureHtml, 'Data through Jun 27'), false)
  assert.equal(htmlIncludes(pictureHtml, 'Invalid Date'), false)
  assert.equal(htmlIncludes(pictureHtml, 'undefined'), false)
  assert.equal(htmlIncludes(pictureHtml, 'null'), false)
})

test('empty Intelligence Surface response does not render a homepage story fallback', () => {
  const view = getLeadStoryView({
    status: 'empty',
    lead_story: null,
    empty_reason: 'no_publishable_coin_story',
    candidates_considered: 2,
    publishable_candidates: 0,
  }, teams)
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

  assert.equal(view.hasStory, false)
  assert.equal(htmlIncludes(html, 'No lead bullpen story has cleared the bar yet.'), false)
  assert.equal(htmlIncludes(html, 'will only surface a lead story when the evidence is strong enough.'), false)
  assert.equal(htmlIncludes(html, 'No publishable bullpen story is available from the current completed-game context.'), false)
})

test('Tonight renders endpoint cards without exposing internal fields', () => {
  const cards = getTonightCards(tonightOk, teams)
  assert.equal(cards.length, 2)
  assert.equal(cards[0].href, '/bullpen?view=board&team=CHC&source=intelligence-tonight')
  assert.equal(cards[0].headline, 'Narrow bullpen margin before first pitch')
  assert.equal(cards[0].summary, 'BaseballOS is watching how much usable bullpen margin is left before the next rest day.')
  assert.equal(cards[0].whyItMatters, 'This matters because Clean Options are limited with a long stretch before the next off day.')
  assert.equal(cards[0].keyNote, 'Key bullpen note: Clean Options are limited, with several arms on watch after recent work.')
  assert.equal(cards[0].starterDependency, 'Starter-length context lives on the team board with recent completed-game detail.')
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
  assert.ok(htmlIncludes(html, 'Starter Length'))
  assert.ok(htmlIncludes(html, 'Starter-length context lives on the team board with recent completed-game detail.'))
  assert.equal(htmlIncludes(html, 'Starters averaged 4.8 innings over the last seven days'), false)
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
  assert.ok(htmlIncludes(html, 'Games are on tonight&#x27;s slate, but no bullpen situation cleared the BaseballOS publication standard.'))
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
  assert.ok(htmlIncludes(html, 'Games are on tonight&#x27;s slate, but no bullpen situation cleared the BaseballOS publication standard.'))
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
  assert.ok(htmlIncludes(html, 'Games are on tonight&#x27;s slate, but no bullpen situation cleared the BaseballOS publication standard.'))
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
  const tonightHtml = sectionSlice(html, 'Tonight&#x27;s Bullpen Watch', 'Learn &amp; Explore BaseballOS')

  assert.ok(htmlIncludes(html, 'Tonight&#x27;s bullpen reads are temporarily unavailable.'))
  assert.ok(htmlIncludes(html, 'The rest of Today can still be used.'))
  assert.ok(htmlIncludes(html, 'Tonight watch generated 11:30 PM ET'))
  assert.ok(htmlIncludes(tonightHtml, 'Tonight slate unavailable'))
  assert.equal(htmlIncludes(tonightHtml, 'Refresh delayed'), false)
  assert.equal(htmlIncludes(tonightHtml, 'Freshness: Current'), false)
  assert.equal(htmlIncludes(html, 'Reading tonight&#x27;s bullpen context...'), false)
  assert.equal(htmlIncludes(html, 'Around Baseball'), false)
  assert.equal(htmlIncludes(html, 'New York Mets added 2 rested arms'), false)
})

test('live publishable dashboard freshness keeps Today current while Tonight is unavailable', () => {
  const liveDashboard = clone(dashboard)
  liveDashboard.freshness = {
    data_through: '2026-07-05',
    latest_workload_date: '2026-07-05',
    last_successful_sync: '2026-07-06T04:34:36Z',
    sync_status: 'success',
    complete_enough_to_publish: true,
    validations_passed: true,
    is_current: false,
    is_stale: false,
    freshness_state: 'incomplete',
    label: 'Baseball data through 2026-07-05 is incomplete and is not publishable as current.',
    limitations: ['Slate coverage validations did not pass.'],
    slate_coverage: {
      complete_enough_to_publish: true,
      validations_passed: true,
      games_final: 15,
      games_fully_ingested: 15,
    },
  }
  const liveLandscape = clone(landscape)
  liveLandscape.games.as_of_date = null
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: {
      ...tonightEmpty,
      reference_date: '2026-07-06',
      empty_reason: 'tonight_live_build_timeout',
      snapshot: {
        served_from: 'live_build_timeout',
        source: 'on_demand',
        generated_at: '2026-07-06T05:24:49',
      },
    },
    dashboard: liveDashboard,
    landscape: liveLandscape,
    teams,
  }))
  const tonightHtml = sectionSlice(html, 'Tonight&#x27;s Bullpen Watch', 'Learn &amp; Explore BaseballOS')

  assert.ok(htmlIncludes(html, 'Published view current'))
  assert.ok(htmlIncludes(html, 'Published view through Jul 5'))
  assert.ok(htmlIncludes(tonightHtml, 'Tonight slate unavailable'))
  assert.equal(htmlIncludes(html, 'Sample data'), false)
  assert.equal(htmlIncludes(html, 'incomplete and is not publishable'), false)
  assert.equal(htmlIncludes(tonightHtml, 'Refresh delayed'), false)
})

test('Bullpen Picture uses current published freshness when landscape freshness is incomplete', () => {
  const liveDashboard = clone(dashboard)
  liveDashboard.freshness = {
    data_through: '2026-07-05',
    latest_workload_date: '2026-07-05',
    last_successful_sync: '2026-07-06T04:34:36Z',
    sync_status: 'success',
    complete_enough_to_publish: true,
    validations_passed: true,
    is_current: false,
    is_stale: false,
    freshness_state: 'incomplete',
    label: 'Baseball data through 2026-07-05 is incomplete and is not publishable as current.',
    limitations: ['Slate coverage validations did not pass.'],
    slate_coverage: {
      complete_enough_to_publish: true,
      validations_passed: true,
      games_final: 15,
      games_fully_ingested: 15,
    },
  }
  const incompleteLandscape = clone(landscape)
  incompleteLandscape.reference_date = '2026-07-06'
  incompleteLandscape.games = {
    ...incompleteLandscape.games,
    as_of_date: '2026-07-05',
    as_of_count: 15,
    data_state: 'historical',
    is_today: false,
    today_count: 0,
  }
  incompleteLandscape.freshness = {
    data_through: '2026-07-05',
    latest_workload_date: '2026-07-05',
    last_successful_sync: '2026-07-06T04:34:36Z',
    sync_status: 'success',
    complete_enough_to_publish: false,
    validations_passed: false,
    is_current: false,
    is_stale: false,
    freshness_state: 'incomplete',
    label: 'Baseball data through 2026-07-05 is incomplete and is not publishable as current.',
    limitations: ['Slate coverage validations did not pass.'],
    slate_coverage: {
      complete_enough_to_publish: false,
      validations_passed: false,
      games_final: 14,
      games_fully_ingested: 14,
      games_included: 15,
      games_incomplete: 1,
    },
  }

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: liveDashboard,
    landscape: incompleteLandscape,
    teams,
  }))
  const pictureHtml = sectionSlice(html, 'Today&#x27;s Bullpen Picture', 'Tonight&#x27;s Bullpen Watch')

  assert.ok(htmlIncludes(pictureHtml, 'Published view current'))
  assert.ok(htmlIncludes(pictureHtml, 'Published view through Jul 5'))
  assert.ok(htmlIncludes(pictureHtml, 'Last synced 12:34 AM ET'))
  assert.equal(htmlIncludes(pictureHtml, 'Refresh delayed'), false)
})

test('Tonight fail-closed payload scopes stale chip to the slate when published view is current', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: {
      status: 'error',
      reference_date: '2026-06-26',
      cards: [],
      limitations: ['Tonight watch is temporarily unavailable.'],
      snapshot: {
        generated_at: '2026-06-26T03:30:00',
      },
    },
    dashboard,
    landscape,
    teams,
  }))
  const tonightHtml = sectionSlice(html, 'Tonight&#x27;s Bullpen Watch', 'Learn &amp; Explore BaseballOS')

  assert.ok(htmlIncludes(tonightHtml, 'Tonight slate unavailable'))
  assert.ok(htmlIncludes(tonightHtml, 'Published view through Jun 25'))
  assert.ok(htmlIncludes(tonightHtml, 'Last synced 6:04 AM ET'))
  assert.equal(htmlIncludes(tonightHtml, 'Refresh delayed'), false)
})

test('Tonight unavailable keeps generic stale copy when published bullpen view is stale', () => {
  const staleDashboard = {
    ...dashboard,
    freshness: {
      ...dashboard.freshness,
      freshness_state: 'stale',
      is_current: false,
      is_stale: true,
    },
  }
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: {
      status: 'error',
      reference_date: '2026-06-26',
      cards: [],
      snapshot: {
        generated_at: '2026-06-26T03:30:00',
      },
    },
    dashboard: staleDashboard,
    landscape,
    teams,
  }))
  const tonightHtml = sectionSlice(html, 'Tonight&#x27;s Bullpen Watch', 'Learn &amp; Explore BaseballOS')

  assert.ok(htmlIncludes(tonightHtml, 'Refresh delayed'))
  assert.equal(htmlIncludes(tonightHtml, 'Tonight slate unavailable'), false)
  assert.equal(htmlIncludes(tonightHtml, 'Freshness: Current'), false)
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

  assert.equal(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'), false)
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

  assert.equal(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'), false)
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s bullpen reads are temporarily unavailable.'))
  assert.ok(htmlIncludes(html, 'The rest of Today can still be used.'))
  assert.ok(htmlIncludes(html, 'Most Available'))
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
  assert.ok(htmlIncludes(html, 'Games are on tonight&#x27;s slate, but no bullpen situation cleared the BaseballOS publication standard.'))
})

test('fallback dashboard failure does not prevent Today sections rendering', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightEmpty,
    dashboard: null,
    dashboardError: 'Dashboard unavailable',
    landscape,
    teams,
  }))

  assert.equal(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'), false)
  assert.equal(htmlIncludes(html, 'The Giants reached the seventh with a cushion'), false)
  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight.'))
  assert.ok(htmlIncludes(html, 'Most Available'))
})

test('Bullpen Picture failure does not prevent Today page rendering', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape: null,
    landscapeError: 'Landscape unavailable',
    teams,
  }))

  assert.equal(htmlIncludes(html, 'Giants bullpen let a four-run lead get away'), false)
  assert.equal(htmlIncludes(html, 'Why BaseballOS Sees It'), false)
  assert.ok(htmlIncludes(html, 'No current bullpen read available.'))
  assert.ok(htmlIncludes(html, 'Today&#x27;s bullpen picture is temporarily unavailable.'))
  assert.ok(htmlIncludes(html, 'Narrow bullpen margin before first pitch'))
})

test('Bullpen Picture renders existing landscape lanes and handles missing data', () => {
  const picture = getBullpenPictureView(landscape)
  assert.equal(picture.hasLandscape, true)
  assert.deepEqual(picture.columns.map(column => column.title), [
    'Most Available',
    'On Watch',
    'Most Stretched',
  ])
  assert.equal(picture.columns.find(column => column.title === 'Most Stretched')?.entries[0]?.restricted, 4)
  // Teaser view-model: one standout team per lane plus an overflow count.
  assert.equal(picture.columns.find(column => column.title === 'Most Stretched')?.lead?.restricted, 4)
  assert.equal(picture.columns.every(column => column.moreCount === 0), true)

  const crowdedPicture = getBullpenPictureView({
    ...landscape,
    available_bullpens: [
      ...landscape.available_bullpens,
      { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM', total_relievers: 8, available: 5, monitor: 2, restricted: 1 },
    ],
  })
  const availableLane = crowdedPicture.columns.find(column => column.title === 'Most Available')
  assert.equal(availableLane?.lead?.teamAbbrev, 'SF')
  assert.equal(availableLane?.moreCount, 1)

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Today&#x27;s Bullpen Picture'))
  assert.ok(htmlIncludes(html, 'A quick look at which bullpens look rested and available, stretched, or on watch.'))
  assert.ok(htmlIncludes(html, 'Published view through Jun 25'))
  assert.ok(htmlIncludes(html, 'Most Available'))
  assert.ok(htmlIncludes(html, 'Most Stretched'))
  assert.ok(htmlIncludes(html, 'On Watch'))
  assert.ok(htmlIncludes(html, 'SF'))
  assert.ok(htmlIncludes(html, 'MIL'))
  assert.ok(htmlIncludes(html, 'TOR'))
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
  assert.ok(htmlIncludes(emptyLaneHtml, 'No bullpen currently shows enough stretched workload to stand out.'))
  assert.equal(htmlIncludes(emptyLaneHtml, 'No bullpen currently meets this threshold.'), false)
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

  assert.ok(htmlIncludes(html, 'Learn &amp; Explore'))
  assert.ok(htmlIncludes(html, 'Learn &amp; Explore BaseballOS'))
  assert.ok(htmlIncludes(html, 'Get to know BaseballOS, then dig into every bullpen.'))

  for (const href of [
    'href="/about"',
    'href="/how-to-read"',
    'href="/methodology"',
    'href="/trust"',
  ]) {
    assert.ok(htmlIncludes(html, href), href)
  }

  assert.ok(htmlIncludes(html, 'About BaseballOS'))
  assert.ok(htmlIncludes(html, 'Why BaseballOS exists, in a minute.'))
  assert.ok(htmlIncludes(html, 'How to Read BaseballOS'))
  assert.ok(htmlIncludes(html, 'Learn every term in one line each.'))
  assert.ok(htmlIncludes(html, 'See how each read is built.'))
  assert.ok(htmlIncludes(html, 'Check freshness and how we know.'))

  const exploreHtml = sectionSlice(html, 'Learn &amp; Explore BaseballOS')
  const orderedTitles = [
    'About BaseballOS',
    'How to Read BaseballOS',
    'Methodology',
    'Data &amp; Trust',
  ]
  let previousIndex = -1
  for (const title of orderedTitles) {
    const index = exploreHtml.indexOf(title)
    assert.ok(index > previousIndex, title)
    previousIndex = index
  }
  for (const removedTitle of ['Dashboard', 'Bullpen', 'Stories']) {
    assert.equal(htmlIncludes(exploreHtml, removedTitle), false, removedTitle)
  }
  assert.equal(htmlIncludes(exploreHtml, 'href="/dashboard"'), false)
  assert.equal(htmlIncludes(exploreHtml, 'href="/bullpen"'), false)
  assert.equal(htmlIncludes(exploreHtml, 'href="/stories"'), false)

  assert.equal(countOccurrences(html, 'href="/bullpen"'), 0)
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

test('Tonight verified off-day slate renders a deliberate league pause, not an empty analysis', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: {
      status: 'empty',
      reference_date: '2026-07-13',
      card_count: 0,
      cards: [],
      empty_reason: 'no_teams_playing_today',
      limitations: [],
    },
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'No MLB games scheduled tonight.'))
  assert.ok(htmlIncludes(html, 'A league off-day. Bullpen Watch returns with the next MLB game slate.'))
  // A verified empty slate is never presented as an analyzed-but-quiet slate,
  // a missing-data problem, or an error.
  assert.equal(htmlIncludes(html, 'No standout bullpen watch point tonight.'), false)
  assert.equal(htmlIncludes(html, 'Tonight&#x27;s schedule view is unavailable.'), false)
  assert.equal(htmlIncludes(html, 'Tonight&#x27;s bullpen reads are temporarily unavailable.'), false)
})

test('Tonight unverified schedule fails closed as a limited read, never as an off-day', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: {
      status: 'empty',
      reference_date: '2026-07-13',
      card_count: 0,
      cards: [],
      empty_reason: 'no_schedule_context',
      limitations: [],
    },
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'Tonight&#x27;s schedule view is unavailable.'))
  assert.ok(htmlIncludes(html, 'BaseballOS could not verify tonight&#x27;s MLB schedule, so Bullpen Watch is holding its read instead of guessing.'))
  assert.equal(htmlIncludes(html, 'No MLB games scheduled tonight.'), false)
  assert.equal(htmlIncludes(html, 'No standout bullpen watch point tonight.'), false)
})

test('Tonight no-signal slate keeps the standout copy and says games exist', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: {
      status: 'empty',
      reference_date: '2026-07-17',
      card_count: 0,
      cards: [],
      empty_reason: 'no_tonight_signals',
      limitations: [],
    },
    dashboard,
    landscape,
    teams,
  }))

  assert.ok(htmlIncludes(html, 'No standout bullpen watch point tonight.'))
  assert.ok(htmlIncludes(html, 'Games are on tonight&#x27;s slate, but no bullpen situation cleared the BaseballOS publication standard.'))
  assert.equal(htmlIncludes(html, 'No MLB games scheduled tonight.'), false)
})

test('Since Yesterday snapshot-chain gap explains the wait for two consecutive views', () => {
  const dashboardWaiting = {
    ...dashboard,
    what_changed_since_yesterday: {
      capability: 'what_changed_since_yesterday_public_v1',
      state: 'insufficient_context',
      comparison: {
        comparison_available: false,
        previous_data_through: null,
        current_data_through: '2026-07-12',
        reason_codes: ['no_prior_snapshot', 'comparison_withheld'],
      },
      reason_codes: ['no_prior_snapshot', 'comparison_withheld'],
      limitations: [],
      items: [],
      item_count: 0,
    },
  }
  const view = getSinceYesterdayView(dashboardWaiting, teams)
  assert.equal(view.state, 'insufficient_context')

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardWaiting,
    landscape,
    teams,
  }))
  assert.ok(htmlIncludes(html, 'Movement comparison is paused while BaseballOS waits for two consecutive complete daily views.'))
  assert.ok(htmlIncludes(html, 'It resumes automatically when two consecutive complete game-day views are available — no movement is being hidden or assumed.'))
  assert.equal(htmlIncludes(html, 'could not be compared safely'), false)
  // Comparison stays withheld — the copy never reads as quiet/zero movement.
  assert.equal(htmlIncludes(html, 'No meaningful bullpen movement was found'), false)
})

test('Since Yesterday non-adjacent views explain a league off-day gap', () => {
  const dashboardOffDayGap = {
    ...dashboard,
    what_changed_since_yesterday: {
      capability: 'what_changed_since_yesterday_public_v1',
      state: 'insufficient_context',
      comparison: {
        comparison_available: false,
        previous_data_through: '2026-07-12',
        current_data_through: '2026-07-17',
        reason_codes: ['snapshots_not_comparable', 'comparison_withheld'],
      },
      reason_codes: ['snapshots_not_comparable', 'comparison_withheld'],
      limitations: [],
      items: [],
      item_count: 0,
    },
  }
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardOffDayGap,
    landscape,
    teams,
  }))
  assert.ok(htmlIncludes(html, 'The two most recent complete daily views are not adjacent days — a league off-day gap.'))
  assert.ok(htmlIncludes(html, 'resumes automatically after the next comparable game-day view'))
  assert.equal(htmlIncludes(html, 'No meaningful bullpen movement was found'), false)
})
