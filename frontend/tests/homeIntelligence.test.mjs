import assert from 'node:assert/strict'
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

const { HomeView } = await server.ssrLoadModule('/src/components/home/Home.jsx')
const {
  default: BullpenStories,
  StoryPresentation,
  shouldRenderStoryContext,
} = await server.ssrLoadModule('/src/components/home/BullpenStories.jsx')
const { default: RankingsPreview } = await server.ssrLoadModule('/src/components/home/RankingsPreview.jsx')
const {
  getHeroStory,
  getLeagueCards,
  getLeagueContext,
  getBullpenStories,
  getRankingsPreview,
  getTodayWatchItems,
  getMastheadView,
  STORIES_FALLBACK,
  STORY_TITLE_GUIDELINES,
} = await server.ssrLoadModule('/src/components/home/homeIntelligenceView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

// League dashboard payload shaped like /api/bullpen/dashboard.
const dashboard = {
  capability: 'bullpen_dashboard',
  ranking_applied: false,
  selection_made: false,
  context: {
    health: { state: 'strained', label: 'Several bullpens are working through heavy recent usage.', reasons: [] },
    metrics: {
      total_relievers: 64, available: 38, monitor: 14, restricted: 9,
      pct_available: 59, pct_restricted: 14,
    },
    confidence: 'high',
  },
  roles: { order: [], counts: {}, total: 64 },
  landscape: {
    capability: 'tonights_bullpen_landscape',
    reference_date: '2026-06-06',
    teams_evaluated: 8,
    games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-05', as_of_count: 6, is_today: false, message: null },
    constrained_bullpens: [
      { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL', total_relievers: 8, available: 2, monitor: 2, restricted: 4, pct_available: 25, pct_restricted: 50 },
      { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM', total_relievers: 8, available: 3, monitor: 2, restricted: 3, pct_available: 37, pct_restricted: 37 },
    ],
    available_bullpens: [
      { team_id: 120, team_name: 'Washington Nationals', team_abbreviation: 'WSH', total_relievers: 8, available: 6, monitor: 1, restricted: 1, pct_available: 75, pct_restricted: 12 },
      { team_id: 137, team_name: 'San Francisco Giants', team_abbreviation: 'SF', total_relievers: 8, available: 5, monitor: 2, restricted: 1, pct_available: 62, pct_restricted: 12 },
    ],
    monitoring_concentration: [
      { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR', total_relievers: 8, available: 4, monitor: 4, restricted: 0, pct_available: 50, pct_restricted: 0 },
    ],
    notes: [],
  },
  freshness: { data_through: '2026-06-05', last_successful_sync: '2026-06-06T08:00:00Z', is_current: true, sync_status: 'success' },
  availability_summary: { statuses: {} },
}

const observations = {
  contractState: 'available',
  observations: [
    {
      observation_id: 'obs-1', observation_type: 'workload_pressure', family: 'workload_pressure',
      severity: 'elevated', title: 'Bullpen workload pressure is elevated.',
      summary: 'Recent appearance density is elevated across several tracked bullpens.',
      evidence: [
        {
          evidence_id: 'obs-1-evidence',
          source: 'baseballos_v5_deterministic_sample_state',
          source_type: 'trusted_platform_state',
          label: 'Elevated workload record count',
          value: 3,
          freshness_status: 'current',
          data_through: '2026-06-05',
        },
      ],
      freshness: { status: 'current', data_through: '2026-06-05' },
      confidence: { status: 'medium' },
    },
  ],
}

const continuityNote = 'The same core relievers have carried most of the bullpen workload over the last 10 days.'
const contextNote = 'Recent bullpen work has picked up: 4 appearances and 72 pitches over the last 7 days, up from 2 appearances and 24 pitches the week before.'

function dashboardWithMonitoringContinuity(base = dashboard) {
  return {
    ...base,
    landscape: {
      ...base.landscape,
      monitoring_concentration: base.landscape.monitoring_concentration.map((entry, index) => (index === 0
        ? {
            ...entry,
            continuity_note: continuityNote,
            continuity: {
              type: 'workload_concentration',
              window_days: 10,
              data_through_date: '2026-06-05',
              evidence: { bullpen_appearances: 10 },
              limitations: [],
            },
          }
        : entry)),
    },
  }
}

function dashboardWithMonitoringContext(base = dashboard) {
  const entry = {
    team_id: 141,
    context_note: contextNote,
    context: {
      type: 'usage_demand',
      window_days: 7,
      data_through_date: '2026-06-05',
      evidence: {
        trend: 'increasing_demand',
        bullpen_appearances_last_7: 4,
        bullpen_appearances_prev_7: 2,
        bullpen_pitches_last_7: 72,
        bullpen_pitches_prev_7: 24,
      },
      limitations: [],
    },
  }
  return {
    ...base,
    story_context: {
      capability: 'bullpen_context_story_v1',
      teams: {
        141: {
          ...entry,
          by_type: {
            usage_demand: entry,
          },
        },
      },
    },
  }
}

// ── Hero story ──────────────────────────────────────────────────────────────

test('the hero leads with the most constrained bullpen', () => {
  const hero = getHeroStory(dashboard)
  assert.ok(hero.hasStory)
  assert.equal(hero.angle, 'stress')
  assert.equal(hero.team.teamName, 'Milwaukee Brewers')
  assert.ok(/4 of the pen/.test(hero.observation))
  assert.ok(hero.whyItMatters.length > 0)
})

test('the hero headline states what the data shows, not a forecast', () => {
  const hero = getHeroStory(dashboard)
  assert.match(hero.headline, /thinnest late-inning margin in baseball today/)
  // No drama, no fortune-telling.
  for (const phrase of [/running out/i, /collapse/i, /will\s/i, /guarantee/i, /doomed/i]) {
    assert.ok(!phrase.test(hero.headline), `headline leaked: ${phrase}`)
  }
})

test('the hero falls back to the heaviest watch list, then the most rested pen', () => {
  const noStress = {
    ...dashboard,
    landscape: { ...dashboard.landscape, constrained_bullpens: [] },
  }
  const watchHero = getHeroStory(noStress)
  assert.equal(watchHero.angle, 'concentration')
  assert.equal(watchHero.team.teamName, 'Toronto Blue Jays')
  assert.match(watchHero.headline, /keep asking the same relievers for the heavy lifting/)

  const restOnly = {
    ...dashboard,
    landscape: { ...dashboard.landscape, constrained_bullpens: [], monitoring_concentration: [] },
  }
  const restHero = getHeroStory(restOnly)
  assert.equal(restHero.angle, 'rest')
  assert.equal(restHero.team.teamName, 'Washington Nationals')
  assert.match(restHero.headline, /more ways through the late innings than anyone today/)
})

test('a quiet league day still produces a hero story', () => {
  const quiet = getHeroStory({})
  assert.equal(quiet.hasStory, false)
  assert.equal(quiet.angle, 'quiet')
  assert.ok(quiet.headline.length > 0)
  assert.ok(quiet.whyItMatters.length > 0)
})

test('story candidates attach matching continuity from the dashboard payload', () => {
  const concentrationNote = 'Core One and Core Two handled 8 of 10 bullpen appearances over the last 10 days.'
  const easingNote = 'Bullpen flexibility has improved over the last 14 days.'
  const continuityDashboard = {
    ...dashboard,
    continuity: {
      capability: 'bullpen_continuity_v1',
      teams: {
        141: {
          continuity_note: concentrationNote,
          continuity: {
            type: 'workload_concentration',
            window_days: 10,
            data_through_date: '2026-06-05',
            evidence: { bullpen_appearances: 10 },
            limitations: [],
          },
          by_type: {
            workload_concentration: {
              continuity_note: concentrationNote,
              continuity: {
                type: 'workload_concentration',
                window_days: 10,
                data_through_date: '2026-06-05',
                evidence: { bullpen_appearances: 10 },
                limitations: [],
              },
            },
          },
        },
        120: {
          continuity_note: easingNote,
          continuity: {
            type: 'workload_easing',
            window_days: 14,
            data_through_date: '2026-06-05',
            evidence: { workload_easing_signal_count: 3 },
            limitations: [],
          },
          by_type: {
            workload_easing: {
              continuity_note: easingNote,
              continuity: {
                type: 'workload_easing',
                window_days: 14,
                data_through_date: '2026-06-05',
                evidence: { workload_easing_signal_count: 3 },
                limitations: [],
              },
            },
          },
        },
      },
    },
  }
  const workloadHero = getHeroStory({
    ...continuityDashboard,
    landscape: { ...continuityDashboard.landscape, constrained_bullpens: [] },
  })
  const recoveryHero = getHeroStory({
    ...continuityDashboard,
    landscape: {
      ...continuityDashboard.landscape,
      constrained_bullpens: [],
      monitoring_concentration: [],
    },
  })

  assert.equal(workloadHero.storyKind, 'team_workload_continuity')
  assert.equal(workloadHero.continuity_note, concentrationNote)
  assert.equal(workloadHero.continuity.type, 'workload_concentration')
  assert.equal(recoveryHero.storyKind, 'team_recovery')
  assert.equal(recoveryHero.continuity_note, easingNote)
  assert.equal(recoveryHero.continuity.type, 'workload_easing')
  assert.ok(!JSON.stringify([workloadHero, recoveryHero]).includes('Narrative Memory'))
})

test('stories without continuity stay unchanged', () => {
  const hero = getHeroStory(dashboard)
  assert.equal(hero.continuity_note, undefined)
  assert.equal(hero.continuity, undefined)
})

test('the flagship story renders continuity when the selected story carries it', () => {
  const continuityDashboard = dashboardWithMonitoringContinuity({
    ...dashboard,
    landscape: {
      ...dashboard.landscape,
      constrained_bullpens: [],
    },
  })
  const html = render(React.createElement(HomeView, { dashboard: continuityDashboard, observations }))

  assert.ok(htmlIncludes(html, 'The Toronto Blue Jays keep asking the same relievers for the heavy lifting'))
  assert.ok(htmlIncludes(html, continuityNote))
  for (const phrase of [
    'Narrative Memory',
    'algorithm',
    'model',
    'confidence score',
    'fatigue score',
    'story has been developing',
  ]) {
    assert.ok(!htmlIncludes(html, phrase), `rendered forbidden phrase: ${phrase}`)
  }
})

test('the flagship story renders context after continuity when evidence fits the story', () => {
  const contextDashboard = dashboardWithMonitoringContext(dashboardWithMonitoringContinuity({
    ...dashboard,
    landscape: {
      ...dashboard.landscape,
      constrained_bullpens: [],
    },
  }))
  const hero = getHeroStory(contextDashboard)
  const html = render(React.createElement(HomeView, { dashboard: contextDashboard, observations }))
  const continuityIndex = html.indexOf(continuityNote)
  const contextIndex = html.indexOf(contextNote)

  assert.equal(hero.storyKind, 'team_workload_continuity')
  assert.equal(hero.continuity_note, continuityNote)
  assert.equal(hero.context_note, contextNote)
  assert.equal(hero.context.type, 'usage_demand')
  assert.ok(continuityIndex >= 0, 'continuity note should render')
  assert.ok(contextIndex >= 0, 'context note should render')
  assert.ok(contextIndex > continuityIndex, 'context should render after continuity')
})

test('story presentation renders a labeled observation without empty support sections', () => {
  const html = render(React.createElement(BullpenStories, {
    showCta: false,
    stories: {
      hasStories: true,
      items: [{
        kicker: 'Pressure Watch',
        tone: 'stress',
        title: 'A pen has less room to breathe late',
        body: 'The late-inning bench is thinner here too.',
        storyKind: 'team_pressure',
        teamId: 121,
      }],
    },
  }))

  assert.ok(htmlIncludes(html, 'Observation'))
  assert.ok(htmlIncludes(html, 'The late-inning bench is thinner here too.'))
  assert.ok(!htmlIncludes(html, 'Continuity'))
  assert.ok(!htmlIncludes(html, 'Context'))
})

test('context does not render automatically just because a note exists', () => {
  const story = {
    storyKind: 'league_workload',
    kicker: 'Across The League',
    tone: 'watch',
    title: 'The heavy lifting is not isolated to one bullpen',
    body: 'Heavy recent work is showing up in more than one place.',
    context_note: contextNote,
  }
  const html = render(React.createElement(StoryPresentation, { story, compact: true }))

  assert.equal(shouldRenderStoryContext(story), false)
  assert.ok(htmlIncludes(html, 'Observation'))
  assert.ok(!htmlIncludes(html, contextNote))
  assert.ok(!htmlIncludes(html, 'Context'))
})

test('context renders for flagship team stories but stays off compact normal cards', () => {
  const allowedFlagship = {
    storyKind: 'team_pressure',
    teamId: 121,
    title: 'A thin-margin team story',
    body: 'This pen has less room to breathe late.',
    context_note: contextNote,
  }
  const generic = {
    storyKind: 'general_note',
    teamId: 121,
    title: 'A generic team note',
    body: 'This is a team note without a context presentation lane.',
    context_note: contextNote,
  }
  const flagshipHtml = render(React.createElement(StoryPresentation, { story: allowedFlagship }))
  const compactHtml = render(React.createElement(StoryPresentation, { story: allowedFlagship, compact: true }))

  assert.equal(shouldRenderStoryContext(allowedFlagship), true)
  assert.equal(shouldRenderStoryContext(allowedFlagship, { compact: true }), false)
  assert.equal(shouldRenderStoryContext(generic), false)
  assert.ok(htmlIncludes(flagshipHtml, 'Context'))
  assert.ok(htmlIncludes(flagshipHtml, contextNote))
  assert.ok(!htmlIncludes(compactHtml, contextNote))
})

test('compact cards render context only for major workload continuity stories', () => {
  const major = {
    storyKind: 'team_workload_continuity',
    teamId: 141,
    title: 'A workload story with context',
    body: 'This bullpen keeps leaning on the same group.',
    continuity_note: continuityNote,
    context_note: contextNote,
    context: {
      type: 'usage_demand',
      evidence: { trend: 'increasing_demand' },
    },
  }
  const weak = {
    ...major,
    context: {
      type: 'usage_demand',
      evidence: { trend: 'insufficient_data' },
    },
  }
  const html = render(React.createElement(StoryPresentation, { story: major, compact: true }))

  assert.equal(shouldRenderStoryContext(major, { compact: true }), true)
  assert.equal(shouldRenderStoryContext(weak, { compact: true }), false)
  assert.ok(htmlIncludes(html, 'Context'))
  assert.ok(htmlIncludes(html, contextNote))
})

// ── League intelligence cards ───────────────────────────────────────────────

test('all four league intelligence cards are derived from the landscape', () => {
  const cards = getLeagueCards(dashboard)
  const byKey = Object.fromEntries(cards.map(card => [card.key, card]))
  assert.equal(cards.length, 4)
  assert.equal(byKey['most-stressed'].team.abbr, 'MIL')
  assert.equal(byKey['most-rested'].team.abbr, 'WSH')
  assert.equal(byKey['bullpen-to-watch'].team.abbr, 'TOR')
  // Two constrained clubs → the trend card reads league-wide stress.
  assert.equal(byKey['biggest-trend'].stat, '2')
  assert.match(byKey['biggest-trend'].line, /heavy lifting is not isolated to one bullpen/)
})

test('card copy reads like a hook, not a metric summary', () => {
  const cards = getLeagueCards(dashboard)
  const byKey = Object.fromEntries(cards.map(card => [card.key, card]))
  assert.equal(byKey['most-stressed'].line,
    'No pen has less room to breathe late today.')
  assert.equal(byKey['most-rested'].line,
    'No pen has more ways through the late innings today.')
  assert.equal(byKey['bullpen-to-watch'].line,
    'The surface can look calm while the same arms keep getting the call.')
})

test('cards degrade to quiet copy when the landscape is empty', () => {
  const cards = getLeagueCards({})
  assert.equal(cards.length, 4)
  for (const card of cards) {
    assert.equal(card.team, null)
    assert.ok(card.line.length > 0)
    assert.ok(card.href)
  }
})

// ── Today briefing ──────────────────────────────────────────────────────────

test('today watch items are briefing-only and exclude the flagship club', () => {
  const hero = getHeroStory(dashboard)
  const watchItems = getTodayWatchItems(dashboard)
  assert.ok(watchItems.hasStories)
  assert.equal(watchItems.items.length, 3)
  assert.ok(watchItems.items.every(item => item.teamId !== hero.team.teamId))
  assert.deepEqual(
    watchItems.items.map(item => item.title),
    [
      'Another pen has less room to breathe late',
      'Another club is leaning on the same names',
      'A rested pen has more ways through the late innings',
    ],
  )
})

test('today story cards render continuity when present and stay unchanged without it', () => {
  const html = render(React.createElement(HomeView, {
    dashboard: dashboardWithMonitoringContinuity(),
    observations,
  }))
  const plainHtml = render(React.createElement(HomeView, { dashboard, observations }))

  assert.ok(htmlIncludes(html, 'Another club is leaning on the same names'))
  assert.ok(htmlIncludes(html, continuityNote))
  assert.ok(!htmlIncludes(plainHtml, continuityNote))
})

test('today league context talks baseball and keeps the vocabulary on the fact labels', () => {
  const context = getLeagueContext(dashboard)
  assert.match(context.summary, /need rest after recent work/)
  assert.match(context.summary, /rested enough to be usable today/)
  assert.equal(context.facts.length, 3)
  assert.deepEqual(context.facts.map(fact => fact.label), [
    'Bullpen Pressure',
    'Usage Trend',
    'Rested Options',
  ])
  assert.equal(context.href, '/stories')
})

// ── Bullpen stories ─────────────────────────────────────────────────────────

test('stories are derived from the landscape without repeating the hero club', () => {
  const stories = getBullpenStories(dashboard, null)
  assert.ok(stories.hasStories)
  const titles = stories.items.map(story => story.title).join(' | ')
  // Hero features Milwaukee; the stories pick up the other clubs.
  assert.ok(!/Milwaukee/.test(titles))
  assert.ok(/Toronto Blue Jays/.test(titles))
  assert.ok(/New York Mets/.test(titles))
  assert.ok(/Washington Nationals/.test(titles))
})

test('story titles read like a baseball writer, not a system', () => {
  const stories = getBullpenStories(dashboard, null)
  const titles = stories.items.map(story => story.title)
  // Toronto (4 monitor, 0 restricted) is the hidden-workload shape.
  assert.ok(titles.includes('The Toronto Blue Jays box score looks calm. The bullpen does not.'))
  assert.ok(titles.includes('The New York Mets are managing from a thinner late-inning bench'))
})

test('governed observations are retold in editorial language, never verbatim', () => {
  const stories = getBullpenStories(dashboard, observations)
  const titles = stories.items.map(story => story.title)
  assert.ok(titles.includes('The league-wide workload picture is starting to tighten'))
  assert.ok(!titles.includes('Bullpen workload pressure is elevated.'))
})

test('observation families without an editorial translation are left off the page', () => {
  const unknownFamily = {
    contractState: 'available',
    observations: [
      { family: 'mystery_family', severity: 'monitor', title: 'Raw system text.', summary: 'Raw system summary.' },
    ],
  }
  const stories = getBullpenStories(dashboard, unknownFamily)
  const text = stories.items.map(story => `${story.title} ${story.body}`).join(' ')
  assert.ok(!text.includes('Raw system'))
})

test('unsafe or empty observation feeds are ignored', () => {
  const unsafe = { contractState: 'unavailable', observations: [{ title: 'X', summary: 'Y', family: 'trust', severity: 'monitor' }] }
  const stories = getBullpenStories(dashboard, unsafe)
  assert.ok(!stories.items.some(story => story.title === 'X'))
})

test('story list is capped and falls back gracefully', () => {
  const stories = getBullpenStories(dashboard, observations)
  assert.ok(stories.items.length <= 8)
  const empty = getBullpenStories({}, null)
  assert.equal(empty.hasStories, false)
  assert.equal(empty.fallback, STORIES_FALLBACK)
})

test('story title guidelines prefer observations over conclusions', () => {
  assert.ok(STORY_TITLE_GUIDELINES.prefer.some(line => /curiosity/i.test(line)))
  assert.ok(STORY_TITLE_GUIDELINES.avoid.some(line => /in good shape/i.test(line)))
  const stories = getBullpenStories(dashboard, observations)
  const titles = stories.items.map(story => story.title).join(' | ').toLowerCase()
  for (const weak of ['pen is in good shape', 'bullpen is healthy', 'strong availability']) {
    assert.ok(!titles.includes(weak), `conclusion-driven title leaked: ${weak}`)
  }
  assert.ok(titles.includes('rested options behind the late innings today'))
})

// ── Rankings preview ────────────────────────────────────────────────────────

test('rankings preview is placeholder-only and does not order teams', () => {
  const rankings = getRankingsPreview(dashboard)
  const byKey = Object.fromEntries(rankings.boards.map(board => [board.key, board]))
  assert.equal(rankings.boards.length, 4)
  assert.ok(byKey.shape.placeholder)
  assert.ok(byKey.recovery.placeholder)
  assert.ok(byKey.pressure.placeholder)
  assert.ok(byKey.movement.placeholder)
  for (const board of rankings.boards) {
    assert.equal(board.entries.length, 0)
    assert.ok(board.placeholderCopy.length > 0)
  }
})

test('rankings carry explicit not-ready framing', () => {
  const rankings = getRankingsPreview(dashboard)
  assert.match(rankings.framing, /Preview only/)
  assert.match(rankings.framing, /Not yet validated/)
  assert.match(rankings.framing, /Coming later/)
  assert.match(rankings.updateNote, /No rankings are active/)
})

// ── Masthead ────────────────────────────────────────────────────────────────

test('the masthead reports the data window in plain language', () => {
  const masthead = getMastheadView(dashboard, new Date('2026-06-06T12:00:00Z'))
  assert.ok(/Built from completed games through Jun 5, 2026/.test(masthead.dataLine))
  assert.ok(masthead.editionDate.includes('2026'))
  const cold = getMastheadView({}, new Date('2026-06-06T12:00:00Z'))
  assert.equal(cold.dataLine, 'Waiting on the first completed games')
})

// ── Rendering & placement ───────────────────────────────────────────────────

test('the homepage renders the morning briefing sections in order', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  const sections = [
    'What BaseballOS Sees Today',
    'Three Things To Watch',
    'League Context',
  ]
  let lastIndex = -1
  for (const section of sections) {
    const index = html.indexOf(section)
    assert.ok(index >= 0, `missing section: ${section}`)
    assert.ok(index > lastIndex, `out of order: ${section}`)
    lastIndex = index
  }
})

test('today is curated: no team explorer, feedback CTA intact', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  assert.ok(!htmlIncludes(html, 'Explore Every Bullpen'))
  assert.ok(!htmlIncludes(html, 'arms tracked'))
  assert.ok(!htmlIncludes(html, 'The Story Feed'))
  assert.ok(htmlIncludes(html, 'Help shape BaseballOS'))
})

test('today shows three briefing watch items without repeating Stories titles', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'Another pen has less room to breathe late'))
  assert.ok(htmlIncludes(html, 'Another club is leaning on the same names'))
  assert.ok(htmlIncludes(html, 'A rested pen has more ways through the late innings'))
  // Full-feed story titles stay in Stories, not on the briefing.
  assert.ok(!htmlIncludes(html, 'box score looks calm'))
  assert.ok(!htmlIncludes(html, 'managing from a thinner late-inning bench'))
  assert.ok(!htmlIncludes(html, 'No club has more late-inning options'))
  assert.ok(!htmlIncludes(html, 'The workload underneath is worth watching'))
})

test('today ends with short league context and a Stories handoff', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'League Context'))
  assert.ok(htmlIncludes(html, 'Bullpen Pressure'))
  assert.ok(htmlIncludes(html, 'Usage Trend'))
  assert.ok(htmlIncludes(html, 'Rested Options'))
  assert.ok(htmlIncludes(html, 'href="/stories"'))
  assert.ok(htmlIncludes(html, 'Open Stories for more observations'))
})

test('the hero renders the flagship observation with Why It Matters', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'Why It Matters'))
  assert.ok(htmlIncludes(html, 'Milwaukee Brewers'))
  assert.ok(htmlIncludes(html, 'thinnest late-inning margin in baseball today'))
  assert.ok(htmlIncludes(html, 'Step inside the MIL pen'))
})

test('the rankings preview is not part of the short Today briefing', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  assert.ok(!htmlIncludes(html, 'Rankings Preview'))
  assert.ok(!htmlIncludes(html, 'No rankings are active on this page.'))
})

test('the homepage keeps a path to the original dashboard', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'href="/dashboard"'))
})

test('loading and error states render without data', () => {
  const loadingHtml = render(React.createElement(HomeView, { dashboard: null, loading: true }))
  assert.ok(htmlIncludes(loadingHtml, 'bullpen report'))
  const errorHtml = render(React.createElement(HomeView, { dashboard: null, error: 'API 500' }))
  assert.ok(htmlIncludes(errorHtml, 'API 500'))
})

// ── Depth links: every strong hook leads somewhere real ────────────────────

test('the hero primary CTA deep-links into the featured club’s bullpen board', () => {
  const hero = getHeroStory(dashboard)
  assert.equal(hero.team.href, '/bullpen?view=board&team=MIL&source=home-hero')
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'view=board') && htmlIncludes(html, 'team=MIL'))
})

test('league intelligence cards link to team boards, and the trend to the league view', () => {
  const cards = getLeagueCards(dashboard)
  const byKey = Object.fromEntries(cards.map(card => [card.key, card]))
  assert.ok(byKey['most-stressed'].href.includes('team=MIL'))
  assert.ok(byKey['most-rested'].href.includes('team=WSH'))
  assert.ok(byKey['bullpen-to-watch'].href.includes('team=TOR'))
  assert.equal(byKey['biggest-trend'].href, '/dashboard')
})

test('team stories step into the club; league and data notes open their own surfaces', () => {
  const mixedObservations = {
    contractState: 'available',
    observations: [
      {
        family: 'workload_pressure',
        severity: 'elevated',
        title: 'x',
        summary: 'y',
        evidence: [
          {
            label: 'Elevated workload record count',
            value: 3,
            source: 'test_observation_feed',
            source_type: 'trusted_platform_state',
            freshness_status: 'current',
          },
        ],
        freshness: { status: 'current' },
        confidence: { status: 'medium' },
      },
      {
        family: 'trust',
        severity: 'significant',
        title: 'x',
        summary: 'y',
        evidence: [
          {
            label: 'Trust limitation state',
            value: 'represented',
            source: 'test_observation_feed',
            source_type: 'trusted_platform_state',
            freshness_status: 'current',
          },
        ],
        freshness: { status: 'current' },
        confidence: { status: 'medium' },
      },
    ],
  }
  const stories = getBullpenStories(dashboard, mixedObservations)
  for (const story of stories.items) {
    assert.ok(story.href, `story has no destination: ${story.title}`)
    if (story.teamId != null) {
      assert.ok(story.href.includes('/bullpen?') && story.href.includes('team='))
      assert.equal(story.cta, 'Step inside this pen')
    }
  }
  const leagueNote = stories.items.find(story => story.kicker === 'Usage Trend' && story.teamId == null)
  assert.equal(leagueNote.href, '/dashboard')
  assert.equal(leagueNote.cta, 'See the league view')
  const dataNote = stories.items.find(story => story.kicker === 'Data Note')
  assert.equal(dataNote.href, '/trust')
  assert.equal(dataNote.cta, 'Open the full picture')
})

test('a story without a destination renders as plain copy, not a pretend link', () => {
  const html = render(React.createElement(BullpenStories, {
    stories: {
      hasStories: true,
      items: [{ kicker: 'League Note', tone: 'neutral', title: 'No destination here', body: 'Copy only.', href: null }],
      fallback: '',
    },
  }))
  assert.ok(htmlIncludes(html, 'No destination here'))
  // The only anchor in the section is the standing hand-off to the feed.
  assert.equal((html.match(/<a /g) || []).length, 1)
  assert.ok(htmlIncludes(html, 'href="/stories"'))
  assert.ok(htmlIncludes(html, 'Open Stories for more observations'))
  assert.ok(!htmlIncludes(html, 'Open the full picture'), 'no card CTA should render without a destination')
})

test('rankings preview renders no live rows or team links', () => {
  const rankings = getRankingsPreview(dashboard)
  assert.ok(rankings.boards.every(board => board.placeholder))
  assert.ok(rankings.boards.every(board => board.entries.length === 0))
  const html = render(React.createElement(RankingsPreview, { rankings }))
  const anchorCount = (html.match(/<a /g) || []).length
  assert.equal(anchorCount, 0)
  assert.ok(!htmlIncludes(html, 'WSH'))
  assert.ok(!htmlIncludes(html, 'MIL'))
})

test('CTA language is specific, never vague', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations }))
  assert.ok(htmlIncludes(html, 'Step inside the MIL pen'))
  assert.ok(htmlIncludes(html, 'Open Stories for more observations'))
  for (const vague of ['Learn more', 'Click here', '>Details<', 'Read more']) {
    assert.ok(!htmlIncludes(html, vague), `vague CTA leaked: ${vague}`)
  }
})

// ── Guardrails: language stays descriptive and human ───────────────────────

test('the homepage avoids advisory, ranking, and prediction language', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations })).toLowerCase()
  for (const term of [
    'should use', 'best option', 'best bullpen', 'worst bullpen', 'best arm',
    'recommended', 'recommendation', 'strongest bullpen', 'weakest bullpen',
    'expected to win', 'likely to win', 'win probability', 'odds', 'projection',
    'prediction', 'preferred arm', 'will collapse', 'guaranteed', 'bet on',
    'betting', 'parlay', 'moneyline', 'injury', 'manager should',
  ]) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})

test('the homepage avoids raw system phrasing', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations })).toLowerCase()
  for (const term of [
    'availability inventory', 'readiness limitations', 'limitations are present',
    'trusted snapshot', 'snapshot', 'data state', 'data_state', 'contract',
    'fail closed', 'fail_closed', 'governance',
    // Mechanical phrasing the language layer exists to prevent in prose.
    'register as', 'limited recovery window', 'availability context',
    'carrying workload concentration', 'workload-restricted',
  ]) {
    assert.ok(!html.includes(term), `leaked system phrasing: ${term}`)
  }
})

test('the homepage avoids repeated fresh-pen shorthand in story copy', () => {
  const html = render(React.createElement(HomeView, { dashboard, observations })).toLowerCase()
  for (const phrase of [
    'fresh pen',
    'fresh arms',
    'fresher bullpen',
    'freshest bullpen',
    'come in fresh',
  ]) {
    assert.ok(!html.includes(phrase), `stale story shorthand leaked: ${phrase}`)
  }
})
