import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
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

after(async () => server.close())

const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const {
  TRAFFIC_EMPTY_COPY,
  TRAFFIC_ROBOTS_CONTENT,
  TrafficAccessState,
  TrafficIntelligenceAdminView,
  TrafficReport,
} = await server.ssrLoadModule('/src/components/admin/TrafficIntelligenceAdmin.jsx')
const {
  fetchTrafficSummary,
  TRAFFIC_REPORTING_PATH,
} = await server.ssrLoadModule('/src/utils/trafficReporting.js')
const { canonicalPage } = await server.ssrLoadModule('/src/utils/trafficMeasurement.js')
const { formatAdminDateTime } = await server.ssrLoadModule('/src/utils/adminDateTime.js')

function render(element) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
}

function reportFixture(overrides = {}) {
  return {
    generated_at: '2026-07-14T16:00:00Z',
    timezone: 'America/New_York',
    selected_range: { key: '7d', label: 'Last 7 days' },
    measurement_start: '2026-07-01T15:00:00Z',
    definitions: {
      external_visitors: 'Distinct qualifying browser identities active in the selected period; these are not verified individual people.',
      sessions: 'Distinct qualifying browser sessions.',
      page_views: 'Canonical public page views.',
      returning_visitors: 'First qualifying view occurred before the period.',
      new_visitors: 'First qualifying view occurred in the period.',
      multi_page_sessions: 'Sessions with at least two page views.',
      pages_per_session: 'Page views divided by sessions.',
      entry_source: 'Bounded navigation context.',
      evidence_target_views: 'Opening does not prove every item was read.',
      evidence_and_trust_use: 'Canonical evidence and trust page views, read as one group. A view is an opening, not proof of reading.',
      reliever_finder_views: 'Canonical Reliever Finder page views (stored as all_pitchers).',
      methodology_views: 'Canonical Methodology page views.',
      data_trust_views: 'Canonical Data & Trust page views.',
      since_yesterday_evidence_opens: 'Team Board views opened from a Since Yesterday link.',
      shared_link_landing_sessions: 'Sessions beginning from a share-oriented URL.',
      evidence_depth: 'Bullpen sessions opening deeper evidence.',
      comparison_pairs: 'Descriptive URL selections, not game predictions.',
      completed_share_actions: 'Browser-observed completed sharing actions.',
      copied_links: 'Successful clipboard writes.',
      card_downloads: 'Successful browser download starts.',
      anonymous_share_visitors: 'Distinct anonymous browser identities completing an action.',
      card_version: 'A bounded implementation identifier attached when a generated evidence-card model was available. Unversioned actions may include historical clients or link-only fallbacks.',
      story_angle: 'A bounded editorial category describing the evidence-led headline type on a generated card. It does not represent user intent, delivery to any person, or an outcome.',
    },
    summary: {
      external_visitors: 12,
      sessions: 15,
      page_views: 24,
      returning_visitors: 4,
      new_visitors: 8,
      multi_page_sessions: 6,
      pages_per_session: 1.6,
    },
    comparison: {
      available: true,
      reason: null,
      changes: Object.fromEntries([
        'external_visitors', 'sessions', 'page_views', 'returning_visitors',
        'new_visitors', 'multi_page_sessions', 'pages_per_session',
      ].map(key => [key, { absolute: 1, percent: 10 }])),
    },
    daily: [{ date: '2026-07-14', visitors: 3, sessions: 4, page_views: 7 }],
    session_depth: { single_page_sessions: 9, multi_page_sessions: 6, pages_per_session: 1.6 },
    acquisition: {
      campaign: { sessions: 3, percentage: 20 },
      referral: { sessions: 4, percentage: 26.67 },
      direct_unknown: { sessions: 8, percentage: 53.33 },
    },
    top_referrers: [{ referrer_domain: 'example.com', sessions: 4 }],
    campaigns: [{ utm_source: 'newsletter', utm_medium: 'email', utm_campaign: 'launch', sessions: 3 }],
    landing_surfaces: [{ surface: 'today', sessions: 8 }],
    most_visited_surfaces: [{ surface: 'bullpen_board', page_views: 9 }],
    bullpen_exploration: {
      bullpen_board_views: 9,
      compare_bullpens_views: 3,
      all_pitchers_views: 2,
      team_contexts: [{ team_ref: 'NYY', page_views: 2 }],
      pitcher_context_page_views: 1,
    },
    evidence_exploration: {
      team_read_views: 7,
      team_relief_work_views: 4,
      pitcher_lanes_views: 3,
      pitcher_detail_views: 2,
      comparison_read_views: 5,
      comparison_evidence_views: 1,
      team_contexts: [{ team_ref: 'BOS', page_views: 6 }],
      comparison_pairs: [{ team_a_ref: 'BOS', team_b_ref: 'NYY', pair_key: 'BOS:NYY', page_views: 5 }],
      entry_sources: [{ entry_source: 'share_link', page_views: 3, sessions: 2 }],
    },
    shared_link_landings: {
      share_origin_sessions: 2,
      share_origin_visitors: 1,
      share_origin_page_views: 2,
    },
    evidence_depth: {
      sessions_opening_deeper_evidence: 4,
      percentage_of_bullpen_sessions_opening_deeper_evidence: 40,
    },
    evidence_and_trust_use: {
      team_read_views: 7,
      recent_bullpen_work_views: 4,
      pitcher_lane_views: 3,
      reliever_detail_views: 2,
      comparison_read_views: 5,
      comparison_evidence_views: 1,
      reliever_finder_views: 2,
      methodology_views: 6,
      data_trust_views: 3,
      since_yesterday_evidence_opens: 8,
      sessions_with_deeper_evidence: 4,
      evidence_depth_percentage: 40,
    },
    sharing: {
      completed_share_actions: 9,
      anonymous_visitors_completing_share_actions: 4,
      story_classified_actions: 7,
      unversioned_share_actions: 2,
      team_card_actions: 4,
      comparison_card_actions: 3,
      link_only_actions: 2,
      card_downloads: 2,
      native_card_shares: 2,
      native_link_shares: 1,
      copied_links: 4,
      share_methods: [{ action: 'copy_link', completed_actions: 4 }],
      most_shared_teams: [{ team_ref: 'NYY', completed_actions: 4 }],
      most_shared_comparison_pairs: [{ pair_key: 'BOS:NYY', completed_actions: 3 }],
      actions_by_surface: [{ surface: 'bullpen_board', completed_actions: 5 }],
      actions_by_evidence_target: [{ evidence_target: 'team_read', completed_actions: 3 }],
      actions_by_card_version: [
        { card_version: 'team_story_v2', completed_actions: 5, anonymous_visitors: 3 },
        { card_version: 'comparison_story_v2', completed_actions: 2, anonymous_visitors: 1 },
      ],
      actions_by_story_angle: [
        {
          story_angle: 'availability_constraint', completed_actions: 4, anonymous_visitors: 2,
          native_card_shares: 1, native_link_shares: 1, copied_links: 1, card_downloads: 1,
        },
        {
          story_angle: 'comparison_availability', completed_actions: 2, anonymous_visitors: 1,
          native_card_shares: 1, native_link_shares: 0, copied_links: 1, card_downloads: 0,
        },
      ],
    },
    measurement_health: {
      measurement_started_at: '2026-07-01T15:00:00Z',
      last_external_page_view_at: '2026-07-14T15:00:00Z',
      last_canonical_page_view_at: '2026-07-14T15:30:00Z',
      registered_internal_browser_ids: 2,
      selected_period: {
        canonical_page_views: 30,
        external_page_views: 24,
        excluded_internal_page_views: 4,
        excluded_bot_page_views: 2,
        unknown_device_external_page_views: 1,
      },
    },
    ...overrides,
  }
}

test('internal route is registered but absent from public navigation', () => {
  assert.ok(APP_ROUTES.some(route => route.path === TRAFFIC_REPORTING_PATH))
  assert.equal(TRAFFIC_REPORTING_PATH, '/admin/product-intelligence')
  const sidebar = readFileSync('src/components/Sidebar.jsx', 'utf8')
  const footer = readFileSync('src/components/layout/Footer.jsx', 'utf8')
  assert.equal(sidebar.includes(TRAFFIC_REPORTING_PATH), false)
  assert.equal(footer.includes(TRAFFIC_REPORTING_PATH), false)
})

test('page declares noindex nofollow metadata and uses normal auth state', () => {
  const source = readFileSync('src/components/admin/TrafficIntelligenceAdmin.jsx', 'utf8')
  assert.equal(TRAFFIC_ROBOTS_CONTENT, 'noindex,nofollow')
  assert.ok(source.includes('meta[name="robots"]'))
  assert.ok(source.includes('useAuthState'))
})

test('access states distinguish checking, sign-in, and forbidden access', () => {
  const checking = render(React.createElement(TrafficAccessState, { state: 'checking' }))
  const unauthenticated = render(React.createElement(TrafficAccessState, { state: 'unauthenticated' }))
  const forbidden = render(React.createElement(TrafficAccessState, { state: 'forbidden' }))
  assert.ok(checking.includes('Checking access'))
  assert.ok(unauthenticated.includes('Sign in'))
  assert.ok(unauthenticated.includes('%2Fadmin%2Fproduct-intelligence'))
  assert.ok(forbidden.includes('not authorized'))
  assert.equal(forbidden.includes('>Sign in<'), false)
})

test('range controls expose 7, 30, 90, and All with selected state', () => {
  const html = render(React.createElement(TrafficIntelligenceAdminView, {
    data: reportFixture(),
    range: '30d',
  }))
  for (const label of ['>7<', '>30<', '>90<', '>All<']) assert.ok(html.includes(label))
  assert.match(html, /aria-pressed="true"[^>]*>30<\/button>/)
})

test('loading error restricted and honest empty states render', () => {
  const loading = render(React.createElement(TrafficIntelligenceAdminView, { loading: true }))
  const error = render(React.createElement(TrafficIntelligenceAdminView, { error: new Error('offline') }))
  const forbiddenError = new Error('forbidden')
  forbiddenError.status = 403
  const forbidden = render(React.createElement(TrafficIntelligenceAdminView, { error: forbiddenError }))
  const empty = render(React.createElement(TrafficIntelligenceAdminView, {
    data: reportFixture({ summary: { ...reportFixture().summary, page_views: 0 } }),
  }))
  assert.ok(loading.includes('Loading traffic intelligence'))
  assert.ok(error.includes('Traffic intelligence is unavailable'))
  assert.ok(error.includes('Retry'))
  assert.ok(forbidden.includes('Access Restricted'))
  assert.ok(empty.includes(TRAFFIC_EMPTY_COPY))
})

test('summary, comparison, reporting sections, and definitions render honestly', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  for (const text of [
    'External Visitors', 'Sessions', 'Page Views', 'Returning Visitors', 'New Visitors',
    'Multi-Page Sessions', 'Pages per Session', 'Daily Traffic', 'Acquisition',
    'Landing Surfaces', 'Most Visited Surfaces', 'Top Referrer Domains', 'Campaigns',
    'Bullpen Exploration', 'Evidence Exploration', 'Top Team Evidence', 'Top Comparison Pairs',
    'Entry Sources', 'Shared-Link Landings', 'Evidence Depth', 'Sharing', 'Measurement Health', 'Metric Definitions',
  ]) assert.ok(html.includes(text), text)
  assert.ok(html.includes('distinct browser identities, not confirmed individual people'))
  assert.equal(/engaged users/i.test(html), false)
})

test('evidence context sections render bounded counts and precise labels', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  for (const text of [
    'Team Read Views', 'Recent Relief Work Views', 'Pitcher Lanes Views', 'Pitcher Detail Views',
    'Comparison Read Views', 'Comparison Evidence Views', 'BOS:NYY', 'Share Link',
    '3 views', '2 sessions', 'Anonymous Visitors', 'Sessions Opening Deeper Evidence',
    'Percentage of Bullpen Sessions', '40%',
  ]) assert.ok(html.includes(text), text)
  for (const definition of [
    'Entry Source', 'Evidence-Target Views', 'Shared-Link Landing Sessions',
    'Evidence Depth', 'Comparison Pairs', 'not game predictions',
  ]) assert.ok(html.includes(definition), definition)
  for (const forbidden of ['People who read', 'Share conversions', 'Viral traffic', 'Engagement score']) {
    assert.equal(html.includes(forbidden), false)
  }
})

test('evidence and trust use consolidates the evidence-first read with honest labels', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  assert.ok(html.includes('Evidence &amp; Trust Use'))
  for (const label of [
    'Recent Bullpen Work Views', 'Pitcher Lane Views', 'Reliever Detail Views',
    'Reliever Finder Views', 'Methodology Views', 'Data &amp; Trust Views',
    'Since Yesterday Evidence Opens', 'Sessions With Deeper Evidence',
  ]) assert.ok(html.includes(label), label)
  // A view is an opening, never proof of reading, comprehension, or trust.
  assert.ok(html.includes('does not prove the visitor read, understood, or trusted every'))
  assert.ok(html.includes('counts, not rankings or scores'))
  // No leaderboard, engagement, or virality framing anywhere in the section.
  for (const forbidden of [/leaderboard/i, /engagement score/i, /most engaged/i, /viral/i]) {
    assert.equal(forbidden.test(html), false, String(forbidden))
  }
})

test('evidence and trust use stays zero-safe and unknown-honest when empty', () => {
  const html = render(React.createElement(TrafficReport, {
    report: reportFixture({ evidence_and_trust_use: {} }),
  }))
  assert.ok(html.includes('Evidence &amp; Trust Use'))
  assert.ok(html.includes('Percentage unavailable'))
  assert.equal(html.includes('NaN'), false)
  assert.equal(html.includes('undefined'), false)
})

test('empty evidence sections remain compact and zero-safe', () => {
  const report = reportFixture({
    evidence_exploration: {},
    shared_link_landings: {},
    evidence_depth: {},
  })
  const html = render(React.createElement(TrafficReport, { report }))
  assert.ok(html.includes('No bounded entry source recorded.'))
  assert.ok(html.includes('Percentage unavailable'))
  assert.equal(html.includes('NaN'), false)
  assert.equal(html.includes('Infinity'), false)
})

test('sharing reports completed actions separately from shared-link landings', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  for (const text of [
    'Completed Share Actions', 'Anonymous Visitors Completing Share Actions',
    'Team Card Actions', 'Comparison Card Actions', 'Link-Only Actions',
    'Card Downloads', 'Native Card Shares', 'Native Link Shares', 'Copied Links',
    'Share Methods', 'Most Shared Teams', 'Most Shared Comparison Pairs',
    'Share Actions by Surface', 'Share Actions by Evidence Target',
    'Copy Link', 'NYY', 'BOS:NYY', 'Bullpen Board', 'Team Read',
    'do not prove where or to whom a link was shared',
  ]) assert.ok(html.includes(text), text)
  assert.equal(/recipient|platform/i.test(html), false)
})

test('sharing summary reports story-classified and unversioned actions honestly', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  assert.ok(html.includes('Story-Classified Actions'))
  assert.ok(html.includes('Unversioned Share Actions'))
  // Completed actions stay distinct from landing sessions.
  assert.ok(html.includes('Completed actions are browser-observed completions'))
  assert.ok(html.includes('Shared-link landing sessions remain separate'))
  // Accurate meaning: no recorded version/angle context, not "no card model existed".
  assert.ok(html.includes('no recorded card-version or story-angle context'))
  assert.ok(html.includes('historical or cached clients'))
  assert.ok(html.includes('link-only fallbacks'))
  assert.ok(html.includes('are not failures'))
  // The obsolete, too-absolute claim must be gone.
  assert.equal(html.includes('carry no generated card model'), false)
  assert.equal(html.includes('no generated card model'), false)
  assert.equal(/unversioned actions[^<]*fail/i.test(html.replace('are not failures', '')), false)
})

test('card versions and story angles render bounded counts, visitors, and method breakdowns', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  assert.ok(html.includes('Card Versions'))
  assert.ok(html.includes('Story Angles'))
  // Human-readable underscore-to-label formatting.
  assert.ok(html.includes('Team Story V2'))
  assert.ok(html.includes('Comparison Story V2'))
  assert.ok(html.includes('Availability Constraint'))
  assert.ok(html.includes('Comparison Availability'))
  // Column headers for the story-angle method breakdown.
  for (const heading of ['Native Card Shares', 'Native Link Shares', 'Copied Links', 'Card Downloads', 'Anonymous Visitors']) {
    assert.ok(html.includes(heading), heading)
  }
  // Definitions render with matching keys.
  assert.ok(html.includes('Card Version'))
  assert.ok(html.includes('Story Angle'))
  assert.ok(html.includes('bounded editorial category'))
  // Descriptive only — never engagement, virality, or winner framing.
  for (const forbidden of [/conversion/i, /viral/i, /virality/i, /recipient/i, /best-performing/i, /engagement score/i]) {
    assert.equal(forbidden.test(html), false, String(forbidden))
  }
})

test('empty card version and story angle sections stay compact and zero-safe', () => {
  const report = reportFixture({
    sharing: {
      ...reportFixture().sharing,
      story_classified_actions: 0,
      unversioned_share_actions: 0,
      actions_by_card_version: [],
      actions_by_story_angle: [],
    },
  })
  const html = render(React.createElement(TrafficReport, { report }))
  assert.ok(html.includes('No versioned card actions were recorded in this period.'))
  assert.ok(html.includes('No story-classified card actions were recorded in this period.'))
  assert.equal(html.includes('NaN'), false)
  assert.equal(html.includes('undefined'), false)
})

test('acquisition renders session percentages and remains zero-safe', () => {
  const populated = render(React.createElement(TrafficReport, { report: reportFixture() }))
  for (const value of ['3 sessions · 20%', '4 sessions · 26.67%', '8 sessions · 53.33%']) {
    assert.ok(populated.includes(value), value)
  }

  const empty = reportFixture({
    acquisition: {
      campaign: { sessions: 0, percentage: null },
      referral: { sessions: 0, percentage: null },
      direct_unknown: { sessions: 0, percentage: null },
    },
  })
  const emptyHtml = render(React.createElement(TrafficReport, { report: empty }))
  assert.ok(emptyHtml.includes('Percentage unavailable'))
  assert.equal(emptyHtml.includes('NaN'), false)
  assert.equal(emptyHtml.includes('Infinity'), false)
})

test('daily breakdown presents visitors sessions and page views for every date', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  assert.ok(html.includes('Daily visitors, sessions, and page views'))
  for (const heading of ['Date', 'Visitors', 'Sessions', 'Page Views']) assert.ok(html.includes(heading))
  assert.match(html, /2026-07-14[\s\S]*>3<[\s\S]*>4<[\s\S]*>7</)
})

test('measurement health renders all-time state and selected-period labels', () => {
  const html = render(React.createElement(TrafficReport, { report: reportFixture() }))
  for (const text of [
    'Measurement Started At', 'Last External Page View At', 'Last Canonical Page View At',
    'Registered Internal Browser IDs', 'Selected-Period Canonical Page Views',
    'Selected-Period External Page Views', 'Selected-Period Excluded Internal Page Views',
    'Selected-Period Excluded Bot Page Views', 'Selected-Period Unknown-Device External Page Views',
    'July 1, 2026 at 11:00 AM ET', 'July 14, 2026 at 11:30 AM ET',
  ]) assert.ok(html.includes(text), text)
  assert.ok(html.includes('title="2026-07-01T15:00:00Z"'))
  assert.ok(html.includes('title="2026-07-14T15:30:00Z"'))
  assert.equal(html.includes('>2026-07-01T15:00:00Z<'), false)
})

test('admin timestamp formatter is readable, raw-preserving, and timezone-safe', () => {
  assert.deepEqual(formatAdminDateTime('2026-07-15T23:22:00Z'), {
    display: 'July 15, 2026 at 7:22 PM ET',
    title: '2026-07-15T23:22:00Z',
  })
  assert.deepEqual(formatAdminDateTime('2026-07-15'), {
    display: 'July 15, 2026',
    title: '2026-07-15',
  })
  assert.deepEqual(formatAdminDateTime('not-a-date'), { display: '—', title: null })
  assert.deepEqual(formatAdminDateTime(null), { display: '—', title: null })
})

test('comparison unavailable reason is visible without invented percentage', () => {
  const report = reportFixture({
    comparison: { available: false, reason: 'incomplete_prior_period', previous: null, changes: null },
  })
  const html = render(React.createElement(TrafficReport, { report }))
  assert.ok(html.includes('Comparison unavailable'))
  assert.ok(html.includes('Incomplete Prior Period'))
  assert.equal(html.includes('Infinity'), false)
})

test('reporting fetch uses bearer auth and configured backend origin', async () => {
  const calls = []
  const result = await fetchTrafficSummary('30d', {
    authToken: 'normal-bearer',
    configuredBackendOrigin: 'https://api.baseballos.app',
    fetchImpl: async (url, options) => {
      calls.push({ url, options })
      return { ok: true, status: 200, json: async () => ({ summary: {} }) }
    },
  })
  assert.deepEqual(result, { summary: {} })
  assert.equal(calls[0].url, 'https://api.baseballos.app/api/traffic/internal/summary?range=30d')
  assert.equal(calls[0].options.headers.Authorization, 'Bearer normal-bearer')
  assert.deepEqual(Object.keys(calls[0].options.headers).sort(), ['Authorization', 'Content-Type'])
})

test('restricted fetch status is preserved for the page access state', async () => {
  await assert.rejects(
    () => fetchTrafficSummary('7d', {
      authToken: 'normal-bearer',
      fetchImpl: async () => ({ ok: false, status: 403 }),
    }),
    error => error.status === 403,
  )
})

test('dashboard renders no raw identifiers and uses no privileged browser token', () => {
  const report = reportFixture({
    visitor_id: 'visitor-secret',
    session_id: 'session-secret',
    view_id: 'view-secret',
    registered_by_user_id: 99,
    pitcher_id: 42,
  })
  const html = render(React.createElement(TrafficReport, { report }))
  for (const secret of ['visitor-secret', 'session-secret', 'view-secret']) {
    assert.equal(html.includes(secret), false)
  }
  const sources = [
    readFileSync('src/components/admin/TrafficIntelligenceAdmin.jsx', 'utf8'),
    readFileSync('src/utils/trafficReporting.js', 'utf8'),
  ].join('\n')
  assert.equal(sources.includes('ADMIN_API_TOKEN'), false)
  assert.equal(sources.includes('X-Admin-Token'), false)
})

test('admin route is excluded from traffic measurement', () => {
  assert.equal(canonicalPage('/admin/product-intelligence'), null)
})
