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
  STORY_TYPE_DISPLAY,
  getStoryCardView,
  storyCardHasBannedLanguage,
} = await server.ssrLoadModule('/src/components/bullpen/board/storyCardView.js')
const {
  getTeamStory,
} = await server.ssrLoadModule('/src/utils/api.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (props) => renderToStaticMarkup(React.createElement(StoryCard, props))
const OLD_PUBLIC_LABELS = [
  'Depth Pressure',
  'Bullpen Route Change',
  'Starter Coverage Pressure',
  'Workload Concentration',
  'Clean Options',
  'Stable Bullpen Core',
]
const OLD_INTERNAL_TYPES = [
  'depth_pressure',
  'core_transition',
  'rotation_pressure',
  'concentration_pressure',
  'optionality_strength',
  'stable_core',
]

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
    story_type: 'sustainability_question',
    headline: "Kansas City's bullpen is running through three arms",
    observation: 'The top group has handled 94% of recent bullpen workload.',
    baseline: 'The league comparison is 58% for top-three bullpen workload.',
    cause: 'Shorter starts have created more innings for the relief group.',
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

  assert.ok(htmlIncludes(html, 'Bullpen Note'))
  assert.ok(htmlIncludes(html, "Kansas City&#x27;s bullpen is running through three arms"))
  assert.ok(htmlIncludes(html, 'Sustainability Question'))
  assert.ok(htmlIncludes(html, 'Whether the current usage pattern can keep functioning.'))
  assert.ok(htmlIncludes(html, 'Data through Jun 20, 2026'))
  assert.ok(htmlIncludes(html, 'Written from BaseballOS data'))
  assert.ok(htmlIncludes(html, 'What changed'))
  assert.ok(htmlIncludes(html, 'Comparison point'))
  assert.ok(htmlIncludes(html, 'Why it happened'))
  assert.ok(htmlIncludes(html, 'What it creates'))
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
    'deterministic',
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

  assert.ok(htmlIncludes(html, 'Story note is quiet right now'))
  assert.ok(htmlIncludes(html, 'holding this note until the bullpen context has a clear enough signal'))
  assert.equal(storyCardHasBannedLanguage(html), false)
})

test('StoryCard handles loading and error states cleanly', () => {
  const loadingHtml = render({ loading: true })
  const errorHtml = render({ error: 'API 500', onRetry: () => {} })

  assert.ok(htmlIncludes(loadingHtml, 'Checking the team story note'))
  assert.ok(htmlIncludes(errorHtml, 'Story note paused'))
  assert.ok(htmlIncludes(errorHtml, 'bullpen board is still available'))
  assert.ok(htmlIncludes(errorHtml, 'Retry note'))
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
  assert.ok(htmlIncludes(html, 'What changed'))
  assert.ok(htmlIncludes(html, 'What it creates'))
  assert.ok(!htmlIncludes(html, 'Comparison point'))
})

test('StoryCard renders the public beat labels with helper text', () => {
  assert.deepEqual(
    Object.keys(STORY_TYPE_DISPLAY).sort(),
    [
      'availability_depth',
      'bridge',
      'coverage_pressure',
      'depth_constraint',
      'route_change',
      'sustainability_question',
      'trust_lane',
    ],
  )

  for (const [storyType, display] of Object.entries(STORY_TYPE_DISPLAY)) {
    const html = render({
      story: storyPayload({
        story_type: storyType,
        headline: `${display.label} is shaping this bullpen`,
        observation: `${display.label} changed the bullpen route.`,
        baseline: 'The comparison point stays visible.',
        cause: 'The cause is tied to how the innings are being covered.',
        constraint: 'The resulting constraint stays tied to the bullpen route.',
      }),
    })
    const view = getStoryCardView(storyPayload({ story_type: storyType }))

    assert.equal(view.storyType, display.label)
    assert.equal(view.storyTypeHelper, display.helper)
    assert.ok(htmlIncludes(html, display.label))
    assert.ok(htmlIncludes(html, display.helper))
    assert.equal(html.includes(storyType), false, storyType)
    assert.ok(htmlIncludes(html, 'What changed'))
    assert.ok(htmlIncludes(html, 'Comparison point'))
    assert.ok(htmlIncludes(html, 'Why it happened'))
    assert.ok(htmlIncludes(html, 'What it creates'))
    assert.equal(storyCardHasBannedLanguage(html), false)
  }
})

test('StoryCard labels the availability_depth positive beat as More Options', () => {
  const story = storyPayload({
    story_type: 'availability_depth',
    headline: 'The Royals bullpen has more rested options than most clubs today',
    observation: 'Seven relievers come in rested enough to use.',
    baseline: 'That is a deeper available board than the league norm.',
    cause: 'Recent relief work has been spread across the group.',
    constraint: 'If the game stays close, the manager can spread the late innings across several rested arms.',
  })
  const view = getStoryCardView(story)
  const html = render({ story })

  assert.equal(view.storyType, 'More Options')
  assert.equal(view.storyTypeHelper, 'How much rested late-inning depth the bullpen has to work with.')
  assert.notEqual(view.storyType, 'Bullpen story') // no longer the generic fallback
  assert.ok(htmlIncludes(html, 'More Options'))
  assert.ok(htmlIncludes(html, 'The Royals bullpen has more rested options than most clubs today'))
  assert.equal(html.includes('availability_depth'), false) // internal type not leaked
  assert.equal(storyCardHasBannedLanguage(html), false)
})

test('StoryCard labels the trust_lane beat as Trust Lane', () => {
  const story = storyPayload({
    story_type: 'trust_lane',
    headline: 'The Royals have arms available but a thin trusted late-game lane',
    observation: 'The active board lists six available arms, but only one comes in clean.',
    baseline: 'That is a wider board than the trusted late-inning lane.',
    cause: 'Most of the available arms are pitching through recent workload.',
    constraint: 'If the game tightens, the late-game plan leans back on a short list of arms.',
  })
  const view = getStoryCardView(story)
  const html = render({ story })

  assert.equal(view.storyType, 'Trust Lane')
  assert.equal(view.storyTypeHelper, 'How few rested, trusted arms the late-game plan really leans on.')
  assert.notEqual(view.storyType, 'Bullpen story') // not the generic fallback
  assert.ok(htmlIncludes(html, 'Trust Lane'))
  assert.equal(html.includes('trust_lane'), false) // internal type not leaked
  assert.equal(storyCardHasBannedLanguage(html), false)
})

test('StoryCard labels the bridge beat as Bridge Instability', () => {
  const story = storyPayload({
    story_type: 'bridge',
    headline: 'The Royals are settled at the back but fragile in the bridge',
    observation: 'The late-game core is settled, but the bullpen reaches it through volatile middle arms.',
    baseline: 'That is a thin handoff against a stable late group.',
    cause: 'The starters keep handing off early.',
    constraint: 'If the starters keep exiting early, the path to the late arms runs through a fragile middle.',
  })
  const view = getStoryCardView(story)
  const html = render({ story })

  assert.equal(view.storyType, 'Bridge Instability')
  assert.equal(view.storyTypeHelper, 'How fragile the path is from the starter to the trusted late-game arms.')
  assert.notEqual(view.storyType, 'Bullpen story') // not the generic fallback
  assert.ok(htmlIncludes(html, 'Bridge Instability'))
  assert.equal(html.includes('bridge_instability'), false) // internal type not leaked
  assert.equal(storyCardHasBannedLanguage(html), false)
})

test('StoryCard does not frame the positive availability_depth story as a warning', () => {
  const html = render({ story: storyPayload({ story_type: 'availability_depth', headline: 'More rested options today' }) })

  // Renders the neutral available shell (not the error/paused state) and shows
  // no pressure/constraint label for this positive beat.
  assert.ok(htmlIncludes(html, 'bg-dugout/75'))
  assert.equal(htmlIncludes(html, 'bg-amber/5'), false)
  assert.equal(htmlIncludes(html, 'Story note paused'), false)
  assert.equal(htmlIncludes(html, 'Coverage Pressure'), false)
  assert.equal(htmlIncludes(html, 'Depth Constraint'), false)
  assert.equal(htmlIncludes(html, 'Sustainability Question'), false)
  assert.ok(htmlIncludes(html, 'More Options'))
})

test('Phase 4B.1 leaves TeamBullpenStoryPanel mounted on the board (no migration)', () => {
  const board = readFileSync(
    new URL('../src/components/bullpen/board/BullpenBoardView.jsx', import.meta.url),
    'utf8',
  )
  assert.ok(board.includes('import TeamBullpenStoryPanel'))
  assert.ok(board.includes('<TeamBullpenStoryPanel'))
})

test('StoryCard does not display old public labels or raw internal story types', () => {
  for (const oldType of OLD_INTERNAL_TYPES) {
    const html = render({
      story: storyPayload({
        story_type: oldType,
        headline: 'The bullpen note uses the fallback label',
      }),
    })
    const view = getStoryCardView(storyPayload({ story_type: oldType }))

    assert.equal(view.storyType, 'Bullpen story')
    assert.equal(view.storyTypeHelper, null)
    assert.equal(html.includes(oldType), false, oldType)
    for (const label of OLD_PUBLIC_LABELS) {
      assert.equal(htmlIncludes(html, label), false, label)
    }
  }
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
