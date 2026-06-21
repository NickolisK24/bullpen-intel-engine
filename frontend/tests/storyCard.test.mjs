import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
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

const { default: StoryCard } = await server.ssrLoadModule('/src/components/bullpen/board/StoryCard.jsx')
const {
  getStoryCardView,
  storyCardHasBannedLanguage,
} = await server.ssrLoadModule('/src/components/bullpen/board/storyCardView.js')
const {
  getTeamStory,
} = await server.ssrLoadModule('/src/utils/api.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (props) => renderToStaticMarkup(React.createElement(StoryCard, props))

function storyPayload(overrides = {}) {
  return {
    capability: 'story_intelligence_api_v1',
    contract: 'story_intelligence_api_v1',
    contract_state: 'available',
    team_id: 118,
    team_name: 'Kansas City Royals',
    team_abbreviation: 'KC',
    as_of_date: '2026-06-20',
    state: 'story_available',
    story_available: true,
    neutral_reason: null,
    story_type: 'concentration_pressure',
    headline: "Kansas City's bullpen is running through three arms",
    observation: 'The top group has handled 94% of recent bullpen workload.',
    baseline: 'The league comparison is 58% for top-three bullpen workload.',
    cause: 'The rotation context has created more innings for the relief group.',
    constraint: 'If the same game shape repeats, the structure still points back to the same core group.',
    freshness: {
      data_through: '2026-06-20',
    },
    trust_metadata: {
      external_generation_used: false,
    },
    supporting_context: {},
    selected_observation: {},
    construction_frame: {},
    limitations: [],
    ...overrides,
  }
}

test('StoryCard renders a successful deterministic bullpen story note', () => {
  const html = render({ story: storyPayload() })

  assert.ok(htmlIncludes(html, 'Bullpen Story'))
  assert.ok(htmlIncludes(html, "Kansas City&#x27;s bullpen is running through three arms"))
  assert.ok(htmlIncludes(html, 'Concentration pressure'))
  assert.ok(htmlIncludes(html, 'Data through Jun 20, 2026'))
  assert.ok(htmlIncludes(html, 'Deterministic BaseballOS note'))
  assert.ok(htmlIncludes(html, 'What happened'))
  assert.ok(htmlIncludes(html, 'Baseline'))
  assert.ok(htmlIncludes(html, 'Why it happened'))
  assert.ok(htmlIncludes(html, 'Constraint'))
  assert.ok(htmlIncludes(html, 'The top group has handled 94% of recent bullpen workload.'))
  assert.equal(storyCardHasBannedLanguage(html), false)
})

test('StoryCard keeps internal API field names and engine terminology out of the UI', () => {
  const html = render({ story: storyPayload() }).toLowerCase()

  for (const term of [
    'story_type',
    'selected_observation',
    'construction_frame',
    'trust_metadata',
    'external_generation_used',
    'observation engine',
    'construction engine',
    'writer',
    'contract_state',
  ]) {
    assert.equal(html.includes(term), false, term)
  }
})

test('StoryCard renders a trust-first neutral state', () => {
  const html = render({
    story: storyPayload({
      contract_state: 'neutral',
      state: 'neutral',
      story_available: false,
      neutral_reason: 'no_story_observations',
      story_type: null,
      headline: null,
      observation: null,
      baseline: null,
      cause: null,
      constraint: null,
    }),
  })

  assert.ok(htmlIncludes(html, 'No bullpen story note available'))
  assert.ok(htmlIncludes(html, 'does not have a strong enough bullpen story signal'))
  assert.equal(storyCardHasBannedLanguage(html), false)
})

test('StoryCard handles loading and error states cleanly', () => {
  const loadingHtml = render({ loading: true })
  const errorHtml = render({ error: 'API 500', onRetry: () => {} })

  assert.ok(htmlIncludes(loadingHtml, 'Loading bullpen story note'))
  assert.ok(htmlIncludes(errorHtml, 'Story note unavailable'))
  assert.ok(htmlIncludes(errorHtml, 'Retry story note'))
  assert.ok(!htmlIncludes(errorHtml, 'API 500'))
})

test('StoryCard degrades gracefully when optional paragraphs are missing', () => {
  const story = storyPayload({
    baseline: null,
    cause: '',
  })
  const html = render({ story })
  const view = getStoryCardView(story)

  assert.equal(view.paragraphs.map(item => item.key).join(','), 'observation,constraint')
  assert.ok(htmlIncludes(html, 'What happened'))
  assert.ok(htmlIncludes(html, 'Constraint'))
  assert.ok(!htmlIncludes(html, '<div class="font-mono text-[10px] uppercase tracking-widest text-chalk600">Baseline</div>'))
})

test('getTeamStory calls the Story Intelligence API V1 team endpoint', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/bullpen/teams/118/story?as_of_date=2026-06-20')
    assert.equal(options.method, undefined)
    assert.equal(options.headers['Content-Type'], 'application/json')

    return {
      ok: true,
      json: async () => storyPayload(),
    }
  }

  const result = await getTeamStory(118, {
    as_of_date: '2026-06-20',
    empty: '',
    skip: null,
  })

  assert.equal(result.capability, 'story_intelligence_api_v1')
  assert.equal(result.story_available, true)
})

test('Tonight board owns the StoryCard API seam for selected teams', () => {
  const source = readFileSync(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('getTeamStory(selectedTeam)'))
  assert.ok(source.includes('<StoryCard'))
  assert.ok(!source.includes('story_observation_engine'))
  assert.ok(!source.includes('story_construction_engine'))
  assert.ok(!source.includes('story_writer'))
})
