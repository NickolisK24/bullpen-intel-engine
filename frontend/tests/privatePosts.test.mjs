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
const {
  PrivatePostsAccessDenied,
  PrivatePostsView,
} = await server.ssrLoadModule('/src/components/posts/PrivatePosts.jsx')
const {
  DRAFT_SOURCE_GENERATED,
  DRAFT_SOURCE_TEMPLATE_FALLBACK,
  PRIVATE_POSTS_PATH,
  PRIVATE_POSTS_ROBOTS,
  POST_DRAFT_PLATFORMS,
  X_LEAD_CHARACTER_LIMIT,
  auditGeneratedFactClaims,
  buildDraftGenerationPayload,
  buildGeneratedPlatformDrafts,
  buildVerifiedFactSet,
  canonicalPostableStories,
  extractStoryFacts,
  findUnverifiedNumbers,
  flattenTakeDrafts,
  getPrivatePostTakes,
  resolveDraftPackage,
  resolveGeneratedDraftPackage,
} = await server.ssrLoadModule('/src/components/posts/privatePostsView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

// Canonical story feed items (dashboard.stories.items). These carry no legacy
// `computed` structured facts and no beats keyed 'signal'/'evidence'; the posts
// adapter derives takes from headline (signal), canonical evidence (evidence),
// and story_type (rule key).
function canonicalStory(overrides = {}) {
  return {
    story_id: '100:2026-06-17',
    team_id: 100,
    team_name: 'Test Club',
    team_abbreviation: 'TST',
    date: '2026-06-17',
    story_available: true,
    story_type: 'route_change',
    category: 'watch',
    tone: 'watch',
    headline: 'The Test Club has a neutral bullpen read tonight.',
    narrative: 'Test Club observation.\n\nTest Club cause.',
    beats: [
      { key: 'observation', label: 'What stands out', text: 'Ordinary availability across the board.' },
      { key: 'baseline', label: 'Against the baseline', text: 'The workload shape matches a normal week.' },
      { key: 'cause', label: 'Why', text: 'No single arm has been overused recently.' },
      { key: 'constraint', label: 'What it creates', text: 'There is no forced drama in the read.' },
    ],
    evidence: [
      { key: 'baseline', label: 'Against the baseline', text: 'Availability sits at a normal level for this club.' },
      { key: 'cause', label: 'Why', text: 'Recent relief work is spread across the pen.' },
    ],
    continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
    quality_status: 'published',
    ...overrides,
  }
}

// Pressure story: story_type sustainability_question is a tension rule key and
// the headline carries an explicit "but" contrast, so postability flags tension.
const pressureStory = canonicalStory({
  story_id: '158:2026-06-17',
  team_id: 158,
  team_name: 'Milwaukee Brewers',
  team_abbreviation: 'MIL',
  story_type: 'sustainability_question',
  category: 'stressed',
  tone: 'stress',
  headline: 'The Milwaukee Brewers bullpen has pitched well this year, but they are leaning on it hard tonight.',
  narrative: 'The Milwaukee Brewers are carrying the late innings on a small group.\n\nThe recent workload has clustered around the same arms.',
  beats: [
    { key: 'observation', label: 'What stands out', text: 'The same late-inning group keeps getting the call.' },
    { key: 'baseline', label: 'Against the baseline', text: 'Recent workload runs heavier than a normal week.' },
    { key: 'cause', label: 'Why', text: 'Close games have leaned on the trusted arms repeatedly.' },
    { key: 'constraint', label: 'What it creates', text: 'There is less room behind the clean late-inning path.' },
  ],
  evidence: [
    { key: 'baseline', label: 'Against the baseline', text: 'The pen has still prevented runs at a strong rate this season.' },
    { key: 'cause', label: 'Why', text: 'The late-inning workload has concentrated on a small group.' },
  ],
  continuity: { state: 'ongoing', reason: 'story_type_persisted', compared: true },
})

// Rested story: story_type availability_depth, calm read with no "but".
const restedStory = canonicalStory({
  story_id: '136:2026-06-17',
  team_id: 136,
  team_name: 'Seattle Mariners',
  team_abbreviation: 'SEA',
  story_type: 'availability_depth',
  category: 'rested',
  tone: 'rest',
  headline: 'The Seattle Mariners have more rested options than most clubs tonight.',
  narrative: 'The Seattle Mariners spread recent relief work widely.\n\nThe board has room to maneuver.',
  beats: [
    { key: 'observation', label: 'What stands out', text: 'Recent relief work stayed light and broad.' },
    { key: 'baseline', label: 'Against the baseline', text: 'Availability sits above a normal week.' },
    { key: 'cause', label: 'Why', text: 'No single arm has been leaned on recently.' },
    { key: 'constraint', label: 'What it creates', text: 'Multiple clean options sit behind the trust lane.' },
  ],
  evidence: [
    { key: 'baseline', label: 'Against the baseline', text: 'More arms are available than on a typical night.' },
    { key: 'cause', label: 'Why', text: 'Recent relief work was light and broadly shared.' },
  ],
  continuity: { state: 'new', reason: 'no_prior_canonical_story', compared: false },
})

// Neutral story: story_type route_change, straightforward read.
const neutralStory = canonicalStory({
  story_id: '141:2026-06-17',
  team_id: 141,
  team_name: 'Toronto Blue Jays',
  team_abbreviation: 'TOR',
  story_type: 'route_change',
  category: 'watch',
  tone: 'watch',
  headline: 'The Toronto Blue Jays have a straightforward bullpen read tonight.',
  narrative: 'The Toronto Blue Jays show an ordinary board.\n\nNothing sharp stands out.',
})

// A suppressed item (story_available: false) must produce no take.
const suppressedStory = {
  story_id: '121:2026-06-17',
  team_id: 121,
  team_name: 'New York Mets',
  team_abbreviation: 'NYM',
  date: '2026-06-17',
  story_available: false,
  suppression_reason: 'no_story_observations',
  story_type: null,
  category: null,
  tone: null,
  headline: null,
  narrative: null,
  continuity: { state: 'unavailable', compared: true },
}

// The league_context card has no team_id and must produce no take.
const leagueContext = {
  capability: 'baseballos_league_context_v1',
  mode: 'pressure_concentrated',
  day_class: 'low_story',
  headline: "Today's bullpen pressure is concentrated in a small set of clubs.",
  summary: 'Most bullpens are in normal shape; the meaningful workload pressure is contained to a few clubs.',
  evidence: { constrained_team_count: 3, available_team_count: 10 },
  generated: true,
  quality_status: 'published',
}

function scheduleTeam(teamId, overrides = {}) {
  return {
    postable: true,
    state: 'upcoming',
    reason: 'upcoming_game_available',
    doubleheader: false,
    games: [{ game_pk: 800000 + teamId, game_number: 1, status: { normalized: 'upcoming' } }],
    ...overrides,
  }
}

const dashboard = {
  freshness: { data_through: '2026-06-17' },
  schedule_authority: {
    slate_date_et: '2026-06-17',
    freshness: {
      state: 'fresh',
      is_fresh: true,
      schedule_data_through: '2026-06-17T12:00:00Z',
    },
    teams: {
      136: scheduleTeam(136),
      141: scheduleTeam(141),
      158: scheduleTeam(158),
    },
  },
  stories: {
    capability: 'baseballos_canonical_story_v1',
    items: [neutralStory, restedStory, pressureStory, suppressedStory],
    available_count: 3,
    suppressed_count: 1,
    league_context: leagueContext,
  },
}

test('canonical adapter maps publishable team stories and excludes league + suppressed cards', () => {
  const sources = canonicalPostableStories(dashboard)

  // Three publishable team stories; the league_context card (no team_id) and the
  // suppressed item (story_available: false) are excluded.
  assert.deepEqual(sources.map(source => source.team_abbreviation).sort(), ['MIL', 'SEA', 'TOR'])
  assert.equal(sources.some(source => source.story_id === '121:2026-06-17'), false)

  const mil = sources.find(source => source.team_abbreviation === 'MIL')
  assert.equal(mil.rule_key, 'sustainability_question')
  assert.equal(mil.rule_label, 'Same Few Arms')
  assert.equal(mil.kicker, 'Same Few Arms')
  // signal beat = headline; evidence beat = joined canonical evidence text.
  assert.equal(mil.beats.find(beat => beat.key === 'signal').text, mil.title)
  assert.equal(
    mil.beats.find(beat => beat.key === 'evidence').text,
    'The pen has still prevented runs at a strong rate this season. The late-inning workload has concentrated on a small group.',
  )
  assert.equal(mil.source, 'canonical')

  // A missing/malformed canonical feed yields no source stories (and no throw).
  assert.deepEqual(canonicalPostableStories({}), [])
  assert.deepEqual(canonicalPostableStories({ stories: { capability: 'x' } }), [])
  assert.deepEqual(canonicalPostableStories(null), [])
})

test('postability selector is deterministic and ranks the tension story above neutral reads', () => {
  const first = getPrivatePostTakes(dashboard)
  const second = getPrivatePostTakes(JSON.parse(JSON.stringify(dashboard)))

  // Determinism: same dashboard -> same takes in the same order with the same scores.
  assert.deepEqual(
    first.map(take => [take.abbr, take.postability.score]),
    second.map(take => [take.abbr, take.postability.score]),
  )
  assert.equal(first[0].abbr, 'MIL')

  const byTeam = Object.fromEntries(first.map(take => [take.abbr, take]))
  // The sustainability_question story with an explicit "but" contrast is the
  // only canonical story that clears the tension bar; SEA and TOR read neutral
  // because canonical items carry no structured facts to fire a superlative.
  assert.ok(byTeam.MIL.postability.hasTension)
  assert.equal(byTeam.SEA.postability.hasTension, false)
  assert.equal(byTeam.SEA.postability.hasSuperlative, false)
  assert.equal(byTeam.TOR.postability.hasTension, false)
  assert.equal(byTeam.TOR.postability.hasSuperlative, false)
  assert.ok(byTeam.MIL.postability.score > byTeam.SEA.postability.score)
  assert.ok(byTeam.MIL.postability.score > byTeam.TOR.postability.score)

  // ruleKey = story_type; ruleLabel/kicker = mapped label.
  assert.equal(byTeam.MIL.ruleKey, 'sustainability_question')
  assert.equal(byTeam.MIL.ruleLabel, 'Same Few Arms')
  assert.equal(byTeam.SEA.ruleKey, 'availability_depth')
  assert.equal(byTeam.SEA.ruleLabel, 'More Options')
})

test('postability withholds completed, live, uncertain, and cancelled team moments', () => {
  for (const state of ['completed', 'live', 'uncertain', 'cancelled']) {
    const copy = structuredClone(dashboard)
    copy.schedule_authority.teams['158'] = scheduleTeam(158, {
      postable: false,
      state,
      reason: `game_${state}`,
    })
    assert.equal(
      getPrivatePostTakes(copy).some(take => take.teamId === 158),
      false,
      state,
    )
  }
})

test('split doubleheader stays postable when game one is final and game two is upcoming', () => {
  const copy = structuredClone(dashboard)
  copy.schedule_authority.teams['158'] = scheduleTeam(158, {
    doubleheader: true,
    games: [
      { game_pk: 900001, game_number: 1, status: { normalized: 'completed' } },
      { game_pk: 900002, game_number: 2, status: { normalized: 'upcoming' } },
    ],
  })

  const take = getPrivatePostTakes(copy).find(item => item.teamId === 158)
  assert.equal(take.postability.schedulePostable, true)
  assert.equal(take.postability.doubleheader, true)
  assert.deepEqual(take.postability.scheduleGames.map(game => game.game_pk), [900001, 900002])
})

test('missing or stale schedule authority fails closed and renders freshness warning', () => {
  assert.deepEqual(getPrivatePostTakes({ stories: dashboard.stories }), [])

  const stale = structuredClone(dashboard)
  stale.schedule_authority.freshness = {
    state: 'stale',
    is_fresh: false,
    schedule_data_through: '2026-06-16T12:00:00Z',
  }
  assert.deepEqual(getPrivatePostTakes(stale), [])
  const html = render(React.createElement(PrivatePostsView, { dashboard: stale }))
  assert.ok(htmlIncludes(html, 'Schedule data is stale through 2026-06-16T12:00:00Z.'))
  assert.ok(htmlIncludes(html, 'Postable takes are withheld'))
})

test('canonical takes derive signal and evidence from story content, with no structured computed facts', () => {
  const byTeam = Object.fromEntries(getPrivatePostTakes(dashboard).map(take => [take.abbr, take]))
  const mil = byTeam.MIL

  // signal = headline; evidence = joined canonical evidence text.
  assert.equal(mil.signal, 'The Milwaukee Brewers bullpen has pitched well this year, but they are leaning on it hard tonight.')
  assert.equal(
    mil.evidence,
    'The pen has still prevented runs at a strong rate this season. The late-inning workload has concentrated on a small group.',
  )

  // GAP: canonical stories carry no `computed` block, so no structured numeric
  // facts (availability/workload/season ERA/clean-trust/high-risk) are produced.
  for (const take of Object.values(byTeam)) {
    assert.deepEqual(take.facts.items, [])
  }
  // extractStoryFacts still returns its empty-but-valid shape on a canonical
  // source story (documents the gap; no crash downstream).
  const facts = extractStoryFacts(canonicalPostableStories(dashboard)[0])
  assert.deepEqual(facts.items, [])
  assert.equal(facts.availability.available, null)
  assert.equal(facts.cleanTrustCount, null)
})

test('drafts are built from canonical content and never fabricate numbers', () => {
  const [take] = getPrivatePostTakes(dashboard)
  const draftText = flattenTakeDrafts(take).map(draft => draft.text).join('\n\n')

  // Drafts reference the team and stay grounded in the canonical headline.
  assert.ok(draftText.includes('Milwaukee'))
  // Canonical takes carry no structured facts, so no draft may smuggle in a
  // fabricated stat: every numeric token in the copy must be verified.
  for (const draft of flattenTakeDrafts(take)) {
    const copy = [draft.text, draft.lead].filter(Boolean).join('\n')
    assert.deepEqual(findUnverifiedNumbers(copy, take.verifiedFacts), [], draft.label)
  }
  assert.equal(draftText.includes('9/9'), false)
  assert.equal(draftText.includes('No. 1 of 30'), false)
})

test('verified fact object is structured from the canonical story payload', () => {
  const [take] = getPrivatePostTakes(dashboard)
  const facts = buildVerifiedFactSet(take.story, take.facts)

  assert.deepEqual(facts.team, {
    id: 158,
    abbr: 'MIL',
    name: 'Milwaukee Brewers',
  })
  assert.equal(facts.signal, take.signal)
  assert.equal(facts.evidence, take.evidence)
  // story_type carried through as the rule key, with the mapped kicker label.
  assert.equal(facts.story.rule_key, 'sustainability_question')
  assert.equal(facts.story.rule_label, 'Same Few Arms')
  // GAP: canonical stories carry no computed facts, so the structured fact
  // blocks have no text and the fact-item list is empty.
  assert.equal(facts.availability.text, undefined)
  assert.equal(facts.clean_trust.text, undefined)
  assert.equal(facts.season_era.text, undefined)
  assert.equal(facts.high_risk.text, undefined)
  assert.deepEqual(facts.fact_items, [])
  // The only numeric tokens come from identifiers (story_id / team_id), never
  // from structured stat values like a 6/8 availability or a 3.12 ERA.
  for (const statToken of ['6/8', '3.12', '34.2']) {
    assert.equal(facts.numeric_tokens.includes(statToken), false, statToken)
  }
  assert.ok(facts.numeric_tokens.includes('158'))
})

test('generation payload contains the verified fact object and platform constraints', () => {
  const [take] = getPrivatePostTakes(dashboard)
  const payload = buildDraftGenerationPayload(take)

  assert.deepEqual(payload.platforms, POST_DRAFT_PLATFORMS)
  assert.equal('signal' in payload, false)
  assert.equal('evidence' in payload, false)
  assert.equal('postability' in payload, false)
  assert.equal(payload.constraints.use_only_verified_facts, true)
  assert.equal(payload.constraints.return_structured_fact_claims.required, true)
  assert.deepEqual(payload.constraints.return_structured_fact_claims.fields, [
    'names', 'dates', 'pitch_counts', 'percentages', 'teams', 'matchup_facts',
  ])
  assert.equal(payload.constraints.x_lead_character_limit, X_LEAD_CHARACTER_LIMIT)
  assert.equal(payload.writing_instructions.interpretive_license, 'medium')
  assert.match(payload.writing_instructions.lead, /human claim/)
  assert.ok(payload.constraints.forbidden_residue.includes('The catch:'))
  assert.equal(payload.verified_facts.signal, take.signal)
  assert.equal(payload.verified_facts.story.rule_key, 'sustainability_question')
  assert.equal(JSON.stringify(payload).includes('9/9'), false)
})

test('generated drafts clear the absent-number guard while fabricated numbers are flagged', () => {
  const [take] = getPrivatePostTakes(dashboard)
  const generatedPackage = resolveDraftPackage(take, buildGeneratedPlatformDrafts(take))

  assert.equal(generatedPackage.source, DRAFT_SOURCE_GENERATED)
  for (const draft of flattenTakeDrafts({ drafts: generatedPackage.drafts })) {
    assert.deepEqual(draft.factCheck.unverifiedNumbers, [])
    assert.deepEqual(draft.reviewFlags, [])
  }

  const rogueText = 'MIL bullpen tonight: 9/9 arms available and No. 99 of 30.'
  // Canonical takes verify no numbers, so every numeric token in rogue copy is flagged.
  assert.deepEqual(findUnverifiedNumbers(rogueText, take.verifiedFacts), ['9/9', '9', '99', '30'])
})

test('generated fact claims check names, dates, pitch counts, percentages, teams, and matchup facts', () => {
  const verifiedFacts = {
    teams: ['Houston Astros', 'Seattle Mariners'],
    matchup_facts: ['Houston Astros at Seattle Mariners'],
    named_arms: [{
      name: 'Bryan Abreu',
      last_outing_date: '2026-07-17',
      pitch_counts: [18, 22],
      workload_share_pct: 31.4,
    }],
  }
  const valid = auditGeneratedFactClaims({
    names: ['Bryan Abreu'],
    dates: ['2026-07-17'],
    pitch_counts: [18, 22],
    percentages: [31.4],
    teams: ['Houston Astros', 'Seattle Mariners'],
    matchup_facts: ['Houston Astros at Seattle Mariners'],
  }, verifiedFacts)
  const invalid = auditGeneratedFactClaims({
    names: ['Invented Arm'],
    dates: ['2026-07-01'],
    pitch_counts: [99],
    percentages: [70.8],
    teams: ['New York Yankees'],
    matchup_facts: ['Houston Astros at New York Yankees'],
  }, verifiedFacts)

  assert.deepEqual(valid, { checked: true, valid: true, violations: [] })
  assert.equal(invalid.valid, false)
  assert.equal(invalid.violations.length, 6)
})

test('external generated drafts without structured fact claims fail closed to templates', async () => {
  const [take] = getPrivatePostTakes(dashboard)
  const packageWithoutClaims = await resolveGeneratedDraftPackage(take, {
    requestDrafts: async () => buildGeneratedPlatformDrafts(take),
  })

  assert.equal(packageWithoutClaims.source, DRAFT_SOURCE_TEMPLATE_FALLBACK)
  assert.match(packageWithoutClaims.fallbackReason, /no usable copy/i)
})

test('external generated drafts with an unverified structured claim fail closed to templates', async () => {
  const [take] = getPrivatePostTakes(dashboard)
  const drafts = buildGeneratedPlatformDrafts(take)
  for (const draft of flattenTakeDrafts({ drafts })) {
    draft.factClaims = { teams: ['Invented Club'] }
  }
  const guarded = await resolveGeneratedDraftPackage(take, {
    requestDrafts: async () => drafts,
  })

  assert.equal(guarded.source, DRAFT_SOURCE_TEMPLATE_FALLBACK)
})

test('external generated drafts pass only with a complete verified claims contract', async () => {
  const [take] = getPrivatePostTakes(dashboard)
  const drafts = buildGeneratedPlatformDrafts(take)
  for (const draft of flattenTakeDrafts({ drafts })) {
    draft.factClaims = {
      names: [],
      dates: [],
      pitch_counts: [],
      percentages: [],
      teams: ['Milwaukee Brewers'],
      matchup_facts: [],
    }
  }
  const guarded = await resolveGeneratedDraftPackage(take, {
    requestDrafts: async () => drafts,
  })

  assert.equal(guarded.source, DRAFT_SOURCE_GENERATED)
  assert.ok(flattenTakeDrafts({ drafts: guarded.drafts }).every(draft => draft.reviewFlags.length === 0))
})

test('generated drafts lead with human interpretation instead of template residue or stat lists', () => {
  const [take] = getPrivatePostTakes(dashboard)
  const generatedText = flattenTakeDrafts(take).map(draft => draft.text || draft.lead).join('\n\n')
  const xLead = take.drafts.x.lead

  for (const residue of [
    'The catch:',
    'The useful angle',
    'The useful framing',
    'The useful read',
    'the argument is',
    'Verified facts:',
    'clean Trust Arm',
    'current-pen',
    'top 3 carried',
  ]) {
    assert.equal(generatedText.includes(residue), false, residue)
  }
  // The human X lead opens with the market name, not the abbreviation template
  // residue, and stays a human sentence rather than a stat list.
  assert.match(xLead, /^Milwaukee/)
  assert.equal(xLead.startsWith('MIL bullpen tonight:'), false)
  assert.ok(generatedText.includes('Milwaukee'))
})

test('generated drafts avoid future certainty and unsupported causal language', () => {
  const banned = /\b(will|guarantee|guaranteed|certainly|definitely|caused|causes|because of|proves|locks in)\b/i
  for (const take of getPrivatePostTakes(dashboard)) {
    const generatedText = flattenTakeDrafts(take).map(draft => draft.text || draft.lead).join('\n\n')
    assert.doesNotMatch(generatedText, banned, take.abbr)
  }
})

test('request failure and empty generated output fall back to the WP39 template drafts', async () => {
  const [take] = getPrivatePostTakes(dashboard)
  const failedPackage = await resolveGeneratedDraftPackage(take, {
    requestDrafts: async () => {
      throw new Error('unavailable')
    },
  })
  const emptyPackage = resolveDraftPackage(take, {
    reddit: { league: { text: '' } },
  })

  assert.equal(failedPackage.source, DRAFT_SOURCE_TEMPLATE_FALLBACK)
  assert.equal(emptyPackage.source, DRAFT_SOURCE_TEMPLATE_FALLBACK)
  assert.match(failedPackage.fallbackReason, /failed/i)
  assert.ok(flattenTakeDrafts({ drafts: failedPackage.drafts }).every(draft => draft.source === DRAFT_SOURCE_TEMPLATE_FALLBACK))
  assert.ok(flattenTakeDrafts({ drafts: failedPackage.drafts }).every(draft => draft.text || draft.lead))
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
  const sidebarSource = readFileSync(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8')
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))
  const robots = readFileSync(new URL('../public/robots.txt', import.meta.url), 'utf8')

  assert.ok(route?.Component)
  assert.notEqual(PRIVATE_POSTS_PATH, '/posts')
  assert.match(PRIVATE_POSTS_PATH, /^\/posts-[a-z0-9-]{8,}$/)
  assert.equal(htmlIncludes(navHtml, `href="${PRIVATE_POSTS_PATH}"`), false)
  assert.equal(sidebarSource.includes(PRIVATE_POSTS_PATH), false)
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

test('private posts direct route uses protected API instead of public dashboard data', () => {
  const pageSource = readFileSync(new URL('../src/components/posts/PrivatePosts.jsx', import.meta.url), 'utf8')
  const apiSource = readFileSync(new URL('../src/utils/api.js', import.meta.url), 'utf8')

  assert.ok(pageSource.includes('useAuthState'))
  assert.ok(pageSource.includes('getPrivatePostsDashboard'))
  assert.equal(pageSource.includes('getBullpenDashboard'), false)
  assert.ok(apiSource.includes("getPrivatePostsDashboard = () => request('/private-posts/dashboard')"))
})

test('private posts direct route renders no posting board content before authorization', () => {
  const html = render(React.createElement(PrivatePostsAccessDenied))

  assert.ok(htmlIncludes(html, 'data-private-posts-access="denied"'))
  assert.ok(htmlIncludes(html, 'Access Restricted'))
  assert.equal(htmlIncludes(html, 'Private Posting Board'), false)
  assert.equal(htmlIncludes(html, "TONIGHT&#x27;S POSTABLE TAKES"), false)
  assert.equal(htmlIncludes(html, 'Story Authority'), false)
  assert.equal(htmlIncludes(html, 'Verified Facts Object'), false)
  assert.equal(htmlIncludes(html, 'data-copy-draft='), false)
})

test('draft generation stays isolated from public story and bullpen surfaces', () => {
  const publicFiles = [
    '../src/components/stories/Stories.jsx',
    '../src/components/stories/storiesFeedView.js',
    '../src/components/home/Home.jsx',
    '../src/components/bullpen/Bullpen.jsx',
  ]

  for (const path of publicFiles) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8')
    assert.equal(source.includes('VITE_POST_DRAFT_GENERATION_URL'), false, path)
    assert.equal(source.includes('resolveGeneratedDraftPackage'), false, path)
    assert.equal(source.includes('buildDraftGenerationPayload'), false, path)
  }
})

test('private posts surface renders selected takes, internals, and copy affordances', () => {
  const html = render(React.createElement(PrivatePostsView, { dashboard }))

  assert.ok(htmlIncludes(html, 'POSTABLE TAKES'))
  assert.ok(htmlIncludes(html, 'data-private-posts-path="/posts-bpen-7f3d9c"'))
  assert.ok(htmlIncludes(html, 'Milwaukee Brewers bullpen has pitched well'))
  assert.ok(htmlIncludes(html, 'Story Authority'))
  assert.ok(htmlIncludes(html, 'Raw Numbers'))
  assert.ok(htmlIncludes(html, 'Verified Facts Object'))
  assert.ok(htmlIncludes(html, 'Generated draft'))
  assert.ok(htmlIncludes(html, 'Fact check clear'))
  assert.ok(htmlIncludes(html, 'data-copy-draft="Reddit - league-wide"'))
  assert.ok(htmlIncludes(html, 'data-copy-draft="Reddit - team subreddit"'))
  assert.ok(htmlIncludes(html, 'data-copy-draft="LinkedIn"'))
  assert.ok(htmlIncludes(html, 'data-copy-draft="X lead tweet"'))
})
