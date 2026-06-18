// Story Engine V1 foundation.
//
// This module does not create new signals or fetch new data. It takes the
// story candidates the existing homepage and Stories view-models already
// derive, then adds deterministic tiering, significance scoring, evidence
// checks, and suppression.

export const STORY_ENGINE_V1_VERSION = 'story_engine_v1_foundation'

export const STORY_TIERS = Object.freeze({
  league: Object.freeze({
    key: 'tier_1',
    level: 1,
    label: 'League-wide story',
    description: 'A bullpen pattern that matters beyond one club.',
  }),
  team: Object.freeze({
    key: 'tier_2',
    level: 2,
    label: 'Team story',
    description: 'A club-level bullpen story with enough evidence to surface.',
  }),
  pitcher: Object.freeze({
    key: 'tier_3',
    level: 3,
    label: 'Pitcher story',
    description: 'A pitcher-level story that needs broader context to surface.',
  }),
  data: Object.freeze({
    key: 'tier_4',
    level: 4,
    label: 'Data observation / suppressible',
    description: 'A data or trust note that only surfaces when the evidence is useful.',
  }),
})

export const SIGNIFICANCE_LEVELS = Object.freeze({
  lead: Object.freeze({ key: 'lead', label: 'Lead story', min: 78 }),
  high: Object.freeze({ key: 'high', label: 'High significance', min: 62 }),
  solid: Object.freeze({ key: 'solid', label: 'Solid significance', min: 48 }),
  supporting: Object.freeze({ key: 'supporting', label: 'Supporting significance', min: 36 }),
  low: Object.freeze({ key: 'low', label: 'Low significance', min: 0 }),
})

export const STORY_ARCHETYPES = Object.freeze({
  concentratedWorkload: Object.freeze({
    key: 'concentrated_workload',
    label: 'Concentrated Workload',
    lane: 'team',
    theme: 'workload',
  }),
  heavyLifting: Object.freeze({
    key: 'heavy_lifting',
    label: 'Heavy Lifting',
    lane: 'team',
    theme: 'workload',
  }),
  thinMargin: Object.freeze({
    key: 'thin_margin',
    label: 'Thin Margin',
    lane: 'team',
    theme: 'pressure',
  }),
  recoveryWindow: Object.freeze({
    key: 'recovery_window',
    label: 'Recovery Window',
    lane: 'team',
    theme: 'recovery',
  }),
  deepPenAdvantage: Object.freeze({
    key: 'deep_pen_advantage',
    label: 'Deep Pen Advantage',
    lane: 'team',
    theme: 'recovery',
  }),
  watchListGrowth: Object.freeze({
    key: 'watch_list_growth',
    label: 'Watch List Growth',
    lane: 'team',
    theme: 'movement',
  }),
  usageShift: Object.freeze({
    key: 'usage_shift',
    label: 'Usage Shift',
    lane: 'team',
    theme: 'movement',
  }),
  bridgeDependency: Object.freeze({
    key: 'bridge_dependency',
    label: 'Bridge Dependency',
    lane: 'team',
    theme: 'dependency',
  }),
  trustArmDependency: Object.freeze({
    key: 'trust_arm_dependency',
    label: 'Trust Arm Dependency',
    lane: 'team',
    theme: 'dependency',
  }),
  coverageGap: Object.freeze({
    key: 'coverage_gap',
    label: 'Coverage Gap',
    lane: 'team',
    theme: 'depth',
  }),
  depthConstraint: Object.freeze({
    key: 'depth_constraint',
    label: 'Depth Constraint',
    lane: 'team',
    theme: 'depth',
  }),
  leagueWidePressure: Object.freeze({
    key: 'league_wide_pressure',
    label: 'League-Wide Pressure',
    lane: 'league',
    theme: 'pressure',
  }),
  leagueWideRecovery: Object.freeze({
    key: 'league_wide_recovery',
    label: 'League-Wide Recovery',
    lane: 'league',
    theme: 'recovery',
  }),
  leagueCheckIn: Object.freeze({
    key: 'league_check_in',
    label: 'League Check-In',
    lane: 'league',
    theme: 'quiet',
  }),
  dataContext: Object.freeze({
    key: 'data_context',
    label: 'Data Context',
    lane: 'data',
    theme: 'data',
  }),
})

const STORY_ARCHETYPE_BY_KEY = Object.freeze(
  Object.fromEntries(Object.values(STORY_ARCHETYPES).map(archetype => [archetype.key, archetype])),
)

function plural(value, singular, pluralWord = `${singular}s`) {
  return asNumber(value) === 1 ? singular : pluralWord
}

function teamDisplayName(candidate) {
  const team = teamFromCandidate(candidate)
  return text(candidate?.teamName || team?.teamName || candidate?.abbr || team?.abbr) || 'This bullpen'
}

function withTeam(teamName, sentence) {
  return sentence.replace(/\{team\}/g, teamName)
}

function storyCounts(candidate, context = {}) {
  const team = teamFromCandidate(candidate)
  const league = context?.leagueMetrics || {}
  const source = team || league
  return {
    available: asNumber(candidate.available ?? source.available),
    monitor: asNumber(candidate.monitor ?? source.monitor),
    restricted: asNumber(candidate.restricted ?? source.restricted),
    total: asNumber(candidate.total ?? source.total),
  }
}

function firstSentence(value) {
  const clean = text(value)
  if (!clean) return ''
  const match = clean.match(/^.*?[.!?](?:\s|$)/)
  return text(match ? match[0] : clean)
}

function escapeRegExp(value) {
  return text(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function teamFingerprintNames(candidate) {
  const team = teamFromCandidate(candidate) || {}
  return [
    teamDisplayName(candidate),
    team.teamName,
    team.abbr,
    candidate?.teamName,
    candidate?.abbr,
  ].map(text).filter(Boolean)
}

function fingerprintText(value, candidate = null) {
  let clean = text(value).toLowerCase()
  if (candidate) {
    for (const name of teamFingerprintNames(candidate)) {
      clean = clean.replace(new RegExp(`\\b${escapeRegExp(name.toLowerCase())}\\b`, 'g'), 'team')
    }
  }
  return clean
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\b(the|a|an)\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function narrativeTemplate(title, body, whyItMatters = null) {
  return Object.freeze({ title, body, whyItMatters })
}

function titleTarget(story) {
  return text(story.title) ? 'title' : 'headline'
}

function bodyTarget(story) {
  return text(story.body) ? 'body' : 'observation'
}

function renderNarrativeTemplate(template, candidate, context = {}) {
  const teamName = teamDisplayName(candidate)
  const { available, monitor, restricted, total } = storyCounts(candidate, context)
  const safeTotal = total > 0 ? total : 'the group'
  const replacements = {
    team: teamName,
    available,
    monitor,
    restricted,
    total: safeTotal,
    availableRelievers: plural(available, 'reliever'),
    monitorArms: plural(monitor, 'arm'),
    restrictedRelievers: plural(restricted, 'reliever'),
  }
  const apply = value => Object.entries(replacements).reduce(
    (line, [key, replacement]) => line.replace(new RegExp(`\\{${key}\\}`, 'g'), replacement),
    withTeam(teamName, value),
  )
  return {
    title: apply(template.title),
    body: apply(template.body),
    whyItMatters: template.whyItMatters ? apply(template.whyItMatters) : null,
  }
}

export const STORY_NARRATIVE_TEMPLATES = Object.freeze({
  concentrated_workload: Object.freeze([
    narrativeTemplate(
      'The {team} box score looks calm. The bullpen does not.',
      'Nobody in this pen is flashing red, but {monitor} of {total} arms are carrying heavy recent work. That is how a calm-looking bullpen can still have a story underneath.',
      'The bullpen still has options, but the work is collecting on a narrower group than the surface read suggests.',
    ),
    narrativeTemplate(
      'The {team} keep asking the same relievers for the heavy lifting',
      '{monitor} {monitorArms} in the {team} pen are carrying the heavier recent work. That is the kind of quiet strain a box score can miss.',
      'It gets harder to mix and match late when the same arms keep taking the ball.',
    ),
    narrativeTemplate(
      'The {team} bullpen work is flowing through a small core',
      '{monitor} of {total} relievers are on the watch list, so the recent workload is not spreading evenly across the pen.',
      'A concentrated workload can matter even before anyone is fully unavailable.',
    ),
    narrativeTemplate(
      'A familiar group keeps carrying the {team} bullpen',
      'Recent work is still centered on {monitor} {monitorArms}, leaving the rest of the bullpen in a more supporting role.',
      'For fans, repeated late-inning usage can narrow the manager\'s cleanest paths.',
    ),
  ]),
  heavy_lifting: Object.freeze([
    narrativeTemplate(
      'The {team} are leaning on the same names again',
      '{monitor} of {total} arms sit on the watch list. No club is asking more of one group today.',
      'That kind of heavy lifting can shape how much bullpen room exists before the late innings even start.',
    ),
    narrativeTemplate(
      'A handful of {team} relievers are doing most of the lifting',
      '{monitor} {monitorArms} are carrying enough recent work to sit on the watch list, keeping the workload centered on a small group.',
      'The issue is not just who is available; it is how much recent work the same arms have already carried.',
    ),
    narrativeTemplate(
      'Recent {team} leverage is centered on a familiar group',
      'The watch list has {monitor} of {total} relievers, a sign that the recent work is clustering around the same names.',
      'That can make a deep bullpen feel more dependent on one familiar core.',
    ),
  ]),
  thin_margin: Object.freeze([
    narrativeTemplate(
      'The {team} have the thinnest late-inning margin in baseball today',
      '{restricted} of the pen\'s {total} relievers come in needing rest after the work they have carried lately. That leaves less room to breathe late than any club in baseball today.',
      'For fans, the key is whether the club still has more than one clean path through a close game.',
    ),
    narrativeTemplate(
      'The {team} enter today with a thin late-inning margin',
      'The {team} also have {restricted} {restrictedRelievers} needing rest after recent work. The late-inning bench is thinner here too.',
      'The bullpen still has options, but the cleanest late-game routes are more limited than usual.',
    ),
    narrativeTemplate(
      'The {team} are managing from a thinner late-inning bench',
      '{restricted} of {total} relievers need rest after recent work. This pen has less room to breathe late than it would like.',
      'A thinner margin changes how quickly one more busy night can narrow the available options.',
    ),
    narrativeTemplate(
      'The {team} bullpen has less room to absorb more work',
      '{restricted} {restrictedRelievers} already need rest, so another demanding game would press harder on the remaining options.',
      'That matters because the bullpen has less margin for a long starter exit or extra late-inning traffic.',
    ),
    narrativeTemplate(
      'The {team} coverage picture is tighter than usual',
      'With {restricted} of {total} relievers needing rest, the late-inning map has fewer clean routes than normal.',
      'For fans, the key is whether the club can avoid pushing the same available arms into every important inning.',
    ),
  ]),
  recovery_window: Object.freeze([
    narrativeTemplate(
      'No club has more room to maneuver late today than the {team}',
      '{available} of {total} relievers come in rested. That gives this pen more ways through the late innings.',
      'Rested options give a club more ways to get through close innings without forcing the same small group into every spot.',
    ),
    narrativeTemplate(
      'The {team} bullpen has regained flexibility',
      '{available} {availableRelievers} are rested enough to use today, giving the club more room than it had during heavier stretches.',
      'For fans, that matters because one busy stretch does not have to define the next late-game plan.',
    ),
    narrativeTemplate(
      'The recent workload squeeze has eased for the {team}',
      'More options are available now: {available} of {total} relievers come in rested enough to use.',
      'A softer workload picture gives the bullpen more ways to cover a close game.',
    ),
    narrativeTemplate(
      'The {team} have more ways through the late innings',
      'The {team} have {available} {availableRelievers} rested enough to use today. That is the other side of the workload picture.',
      'Depth in rested arms helps keep late-game work from landing on only one narrow path.',
    ),
  ]),
  deep_pen_advantage: Object.freeze([
    narrativeTemplate(
      'The {team} have rested options behind the late innings today',
      '{available} of {total} arms come in rested enough to use, and nobody is carrying too much of the recent load. Depth is part of this pen\'s story today.',
      'Extra rested depth gives the club more ways to bridge a game without leaning only on its core group.',
    ),
    narrativeTemplate(
      'Few bullpens have more routes to the finish than the {team}',
      '{available} {availableRelievers} are rested enough to use, giving this bullpen options beyond its usual late-inning core.',
      'That matters because depth can protect the highest-use arms from taking every close spot.',
    ),
    narrativeTemplate(
      'Depth is creating flexibility for the {team}',
      'The rested group is broad enough that the bullpen can cover innings without forcing one narrow sequence.',
      'A deeper set of usable arms gives the club more room if the game changes shape.',
    ),
  ]),
  watch_list_growth: Object.freeze([
    narrativeTemplate(
      'Who is rested changed overnight',
      'Arms are rotating on and off rest around the league. Today\'s picture is not yesterday\'s.',
      'The change matters because bullpen flexibility can move quickly after one completed game window.',
    ),
    narrativeTemplate(
      'The watch-list picture moved after the latest games',
      'Recent appearances changed which arms need monitoring and which clubs have more room today.',
      'Those shifts explain why the bullpen map can feel different from one morning to the next.',
    ),
    narrativeTemplate(
      'Last night rearranged a few bullpen reads',
      'The newest completed games changed who is rested and who is not. Today\'s bullpen picture reflects it.',
      'That movement is useful because yesterday\'s clean path may not be today\'s clean path.',
    ),
  ]),
  usage_shift: Object.freeze([
    narrativeTemplate(
      'The {team} bullpen workload has shifted recently',
      'Recent usage has picked up around the {team}, and this does not look like the same bullpen pattern from the prior window.',
      'A usage shift matters because the same bullpen can look different once the work starts landing in new places.',
    ),
    narrativeTemplate(
      'Recent {team} usage looks different than it did a week ago',
      'The latest workload pattern is not matching the earlier one, so this bullpen is in a different part of the cycle.',
      'For fans, changing usage can alter which arms are cleanest for the next close game.',
    ),
    narrativeTemplate(
      'The {team} bullpen is entering a different workload phase',
      'The work has moved around the group, and the last few games do not look like the stretch before it.',
      'When the usage phase changes, the bullpen\'s flexibility changes with it.',
    ),
    narrativeTemplate(
      'Workload has redistributed across the {team} bullpen',
      'Recent usage is landing differently across the group, changing the way this bullpen reads today.',
      'That matters because a redistributed workload can create pressure in places the box score does not highlight.',
    ),
  ]),
  bridge_dependency: Object.freeze([
    narrativeTemplate(
      'The {team} are leaning on the bridge again',
      'The middle innings are asking a familiar group to carry the handoff toward the late innings.',
      'Bridge dependency matters because it can narrow the path before the highest-leverage arms even enter.',
    ),
    narrativeTemplate(
      'The {team} middle innings are flowing through a small group',
      'Recent work has kept the bridge portion of the bullpen centered on a familiar set of arms.',
      'That can change how much flexibility remains by the time the late innings arrive.',
    ),
  ]),
  trust_arm_dependency: Object.freeze([
    narrativeTemplate(
      'The {team} trust group is carrying the shape of the pen',
      'The bullpen read is leaning heavily on its most trusted options rather than a broad spread of arms.',
      'That matters because a narrow trust group can make late-game flexibility feel thinner.',
    ),
    narrativeTemplate(
      'The {team} are asking a familiar trust core to hold the line',
      'Recent usage is centered enough that the dependable group is doing much of the stabilizing work.',
      'The key is whether the workload can spread before the core gets overused.',
    ),
  ]),
  coverage_gap: Object.freeze([
    narrativeTemplate(
      'The {team} coverage picture has a gap today',
      'The bullpen has fewer clean ways to cover the middle-to-late bridge than it would like.',
      'Coverage gaps matter because one early exit can force the same arms into harder work.',
    ),
    narrativeTemplate(
      'The {team} have less coverage behind the primary group',
      'The bullpen still has options, but the supporting layer is thinner than usual.',
      'That can matter quickly if the game asks for more than the planned late-inning sequence.',
    ),
  ]),
  depth_constraint: Object.freeze([
    narrativeTemplate(
      'A few bullpens have less room to breathe',
      'Around the league, some clubs are managing from a thinner late-inning bench. The usable options are there, but the margin is tighter.',
      'Depth constraints matter because a narrow bullpen can change quickly after one demanding game.',
    ),
    narrativeTemplate(
      'Depth is tighter in a few bullpen rooms',
      'The bullpen map has pockets where the usable group is narrower than usual.',
      'That gives fans a clearer read on which clubs have less margin if the game stretches.',
    ),
    narrativeTemplate(
      'Some clubs are working with a shorter bullpen runway',
      'The available depth is not spread evenly, so a few pens have fewer clean ways through the night.',
      'A shorter runway matters because one extra inning of work can change tomorrow\'s bullpen shape.',
    ),
  ]),
  league_wide_pressure: Object.freeze([
    narrativeTemplate(
      'The heavy lifting is not isolated to one bullpen',
      '{monitor} tracked arms sit on the watch list and {restricted} need rest. Some of the strain is obvious, and some of it is hiding below a calm surface.',
      'League-wide pressure helps explain whether one club is an outlier or part of a broader bullpen day.',
    ),
    narrativeTemplate(
      'Several bullpens are carrying heavier late-inning work',
      '{monitor} tracked arms sit on the watch list around the league. Heavy recent work is showing up in more than one place.',
      'The wider pattern matters because bullpen pressure is not always isolated to the headline team.',
    ),
    narrativeTemplate(
      'The league-wide workload picture is starting to tighten',
      'Several pens have been busy lately, and the work has not been spread evenly. The same pockets of arms are doing a lot of the lifting.',
      'When the league picture tightens, today\'s team story has useful context around it.',
    ),
  ]),
  league_wide_recovery: Object.freeze([
    narrativeTemplate(
      'The league is not running on empty',
      '{available} tracked relievers are rested enough to be usable today. That does not erase the pressure points, but most bullpens still have room to maneuver.',
      'League-wide recovery matters because not every bullpen pressure point is part of a broad shortage.',
    ),
    narrativeTemplate(
      'The league still has rested options in reserve',
      '{available} tracked relievers are rested enough to be usable today. The pressure points matter, but the league is not running on empty.',
      'That wider recovery picture helps separate isolated stress from a league-wide squeeze.',
    ),
    narrativeTemplate(
      'Rest is quietly changing tonight\'s bullpen map',
      'Some managers have more ways through the late innings than others because the rested options are not spread evenly.',
      'The uneven recovery map helps explain why some clubs have more flexibility than others.',
    ),
  ]),
  league_check_in: Object.freeze([
    narrativeTemplate(
      'A quiet morning across baseball\'s bullpens',
      'No club stands out for bullpen stress or heavy workload today. Around the league, the pens are in reasonable shape.',
      'Quiet days give bullpens a reset point and make the next real pressure point easier to spot.',
    ),
    narrativeTemplate(
      'No bullpen story is separating from the pack today',
      'The league picture is balanced enough that no single club is forcing the headline.',
      'A quiet baseline matters because it gives the next shift more context.',
    ),
  ]),
  data_context: Object.freeze([
    narrativeTemplate(
      'There is not enough recent activity for a stronger bullpen note',
      'The available information only supports a limited read today. That is better than forcing a conclusion.',
      'Limited inputs are useful when they stop short of a bigger claim.',
    ),
    narrativeTemplate(
      'Today\'s picture is waiting on completed games',
      'Part of the bullpen picture comes from earlier in the week. The story sharpens as new completed games arrive.',
      'A data note helps separate a true bullpen read from an incomplete window.',
    ),
    narrativeTemplate(
      'The data note is part of the bullpen story today',
      'The trusted late-inning picture has a caveat, so the note stays inside what the inputs support.',
      'That restraint matters because a clear limitation is more useful than a forced conclusion.',
    ),
  ]),
})

const DEFAULT_MIN_SIGNIFICANCE = 42
const DATA_MIN_SIGNIFICANCE = 36
const LEAGUE_CROWD_OUT_MARGIN = 8

const MECHANICAL_LANGUAGE_PATTERNS = [
  /\bavailability inventory\b/i,
  /\breadiness limitations\b/i,
  /\blimitations are present\b/i,
  /\btrusted snapshot\b/i,
  /\bfatigue score\b/i,
  /\bconfidence score\b/i,
  /\bontology\b/i,
  /\bdata_state\b/i,
  /\bfail_closed\b/i,
  /\bregister as\b/i,
  /\bworkload-restricted\b/i,
  /\blimited recovery window\b/i,
  /\bcarrying workload concentration\b/i,
]

function asNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function text(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function candidateText(candidate) {
  return [
    candidate?.kicker,
    candidate?.title,
    candidate?.body,
    candidate?.observation,
    candidate?.whyItMatters,
  ].map(text).filter(Boolean).join(' ')
}

function storyKind(candidate) {
  return text(candidate?.storyKind || candidate?.family || candidate?.kicker).toLowerCase()
}

function normalizedArchetypeKey(value) {
  return text(value).toLowerCase().replace(/-/g, '_')
}

export function getStoryArchetype(candidate = {}) {
  const explicitKey = normalizedArchetypeKey(candidate.archetype_key || candidate.archetypeKey)
  if (STORY_ARCHETYPE_BY_KEY[explicitKey]) return STORY_ARCHETYPE_BY_KEY[explicitKey]

  const kind = storyKind(candidate)
  const family = text(candidate.family || sourceObservation(candidate)?.family).toLowerCase()
  const contextType = text(candidate.context?.type).toLowerCase()
  const trend = text(candidate.context?.evidence?.trend).toLowerCase()

  if (kind === 'team_workload_continuity') return STORY_ARCHETYPES.concentratedWorkload
  if (kind === 'team_workload') return STORY_ARCHETYPES.heavyLifting
  if (kind === 'team_pressure') return STORY_ARCHETYPES.thinMargin
  if (kind === 'team_recovery') return STORY_ARCHETYPES.recoveryWindow
  if (kind === 'team_depth') return STORY_ARCHETYPES.deepPenAdvantage
  if (kind === 'team_usage_shift') return STORY_ARCHETYPES.usageShift
  if (contextType === 'usage_demand' || contextType === 'rotation_length') {
    return trend === 'decreasing_demand' || trend === 'longer_outings'
      ? STORY_ARCHETYPES.recoveryWindow
      : STORY_ARCHETYPES.usageShift
  }
  if (kind === 'league_check_in') return STORY_ARCHETYPES.leagueCheckIn
  if (kind === 'league_recovery') return STORY_ARCHETYPES.leagueWideRecovery
  if (kind === 'league_workload' || kind === 'league_workload_continuity') {
    return STORY_ARCHETYPES.leagueWidePressure
  }
  if (family === 'availability_movement' || family === 'snapshot_change') return STORY_ARCHETYPES.watchListGrowth
  if (family === 'workload_pressure' || family === 'constraint') return STORY_ARCHETYPES.leagueWidePressure
  if (family === 'readiness') return STORY_ARCHETYPES.leagueWideRecovery
  if (family === 'inventory') return STORY_ARCHETYPES.depthConstraint
  if (family === 'freshness' || family === 'trust' || kind.includes('data')) return STORY_ARCHETYPES.dataContext
  if (kind.includes('depth')) return STORY_ARCHETYPES.depthConstraint
  if (kind.includes('pressure') || kind.includes('stress')) return STORY_ARCHETYPES.thinMargin
  if (kind.includes('recovery') || kind.includes('rest')) return STORY_ARCHETYPES.recoveryWindow
  if (kind.includes('workload') || kind.includes('watch')) return STORY_ARCHETYPES.heavyLifting

  return STORY_ARCHETYPES.dataContext
}

export function getNarrativeTemplatesForArchetype(archetypeKey) {
  return STORY_NARRATIVE_TEMPLATES[normalizedArchetypeKey(archetypeKey)] || []
}

function preferredNarrativeTemplateIndex(candidate, archetype, templates, context = {}) {
  if (templates.length <= 1) return 0
  const { available, monitor, restricted, total } = storyCounts(candidate, context)
  const restrictedShare = total > 0 ? restricted / total : 0
  const monitorShare = total > 0 ? monitor / total : 0
  const availableShare = total > 0 ? available / total : 0
  const kind = storyKind(candidate)
  const kicker = text(candidate.kicker).toLowerCase()
  const contextType = text(candidate.context?.type).toLowerCase()
  const trend = text(candidate.context?.evidence?.trend).toLowerCase()
  const lastIndex = templates.length - 1
  const at = index => Math.min(index, lastIndex)

  switch (archetype.key) {
    case STORY_ARCHETYPES.concentratedWorkload.key:
      if (kicker.includes('hidden')) return 0
      if (monitor >= 4 || monitorShare >= 0.5) return at(1)
      if (monitor >= 3 || monitorShare >= 0.35) return at(2)
      return at(3)
    case STORY_ARCHETYPES.heavyLifting.key:
      if (monitor >= 4 || monitorShare >= 0.5) return 0
      if (monitor >= 3) return at(1)
      return at(2)
    case STORY_ARCHETYPES.thinMargin.key:
      if (restricted >= 4 || restrictedShare >= 0.45) return 0
      if (kicker.includes('pressure watch')) return at(1)
      if (restricted >= 3) return at(2)
      if (restricted >= 2) return at(3)
      return at(4)
    case STORY_ARCHETYPES.recoveryWindow.key:
      if (kicker.includes('rested options')) return at(3)
      if (available >= 6 || availableShare >= 0.7) return 0
      if (trend === 'decreasing_demand' || trend === 'longer_outings') return at(2)
      if (restricted <= 1 && monitor <= 1) return at(1)
      return at(3)
    case STORY_ARCHETYPES.deepPenAdvantage.key:
      if (available >= 6 || availableShare >= 0.7) return at(1)
      if (monitor === 0 && restricted === 0) return at(2)
      return 0
    case STORY_ARCHETYPES.usageShift.key:
      if (contextType === 'rotation_length') return at(1)
      if (trend === 'increasing_demand' || trend === 'shorter_outings') return 0
      if (trend === 'decreasing_demand' || trend === 'longer_outings') return at(2)
      return at(3)
    case STORY_ARCHETYPES.watchListGrowth.key:
      if (kicker.includes('movement')) return 0
      if (kicker.includes('what changed')) return at(2)
      return at(1)
    case STORY_ARCHETYPES.bridgeDependency.key:
    case STORY_ARCHETYPES.trustArmDependency.key:
      return monitor >= 3 ? at(1) : 0
    case STORY_ARCHETYPES.coverageGap.key:
      return restricted >= 2 ? 0 : at(1)
    case STORY_ARCHETYPES.depthConstraint.key:
      if (restricted >= 2) return 0
      if (available <= 3) return at(2)
      return at(1)
    case STORY_ARCHETYPES.leagueWidePressure.key:
      if (restricted > monitor) return 0
      if (monitor >= 20 || monitorShare >= 0.3) return at(1)
      return at(2)
    case STORY_ARCHETYPES.leagueWideRecovery.key:
      if (available >= 40 || availableShare >= 0.6) return 0
      if (available >= 25) return at(1)
      return at(2)
    case STORY_ARCHETYPES.leagueCheckIn.key:
      return contextFreshness(context).is_current === false ? at(1) : 0
    case STORY_ARCHETYPES.dataContext.key:
      if (kind.includes('freshness')) return at(1)
      if (kind.includes('trust')) return 0
      return at(2)
    default:
      return Math.abs((available * 7) + (monitor * 5) + (restricted * 3) + total) % templates.length
  }
}

function storyTitleValue(story) {
  return text(story.title || story.headline)
}

function storyOpeningValue(story) {
  return firstSentence(story.body || story.observation || story.noticed)
}

function storyTitleFingerprint(story, candidate) {
  return fingerprintText(storyTitleValue(story), candidate || story)
}

function storyOpeningFingerprint(story, candidate) {
  return fingerprintText(storyOpeningValue(story), candidate || story)
}

function selectNarrativeVariant(candidate, narrativeContext = {}) {
  const archetype = getStoryArchetype(candidate)
  const templates = getNarrativeTemplatesForArchetype(archetype.key)
  if (templates.length === 0) return null

  const storyContext = narrativeContext.storyContext || {}
  const preferred = preferredNarrativeTemplateIndex(candidate, archetype, templates, storyContext)
  const usedTitleFingerprints = narrativeContext.usedTitleFingerprints || new Set()
  const usedOpeningFingerprints = narrativeContext.usedOpeningFingerprints || new Set()
  const choices = []

  for (let offset = 0; offset < templates.length; offset += 1) {
    const index = (preferred + offset) % templates.length
    const rendered = renderNarrativeTemplate(templates[index], candidate, storyContext)
    const titleFingerprint = fingerprintText(rendered.title, candidate)
    const openingFingerprint = fingerprintText(firstSentence(rendered.body), candidate)
    const duplicates = usedTitleFingerprints.has(titleFingerprint)
      || usedOpeningFingerprints.has(openingFingerprint)
    choices.push({ index, rendered, titleFingerprint, openingFingerprint, duplicates })
    if (!duplicates) return choices[choices.length - 1]
  }

  return choices[0]
}

function applyNarrativeVariant(story, candidate, narrativeContext = {}) {
  const variant = selectNarrativeVariant(candidate, narrativeContext)
  if (!variant) return story

  const titleField = titleTarget(story)
  const bodyField = bodyTarget(story)
  const next = {
    ...story,
    [titleField]: variant.rendered.title || story[titleField],
    [bodyField]: variant.rendered.body || story[bodyField],
    narrative_template_key: `${story.archetype_key}:${variant.index + 1}`,
    narrative_variant_index: variant.index,
    narrative_fingerprint: `${variant.titleFingerprint}|${variant.openingFingerprint}`,
  }
  if (variant.rendered.whyItMatters) {
    next.whyItMatters = variant.rendered.whyItMatters
  }
  return next
}

function storyLane(candidate, tier, archetype) {
  const explicitLane = text(candidate.story_lane || candidate.storyLane).toLowerCase()
  if (['team', 'league', 'pitcher', 'data'].includes(explicitLane)) return explicitLane
  if (tier.key === STORY_TIERS.pitcher.key) return 'pitcher'
  if (tier.key === STORY_TIERS.data.key) return 'data'
  if (teamFromCandidate(candidate)) return 'team'
  return archetype?.lane || 'league'
}

function teamFromCandidate(candidate) {
  if (candidate?.team) return candidate.team
  if (candidate?.teamId == null && candidate?.teamName == null) return null
  return {
    teamId: candidate.teamId ?? null,
    teamName: candidate.teamName ?? null,
    abbr: candidate.abbr ?? null,
    available: asNumber(candidate.available),
    monitor: asNumber(candidate.monitor),
    restricted: asNumber(candidate.restricted),
    total: asNumber(candidate.total),
    pctAvailable: asNumber(candidate.pctAvailable),
    pctRestricted: asNumber(candidate.pctRestricted),
  }
}

function teamKey(candidate) {
  const team = teamFromCandidate(candidate)
  return team?.teamId ?? team?.abbr ?? team?.teamName ?? null
}

function sourceObservation(candidate) {
  return candidate?.sourceObservation || candidate?.observationSource || null
}

function usesLeagueMetricContext(candidate) {
  if (teamFromCandidate(candidate)) return true
  return classifyStoryTier(candidate).key === STORY_TIERS.league.key
}

function contextMetrics(context = {}) {
  return context.leagueMetrics || {}
}

function contextFreshness(context = {}) {
  return context.freshness || {}
}

function normalizeEvidenceItem(item, fallbackSource = 'story_candidate') {
  if (!item || typeof item !== 'object') return null
  const label = text(item.label || item.evidence_label || item.name)
  if (!label) return null
  return {
    label,
    value: item.value ?? item.evidence_value ?? null,
    source: text(item.source) || fallbackSource,
    sourceType: text(item.source_type || item.sourceType) || 'derived_story_evidence',
    detail: text(item.detail || item.summary) || null,
    dataThrough: text(item.data_through || item.dataThrough) || null,
    freshnessStatus: text(item.freshness_status || item.freshnessStatus) || null,
  }
}

function evidenceFromTeam(team) {
  if (!team) return []
  const total = asNumber(team.total)
  if (total <= 0) return []
  return [
    {
      label: 'Relievers needing rest',
      value: `${asNumber(team.restricted)} of ${total}`,
      source: 'bullpen_dashboard_landscape',
      sourceType: 'team_bullpen_counts',
      detail: 'Recent workload has left this many tracked relievers needing a day.',
    },
    {
      label: 'Watch-list arms',
      value: `${asNumber(team.monitor)} of ${total}`,
      source: 'bullpen_dashboard_landscape',
      sourceType: 'team_bullpen_counts',
      detail: 'Tracked relievers carrying enough recent work to watch.',
    },
    {
      label: 'Rested options',
      value: `${asNumber(team.available)} of ${total}`,
      source: 'bullpen_dashboard_landscape',
      sourceType: 'team_bullpen_counts',
      detail: 'Tracked relievers coming in rested.',
    },
  ]
}

function evidenceFromObservation(observation) {
  if (!observation || !Array.isArray(observation.evidence)) return []
  return observation.evidence
    .map(item => normalizeEvidenceItem(item, 'governed_observation_feed'))
    .filter(Boolean)
}

function evidenceFromLeague(candidate, context = {}) {
  const metrics = contextMetrics(context)
  const total = asNumber(metrics.total)
  if (total <= 0) return []
  const kind = storyKind(candidate)
  const includeStress = kind.includes('pressure') || kind.includes('workload') || candidate?.tone === 'stress'
  const includeWorkload = kind.includes('workload') || kind.includes('watch') || candidate?.tone === 'watch'
  const includeRest = kind.includes('recovery') || kind.includes('rest') || candidate?.tone === 'rest'

  const evidence = []
  if (includeStress) {
    evidence.push({
      label: 'League arms needing rest',
      value: `${asNumber(metrics.restricted)} of ${total}`,
      source: 'bullpen_dashboard_context',
      sourceType: 'league_bullpen_counts',
      detail: 'Tracked relievers league-wide needing a day after recent work.',
    })
  }
  if (includeWorkload) {
    evidence.push({
      label: 'League watch-list arms',
      value: `${asNumber(metrics.monitor)} of ${total}`,
      source: 'bullpen_dashboard_context',
      sourceType: 'league_bullpen_counts',
      detail: 'Tracked relievers league-wide carrying enough recent work to watch.',
    })
  }
  if (includeRest) {
    evidence.push({
      label: 'League rested options',
      value: `${asNumber(metrics.available)} of ${total}`,
      source: 'bullpen_dashboard_context',
      sourceType: 'league_bullpen_counts',
      detail: 'Tracked relievers league-wide coming in rested.',
    })
  }
  return evidence
}

export function buildStoryEvidence(candidate = {}, context = {}) {
  const provided = Array.isArray(candidate.evidence)
    ? candidate.evidence.map(item => normalizeEvidenceItem(item)).filter(Boolean)
    : []
  const observationEvidence = evidenceFromObservation(sourceObservation(candidate))
  const teamEvidence = evidenceFromTeam(teamFromCandidate(candidate))
  const leagueEvidence = teamEvidence.length || !usesLeagueMetricContext(candidate)
    ? []
    : evidenceFromLeague(candidate, context)

  const seen = new Set()
  return [...provided, ...observationEvidence, ...teamEvidence, ...leagueEvidence]
    .filter(item => {
      const key = `${item.label}:${item.value}:${item.source}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

export function classifyStoryTier(candidate = {}) {
  if (candidate.tier?.key) {
    const known = Object.values(STORY_TIERS).find(tier => tier.key === candidate.tier.key)
    if (known) return known
  }
  const kind = storyKind(candidate)
  if (candidate.pitcherId != null || kind.includes('pitcher')) return STORY_TIERS.pitcher
  if (candidate.teamId != null || candidate.teamName || candidate.team) return STORY_TIERS.team
  if (
    kind.includes('data')
    || kind.includes('trust')
    || kind.includes('freshness')
    || candidate.kicker === 'Data Note'
  ) {
    return STORY_TIERS.data
  }
  return STORY_TIERS.league
}

function factor(key, label, points, reason) {
  return {
    key,
    label,
    points: Math.round(clamp(points, 0, 30)),
    reason,
  }
}

function workloadConcentrationFactor(candidate, context) {
  const team = teamFromCandidate(candidate)
  const metrics = contextMetrics(context)
  const source = team || (usesLeagueMetricContext(candidate) ? metrics : {})
  const monitor = asNumber(source.monitor)
  const total = asNumber(source.total)
  const kind = storyKind(candidate)
  const observation = sourceObservation(candidate)
  let points = 0

  if (total > 0) {
    const share = monitor / total
    points = Math.max(points, share >= 0.5 ? 24 : share >= 0.35 ? 20 : share >= 0.25 ? 14 : monitor > 0 ? 8 : 0)
  }
  if (monitor >= 4) points = Math.max(points, 22)
  if (monitor >= 3) points = Math.max(points, 18)
  if (kind.includes('workload') || kind.includes('watch') || observation?.family === 'workload_pressure') {
    points = Math.max(points, observation?.family === 'workload_pressure' ? 12 : 10)
  }

  return factor(
    'workload_concentration',
    'Workload concentration',
    points,
    points > 0
      ? `${monitor} tracked ${monitor === 1 ? 'arm is' : 'arms are'} on the watch list.`
      : 'No meaningful watch-list concentration is present.',
  )
}

function bullpenStressFactor(candidate, context) {
  const team = teamFromCandidate(candidate)
  const metrics = contextMetrics(context)
  const source = team || (usesLeagueMetricContext(candidate) ? metrics : {})
  const restricted = asNumber(source.restricted)
  const total = asNumber(source.total)
  const kind = storyKind(candidate)
  let points = 0

  if (total > 0) {
    const share = restricted / total
    points = Math.max(points, share >= 0.45 ? 28 : share >= 0.35 ? 24 : share >= 0.25 ? 18 : restricted > 0 ? 9 : 0)
  }
  if (restricted >= 4) points = Math.max(points, 26)
  if (restricted >= 3) points = Math.max(points, 23)
  if (candidate?.tone === 'stress' || kind.includes('pressure')) points = Math.max(points, 12)

  return factor(
    'bullpen_stress',
    'Bullpen stress',
    points,
    points > 0
      ? `${restricted} tracked ${restricted === 1 ? 'arm needs' : 'arms need'} rest after recent work.`
      : 'No meaningful rest shortage is present.',
  )
}

function recencyFactor(candidate, context) {
  const observation = sourceObservation(candidate)
  const freshness = observation?.freshness || contextFreshness(context)
  const games = context.games || {}
  const evidence = buildStoryEvidence(candidate, context)
  let points = 4
  let reason = 'The story has limited current-date context.'

  if (freshness?.status === 'current' || freshness?.is_current === true || freshness?.sync_status === 'success') {
    points = 14
    reason = 'The source data is marked current.'
  } else if (freshness?.data_through || games.as_of_date || games.data_state === 'historical') {
    points = 11
    reason = 'The story is tied to the latest completed-game window.'
  }

  if (evidence.some(item => item.freshnessStatus === 'current' || item.dataThrough)) {
    points = Math.max(points, 12)
    reason = 'Evidence carries current or dated source context.'
  }

  return factor('recency', 'Recency', points, reason)
}

function teamImpactFactor(candidate, context) {
  const tier = classifyStoryTier(candidate)
  const team = teamFromCandidate(candidate)
  const metrics = contextMetrics(context)
  let points = 0
  let reason = 'The story has limited team or league impact.'

  if (tier.key === STORY_TIERS.team.key && team) {
    const total = asNumber(team.total)
    const restricted = asNumber(team.restricted)
    const monitor = asNumber(team.monitor)
    const available = asNumber(team.available)
    points = total >= 7 ? 12 : total >= 5 ? 9 : 6
    if (restricted >= 3 || monitor >= 4 || available >= 6) points += 3
    reason = `${team.teamName || 'This club'} has a complete enough bullpen shape to carry a team story.`
  } else if (tier.key === STORY_TIERS.league.key) {
    const total = asNumber(metrics.total)
    const affected = asNumber(metrics.monitor) + asNumber(metrics.restricted)
    points = total > 0 ? 10 : 0
    if (affected >= 20) points += 4
    if (affected >= 10) points += 2
    reason = affected > 0
      ? `${affected} tracked league arms sit in watch or rest-shortage buckets.`
      : 'No broad league impact is present.'
  } else if (tier.key === STORY_TIERS.pitcher.key) {
    points = 5
    reason = 'Pitcher-level notes need broader team context before they lead.'
  } else if (tier.key === STORY_TIERS.data.key) {
    points = sourceObservation(candidate)?.severity === 'significant' ? 6 : 3
    reason = 'Data notes explain why the available information only supports a limited read.'
  }

  return factor('team_level_impact', 'Team-level impact', points, reason)
}

function continuityFactor(candidate) {
  const value = candidateText(candidate).toLowerCase()
  const kind = storyKind(candidate)
  const observation = sourceObservation(candidate)
  let points = 0
  let reason = 'No repeated pattern is visible in the supplied story data.'

  if (kind.includes('continuity') || kind.includes('hidden')) {
    points = 12
    reason = 'The candidate is built around a repeated workload pattern.'
  } else if (/(same arms|keep|keeps|lately|night after night|again|still|recent work|heavy work)/.test(value)) {
    points = 8
    reason = 'The story copy is tied to repeated recent usage.'
  }

  const evidence = Array.isArray(observation?.evidence) ? observation.evidence : []
  if (evidence.some(item => item?.metadata?.repeated_pattern || item?.metadata?.continuity)) {
    points = Math.max(points, 12)
    reason = 'Governed evidence marks a repeated pattern.'
  }

  return factor('narrative_continuity', 'Repeated pattern / narrative continuity', points, reason)
}

function evidenceStrengthFactor(candidate, context) {
  const evidence = buildStoryEvidence(candidate, context)
  const observation = sourceObservation(candidate)
  const directEvidenceCount = (
    (Array.isArray(candidate.evidence) ? candidate.evidence.length : 0)
    + (Array.isArray(observation?.evidence) ? observation.evidence.length : 0)
  )
  let points = 0
  let reason = 'No usable evidence is attached.'

  if (evidence.length >= 3) {
    points = 15
    reason = 'The story is backed by multiple count-based evidence items.'
  } else if (evidence.length === 2) {
    points = 12
    reason = 'The story is backed by more than one evidence item.'
  } else if (evidence.length === 1) {
    points = 9
    reason = 'The story has one usable evidence item.'
  }

  const confidenceStatus = observation?.confidence?.status
  if (directEvidenceCount >= 2) points += 4
  else if (directEvidenceCount === 1) points += 2
  if (confidenceStatus === 'high' || confidenceStatus === 'medium') points += 2
  if (observation?.severity === 'significant') points += 4
  if (observation?.severity === 'elevated') points += 2

  return factor('evidence_strength', 'Evidence strength', points, reason)
}

function fanRelevanceFactor(candidate) {
  const tier = classifyStoryTier(candidate)
  const value = candidateText(candidate)
  const hasReadableCopy = text(candidate.title).length >= 12
    && text(candidate.body || candidate.observation).length >= 24
  let points = hasReadableCopy ? 8 : 3
  let reason = hasReadableCopy
    ? 'The candidate has a clear baseball headline and supporting copy.'
    : 'The candidate needs stronger human-readable story copy.'

  if (candidate.href) points += 2
  if (candidate.teamName || candidate.team?.teamName) points += 2
  if (tier.key === STORY_TIERS.data.key) points = Math.min(points, 6)
  if (MECHANICAL_LANGUAGE_PATTERNS.some(pattern => pattern.test(value))) {
    points = 0
    reason = 'The candidate uses mechanical language and should not surface.'
  }

  return factor('fan_relevance_readability', 'Fan relevance / readability', points, reason)
}

function significanceLevel(total) {
  if (total >= SIGNIFICANCE_LEVELS.lead.min) return SIGNIFICANCE_LEVELS.lead
  if (total >= SIGNIFICANCE_LEVELS.high.min) return SIGNIFICANCE_LEVELS.high
  if (total >= SIGNIFICANCE_LEVELS.solid.min) return SIGNIFICANCE_LEVELS.solid
  if (total >= SIGNIFICANCE_LEVELS.supporting.min) return SIGNIFICANCE_LEVELS.supporting
  return SIGNIFICANCE_LEVELS.low
}

export function scoreStorySignificance(candidate = {}, context = {}) {
  const factors = [
    workloadConcentrationFactor(candidate, context),
    bullpenStressFactor(candidate, context),
    recencyFactor(candidate, context),
    teamImpactFactor(candidate, context),
    continuityFactor(candidate),
    evidenceStrengthFactor(candidate, context),
    fanRelevanceFactor(candidate),
  ]
  const total = factors.reduce((sum, item) => sum + item.points, 0)
  const level = significanceLevel(total)
  return {
    total,
    level: level.key,
    levelLabel: level.label,
    factors,
    summary: `${level.label}: ${factors.filter(item => item.points > 0).map(item => item.label).join(', ') || 'limited supporting signal'}.`,
  }
}

function storyThreshold(candidate, options = {}) {
  if (Number.isFinite(options.minSignificance)) return options.minSignificance
  return classifyStoryTier(candidate).key === STORY_TIERS.data.key
    ? DATA_MIN_SIGNIFICANCE
    : DEFAULT_MIN_SIGNIFICANCE
}

export function getStorySuppressionReasons(candidate = {}, context = {}, options = {}) {
  const tier = classifyStoryTier(candidate)
  const significance = scoreStorySignificance(candidate, context)
  const evidence = buildStoryEvidence(candidate, context)
  const reasons = []
  const value = candidateText(candidate)
  const kind = storyKind(candidate)

  if (!text(candidate.title || candidate.headline) || !text(candidate.body || candidate.observation)) {
    reasons.push('story_missing_human_readable_copy')
  }
  if (evidence.length === 0) {
    reasons.push('story_missing_evidence')
  }
  if (MECHANICAL_LANGUAGE_PATTERNS.some(pattern => pattern.test(value))) {
    reasons.push('mechanical_story_language')
  }
  if (
    kind.includes('minor')
    || (
      kind.includes('availability_movement')
      && !significance.factors.find(item => item.key === 'narrative_continuity' && item.points >= 8)
    )
  ) {
    reasons.push('minor_availability_movement')
  }
  if (
    tier.key === STORY_TIERS.pitcher.key
    && !(
      (candidate.teamId != null || candidate.teamName || candidate.team)
      && evidence.length >= 2
      && significance.factors.find(item => item.key === 'narrative_continuity' && item.points >= 8)
    )
  ) {
    reasons.push('one_off_pitcher_observation')
  }
  if (significance.total < storyThreshold(candidate, options)) {
    reasons.push(tier.key === STORY_TIERS.data.key
      ? 'data_observation_below_surface_threshold'
      : 'story_below_significance_threshold')
  }

  return [...new Set(reasons)]
}

function defaultWhyItMatters(candidate, tier) {
  const kind = storyKind(candidate)
  if (candidate.whyItMatters) return candidate.whyItMatters
  if (kind.includes('pressure') || candidate.tone === 'stress') {
    return 'A short bullpen changes how much room the club has in close games.'
  }
  if (kind.includes('workload') || candidate.tone === 'watch') {
    return 'Heavy work on the same few arms changes how much room the club has before the late innings even start.'
  }
  if (kind.includes('recovery') || candidate.tone === 'rest') {
    return 'Rested options give a club more room to handle the late innings.'
  }
  if (tier.key === STORY_TIERS.data.key) {
    return 'The available information only supports a limited read.'
  }
  return 'The wider league picture helps explain whether one club is an outlier or part of the day\'s broader bullpen shape.'
}

function noticed(candidate) {
  return candidate.noticed
    || candidate.observation
    || candidate.body
    || candidate.title
    || candidate.headline
    || 'A bullpen story changed enough to review.'
}

function selectionReason(tier, significance) {
  const strongest = [...significance.factors]
    .sort((a, b) => b.points - a.points)
    .slice(0, 2)
    .map(item => item.label.toLowerCase())
    .join(' and ')
  return `${tier.label} surfaced for ${strongest || 'supporting evidence'}.`
}

function decorateCandidate(candidate, evaluation, narrativeContext = {}) {
  const { tier, significance, evidence } = evaluation
  const archetype = getStoryArchetype(candidate)
  const lane = storyLane(candidate, tier, archetype)
  const teamSpecific = lane === 'team'
  const leagueWide = lane === 'league'
  const base = {
    ...candidate,
    archetype_key: archetype.key,
    archetype_label: archetype.label,
    story_lane: lane,
    team_specific: teamSpecific,
    league_wide: leagueWide,
    tier,
    significance,
    evidence,
    selectionReason: selectionReason(tier, significance),
  }
  const story = applyNarrativeVariant(base, candidate, narrativeContext)
  const storyNoticed = noticed(story)
  const storyWhyItMatters = text(story.whyItMatters) || defaultWhyItMatters(story, tier)

  return {
    ...story,
    noticed: storyNoticed,
    whyItMatters: storyWhyItMatters,
    storySelection: {
      noticed: storyNoticed,
      whyItMatters: storyWhyItMatters,
      evidence,
      tier: tier.label,
      significance: significance.levelLabel,
      archetype_key: archetype.key,
      archetype_label: archetype.label,
      story_lane: lane,
      team_specific: teamSpecific,
      league_wide: leagueWide,
      ...(story.narrative_template_key ? { narrative_template_key: story.narrative_template_key } : {}),
      ...(story.narrative_variant_index != null ? { narrative_variant_index: story.narrative_variant_index } : {}),
      ...(story.narrative_fingerprint ? { narrative_fingerprint: story.narrative_fingerprint } : {}),
      ...(candidate.continuity_note ? { continuity_note: candidate.continuity_note } : {}),
      ...(candidate.continuity ? { continuity: candidate.continuity } : {}),
      ...(candidate.context_note ? { context_note: candidate.context_note } : {}),
      ...(candidate.context ? { context: candidate.context } : {}),
    },
  }
}

export function evaluateStoryCandidate(candidate = {}, context = {}, index = 0, options = {}) {
  const tier = classifyStoryTier(candidate)
  const significance = scoreStorySignificance(candidate, context)
  const evidence = buildStoryEvidence(candidate, context)
  const suppressionReasons = getStorySuppressionReasons(candidate, context, options)
  return {
    candidate,
    index,
    tier,
    significance,
    evidence,
    suppressed: suppressionReasons.length > 0,
    suppressionReasons,
    story: decorateCandidate(candidate, { tier, significance, evidence }, { storyContext: context }),
  }
}

function compareEvaluations(a, b) {
  if (b.significance.total !== a.significance.total) {
    return b.significance.total - a.significance.total
  }
  if (a.tier.level !== b.tier.level) return a.tier.level - b.tier.level
  return a.index - b.index
}

function normalizedKey(value) {
  return value == null ? null : String(value).toLowerCase()
}

function narrativeKey(story) {
  if (teamKey(story) != null) return `team:${normalizedKey(teamKey(story))}`
  const archetype = getStoryArchetype(story)
  if (story.league_wide || archetype.lane === 'league') return `league:${archetype.key}`
  const theme = storyTheme(story)
  if (theme) return `${archetype.lane || 'theme'}:${theme}`
  return `title:${text(story.title).toLowerCase()}`
}

function storyTheme(story) {
  return getStoryArchetype(story).theme
}

function suppressedEvaluation(evaluation, reason) {
  return {
    ...evaluation,
    suppressed: true,
    suppressionReasons: [...new Set([...evaluation.suppressionReasons, reason])],
  }
}

function selectionBlocker(evaluation, excludedTeams, usedTeams, usedNarratives) {
  const key = normalizedKey(teamKey(evaluation.story))
  const storyNarrative = narrativeKey(evaluation.story)

  if (evaluation.suppressed) return evaluation
  if (key && excludedTeams.has(key)) {
    return suppressedEvaluation(evaluation, 'duplicate_flagship_team_story')
  }
  if (key && usedTeams.has(key)) {
    return suppressedEvaluation(evaluation, 'duplicate_team_narrative')
  }
  if (storyNarrative && usedNarratives.has(storyNarrative)) {
    return suppressedEvaluation(evaluation, 'duplicate_story_narrative')
  }
  return null
}

function compareForDiversity(a, b, usedArchetypes, options = {}) {
  const diversify = options.diversifyArchetypes !== false
  if (diversify) {
    const aArchetypeUsed = usedArchetypes.has(a.story.archetype_key)
    const bArchetypeUsed = usedArchetypes.has(b.story.archetype_key)
    if (aArchetypeUsed !== bArchetypeUsed) return aArchetypeUsed ? 1 : -1
  }

  const leagueMargin = Number.isFinite(options.leagueCrowdOutMargin)
    ? options.leagueCrowdOutMargin
    : LEAGUE_CROWD_OUT_MARGIN
  if (a.story.league_wide !== b.story.league_wide) {
    const league = a.story.league_wide ? a : b
    const team = a.story.league_wide ? b : a
    const leagueIsClearlyStronger = league.significance.total >= team.significance.total + leagueMargin
    if (!leagueIsClearlyStronger && team.story.team_specific) {
      return a.story.league_wide ? 1 : -1
    }
  }

  return compareEvaluations(a, b)
}

export function selectStoryCandidates(candidates = [], context = {}, options = {}) {
  const limit = Number.isFinite(options.limit) ? options.limit : 8
  const excludedTeams = new Set((options.excludedTeamIds || []).map(normalizedKey))
  const usedTeams = new Set()
  const usedNarratives = new Set()
  const usedArchetypes = new Set()
  const usedTitleFingerprints = new Set()
  const usedOpeningFingerprints = new Set()
  const surfaced = []
  const suppressed = []

  for (const story of Array.isArray(options.seedStories) ? options.seedStories : []) {
    const [titleFingerprint, openingFingerprint] = text(story?.narrative_fingerprint).split('|')
    const title = titleFingerprint || storyTitleFingerprint(story)
    const opening = openingFingerprint || storyOpeningFingerprint(story)
    if (title) usedTitleFingerprints.add(title)
    if (opening) usedOpeningFingerprints.add(opening)
  }

  let pending = (Array.isArray(candidates) ? candidates : [])
    .map((candidate, index) => evaluateStoryCandidate(candidate, context, index, options))
    .sort(compareEvaluations)

  while (surfaced.length < limit && pending.length > 0) {
    const eligible = []
    for (const evaluation of pending) {
      const blocked = selectionBlocker(evaluation, excludedTeams, usedTeams, usedNarratives)
      if (blocked) suppressed.push(blocked)
      else eligible.push(evaluation)
    }
    if (eligible.length === 0) break

    const [next] = surfaced.length === 0 || limit === 1
      ? eligible
      : [...eligible].sort((a, b) => compareForDiversity(a, b, usedArchetypes, options))
    const selectedStory = decorateCandidate(next.candidate, next, {
      storyContext: context,
      usedTitleFingerprints,
      usedOpeningFingerprints,
    })
    const key = normalizedKey(teamKey(selectedStory))
    const storyNarrative = narrativeKey(selectedStory)
    surfaced.push(selectedStory)
    if (key) usedTeams.add(key)
    if (storyNarrative) usedNarratives.add(storyNarrative)
    if (selectedStory.archetype_key) usedArchetypes.add(selectedStory.archetype_key)
    const titleFingerprint = storyTitleFingerprint(selectedStory, next.candidate)
    const openingFingerprint = storyOpeningFingerprint(selectedStory, next.candidate)
    if (titleFingerprint) usedTitleFingerprints.add(titleFingerprint)
    if (openingFingerprint) usedOpeningFingerprints.add(openingFingerprint)
    pending = eligible.filter(evaluation => evaluation !== next)
  }

  return {
    items: surfaced,
    suppressed,
    suppressedCount: suppressed.length,
    suppressionReasons: [...new Set(suppressed.flatMap(item => item.suppressionReasons))],
  }
}

export function selectLeadStory(candidates = [], context = {}, options = {}) {
  return selectStoryCandidates(candidates, context, { ...options, limit: 1 }).items[0] || null
}
