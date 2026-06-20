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

const { default: TeamBullpenStoryPanel } = await server.ssrLoadModule('/src/components/bullpen/board/TeamBullpenStoryPanel.jsx')
const { default: BullpenBoardView } = await server.ssrLoadModule('/src/components/bullpen/board/BullpenBoardView.jsx')
const {
  getTeamBullpenStoryView,
  deriveStoryFamily,
  deriveTeamStoryArchetype,
  STORY_FRAMING_LINE,
  getPitcherEvidenceName,
  isValidPitcherEvidenceName,
} = await server.ssrLoadModule('/src/components/bullpen/board/teamBullpenStoryView.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))
const BOARD_GROUP_ORDER = ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable']
const ROLE_KEYS = {
  'Trust Arm': 'late_high_leverage',
  'Bridge Arm': 'setup_bridge',
  'Coverage Arm': 'long_multi_inning',
  'Depth Arm': 'depth',
}
const ROLE_LABEL_KEYS = {
  'Trust Arm': 'trust_arm',
  'Bridge Arm': 'bridge_arm',
  'Coverage Arm': 'coverage_arm',
  'Depth Arm': 'depth_arm',
  'Limited Read': 'limited_read',
}
const READ_LABELS_BY_STATUS = {
  Available: { key: 'clean_option', label: 'Clean Option' },
  Monitor: { key: 'watch_arm', label: 'Watch Arm' },
  Limited: { key: 'rest_restricted', label: 'Rest-Restricted' },
  Avoid: { key: 'rest_restricted', label: 'Rest-Restricted' },
  Unavailable: { key: 'unavailable', label: 'Unavailable' },
}

function authoredPitcherLabels(roleLabel, status) {
  const roleKey = ROLE_LABEL_KEYS[roleLabel] || 'limited_read'
  const read = READ_LABELS_BY_STATUS[status] || { key: 'limited_read', label: 'Limited Read' }
  return {
    role: { kind: 'role', key: roleKey, label: roleLabel, source: 'backend:test_fixture' },
    read: { kind: 'read', key: read.key, label: read.label, source: 'backend:test_fixture' },
  }
}

const readTemplate = (key, label, supportingCounts = {}) => ({
  key,
  label,
  explanation: `${label}.`,
  supportingCounts,
  reasons: [`${label}.`],
  source: 'backend:test_fixture',
})

function countBy(cards, predicate) {
  return cards.filter(predicate).length
}

function buildTeamShape(groups, healthState) {
  const cards = groups.flatMap(group => group.pitchers)
  const role = key => cards.filter(card => card.pitcher_labels?.role?.key === key)
  const read = key => cards.filter(card => card.pitcher_labels?.read?.key === key)
  const trust = role('trust_arm')
  const bridge = role('bridge_arm')
  const coverage = role('coverage_arm')
  const depth = role('depth_arm')
  const clean = read('clean_option')
  const watch = read('watch_arm')
  const rest = read('rest_restricted')
  const unavailable = read('unavailable')
  const trustCounts = {
    trustArms: trust.length,
    availableTrustArms: countBy(trust, card => ['clean_option', 'watch_arm'].includes(card.pitcher_labels.read.key)),
    cleanTrustArms: countBy(trust, card => card.pitcher_labels.read.key === 'clean_option'),
    watchTrustArms: countBy(trust, card => card.pitcher_labels.read.key === 'watch_arm'),
    restRestrictedTrustArms: countBy(trust, card => card.pitcher_labels.read.key === 'rest_restricted'),
    unavailableTrustArms: countBy(trust, card => card.pitcher_labels.read.key === 'unavailable'),
  }
  const coverageCounts = {
    coverageArms: coverage.length,
    availableCoverageArms: countBy(coverage, card => ['clean_option', 'watch_arm'].includes(card.pitcher_labels.read.key)),
    cleanCoverageArms: countBy(coverage, card => card.pitcher_labels.read.key === 'clean_option'),
    watchCoverageArms: countBy(coverage, card => card.pitcher_labels.read.key === 'watch_arm'),
    restRestrictedCoverageArms: countBy(coverage, card => card.pitcher_labels.read.key === 'rest_restricted'),
    unavailableCoverageArms: countBy(coverage, card => card.pitcher_labels.read.key === 'unavailable'),
    cleanBridgeArms: countBy(bridge, card => card.pitcher_labels.read.key === 'clean_option'),
    watchBridgeArms: countBy(bridge, card => card.pitcher_labels.read.key === 'watch_arm'),
    substituteCoverageApplied: coverage.length === 0 && countBy(bridge, card => card.pitcher_labels.read.key === 'clean_option') > 0,
  }
  const depthCounts = {
    depthArms: depth.length,
    availableDepthArms: countBy(depth, card => ['clean_option', 'watch_arm'].includes(card.pitcher_labels.read.key)),
    cleanDepthArms: countBy(depth, card => card.pitcher_labels.read.key === 'clean_option'),
    watchDepthArms: countBy(depth, card => card.pitcher_labels.read.key === 'watch_arm'),
    restRestrictedDepthArms: countBy(depth, card => card.pitcher_labels.read.key === 'rest_restricted'),
    unavailableDepthArms: countBy(depth, card => card.pitcher_labels.read.key === 'unavailable'),
  }
  const pressureCounts = {
    watchArmCount: watch.length,
    restRestrictedCount: rest.length,
    unavailableCount: unavailable.length,
    highFatigueArms: countBy(cards, card => card.fatigue_score >= 70),
    restrictedTrustArms: trustCounts.restRestrictedTrustArms,
    unavailableTrustArms: trustCounts.unavailableTrustArms,
    cleanTrustArms: trustCounts.cleanTrustArms,
    usableTrustArms: trustCounts.cleanTrustArms + trustCounts.watchTrustArms,
    stressedBridgeArms: countBy(bridge, card => ['rest_restricted', 'unavailable'].includes(card.pitcher_labels.read.key)),
    stressedCoverageArms: coverageCounts.restRestrictedCoverageArms + coverageCounts.unavailableCoverageArms,
  }
  const cleanCounts = {
    cleanOptionCount: clean.length,
    activeBullpenArms: cards.length - unavailable.length,
    cleanTrustArms: trustCounts.cleanTrustArms,
    cleanBridgeArms: coverageCounts.cleanBridgeArms,
    cleanCoverageArms: coverageCounts.cleanCoverageArms,
    cleanDepthArms: depthCounts.cleanDepthArms,
  }
  const trustLabel = trustCounts.availableTrustArms >= 2 && trustCounts.unavailableTrustArms === 0
    ? 'Stable Trust Arm Availability'
    : trustCounts.availableTrustArms >= 1
      ? 'Thin Trust Arm Availability'
      : 'Limited Trust Arm Availability'
  const trustPressure = (trustCounts.watchTrustArms * 1.5) + (trustCounts.restRestrictedTrustArms * 3) + (trustCounts.unavailableTrustArms * 3)
  const pressureLabel = healthState === 'constrained' || rest.length >= 3 || trustPressure >= 4.5
    ? 'High Trust-Lane Pressure'
    : trustPressure >= 2.5 || watch.length >= 3 || pressureCounts.stressedBridgeArms >= 2
      ? 'Elevated Trust-Lane Pressure'
      : 'Low Trust-Lane Pressure'
  const cleanLabel = clean.length >= 6
    ? 'Deep Clean Options'
    : clean.length >= 4
      ? 'Healthy Clean Options'
      : clean.length >= 2
        ? 'Thin Clean Options'
        : 'Very Thin Clean Options'
  const coverageLabel = coverageCounts.availableCoverageArms >= 2
    ? 'Stable Coverage Safety'
    : coverageCounts.availableCoverageArms >= 1 || coverageCounts.substituteCoverageApplied
      ? 'Thin Coverage Safety'
      : 'Limited Coverage Safety'
  const depthLabel = cards.length >= 8 && depthCounts.availableDepthArms >= 2 && pressureCounts.usableTrustArms > 0
    ? 'Strong Depth Safety'
    : depthCounts.availableDepthArms >= 1
      ? 'Stable Depth Safety'
      : 'Limited Depth Safety'
  const concentrationCounts = cards.length
    ? {
        topArmCount: Math.min(3, cards.length),
        topSharePct: 65,
        participantCount: cards.length,
        totalRecentPitches: 100,
        concentrationDescriptor: 'some concentration',
      }
    : { totalRecentPitches: 0, participantCount: 0 }
  const reads = [
    readTemplate('trustAvailability', cards.length ? trustLabel : 'Limited Read', trustCounts),
    readTemplate('cleanOptions', cards.length ? cleanLabel : 'Limited Read', cleanCounts),
    readTemplate('bullpenPressure', cards.length ? pressureLabel : 'Limited Read', pressureCounts),
    readTemplate('workloadConcentration', cards.length ? 'Some Workload Concentration' : 'Limited Read', concentrationCounts),
    readTemplate('coverageSafety', cards.length ? coverageLabel : 'Limited Read', coverageCounts),
    readTemplate('depthSafety', cards.length ? depthLabel : 'Limited Read', depthCounts),
  ]
  const byKey = Object.fromEntries(reads.map(read => [read.key, read]))
  return {
    source: 'backend:test_fixture',
    reads,
    byKey,
    trustAvailability: byKey.trustAvailability,
    cleanOptions: byKey.cleanOptions,
    bullpenPressure: byKey.bullpenPressure,
    workloadConcentration: byKey.workloadConcentration,
    coverageSafety: byKey.coverageSafety,
    depthSafety: byKey.depthSafety,
    supportingCounts: { totalBullpenArms: cards.length, activeBullpenArms: cards.length - unavailable.length },
  }
}

// Board payloads shaped like /api/bullpen/teams/:id/board.
function makeBoard({ teamName, abbr, state, confidence = 'high', metrics, cardsByStatus = {} }) {
  const groups = BOARD_GROUP_ORDER.map(status => {
    const pitchers = cardsByStatus[status] || []
    return {
      status,
      label: status,
      count: pitchers.length,
      pitchers,
    }
  })
  return {
    capability: 'team_bullpen_board',
    team: { team_id: 1, team_name: teamName, team_abbreviation: abbr },
    context: {
      health: { state, label: 'label', reasons: [] },
      metrics,
      confidence,
      limitations: [],
    },
    groups,
    freshness: {},
    roster_status: null,
    stress: null,
    total_pitchers: metrics.total_relievers,
    team_shape: buildTeamShape(groups, state),
  }
}

function storyPitcher(id, name, roleLabel, status, overrides = {}) {
  return {
    pitcher_id: id,
    name,
    availability_status: status,
    fatigue_score: 25,
    confidence: 'high',
    data_state: 'fresh',
    role: {
      role_key: ROLE_KEYS[roleLabel],
      confidence: 'high',
      sample_size: 4,
      evidence: ['4 appearances in the recent window'],
    },
    pitcher_labels: authoredPitcherLabels(roleLabel, status),
    reasons: [],
    limitations: [],
    ...overrides,
  }
}

const constrainedBoard = makeBoard({
  teamName: 'Milwaukee Brewers', abbr: 'MIL', state: 'constrained',
  metrics: { total_relievers: 8, available: 2, monitor: 2, limited: 0, avoid: 3, unavailable: 1, pct_available: 25, pct_restricted: 50 },
  cardsByStatus: {
    Available: [
      storyPitcher(1, 'Trevor Trust', 'Trust Arm', 'Available'),
      storyPitcher(2, 'Brennan Bridge', 'Bridge Arm', 'Available'),
    ],
    Monitor: [
      storyPitcher(3, 'Wade Watch', 'Trust Arm', 'Monitor'),
      storyPitcher(4, 'Cal Coverage', 'Coverage Arm', 'Monitor'),
    ],
    Avoid: [
      storyPitcher(5, 'Tyler Trust', 'Trust Arm', 'Avoid'),
      storyPitcher(6, 'Cooper Coverage', 'Coverage Arm', 'Avoid'),
      storyPitcher(7, 'Drew Depth', 'Depth Arm', 'Avoid'),
    ],
    Unavailable: [
      storyPitcher(8, 'Uri Depth', 'Depth Arm', 'Unavailable'),
    ],
  },
})

const genuineThinMarginBoard = makeBoard({
  teamName: 'Oakland Athletics', abbr: 'ATH', state: 'elevated',
  metrics: { total_relievers: 8, available: 2, monitor: 0, limited: 3, avoid: 1, unavailable: 0, pct_available: 25, pct_restricted: 12 },
  cardsByStatus: {
    Available: [
      storyPitcher(91, 'Mason Miller', 'Trust Arm', 'Available'),
      storyPitcher(92, 'T.J. McFarland', 'Coverage Arm', 'Available'),
    ],
    Limited: [
      storyPitcher(93, 'Tyler Ferguson', 'Trust Arm', 'Limited'),
      storyPitcher(94, 'Austin Adams', 'Bridge Arm', 'Limited'),
      storyPitcher(95, 'Michel Otanez', 'Depth Arm', 'Limited'),
    ],
    Avoid: [
      storyPitcher(96, 'Sean Newcomb', 'Depth Arm', 'Avoid'),
    ],
  },
})

const watchBoard = makeBoard({
  teamName: 'Toronto Blue Jays', abbr: 'TOR', state: 'manageable',
  metrics: { total_relievers: 8, available: 4, monitor: 4, limited: 0, avoid: 0, unavailable: 0, pct_available: 50, pct_restricted: 0 },
  cardsByStatus: {
    Available: [
      storyPitcher(11, 'Erik Swanson', 'Bridge Arm', 'Available'),
      storyPitcher(12, 'Genesis Cabrera', 'Coverage Arm', 'Available'),
      storyPitcher(13, 'Brendon Little', 'Depth Arm', 'Available'),
      storyPitcher(14, 'Bowden Francis', 'Depth Arm', 'Available'),
    ],
    Monitor: [
      storyPitcher(15, 'Chad Green', 'Trust Arm', 'Monitor', { fatigue_score: 78 }),
      storyPitcher(16, 'Jeff Hoffman', 'Trust Arm', 'Monitor', { fatigue_score: 72 }),
      storyPitcher(17, 'Yimi Garcia', 'Bridge Arm', 'Monitor', { fatigue_score: 68 }),
      storyPitcher(18, 'Tim Mayza', 'Coverage Arm', 'Monitor', { fatigue_score: 54 }),
    ],
  },
})

const oneValidNameBoard = makeBoard({
  teamName: 'Texas Rangers', abbr: 'TEX', state: 'manageable',
  metrics: { total_relievers: 8, available: 4, monitor: 4, limited: 0, avoid: 0, unavailable: 0, pct_available: 50, pct_restricted: 0 },
  cardsByStatus: {
    Available: [
      storyPitcher(41, 'Rested Reliever', 'Bridge Arm', 'Available'),
      storyPitcher(42, 'Clean Option', 'Coverage Arm', 'Available'),
      storyPitcher(43, 'Depth Arm', 'Depth Arm', 'Available'),
      storyPitcher(44, 'Available Arm', 'Depth Arm', 'Available'),
    ],
    Monitor: [
      storyPitcher(45, 'Josh Sborz', 'Trust Arm', 'Monitor', { fatigue_score: 78 }),
      storyPitcher(46, 'Trust Arm', 'Trust Arm', 'Monitor', { fatigue_score: 72 }),
      storyPitcher(47, 'Bridge Arm', 'Bridge Arm', 'Monitor', { fatigue_score: 68 }),
      storyPitcher(48, 'Cal Coverage', 'Coverage Arm', 'Monitor', { fatigue_score: 54 }),
    ],
  },
})

const substituteBridgeBoard = makeBoard({
  teamName: 'Arizona Diamondbacks', abbr: 'AZ', state: 'manageable',
  metrics: { total_relievers: 5, available: 2, monitor: 0, limited: 2, avoid: 1, unavailable: 0, pct_available: 40, pct_restricted: 60 },
  cardsByStatus: {
    Available: [
      storyPitcher(51, 'Justin Martinez', 'Trust Arm', 'Available', { fatigue_score: 18 }),
      storyPitcher(52, 'Kevin Ginkel', 'Bridge Arm', 'Available', { fatigue_score: 22 }),
    ],
    Limited: [
      storyPitcher(53, 'Ryan Thompson', 'Bridge Arm', 'Limited', { fatigue_score: 64 }),
      storyPitcher(54, 'Joe Mantiply', 'Bridge Arm', 'Limited', { fatigue_score: 66 }),
    ],
    Avoid: [
      storyPitcher(55, 'Andrew Saalfrank', 'Depth Arm', 'Avoid', { fatigue_score: 84 }),
    ],
  },
})

const restedBoard = makeBoard({
  teamName: 'Washington Nationals', abbr: 'WSH', state: 'manageable',
  metrics: { total_relievers: 8, available: 6, monitor: 1, limited: 0, avoid: 1, unavailable: 0, pct_available: 75, pct_restricted: 12 },
  cardsByStatus: {
    Available: [
      storyPitcher(21, 'Kyle Finnegan', 'Trust Arm', 'Available', { fatigue_score: 18 }),
      storyPitcher(22, 'Hunter Harvey', 'Bridge Arm', 'Available', { fatigue_score: 20 }),
      storyPitcher(23, 'Derek Law', 'Coverage Arm', 'Available', { fatigue_score: 24 }),
      storyPitcher(24, 'Jordan Weems', 'Depth Arm', 'Available', { fatigue_score: 19 }),
      storyPitcher(25, 'Robert Garcia', 'Depth Arm', 'Available', { fatigue_score: 22 }),
      storyPitcher(26, 'Tanner Rainey', 'Depth Arm', 'Available', { fatigue_score: 28 }),
    ],
    Monitor: [
      storyPitcher(27, 'Jacob Barnes', 'Bridge Arm', 'Monitor', { fatigue_score: 42 }),
    ],
    Avoid: [
      storyPitcher(28, 'Dylan Floro', 'Coverage Arm', 'Avoid', { fatigue_score: 84 }),
    ],
  },
})

const thinningTrustLaneBoard = makeBoard({
  teamName: 'New York Yankees', abbr: 'NYY', state: 'manageable',
  metrics: { total_relievers: 8, available: 6, monitor: 1, limited: 1, avoid: 0, unavailable: 0, pct_available: 75, pct_restricted: 0 },
  cardsByStatus: {
    Available: [
      storyPitcher(61, 'Luke Weaver', 'Trust Arm', 'Available', { fatigue_score: 18 }),
      storyPitcher(62, 'Devin Williams', 'Trust Arm', 'Available', { fatigue_score: 20 }),
      storyPitcher(63, 'Fernando Cruz', 'Bridge Arm', 'Available', { fatigue_score: 22 }),
      storyPitcher(64, 'Tim Hill', 'Bridge Arm', 'Available', { fatigue_score: 24 }),
      storyPitcher(65, 'Mark Leiter Jr.', 'Bridge Arm', 'Available', { fatigue_score: 26 }),
      storyPitcher(66, 'Ian Hamilton', 'Coverage Arm', 'Available', { fatigue_score: 28 }),
    ],
    Monitor: [
      storyPitcher(67, 'David Bednar', 'Trust Arm', 'Monitor', { fatigue_score: 54 }),
    ],
    Limited: [
      storyPitcher(68, 'Ryan Yarbrough', 'Trust Arm', 'Limited', { fatigue_score: 64 }),
    ],
  },
})

const balancedBoard = makeBoard({
  teamName: 'Chicago Cubs', abbr: 'CHC', state: 'manageable',
  metrics: { total_relievers: 8, available: 4, monitor: 1, limited: 1, avoid: 0, unavailable: 2, pct_available: 50, pct_restricted: 37 },
  cardsByStatus: {
    Available: [
      storyPitcher(31, 'Adbert Alzolay', 'Trust Arm', 'Available'),
      storyPitcher(32, 'Julian Merryweather', 'Bridge Arm', 'Available'),
      storyPitcher(33, 'Keegan Thompson', 'Coverage Arm', 'Available'),
      storyPitcher(34, 'Luke Little', 'Depth Arm', 'Available'),
    ],
    Monitor: [
      storyPitcher(35, 'Mark Leiter Jr.', 'Bridge Arm', 'Monitor'),
    ],
    Limited: [
      storyPitcher(36, 'Yency Almonte', 'Depth Arm', 'Limited'),
    ],
    Unavailable: [
      storyPitcher(37, 'Caleb Kilian', 'Depth Arm', 'Unavailable'),
      storyPitcher(38, 'Jose Cuas', 'Depth Arm', 'Unavailable'),
    ],
  },
})

const dataLimitedBoard = makeBoard({
  teamName: 'Miami Marlins', abbr: 'MIA', state: 'no_data',
  metrics: { total_relievers: 0, available: 0, monitor: 0, limited: 0, avoid: 0, unavailable: 0, pct_available: 0, pct_restricted: 0 },
})

// ── Story family derivation ────────────────────────────────────────────────

test('each board shape lands in its story family', () => {
  assert.equal(deriveStoryFamily(constrainedBoard), 'constrained')
  assert.equal(deriveStoryFamily(watchBoard), 'watch')
  assert.equal(deriveStoryFamily(restedBoard), 'rested')
  assert.equal(deriveStoryFamily(balancedBoard), 'balanced')
  assert.equal(deriveStoryFamily(dataLimitedBoard), 'data_limited')
  assert.equal(deriveTeamStoryArchetype(watchBoard), 'heavy_lifting')
  assert.equal(deriveTeamStoryArchetype(restedBoard), 'depth_advantage')
  assert.equal(deriveTeamStoryArchetype(thinningTrustLaneBoard), 'thinning_trust_lane')
})

test('high trust-lane pressure with deep clean options does not read as thin margin', () => {
  const story = getTeamBullpenStoryView(thinningTrustLaneBoard)
  const html = render(React.createElement(TeamBullpenStoryPanel, { board: thinningTrustLaneBoard }))

  assert.equal(story.label, 'Thinning Trust Lane')
  assert.match(story.headline, /fewer trusted late-inning options/)
  assert.match(story.observation, /6 relievers are usable/)
  assert.match(story.observation, /2 clean Trust Arms; 1 on watch; 1 needs rest/)
  assert.ok(story.evidence.some(item => /6 usable arms remain available from 8 active bullpen arms/.test(item)))
  assert.ok(htmlIncludes(html, 'Deep Clean Options'))
  assert.ok(htmlIncludes(html, 'Stable Late-Inning Trust'))
  assert.ok(htmlIncludes(html, 'High Late-Inning Pressure'))
  assert.ok(!htmlIncludes(html, 'Thin Margin'))
  assert.ok(!htmlIncludes(html, 'fewer clean paths'))
})

test('genuine low-availability pressure still reads as thin margin with count copy', () => {
  const story = getTeamBullpenStoryView(genuineThinMarginBoard)

  assert.equal(story.label, 'Thin Margin')
  assert.match(story.observation, /4 relievers of 8 need rest/)
  assert.match(story.whyItMatters, /short on clean late-game options/)
})

test('a constrained club gets a specific story with real counts', () => {
  const story = getTeamBullpenStoryView(constrainedBoard)
  assert.equal(story.family, 'constrained')
  assert.equal(story.archetypeKey, 'coverage_concern')
  assert.equal(story.label, 'Coverage Concern')
  assert.match(story.headline, /Milwaukee Brewers have a shorter bridge/)
  assert.match(story.observation, /Middle-inning coverage is thin/)
  assert.ok(story.evidence.some(item => /1 of 2 middle-inning options are clean or only lightly flagged/.test(item)))
  assert.ok(!/Cal Coverage|Cooper Coverage|Drew Depth/.test(story.evidence.join(' ')))
  assert.ok(!story.evidence.some(item => /most directly shaping the coverage read/.test(item)))
  assert.ok(story.watchItems.length >= 2 && story.watchItems.length <= 4)
})

test('Coverage Concern requires actual Coverage Arms under stress', () => {
  const story = getTeamBullpenStoryView(constrainedBoard)
  const storyText = [
    story.headline,
    story.observation,
    story.whyItMatters,
    ...story.evidence,
  ].join(' ')

  assert.equal(deriveTeamStoryArchetype(constrainedBoard), 'coverage_concern')
  assert.equal(story.label, 'Coverage Concern')
  assert.match(story.observation, /1 of 2 middle-inning options are clean or only lightly flagged/)
  assert.ok(!storyText.includes('0 of 0 Coverage Arms'))
})

test('zero Coverage Arms fall to Bridge Dependency when substitute bridge stress exists', () => {
  const story = getTeamBullpenStoryView(substituteBridgeBoard)
  const html = render(React.createElement(TeamBullpenStoryPanel, { board: substituteBridgeBoard }))
  const storyText = [
    story.headline,
    story.observation,
    story.whyItMatters,
    ...story.evidence,
    ...story.watchItems,
    html,
  ].join(' ')

  assert.equal(deriveTeamStoryArchetype(substituteBridgeBoard), 'bridge_dependency')
  assert.equal(story.label, 'Bridge Dependency')
  assert.ok(!storyText.includes('0 of 0 Coverage Arms'))
  assert.ok(!/tighter coverage picture|coverage layer is tighter/.test(storyText))
})

test('a watch-list club reads calm surface, heavy workload', () => {
  const story = getTeamBullpenStoryView(watchBoard)
  assert.equal(story.label, 'Heavy Lifting')
  assert.match(story.headline, /same relievers to carry the workload/)
  assert.match(story.observation, /4 relievers of 8 sit on the watch list/)
  assert.ok(story.evidence.some(item => /Chad Green, Jeff Hoffman, Yimi Garcia/.test(item)))
})

test('a rested club reads as a deeper bullpen with room to maneuver', () => {
  const story = getTeamBullpenStoryView(restedBoard)
  assert.equal(story.label, 'Depth Advantage')
  assert.match(story.headline, /multiple routes through the late innings/)
  assert.match(story.observation, /usable group goes beyond one or two names/)
  assert.ok(story.evidence.some(item => /Kyle Finnegan, Hunter Harvey, and Derek Law/.test(item)))
})

test('story generation is deterministic for the same board', () => {
  assert.deepEqual(
    getTeamBullpenStoryView(restedBoard),
    getTeamBullpenStoryView(restedBoard),
  )
})

test('public team story fields avoid robotic voice residue', () => {
  const stories = [
    constrainedBoard,
    watchBoard,
    restedBoard,
    thinningTrustLaneBoard,
    substituteBridgeBoard,
  ].map(board => getTeamBullpenStoryView(board))
  const text = stories.map(story => [
    story.headline,
    story.observation,
    story.whyItMatters,
    ...story.evidence,
    ...story.watchItems,
  ].join(' ')).join(' ').toLowerCase()

  for (const phrase of [
    'story starts with',
    'the watch is',
    'watch point',
    'current read',
    'current window',
    'reads differently from the prior bullpen shape',
    'late-game flexibility can become less balanced',
  ]) {
    assert.equal(text.includes(phrase), false, phrase)
  }
})

test('a neutral club gets balanced story copy', () => {
  const story = getTeamBullpenStoryView(balancedBoard)
  assert.equal(story.label, 'Stable Bullpen')
  assert.match(story.headline, /holding steady today/)
  assert.match(story.observation, /4 usable arms, 1 watch-list arm, and 1 needing rest/)
})

test('a thin dataset gets an honest limited read', () => {
  const story = getTeamBullpenStoryView(dataLimitedBoard)
  assert.equal(story.label, 'Limited Read')
  assert.match(story.headline, /not enough bullpen data/)
  assert.ok(story.evidence.length >= 1)
})

test('no board means no story', () => {
  assert.equal(getTeamBullpenStoryView(null).hasStory, false)
  assert.equal(render(React.createElement(TeamBullpenStoryPanel, { board: null })), '')
})

// ── Panel rendering & placement ────────────────────────────────────────────

test('the panel renders headline, unlabeled narrative, and the framing line', () => {
  const story = getTeamBullpenStoryView(constrainedBoard)
  const html = render(React.createElement(TeamBullpenStoryPanel, { board: constrainedBoard }))
  assert.ok(htmlIncludes(html, 'What BaseballOS Sees About This Bullpen'))
  assert.ok(htmlIncludes(html, 'aria-label="Share Milwaukee Brewers bullpen"'))
  assert.ok(htmlIncludes(html, 'data-share-url="https://baseballos.vercel.app/team/MIL"'))
  assert.ok(htmlIncludes(html, story.observation))
  assert.ok(htmlIncludes(html, story.whyItMatters))
  assert.ok(htmlIncludes(html, story.watchItems[0]))
  assert.ok(!htmlIncludes(html, 'Observation'))
  assert.ok(!htmlIncludes(html, 'Evidence'))
  assert.ok(!htmlIncludes(html, 'Why It Matters'))
  assert.ok(!htmlIncludes(html, 'What BaseballOS Is Watching'))
  assert.ok(htmlIncludes(html, STORY_FRAMING_LINE))
})

test('the panel renders Today’s Bullpen Shape in the required order with explanations', () => {
  const html = render(React.createElement(TeamBullpenStoryPanel, { board: constrainedBoard }))
  const orderedLabels = [
    'Late-Inning Trust',
    'Clean Options',
    'Late-Inning Pressure',
    'Workload Concentration',
    'Coverage Margin',
    'Depth Margin',
  ]

  assert.ok(htmlIncludes(html, 'Today’s Bullpen Shape'))
  assert.ok(htmlIncludes(html, '6 reads'))
  let cursor = html.indexOf('Today’s Bullpen Shape')
  for (const label of orderedLabels) {
    const index = html.indexOf(label, cursor)
    assert.ok(index > cursor, `${label} should render after the prior shape row`)
    cursor = index
  }
  assert.ok(htmlIncludes(html, 'Stable Late-Inning Trust'))
  assert.ok(htmlIncludes(html, 'Thin Clean Options'))
  assert.ok(htmlIncludes(html, 'High Late-Inning Pressure'))
  assert.ok(htmlIncludes(html, 'Some Workload Concentration'))
  assert.ok(htmlIncludes(html, 'Thin Coverage Margin'))
  assert.ok(htmlIncludes(html, 'Limited Depth Margin'))
  assert.ok(htmlIncludes(html, 'Trusted late-inning arms: 1 Clean Option; 1 Watch Arm; 1 Rest-Restricted.'))
  assert.ok(htmlIncludes(html, '2 Clean Options from 7 active arms.'))
  assert.ok(htmlIncludes(html, 'Late-inning pressure: 2 Watch Arms; 3 Rest-Restricted; 1 Unavailable.'))
  assert.ok(htmlIncludes(html, 'Top 3 arms: 65% of recent relief pitches across 8 participating arms.'))
  assert.ok(htmlIncludes(html, 'aria-label="Stable Late-Inning Trust. Trusted late-inning arms: 1 Clean Option; 1 Watch Arm; 1 Rest-Restricted."'))
  assert.ok(!htmlIncludes(html, 'BaseballOS Reads'))
  assert.ok(!htmlIncludes(html, 'What these mean'))
  assert.ok(!htmlIncludes(html, 'Recovery Window'))
})

test('the shape section stays label-led and avoids score ranking or grade language', () => {
  const html = render(React.createElement(TeamBullpenStoryPanel, { board: constrainedBoard }))
  const start = html.indexOf('Today’s Bullpen Shape')
  const end = html.indexOf(STORY_FRAMING_LINE)
  const shapeHtml = html.slice(start, end)

  for (const term of [
    'Team Score', 'Bullpen Score', 'Score:', 'Rating', 'Grade', 'Index',
    'ranking', 'ranked', 'leaderboard', 'scorecard',
  ]) {
    assert.ok(!shapeHtml.includes(term), `shape section leaked score/ranking language: ${term}`)
  }
})

test('the board view mounts the story panel above the board only when asked', () => {
  const withPanel = render(React.createElement(BullpenBoardView, { board: constrainedBoard, showStoryPanel: true }))
  assert.ok(htmlIncludes(withPanel, 'What BaseballOS Sees About This Bullpen'))
  assert.ok(
    withPanel.indexOf('What BaseballOS Sees About This Bullpen') < withPanel.indexOf('Bullpen Board'),
    'story panel should sit above the board heading',
  )

  // Embedded uses (e.g. the side-by-side comparison) stay unchanged.
  const withoutPanel = render(React.createElement(BullpenBoardView, { board: constrainedBoard }))
  assert.ok(!htmlIncludes(withoutPanel, 'What BaseballOS Sees About This Bullpen'))
})

test('the mounted panel labels trust-lane pressure separately from overall availability', () => {
  const board = {
    ...thinningTrustLaneBoard,
    stress: {
      label: 'Manageable',
      summary: 'Overall bullpen availability is manageable.',
      reasons: ['6 of 8 relievers are classified Available.'],
      limitations: [],
      confidence: 'high',
      is_stale: false,
      tone: 'manageable',
    },
  }
  const html = render(React.createElement(BullpenBoardView, { board, showStoryPanel: true }))

  assert.ok(htmlIncludes(html, 'Late-Inning Pressure'))
  assert.ok(htmlIncludes(html, 'High Late-Inning Pressure'))
  assert.ok(htmlIncludes(html, 'Overall Availability: Manageable'))
  assert.ok(!htmlIncludes(html, 'Bullpen Stress: Manageable'))
  assert.ok(!htmlIncludes(html, 'Bullpen Pressure'))
})

test('different bullpen shapes create different narratives', () => {
  const stories = [constrainedBoard, watchBoard, restedBoard, balancedBoard]
    .map(board => getTeamBullpenStoryView(board))

  assert.equal(new Set(stories.map(story => story.archetypeKey)).size, stories.length)
  assert.equal(new Set(stories.map(story => story.headline)).size, stories.length)
  assert.equal(new Set(stories.map(story => story.observation)).size, stories.length)
})

test('evidence names are deterministic and support the observation', () => {
  const story = getTeamBullpenStoryView(watchBoard)
  const evidenceText = story.evidence.join(' ')

  assert.ok(/Chad Green/.test(evidenceText))
  assert.ok(/Jeff Hoffman/.test(evidenceText))
  assert.ok(/Yimi Garcia/.test(evidenceText))
  assert.ok(!/Erik Swanson/.test(evidenceText), 'clean options should not drive the heavy-lifting evidence')
  assert.ok(story.evidence.length >= 2 && story.evidence.length <= 4)
})

test('evidence name helper only uses actual player name fields', () => {
  assert.equal(getPitcherEvidenceName({ name: 'Chad Green' }), 'Chad Green')
  assert.equal(getPitcherEvidenceName({ name: 'Coverage Arm', player_name: 'Elvis Peguero' }), 'Elvis Peguero')
  assert.equal(getPitcherEvidenceName({ name: '', pitcher_name: 'Bryan Hudson' }), 'Bryan Hudson')
  assert.equal(getPitcherEvidenceName({ name: 'Coverage Arm', role_label: 'Chad Green' }), '')
})

test('role and read labels are not treated as evidence names', () => {
  for (const label of [
    'Trust Arm',
    'Bridge Arm',
    'Coverage Arm',
    'Depth Arm',
    'Limited Read',
    'Watch Arm',
    'Clean Option',
    'Rest-Restricted',
    'Unavailable',
    'Active MLB',
    'Strong Read',
  ]) {
    assert.equal(isValidPitcherEvidenceName(label), false, `${label} should not be a pitcher name`)
  }
})

test('coverage and depth labels are rejected as synthetic evidence names', () => {
  for (const label of [
    'Coverage Safety',
    'Depth Safety',
    'Coverage Concern',
    'Depth Advantage',
    'Cal Coverage',
    'Cooper Coverage',
    'Drew Depth',
    'Uri Depth',
  ]) {
    assert.equal(isValidPitcherEvidenceName(label), false, `${label} should not be a pitcher name`)
  }
})

test('pitcher-name evidence falls back to counts when fewer than two valid names exist', () => {
  const story = getTeamBullpenStoryView(oneValidNameBoard)
  const evidenceText = story.evidence.join(' ')

  assert.equal(story.label, 'Heavy Lifting')
  assert.ok(!/Josh Sborz/.test(evidenceText), 'single valid name should not produce a name sentence')
  assert.ok(!/Trust Arm|Bridge Arm|Cal Coverage/.test(evidenceText))
  assert.ok(story.evidence.some(item => /4 of 8 relievers are on the watch list/.test(item)))
  assert.ok(story.evidence.some(item => /4 usable arms remain available/.test(item)))
})

test('pitcher names stay out of headline, observation, why, and watch items', () => {
  const story = getTeamBullpenStoryView(watchBoard)
  const nonEvidenceText = [
    story.headline,
    story.narrative,
    story.observation,
    story.whyItMatters,
    ...story.watchItems,
  ].join(' ')

  for (const name of ['Chad Green', 'Jeff Hoffman', 'Yimi Garcia']) {
    assert.ok(story.evidence.join(' ').includes(name), `${name} should appear in evidence`)
    assert.ok(!nonEvidenceText.includes(name), `${name} leaked outside evidence`)
  }
})

// ── Language guardrails ────────────────────────────────────────────────────

const allBoards = [constrainedBoard, watchBoard, restedBoard, balancedBoard, dataLimitedBoard]

test('the story panel never renders raw system phrasing', () => {
  for (const board of allBoards) {
    const html = render(React.createElement(TeamBullpenStoryPanel, { board })).toLowerCase()
    for (const term of [
      'availability inventory', 'readiness limitations', 'limitations are present',
      'snapshot', 'governance', 'classification', 'algorithm', 'data state',
      'contract', 'fail closed',
      // Mechanical phrasing the language layer exists to prevent in prose.
      'workload-restricted', 'register as', 'availability picture',
    ]) {
      assert.ok(!html.includes(term), `${board.team.team_abbreviation} leaked system phrasing: ${term}`)
    }
  }
})

test('the story panel avoids prediction, betting, injury, and recommendation language', () => {
  for (const board of allBoards) {
    const html = render(React.createElement(TeamBullpenStoryPanel, { board }))
      .replace(new RegExp(escapeRegExp(STORY_FRAMING_LINE), 'g'), '')
      .toLowerCase()
    for (const term of [
      'will collapse', 'guaranteed', 'bet ', 'betting', 'odds', 'parlay',
      'injury', 'prediction', 'predict', 'recommended', 'recommendation',
      'should use', 'use this pitcher', 'manager should', 'best arm', 'best option',
    ]) {
      assert.ok(!html.includes(term), `${board.team.team_abbreviation} leaked: ${term}`)
    }
  }
})
