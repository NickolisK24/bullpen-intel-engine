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
  filterSinceYesterdayLanes,
  filterSinceYesterdayItems,
  buildSinceYesterdayTabs,
  sinceYesterdayCountClarity,
  getTonightCards,
  submitAudienceSignup,
} = await server.ssrLoadModule('/src/components/home/IntelligenceSurface.jsx')
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
    summary: {
      meaningful_change_count: 2,
      more_breathing_room_count: 1,
      tighter_today_count: 1,
      structure_changed_count: 0,
      other_meaningful_change_count: 0,
      counts_complete: true,
      steady_count: 2,
      steady_teams: [
        { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL' },
        { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR' },
      ],
    },
    items: [
      {
        key: 'NYM-what-changed',
        team_id: 121,
        team_name: 'New York Mets',
        team_abbreviation: 'NYM',
        movement_lane: 'more_breathing_room',
        movement_label: 'More breathing room',
        primary_delta: {
          label: 'Rested relievers',
          previous: 3,
          current: 5,
          net_delta: 2,
        },
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
        movement_lane: 'tighter_today',
        movement_label: 'Tighter today',
        primary_delta: {
          label: 'Rested relievers',
          previous: 4,
          current: 2,
          net_delta: -2,
        },
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
  // The persistent first-use entry area links to the primary bullpen surfaces
  // even in the loading shell, but no team-specific board deep link appears
  // before data resolves.
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=compare"'))
  assert.equal(htmlIncludes(html, 'team='), false)
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

test('Since Yesterday groups changes into descriptive lanes led by the primary delta', () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayChanges, teams)
  assert.equal(view.state, 'changes_detected')
  assert.equal(view.comparisonAvailable, true)
  assert.deepEqual(view.items.map(item => item.teamAbbr), ['NYM', 'SF'])

  // Backend-authored lane and primary delta flow straight through.
  assert.equal(view.items[0].movementLane, 'more_breathing_room')
  assert.equal(view.items[0].movementLabel, 'More breathing room')
  assert.deepEqual(view.items[0].primaryDelta, {
    label: 'Rested relievers',
    previous: 3,
    current: 5,
    netDelta: 2,
  })
  assert.equal(view.items[1].movementLane, 'tighter_today')
  assert.deepEqual(view.items[1].primaryDelta, {
    label: 'Rested relievers',
    previous: 4,
    current: 2,
    netDelta: -2,
  })

  // Lanes render in the canonical order, one team each, alphabetical inside.
  assert.deepEqual(view.lanes.map(lane => lane.key), ['more_breathing_room', 'tighter_today'])
  assert.deepEqual(view.lanes[0].items.map(item => item.teamAbbr), ['NYM'])
  assert.deepEqual(view.lanes[1].items.map(item => item.teamAbbr), ['SF'])

  // Tabs lead with "All changes" then each non-empty lane in canonical order.
  assert.deepEqual(view.tabs.map(tab => tab.key), ['all', 'more_breathing_room', 'tighter_today'])
  assert.deepEqual(view.tabs.map(tab => tab.shortLabel), ['All', 'More room', 'Tighter'])
  // Category counts always sum to the All count (each team lands in one lane).
  assert.equal(view.tabs[0].count, 2)
  assert.equal(
    view.tabs.slice(1).reduce((total, tab) => total + tab.count, 0),
    view.tabs[0].count,
  )

  // League summary counts are normalized from the backend, not inferred here.
  assert.equal(view.summary.moreBreathingRoomCount, 1)
  assert.equal(view.summary.tighterTodayCount, 1)
  assert.equal(view.summary.meaningfulChangeCount, 2)
  assert.equal(view.summary.steadyCount, 2)
  assert.deepEqual(view.summary.steadyTeams.map(team => team.teamAbbr), ['MIL', 'TOR'])

  assert.deepEqual(view.items[0].publicEvidence, [
    {
      key: 'Resource pool-tight-less tight-0',
      label: 'Resource pool',
      yesterday: 'tight',
      today: 'less tight',
    },
  ])

  // Lane order is backend-authored and stable regardless of item order.
  const sourceOrderedDashboard = clone(dashboardWithSinceYesterdayChanges)
  sourceOrderedDashboard.what_changed_since_yesterday.items.reverse()
  const sourceOrderView = getSinceYesterdayView(sourceOrderedDashboard, teams)
  assert.deepEqual(sourceOrderView.items.map(item => item.teamAbbr), ['SF', 'NYM'])
  assert.deepEqual(sourceOrderView.lanes.map(lane => lane.key), ['more_breathing_room', 'tighter_today'])

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
  // League movement summary.
  assert.ok(htmlIncludes(sinceHtml, 'Across MLB since yesterday'))
  assert.ok(htmlIncludes(sinceHtml, 'gained breathing room'))
  assert.ok(htmlIncludes(sinceHtml, 'became tighter'))
  assert.ok(htmlIncludes(sinceHtml, 'remained steady'))
  // Movement tabs replace the stacked lanes: a tablist with a tab per category.
  assert.ok(htmlIncludes(sinceHtml, 'role="tablist"'))
  assert.equal(countOccurrences(sinceHtml, 'role="tab"'), 3)
  // The full lane name reaches screen readers through the tab aria-label,
  // even though the visible chip uses the compact label.
  assert.ok(htmlIncludes(sinceHtml, 'aria-label="More breathing room, 1 team"'))
  assert.ok(htmlIncludes(sinceHtml, 'aria-label="Tighter today, 1 team"'))
  assert.ok(htmlIncludes(sinceHtml, 'aria-label="All changes, 2 teams"'))
  // "All changes" is the default active tab; exactly one panel is in the DOM.
  assert.ok(htmlIncludes(sinceHtml, 'id="since-yesterday-tab-all" aria-selected="true"'))
  assert.equal(countOccurrences(sinceHtml, 'aria-selected="true"'), 1)
  assert.equal(countOccurrences(sinceHtml, 'role="tabpanel"'), 1)
  assert.ok(htmlIncludes(sinceHtml, 'id="since-yesterday-panel-all"'))
  assert.ok(htmlIncludes(sinceHtml, 'aria-labelledby="since-yesterday-tab-all"'))
  // No "Steady" tab is ever offered — steadiness is not a movement category.
  assert.equal(htmlIncludes(sinceHtml, 'aria-label="Steady'), false)
  // The default All panel shows every card and states how many are detailed.
  assert.ok(htmlIncludes(sinceHtml, 'Showing all 2 detailed team changes.'))
  assert.ok(htmlIncludes(sinceHtml, 'Find a team'))
  // Primary delta anchor (numbers + signed net) and consolidated prose.
  assert.ok(htmlIncludes(sinceHtml, 'Rested relievers'))
  assert.ok(htmlIncludes(sinceHtml, '+2'))
  assert.ok(htmlIncludes(sinceHtml, 'New York has more usable late-inning margin than yesterday.'))
  assert.ok(htmlIncludes(sinceHtml, 'That creates more ways through a close game tonight.'))
  assert.ok(htmlIncludes(sinceHtml, 'San Francisco has fewer rested relievers than yesterday.'))
  // Compact workload evidence.
  assert.ok(htmlIncludes(sinceHtml, 'Worked yesterday'))
  assert.ok(htmlIncludes(sinceHtml, 'Reed Garrett'))
  assert.ok(htmlIncludes(sinceHtml, '21 pitches'))
  // Expandable evidence keeps the structured rows available.
  assert.ok(htmlIncludes(sinceHtml, 'View evidence'))
  assert.ok(htmlIncludes(sinceHtml, 'Resource pool'))
  assert.ok(htmlIncludes(sinceHtml, 'Yesterday tight'))
  assert.ok(htmlIncludes(sinceHtml, 'Today less tight'))
  // Steady disclosure lists proven-steady teams only.
  assert.ok(htmlIncludes(sinceHtml, 'had no meaningful'))
  assert.ok(htmlIncludes(sinceHtml, 'Milwaukee Brewers'))
  assert.ok(htmlIncludes(sinceHtml, 'Toronto Blue Jays'))
  // Team-board links preserved with the existing analytics source.
  assert.ok(htmlIncludes(sinceHtml, 'href="/bullpen?view=board&amp;team=NYM&amp;source=today"'))
  assert.ok(htmlIncludes(sinceHtml, 'href="/bullpen?view=board&amp;team=SF&amp;source=today"'))
  // Two card evidence disclosures + one steady disclosure, none open by default.
  assert.equal(countOccurrences(sinceHtml, '<details'), 3)
  assert.equal(countOccurrences(sinceHtml, '<summary'), 3)
  assert.equal(/<details[^>]*\sopen(?:=|>|\s)/i.test(sinceHtml), false)
  assert.equal(htmlIncludes(sinceHtml, 'what_changed_item_opened'), false)
  // The old repetitive headline line is no longer shown as separate prose.
  assert.equal(htmlIncludes(sinceHtml, 'Mets bullpen has more breathing room today.'), false)
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
  assert.equal(cards[0].href, '/bullpen?view=board&team=CHC&source=today')
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
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=CHC&amp;source=today"'))
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
  assert.equal(countOccurrences(html, 'source=today'), 1)
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
  // The Learn & Explore (supporting) section links only to the trust/explainer
  // pages — the primary bullpen links live in the separate first-use entry area.
  assert.equal(htmlIncludes(exploreHtml, 'href="/dashboard"'), false)
  assert.equal(htmlIncludes(exploreHtml, 'href="/bullpen"'), false)
  assert.equal(htmlIncludes(exploreHtml, 'href="/stories"'), false)

  // The first-use entry area does link to the primary bullpen surfaces.
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=compare"'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=pitchers"'))
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


// ---------------------------------------------------------------------------
// Daily briefing enhancements: lanes, team filtering, league summary, deltas.
// ---------------------------------------------------------------------------

const dashboardStructureIncompleteCounts = {
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
    item_count: 1,
    summary: {
      meaningful_change_count: 1,
      more_breathing_room_count: 0,
      tighter_today_count: 0,
      structure_changed_count: 1,
      other_meaningful_change_count: 0,
      counts_complete: false,
    },
    items: [
      {
        key: 'LAD-what-changed',
        team_id: 119,
        team_name: 'Los Angeles Dodgers',
        team_abbreviation: 'LAD',
        movement_lane: 'structure_changed',
        movement_label: 'Structure changed',
        primary_delta: {
          label: 'Late-inning support arms',
          previous: 2,
          current: 5,
          net_delta: null,
        },
        public_summary: 'Los Angeles reshaped its late-inning support group.',
        public_context: 'That changes the path to the final outs tonight.',
      },
    ],
  },
}

const dashboardLegacyChangeNoLane = {
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
    item_count: 1,
    items: [
      {
        key: 'ATH-what-changed',
        team_id: 133,
        team_name: 'Athletics',
        team_abbreviation: 'ATH',
        public_summary: 'Movement without a backend-authored lane.',
        public_context: 'Context sentence.',
        yesterday_rested_count: 2,
        today_rested_count: 4,
      },
    ],
  },
}

test('Since Yesterday team filter matches full name and abbreviation', () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayChanges, teams)

  const byName = filterSinceYesterdayLanes(view.lanes, 'new york')
  assert.deepEqual(byName.flatMap(lane => lane.items.map(item => item.teamAbbr)), ['NYM'])

  const byAbbr = filterSinceYesterdayLanes(view.lanes, 'sf')
  assert.deepEqual(byAbbr.flatMap(lane => lane.items.map(item => item.teamAbbr)), ['SF'])

  const empty = filterSinceYesterdayLanes(view.lanes, '')
  assert.deepEqual(empty.map(lane => lane.key), ['more_breathing_room', 'tighter_today'])
})

test('Since Yesterday team filter no-match returns no lanes (never implies steady)', () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayChanges, teams)
  const noMatch = filterSinceYesterdayLanes(view.lanes, 'zzz nonexistent')
  assert.deepEqual(noMatch, [])
})

test('Since Yesterday structure lane renders a delta with no signed net', () => {
  const view = getSinceYesterdayView(dashboardStructureIncompleteCounts, teams)
  assert.deepEqual(view.lanes.map(lane => lane.key), ['structure_changed'])
  assert.equal(view.items[0].primaryDelta.netDelta, null)

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardStructureIncompleteCounts,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')
  assert.ok(htmlIncludes(sinceHtml, 'Structure changed'))
  assert.ok(htmlIncludes(sinceHtml, 'Late-inning support arms'))
  assert.ok(htmlIncludes(sinceHtml, 'changed structurally'))
  // A structural delta must not fabricate a +/- net value.
  assert.equal(/net change/.test(sinceHtml), false)
})

test('Since Yesterday summary omits zero-count lanes and withholds unproven steady count', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardStructureIncompleteCounts,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')
  const view = getSinceYesterdayView(dashboardStructureIncompleteCounts, teams)

  assert.equal(view.summary.countsComplete, false)
  assert.equal('steadyCount' in view.summary, false)
  assert.ok(htmlIncludes(sinceHtml, 'changed structurally'))
  // Zero-count directions are not rendered as "0 gained breathing room".
  assert.equal(htmlIncludes(sinceHtml, 'gained breathing room'), false)
  assert.equal(htmlIncludes(sinceHtml, 'became tighter'), false)
  // Steady is withheld when the population is not provably complete.
  assert.equal(htmlIncludes(sinceHtml, 'remained steady'), false)
  assert.equal(htmlIncludes(sinceHtml, 'had no meaningful'), false)
})

test('Since Yesterday item without a backend lane falls closed to the neutral lane', () => {
  const view = getSinceYesterdayView(dashboardLegacyChangeNoLane, teams)
  assert.deepEqual(view.lanes.map(lane => lane.key), ['other_meaningful_changes'])
  assert.deepEqual(view.lanes[0].items.map(item => item.teamAbbr), ['ATH'])
  // No backend summary block -> no synthesized league counts.
  assert.equal(view.summary, null)

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardLegacyChangeNoLane,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')
  assert.ok(htmlIncludes(sinceHtml, 'Other meaningful change'))
  assert.ok(htmlIncludes(sinceHtml, 'Movement without a backend-authored lane.'))
  assert.equal(htmlIncludes(sinceHtml, 'Across MLB since yesterday'), false)
})

// A day where the league summary counts more moving teams than there are
// published cards: several teams moved but their write-ups were held back by
// copy review, so no detailed card is emitted for them. The counts are correct;
// the UI must reconcile them rather than hide the gap or imply steadiness.
const dashboardWithSuppressedCards = (() => {
  const base = clone(dashboardWithSinceYesterdayChanges)
  const block = base.what_changed_since_yesterday
  block.summary.meaningful_change_count = 5
  block.summary.more_breathing_room_count = 3
  block.summary.tighter_today_count = 2
  block.summary.steady_count = 1
  block.summary.steady_teams = [
    { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL' },
  ]
  return base
})()

test('Since Yesterday tabs lead with All, hide empty lanes, and keep counts consistent', () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayChanges, teams)
  const tabs = buildSinceYesterdayTabs(view.items)

  // "All changes" leads, then each non-empty lane in canonical order. Empty
  // lanes get no tab, and there is never a "Steady" tab.
  assert.deepEqual(tabs.map(tab => tab.key), ['all', 'more_breathing_room', 'tighter_today'])
  assert.equal(tabs.some(tab => tab.key === 'structure_changed'), false)
  assert.equal(tabs.some(tab => /steady/i.test(tab.label)), false)

  // The All tab holds every item; the categories partition it exactly, so the
  // tab counts can never disagree with the total.
  assert.equal(tabs[0].count, view.items.length)
  assert.equal(tabs.slice(1).reduce((total, tab) => total + tab.count, 0), tabs[0].count)

  // A single change with no backend lane collapses to exactly All + Other.
  const neutralView = getSinceYesterdayView(dashboardLegacyChangeNoLane, teams)
  const neutralTabs = buildSinceYesterdayTabs(neutralView.items)
  assert.deepEqual(neutralTabs.map(tab => tab.key), ['all', 'other_meaningful_changes'])
  assert.deepEqual(neutralTabs.map(tab => tab.shortLabel), ['All', 'Other'])

  // Empty input yields just the All tab with a zero count (never "of 0" copy).
  const emptyTabs = buildSinceYesterdayTabs([])
  assert.deepEqual(emptyTabs.map(tab => tab.key), ['all'])
  assert.equal(emptyTabs[0].count, 0)
})

test('Since Yesterday item filter matches name and abbreviation without touching counts', () => {
  const view = getSinceYesterdayView(dashboardWithSinceYesterdayChanges, teams)
  const allItems = view.tabs[0].items

  assert.deepEqual(filterSinceYesterdayItems(allItems, 'new york').map(item => item.teamAbbr), ['NYM'])
  assert.deepEqual(filterSinceYesterdayItems(allItems, 'SF').map(item => item.teamAbbr), ['SF'])
  // Blank/whitespace queries return the full list.
  assert.deepEqual(filterSinceYesterdayItems(allItems, '  ').map(item => item.teamAbbr), ['NYM', 'SF'])
  // A no-match returns an empty list, never a "steady" implication.
  assert.deepEqual(filterSinceYesterdayItems(allItems, 'zzz nonexistent'), [])
  // Search filters the rendered cards only; the pre-search tab count is intact.
  assert.equal(view.tabs[0].count, 2)
})

test('Since Yesterday count clarity reconciles detailed cards with the complete league counts', () => {
  const view = getSinceYesterdayView(dashboardWithSuppressedCards, teams)
  const [allTab, moreRoomTab, tighterTab] = view.tabs
  assert.deepEqual([allTab.key, moreRoomTab.key, tighterTab.key], ['all', 'more_breathing_room', 'tighter_today'])

  // All tab, plural withheld: the additional teams belong to the trusted league
  // summary but have no public-safe card, and are explicitly not steady.
  const allClarity = sinceYesterdayCountClarity(allTab, view.summary)
  assert.equal(
    allClarity,
    'Showing 2 of 5 teams with movement. Three additional teams are included in the league summary but do not have a publishable detailed card. They are not counted as steady.',
  )
  // Category tab, plural withheld: reconciles against the lane league count and
  // does not repeat the steady clarification.
  assert.equal(
    sinceYesterdayCountClarity(moreRoomTab, view.summary),
    'Showing 1 of 3 teams with movement in this category. Two additional teams are included in the league count but do not have a publishable detailed card.',
  )
  // Category tab, singular withheld: "One additional team ... does not have".
  assert.equal(
    sinceYesterdayCountClarity(tighterTab, view.summary),
    'Showing 1 of 2 teams with movement in this category. One additional team is included in the league count but does not have a publishable detailed card.',
  )

  // All tab, large plural example (11 of 22) spelled-out and steady-qualified.
  assert.equal(
    sinceYesterdayCountClarity({ key: 'all', count: 11 }, { meaningfulChangeCount: 22 }),
    'Showing 11 of 22 teams with movement. Eleven additional teams are included in the league summary but do not have a publishable detailed card. They are not counted as steady.',
  )
  // Category tab, larger example (6 of 10) — uses "league count", no steady line.
  assert.equal(
    sinceYesterdayCountClarity({ key: 'more_breathing_room', count: 6 }, { moreBreathingRoomCount: 10 }),
    'Showing 6 of 10 teams with movement in this category. Four additional teams are included in the league count but do not have a publishable detailed card.',
  )
  // All tab, singular withheld: both 1-of-2 and 2-of-3 leave exactly one team
  // withheld and must read "One additional team ... does not have ... It is not
  // counted as steady."
  assert.equal(
    sinceYesterdayCountClarity({ key: 'all', count: 1 }, { meaningfulChangeCount: 2 }),
    'Showing 1 of 2 teams with movement. One additional team is included in the league summary but does not have a publishable detailed card. It is not counted as steady.',
  )
  assert.equal(
    sinceYesterdayCountClarity({ key: 'all', count: 2 }, { meaningfulChangeCount: 3 }),
    'Showing 2 of 3 teams with movement. One additional team is included in the league summary but does not have a publishable detailed card. It is not counted as steady.',
  )

  // When every moving team has a card, reassure that all are shown — with no
  // additional-team sentence at all.
  const completeView = getSinceYesterdayView(dashboardWithSinceYesterdayChanges, teams)
  const allComplete = sinceYesterdayCountClarity(completeView.tabs[0], completeView.summary)
  assert.equal(allComplete, 'Showing all 2 detailed team changes.')
  assert.equal(/additional team/.test(allComplete), false)
  assert.equal(
    sinceYesterdayCountClarity(completeView.tabs[1], completeView.summary),
    'Showing all 1 detailed team change in this category.',
  )

  // No summary / unknown denominator: numerator only, never "of 0", and no
  // withheld-card explanation.
  const numeratorOnly = sinceYesterdayCountClarity(completeView.tabs[0], null)
  assert.equal(numeratorOnly, 'Showing 2 detailed team changes.')
  assert.equal(/of 0/.test(numeratorOnly), false)
  assert.equal(/additional team/.test(numeratorOnly), false)

  // A complete count smaller than the cards on hand is ignored, not shown as a
  // zero or negative remainder.
  assert.equal(
    sinceYesterdayCountClarity({ key: 'all', count: 3 }, { meaningfulChangeCount: 1 }),
    'Showing 3 detailed team changes.',
  )

  // The retired internal-sounding phrasing never appears in any produced copy.
  const everyString = [
    allClarity,
    sinceYesterdayCountClarity(moreRoomTab, view.summary),
    sinceYesterdayCountClarity(tighterTab, view.summary),
    sinceYesterdayCountClarity({ key: 'all', count: 11 }, { meaningfulChangeCount: 22 }),
    sinceYesterdayCountClarity({ key: 'all', count: 1 }, { meaningfulChangeCount: 2 }),
    allComplete,
    numeratorOnly,
  ].join('')
  for (const banned of ['published write-up', 'write-up yet', 'moved too']) {
    assert.equal(everyString.includes(banned), false, banned)
  }
})

test('Since Yesterday panel explains when detailed cards are fewer than the league count', () => {
  const view = getSinceYesterdayView(dashboardWithSuppressedCards, teams)
  assert.equal(view.summary.meaningfulChangeCount, 5)
  assert.equal(view.tabs[0].count, 2)

  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardWithSuppressedCards,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')

  // The league summary still reports the complete counts...
  assert.ok(htmlIncludes(sinceHtml, 'gained breathing room'))
  assert.ok(htmlIncludes(sinceHtml, 'remained steady'))
  // ...and the active All panel reconciles them with the detailed cards shown:
  // the additional teams are inside the league summary but have no public-safe
  // card, and are explicitly not counted as steady.
  assert.ok(htmlIncludes(
    sinceHtml,
    'Showing 2 of 5 teams with movement. Three additional teams are included in the league summary but do not have a publishable detailed card. They are not counted as steady.',
  ))
  assert.equal(/\bof 0\b/.test(sinceHtml), false)
  // Retired internal-sounding phrasing is gone from the rendered copy.
  for (const banned of ['published write-up', 'write-up yet', 'moved too']) {
    assert.equal(sinceHtml.includes(banned), false, banned)
  }
})

test('Since Yesterday tabs expose roving focus and panel wiring, with only the active panel mounted', () => {
  const html = render(React.createElement(IntelligenceSurfaceView, {
    intelligence: intelligenceOk,
    tonight: tonightOk,
    dashboard: dashboardWithSinceYesterdayChanges,
    landscape,
    teams,
  }))
  const sinceHtml = sectionSlice(html, 'SINCE YESTERDAY', 'Tonight&#x27;s Bullpen Watch')

  // Roving tabindex: only the active tab is focusable; the other two are -1.
  assert.equal(countOccurrences(sinceHtml, 'tabindex="-1"'), 2)
  // Every tab points at its own panel id (arrow-key handler is attached to the
  // labelled, horizontally oriented tablist).
  assert.ok(htmlIncludes(sinceHtml, 'aria-label="Movement categories"'))
  assert.ok(htmlIncludes(sinceHtml, 'aria-orientation="horizontal"'))
  assert.ok(htmlIncludes(sinceHtml, 'aria-controls="since-yesterday-panel-all"'))
  assert.ok(htmlIncludes(sinceHtml, 'aria-controls="since-yesterday-panel-more_breathing_room"'))
  assert.ok(htmlIncludes(sinceHtml, 'aria-controls="since-yesterday-panel-tighter_today"'))
  // Only the active tab's panel is in the DOM; inactive panels are not mounted.
  assert.equal(countOccurrences(sinceHtml, 'role="tabpanel"'), 1)
  assert.equal(htmlIncludes(sinceHtml, 'id="since-yesterday-panel-more_breathing_room"'), false)
  assert.equal(htmlIncludes(sinceHtml, 'id="since-yesterday-panel-tighter_today"'), false)
})
