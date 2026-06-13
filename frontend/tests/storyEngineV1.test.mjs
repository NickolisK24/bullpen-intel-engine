import assert from 'node:assert/strict'
import test from 'node:test'

import {
  STORY_TIERS,
  buildStoryEvidence,
  classifyStoryTier,
  evaluateStoryCandidate,
  scoreStorySignificance,
  selectStoryCandidates,
} from '../src/components/home/storyEngineV1.js'

const context = {
  leagueMetrics: {
    total: 64,
    available: 38,
    monitor: 14,
    restricted: 9,
    pctAvailable: 59,
    pctRestricted: 14,
  },
  freshness: {
    is_current: true,
    sync_status: 'success',
    data_through: '2026-06-05',
  },
  games: {
    data_state: 'historical',
    as_of_date: '2026-06-05',
  },
}

const pressureStory = {
  teamId: 121,
  teamName: 'New York Mets',
  abbr: 'NYM',
  available: 3,
  monitor: 2,
  restricted: 3,
  total: 8,
  storyKind: 'team_pressure',
  kicker: 'Pressure Point',
  tone: 'stress',
  title: 'A thin late-inning margin is forming for the New York Mets',
  body: '3 of 8 relievers need rest after recent work, so one long night could leave this pen short.',
  href: '/bullpen?view=board&team=NYM&source=stories',
}

const workloadStory = {
  teamId: 141,
  teamName: 'Toronto Blue Jays',
  abbr: 'TOR',
  available: 4,
  monitor: 4,
  restricted: 0,
  total: 8,
  storyKind: 'team_workload_continuity',
  kicker: 'Hidden Workload',
  tone: 'watch',
  title: 'The Toronto Blue Jays box score looks calm. The bullpen does not.',
  body: 'Nobody is flashing red, but 4 of 8 arms are carrying heavy recent work on the same small group.',
  href: '/bullpen?view=board&team=TOR&source=stories',
}

const restStory = {
  teamId: 120,
  teamName: 'Washington Nationals',
  abbr: 'WSH',
  available: 6,
  monitor: 1,
  restricted: 1,
  total: 8,
  storyKind: 'team_recovery',
  kicker: 'Fresh Pen',
  tone: 'rest',
  title: 'Nobody brings a fresher bullpen into today than the Washington Nationals',
  body: '6 of 8 relievers come in rested, giving this pen more room to breathe.',
  href: '/bullpen?view=board&team=WSH&source=stories',
}

const dataObservationStory = {
  teamId: null,
  family: 'trust',
  sourceObservation: {
    family: 'trust',
    severity: 'significant',
    evidence: [
      {
        label: 'Trust limitation state',
        value: 'represented',
        source: 'test_observation_feed',
        source_type: 'trusted_platform_state',
        freshness_status: 'current',
        data_through: '2026-06-05',
      },
    ],
    freshness: { status: 'current', data_through: '2026-06-05' },
    confidence: { status: 'medium' },
  },
  storyKind: 'data_observation',
  kicker: 'Data Note',
  tone: 'neutral',
  title: 'BaseballOS is staying quiet where the data is thin',
  body: 'When the inputs are not solid enough to stand behind, the page says less rather than guessing.',
  href: '/trust',
}

const leagueWorkloadContext = {
  ...context,
  leagueMetrics: {
    total: 90,
    available: 40,
    monitor: 34,
    restricted: 16,
    pctAvailable: 44,
    pctRestricted: 18,
  },
}

const leagueWorkloadStory = {
  teamId: null,
  storyKind: 'league_workload_continuity',
  kicker: 'League Watch',
  tone: 'watch',
  title: 'The heavy lifting is spread around baseball today',
  body: '34 tracked arms sit on the watch list, and the same bullpen work is showing up across several clubs.',
  href: '/dashboard',
}

test('classifies league, team, pitcher, and suppressible data tiers', () => {
  assert.equal(classifyStoryTier({ storyKind: 'league_workload', title: 'League workload', body: 'League workload is visible.' }).key, STORY_TIERS.league.key)
  assert.equal(classifyStoryTier(pressureStory).key, STORY_TIERS.team.key)
  assert.equal(classifyStoryTier({
    pitcherId: 99,
    title: 'One arm carried the night',
    body: 'A pitcher-level note needs the club context before it leads.',
    evidence: [{ label: 'Appearance count', value: 1, source: 'test' }],
  }).key, STORY_TIERS.pitcher.key)
  assert.equal(classifyStoryTier(dataObservationStory).key, STORY_TIERS.data.key)
})

test('orders significance from broad stress and workload above lower-signal notes', () => {
  const pressure = scoreStorySignificance(pressureStory, context)
  const workload = scoreStorySignificance(workloadStory, context)
  const rest = scoreStorySignificance(restStory, context)
  const weakData = scoreStorySignificance({
    ...dataObservationStory,
    sourceObservation: { family: 'trust', severity: 'monitor', evidence: [] },
  }, context)

  assert.ok(pressure.total > rest.total)
  assert.ok(workload.total > rest.total)
  assert.ok(rest.total > weakData.total)
  assert.deepEqual(
    pressure.factors.map(item => item.key),
    [
      'workload_concentration',
      'bullpen_stress',
      'recency',
      'team_level_impact',
      'narrative_continuity',
      'evidence_strength',
      'fan_relevance_readability',
    ],
  )
})

test('strong league-wide workload concentration can lead over one team stress story', () => {
  const teamStress = {
    ...pressureStory,
    teamId: 110,
    teamName: 'Baltimore Orioles',
    abbr: 'BAL',
    available: 2,
    monitor: 1,
    restricted: 4,
    total: 8,
    title: 'A short bullpen day is forming for the Baltimore Orioles',
    body: '4 of 8 relievers need rest after recent work, leaving a shorter team margin.',
  }

  const selection = selectStoryCandidates([
    teamStress,
    leagueWorkloadStory,
  ], leagueWorkloadContext)

  assert.equal(selection.items[0].title, leagueWorkloadStory.title)
  assert.equal(selection.items[0].tier.key, STORY_TIERS.league.key)
  assert.ok(selection.items[0].evidence.some(item => item.label === 'League watch-list arms'))
})

test('a strong team-level bullpen stress story still surfaces with its evidence contract', () => {
  const evaluation = evaluateStoryCandidate({
    ...pressureStory,
    restricted: 4,
    available: 2,
    monitor: 1,
    title: 'A short bullpen day is forming for the New York Mets',
    body: '4 of 8 relievers need rest after recent work, so the late innings have less room than usual.',
  }, context)

  assert.equal(evaluation.suppressed, false)
  assert.equal(evaluation.tier.key, STORY_TIERS.team.key)
  assert.ok(evaluation.story.evidence.some(item => item.label === 'Relievers needing rest'))
  assert.match(evaluation.story.selectionReason, /Team story surfaced/)
})

test('suppresses missing evidence, minor movement, and duplicate team narratives', () => {
  const weakData = evaluateStoryCandidate({
    ...dataObservationStory,
    sourceObservation: { family: 'trust', severity: 'significant', evidence: [] },
  }, context)
  assert.ok(weakData.suppressed)
  assert.ok(weakData.suppressionReasons.includes('story_missing_evidence'))

  const minorMovement = evaluateStoryCandidate({
    storyKind: 'minor_availability_movement',
    title: 'One bullpen label moved overnight',
    body: 'One appearance changed a label without a broader bullpen pattern.',
    evidence: [{ label: 'Appearance count', value: 1, source: 'test' }],
  }, context)
  assert.ok(minorMovement.suppressed)
  assert.ok(minorMovement.suppressionReasons.includes('minor_availability_movement'))

  const selection = selectStoryCandidates([
    workloadStory,
    { ...workloadStory, title: 'The Toronto bullpen keeps asking the same group for outs' },
    pressureStory,
  ], context)
  assert.equal(selection.items.filter(item => item.teamId === 141).length, 1)
  assert.ok(selection.suppressionReasons.includes('duplicate_team_narrative'))
})

test('weak one-off pitcher stories suppress even with team context present', () => {
  const pitcherStory = evaluateStoryCandidate({
    pitcherId: 77,
    teamId: 121,
    teamName: 'New York Mets',
    abbr: 'NYM',
    available: 3,
    monitor: 2,
    restricted: 3,
    total: 8,
    storyKind: 'pitcher_one_off',
    title: 'One Mets reliever worked last night',
    body: 'One pitcher appeared once without a broader bullpen pattern around it.',
    evidence: [
      { label: 'Appearance count', value: 1, source: 'game_log' },
    ],
  }, context)

  assert.equal(pitcherStory.tier.key, STORY_TIERS.pitcher.key)
  assert.ok(pitcherStory.suppressed)
  assert.ok(pitcherStory.suppressionReasons.includes('one_off_pitcher_observation'))
})

test('duplicate team narratives keep only the stronger story for that club', () => {
  const weakerToronto = {
    ...workloadStory,
    monitor: 1,
    restricted: 0,
    title: 'The Toronto Blue Jays have one arm on the watch list',
    body: 'One reliever is on the watch list, but the broader bullpen story is modest.',
  }

  const selection = selectStoryCandidates([
    weakerToronto,
    workloadStory,
    pressureStory,
  ], context)

  const torontoStories = selection.items.filter(item => item.teamId === workloadStory.teamId)
  assert.equal(torontoStories.length, 1)
  assert.equal(torontoStories[0].title, workloadStory.title)
  assert.ok(selection.suppressionReasons.includes('duplicate_team_narrative'))
})

test('mechanical-language stories suppress instead of beating baseball-language stories', () => {
  const mechanical = evaluateStoryCandidate({
    teamId: null,
    storyKind: 'league_workload',
    kicker: 'System Note',
    tone: 'watch',
    title: 'Availability inventory workload signal is elevated',
    body: 'The fatigue score and confidence score indicate a workload concentration signal.',
    evidence: [
      { label: 'League watch-list arms', value: 14, source: 'bullpen_dashboard_context' },
    ],
    href: '/dashboard',
  }, context)

  assert.ok(mechanical.suppressed)
  assert.ok(mechanical.suppressionReasons.includes('mechanical_story_language'))
  assert.equal(
    mechanical.significance.factors.find(item => item.key === 'fan_relevance_readability').points,
    0,
  )
})

test('data notes do not inherit league workload and stress points by accident', () => {
  const score = scoreStorySignificance(dataObservationStory, leagueWorkloadContext)
  const byKey = Object.fromEntries(score.factors.map(item => [item.key, item]))

  assert.equal(byKey.workload_concentration.points, 0)
  assert.equal(byKey.bullpen_stress.points, 0)
  assert.ok(byKey.evidence_strength.points > 0)
})

test('evidence-rich repeated workload can beat a raw-count spike with weaker evidence', () => {
  const rawStressSpike = {
    teamId: 144,
    teamName: 'Atlanta Braves',
    abbr: 'ATL',
    available: 2,
    monitor: 0,
    restricted: 4,
    total: 8,
    storyKind: 'team_pressure',
    kicker: 'Pressure Point',
    tone: 'stress',
    title: 'The Atlanta Braves are short in the pen today',
    body: '4 of 8 relievers need rest today, creating a short late-inning margin.',
    href: '/bullpen?view=board&team=ATL&source=stories',
  }
  const evidenceRichPattern = {
    teamId: 139,
    teamName: 'Tampa Bay Rays',
    abbr: 'TB',
    available: 4,
    monitor: 3,
    restricted: 1,
    total: 8,
    storyKind: 'team_workload_continuity',
    kicker: 'Hidden Workload',
    tone: 'watch',
    title: 'The Tampa Bay Rays keep handing the ball to the same relievers',
    body: 'The same small group has carried the heavy work night after night, even with only one arm needing rest.',
    evidence: [
      { label: 'Three-game repeat usage', value: 'same late-inning group', source: 'game_log' },
      { label: 'Watch-list arms', value: '3 of 8', source: 'bullpen_dashboard_landscape' },
    ],
    href: '/bullpen?view=board&team=TB&source=stories',
  }

  const rawStress = scoreStorySignificance(rawStressSpike, context)
  const richPattern = scoreStorySignificance(evidenceRichPattern, context)
  assert.ok(
    rawStress.factors.find(item => item.key === 'bullpen_stress').points
      > richPattern.factors.find(item => item.key === 'bullpen_stress').points,
  )

  const selection = selectStoryCandidates([
    rawStressSpike,
    evidenceRichPattern,
  ], context)

  assert.equal(selection.items[0].title, evidenceRichPattern.title)
})

test('adds the evidence contract to every surfaced story', () => {
  const selection = selectStoryCandidates([
    pressureStory,
    dataObservationStory,
  ], context)

  assert.ok(selection.items.length >= 2)
  for (const story of selection.items) {
    assert.ok(story.noticed.length > 0)
    assert.ok(story.whyItMatters.length > 0)
    assert.ok(story.evidence.length > 0)
    assert.ok(story.tier.label.length > 0)
    assert.ok(story.significance.levelLabel.length > 0)
    assert.equal(story.storySelection.evidence.length, story.evidence.length)
  }

  const teamEvidence = buildStoryEvidence(pressureStory, context)
  assert.ok(teamEvidence.some(item => item.label === 'Relievers needing rest'))
})

test('selection output is deterministic for the same candidate set', () => {
  const candidates = [
    restStory,
    pressureStory,
    workloadStory,
    dataObservationStory,
  ]
  assert.deepEqual(
    selectStoryCandidates(candidates, context),
    selectStoryCandidates(candidates, context),
  )
})
