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

after(async () => {
  await server.close()
})

const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')
const { PrivatePostsView } = await server.ssrLoadModule('/src/components/posts/PrivatePosts.jsx')
const {
  PRIVATE_POSTS_PATH,
  PRIVATE_POSTS_ROBOTS,
  X_LEAD_CHARACTER_LIMIT,
  flattenTakeDrafts,
  getPrivatePostTakes,
} = await server.ssrLoadModule('/src/components/posts/privatePostsView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

function story(overrides = {}) {
  return {
    story_id: `${overrides.team_abbreviation || 'TST'}:${overrides.rule_key || 'test_rule'}`,
    rule_key: 'test_rule',
    rule_label: 'Test Rule',
    team_id: 100,
    team_name: 'Test Club',
    team_abbreviation: 'TST',
    kicker: 'Test Rule',
    tone: 'watch',
    category: 'watch',
    title: 'The Test Club has a neutral bullpen read tonight.',
    body: 'The current bullpen shape is specific but not especially argumentative.',
    href: '/bullpen?view=board&team=TST&source=four-beat-stories',
    cta: 'Open the team board',
    strength: 40,
    lead_dimension: null,
    lead_dimension_detail: null,
    beats: [
      {
        key: 'signal',
        label: 'Signal',
        text: 'The Test Club has a neutral bullpen read tonight.',
      },
      {
        key: 'evidence',
        label: 'Evidence',
        text: 'The board has ordinary availability and workload shape.',
      },
      {
        key: 'mechanism',
        label: 'Mechanism',
        text: 'The public story remains descriptive.',
      },
      {
        key: 'implication',
        label: 'Implication',
        text: 'There is no forced drama in the read.',
      },
    ],
    computed: {
      conditions: {},
      workload: {
        total_pitches: 70,
        participant_count: 5,
        top_arm_count: 3,
        top_share: 0.5,
        concentration_level: 'none',
        concentration_descriptor: 'no concentration',
        per_arm_pitches: 14,
      },
      availability: {
        available: 4,
        available_share: 0.5,
        total: 8,
      },
      season_era: {
        available: true,
        era: 4.21,
        rank: 18,
        rank_total: 30,
        strong_results: false,
        solid_results: false,
      },
      high_risk_arms: 0,
      high_risk_arm_count: 0,
      high_risk_arm_names: [],
      roster_unavailable_arms: 0,
      clean_trust_count: 2,
      clean_trust_names: ['Example Closer', 'Example Setup'],
      clean_option_count: 3,
    },
    ...overrides,
  }
}

const tensionStory = story({
  story_id: '158:sustainability_question',
  rule_key: 'sustainability_question',
  rule_label: 'Sustainability Question',
  team_id: 158,
  team_name: 'Milwaukee Brewers',
  team_abbreviation: 'MIL',
  abbr: 'MIL',
  tone: 'stress',
  category: 'stressed',
  title: 'The Milwaukee Brewers bullpen has pitched well this year, but they are leaning on it hard tonight.',
  body: 'Their current bullpen group owns a strong season ERA while recent workload sits high.',
  strength: 118,
  lead_dimension: 'workload_high',
  lead_dimension_detail: {
    dimension: 'workload_high',
    score: 840,
    reason: 'highest or heavy recent workload in the same-rule cluster',
  },
  beats: [
    {
      key: 'signal',
      label: 'Signal',
      text: 'The Milwaukee Brewers bullpen has pitched well this year, but they are leaning on it hard tonight.',
    },
    {
      key: 'evidence',
      label: 'Evidence',
      text: 'Their current bullpen group owns a 3.12 season ERA, 2nd among current pens, while recent workload sits at 34.2 pitches per participating arm with 2 arms at HIGH or CRITICAL fatigue.',
    },
    {
      key: 'mechanism',
      label: 'Mechanism',
      text: "That does not say the results are changing; it does make tonight's clean innings feel more expensive to spend.",
    },
    {
      key: 'implication',
      label: 'Implication',
      text: 'Tonight, Trevor Megill is still the clean Trust Arm path, so the watch is how early that lane has to open.',
    },
  ],
  computed: {
    conditions: {
      season_era_strong: true,
      heavy_recent_workload: true,
      workload_concentrated: false,
      depleted_depth: false,
    },
    workload: {
      total_pitches: 171,
      participant_count: 5,
      top_arm_count: 3,
      top_share: 0.58,
      concentration_level: 'none',
      concentration_descriptor: 'no concentration',
      per_arm_pitches: 34.2,
    },
    availability: {
      available: 6,
      available_share: 0.75,
      total: 8,
    },
    season_era: {
      available: true,
      era: 3.12,
      rank: 2,
      rank_total: 30,
      strong_results: true,
      solid_results: true,
    },
    high_risk_arms: 2,
    high_risk_arm_count: 2,
    high_risk_arm_names: ['Abner Uribe', 'Elvis Peguero'],
    roster_unavailable_arms: 0,
    clean_trust_count: 1,
    clean_trust_names: ['Trevor Megill'],
    clean_option_count: 5,
  },
})

const superlativeStory = story({
  story_id: '136:pressure_distribution',
  rule_key: 'pressure_distribution',
  rule_label: 'Pressure Distribution',
  team_id: 136,
  team_name: 'Seattle Mariners',
  team_abbreviation: 'SEA',
  abbr: 'SEA',
  tone: 'rest',
  category: 'rested',
  title: 'The Seattle Mariners have pressure spread across the pen tonight.',
  body: 'Recent relief work stayed light and broad.',
  strength: 94,
  lead_dimension: 'participation_broad',
  lead_dimension_detail: {
    dimension: 'participation_broad',
    score: 760,
    reason: 'broadest participation breadth in the same-rule cluster',
  },
  beats: [
    {
      key: 'signal',
      label: 'Signal',
      text: 'The Seattle Mariners have pressure spread across the pen tonight.',
    },
    {
      key: 'evidence',
      label: 'Evidence',
      text: 'Seven arms shared recent relief work at 14.0 pitches per participating arm.',
    },
    {
      key: 'mechanism',
      label: 'Mechanism',
      text: 'When recent work is light and spread out, the pen tends to have more room to maneuver tonight.',
    },
    {
      key: 'implication',
      label: 'Implication',
      text: 'Tonight, multiple clean options are available behind the trust lane.',
    },
  ],
  computed: {
    conditions: {
      workload_light: true,
      broad_participation: true,
      workload_concentrated: false,
      heavy_recent_workload: false,
      depleted_depth: false,
    },
    workload: {
      total_pitches: 98,
      participant_count: 7,
      top_arm_count: 3,
      top_share: 0.44,
      concentration_level: 'none',
      concentration_descriptor: 'no concentration',
      per_arm_pitches: 14,
    },
    availability: {
      available: 8,
      available_share: 1,
      total: 8,
    },
    season_era: {
      available: true,
      era: 3.76,
      rank: 8,
      rank_total: 30,
      strong_results: true,
      solid_results: true,
    },
    high_risk_arms: 0,
    high_risk_arm_count: 0,
    high_risk_arm_names: [],
    roster_unavailable_arms: 0,
    clean_trust_count: 3,
    clean_trust_names: ['Andres Munoz', 'Matt Brash', 'Gabe Speier'],
    clean_option_count: 6,
  },
})

const neutralStory = story({
  story_id: '141:neutral_watch',
  rule_key: 'neutral_watch',
  rule_label: 'Neutral Watch',
  team_id: 141,
  team_name: 'Toronto Blue Jays',
  team_abbreviation: 'TOR',
  abbr: 'TOR',
  title: 'The Toronto Blue Jays have a straightforward bullpen read tonight.',
  beats: [
    {
      key: 'signal',
      label: 'Signal',
      text: 'The Toronto Blue Jays have a straightforward bullpen read tonight.',
    },
    {
      key: 'evidence',
      label: 'Evidence',
      text: 'The current board has ordinary availability and workload distribution.',
    },
    {
      key: 'mechanism',
      label: 'Mechanism',
      text: 'Nothing in the current read creates a sharp public argument.',
    },
    {
      key: 'implication',
      label: 'Implication',
      text: 'The honest post framing is mild.',
    },
  ],
})

const dashboard = {
  freshness: { data_through: '2026-06-17' },
  four_beat_stories: {
    capability: 'four_beat_story_template_v1',
    enabled: true,
    items: [neutralStory, superlativeStory, tensionStory],
  },
}

test('postability selector is deterministic and ranks tension and superlative stories above neutral reads', () => {
  const first = getPrivatePostTakes(dashboard)
  const second = getPrivatePostTakes(JSON.parse(JSON.stringify(dashboard)))

  assert.deepEqual(
    first.map(take => [take.abbr, take.postability.score]),
    second.map(take => [take.abbr, take.postability.score]),
  )
  assert.equal(first[0].abbr, 'MIL')

  const byTeam = Object.fromEntries(first.map(take => [take.abbr, take]))
  assert.ok(byTeam.MIL.postability.hasTension)
  assert.ok(byTeam.SEA.postability.hasSuperlative)
  assert.equal(byTeam.TOR.postability.hasTension, false)
  assert.equal(byTeam.TOR.postability.hasSuperlative, false)
  assert.ok(byTeam.MIL.postability.score > byTeam.TOR.postability.score)
  assert.ok(byTeam.SEA.postability.score > byTeam.TOR.postability.score)
})

test('drafts use real four-beat values and avoid fabricated stats', () => {
  const [take] = getPrivatePostTakes(dashboard)
  const draftText = flattenTakeDrafts(take).map(draft => draft.text).join('\n\n')
  const factValues = take.facts.items.map(fact => fact.value).join(' | ')

  for (const expected of [
    '6/8 arms available',
    '1 clean Trust Arm',
    '5 clean options',
    '3.12 current-pen ERA, No. 2 of 30',
    '2 HIGH/CRITICAL arms (Abner Uribe and Elvis Peguero)',
  ]) {
    assert.ok(draftText.includes(expected) || factValues.includes(expected), `missing real value: ${expected}`)
  }
  assert.equal(draftText.includes('9/9'), false)
  assert.equal(draftText.includes('No. 1 of 30'), false)
})

test('each selected take has distinct Reddit, LinkedIn, and X drafts with team-sub and league Reddit versions', () => {
  for (const take of getPrivatePostTakes(dashboard)) {
    assert.ok(take.drafts.reddit.league.text)
    assert.ok(take.drafts.reddit.team.text)
    assert.ok(take.drafts.linkedin.text)
    assert.ok(take.drafts.x.lead)
    assert.notEqual(take.drafts.reddit.league.text, take.drafts.reddit.team.text)
    assert.notEqual(take.drafts.reddit.league.text, take.drafts.linkedin.text)
    assert.notEqual(take.drafts.linkedin.text, take.drafts.x.text)
    assert.ok(take.drafts.reddit.team.audience.includes(`${take.abbr} team subreddit`))
  }
})

test('Reddit and X do not center the product while LinkedIn can mention it, and X lead stays under the limit', () => {
  for (const take of getPrivatePostTakes(dashboard)) {
    const redditText = `${take.drafts.reddit.league.text}\n${take.drafts.reddit.team.text}`
    assert.equal(redditText.includes('BaseballOS'), false)
    assert.equal(take.drafts.x.text.includes('BaseballOS'), false)
    assert.equal(take.drafts.linkedin.text.includes('BaseballOS'), true)
    assert.ok(take.drafts.x.lead.length <= X_LEAD_CHARACTER_LIMIT)
    assert.equal(take.drafts.x.characterCount, take.drafts.x.lead.length)
  }
})

test('private posts route is obscure, noindexed, robots-excluded, and not in navigation', () => {
  const route = APP_ROUTES.find(item => item.path === PRIVATE_POSTS_PATH)
  const navHtml = render(React.createElement(Sidebar))
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  const robots = readFileSync(new URL('../public/robots.txt', import.meta.url), 'utf8')

  assert.ok(route?.Component)
  assert.notEqual(PRIVATE_POSTS_PATH, '/posts')
  assert.match(PRIVATE_POSTS_PATH, /^\/posts-[a-z0-9-]{8,}$/)
  assert.equal(htmlIncludes(navHtml, `href="${PRIVATE_POSTS_PATH}"`), false)
  assert.ok(robots.includes(`Disallow: ${PRIVATE_POSTS_PATH}`))
  assert.deepEqual(config.headers?.[0], {
    source: PRIVATE_POSTS_PATH,
    headers: [
      {
        key: 'X-Robots-Tag',
        value: 'noindex, nofollow, noarchive',
      },
    ],
  })
  assert.equal(PRIVATE_POSTS_ROBOTS, 'noindex,nofollow,noarchive')
  assert.deepEqual(config.rewrites[0], {
    source: '/team/(.*)',
    destination: '/team/index.html',
  })
  assert.deepEqual(config.rewrites[1], {
    source: '/(.*)',
    destination: '/index.html',
  })
})

test('private posts surface renders selected takes, internals, and copy affordances', () => {
  const html = render(React.createElement(PrivatePostsView, { dashboard }))

  assert.ok(htmlIncludes(html, 'POSTABLE TAKES'))
  assert.ok(htmlIncludes(html, 'data-private-posts-path="/posts-bpen-7f3d9c"'))
  assert.ok(htmlIncludes(html, 'Milwaukee Brewers bullpen has pitched well'))
  assert.ok(htmlIncludes(html, 'Story Authority'))
  assert.ok(htmlIncludes(html, 'Raw Numbers'))
  assert.ok(htmlIncludes(html, 'data-copy-draft="Reddit - league-wide"'))
  assert.ok(htmlIncludes(html, 'data-copy-draft="Reddit - team subreddit"'))
  assert.ok(htmlIncludes(html, 'data-copy-draft="LinkedIn"'))
  assert.ok(htmlIncludes(html, 'data-copy-draft="X lead tweet"'))
})
