const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})/
const DAY_MS = 24 * 60 * 60 * 1000

function baseballDay(value) {
  if (value == null) return null
  const match = String(value).match(DATE_ONLY_RE)
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  if (!year || month < 1 || month > 12 || day < 1 || day > 31) return null
  return {
    iso: `${match[1]}-${match[2]}-${match[3]}`,
    time: Date.UTC(year, month - 1, day),
  }
}

function displayBaseballDate(value) {
  const day = baseballDay(value)
  if (!day) return null
  return new Date(day.time).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

function titleCase(value) {
  if (!value) return value
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}`
}

function pitchNoun(count) {
  return Number(count) === 1 ? 'pitch' : 'pitches'
}

function numericPitchCount(value) {
  if (value == null || value === '') return null
  const count = Number(value)
  return Number.isFinite(count) ? count : null
}

function numericValue(value) {
  if (value == null || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function platformDateFromFreshness(freshness) {
  const source = freshness || {}
  return (
    source.data_through
    || source.latest_workload_date
    || source.current_data_through
    || source.latest_game_date
    || source.reference_date
    || source.availability_reference_date
    || null
  )
}

export function normalizeAppearance(input) {
  if (!input || typeof input !== 'object') return null
  const gameDate = (
    input.game_date
    || input.gameDate
    || input.date
    || input.latest_game_date
    || input.latestGameDate
  )
  if (!baseballDay(gameDate)) return null
  return {
    gameDate,
    pitches: numericPitchCount(
      input.pitches
      ?? input.pitch_count
      ?? input.pitchCount
      ?? input.pitches_thrown
      ?? input.pitchesThrown,
    ),
    inningsPitched: numericValue(
      input.innings_pitched
      ?? input.inningsPitched,
    ),
    inningsPitchedOuts: numericValue(
      input.innings_pitched_outs
      ?? input.inningsPitchedOuts,
    ),
  }
}

export function isWorkloadAppearance(input) {
  const normalized = normalizeAppearance(input)
  return Boolean(normalized && normalized.pitches > 0)
}

export function latestAppearanceFromLogs(logs) {
  const appearances = (Array.isArray(logs) ? logs : [])
    .map(normalizeAppearance)
    .filter(Boolean)

  if (!appearances.length) return null

  const latest = appearances.reduce((winner, item) => (
    baseballDay(item.gameDate).time > baseballDay(winner.gameDate).time ? item : winner
  ))
  const pitches = appearances
    .filter(item => baseballDay(item.gameDate).time === baseballDay(latest.gameDate).time)
    .reduce((sum, item) => sum + (item.pitches || 0), 0)

  return {
    gameDate: latest.gameDate,
    pitches,
  }
}

export function latestWorkloadAppearanceFromLogs(logs) {
  const appearances = (Array.isArray(logs) ? logs : [])
    .map(normalizeAppearance)
    .filter(item => item && item.pitches > 0)

  if (!appearances.length) return null

  const latest = appearances.reduce((winner, item) => (
    baseballDay(item.gameDate).time > baseballDay(winner.gameDate).time ? item : winner
  ))
  const pitches = appearances
    .filter(item => baseballDay(item.gameDate).time === baseballDay(latest.gameDate).time)
    .reduce((sum, item) => sum + (item.pitches || 0), 0)

  return {
    gameDate: latest.gameDate,
    pitches,
  }
}

export function baseballDayDiff(appearanceDate, platformDate) {
  const appearance = baseballDay(appearanceDate)
  const current = baseballDay(platformDate)
  if (!appearance || !current) return null
  return Math.round((current.time - appearance.time) / DAY_MS)
}

export function relativeAppearanceLabel(appearanceDate, platformDate) {
  const diff = baseballDayDiff(appearanceDate, platformDate)
  if (diff == null) return null
  if (diff <= 0) return 'today'
  if (diff === 1) return 'yesterday'
  return `${diff} days ago`
}

export function appearanceDisplayDate(appearanceDate, platformDate) {
  const base = displayBaseballDate(appearanceDate)
  if (!base) return null

  const diff = baseballDayDiff(appearanceDate, platformDate)
  if (diff === 0) return `${base} (Today)`
  if (diff === 1) return `${base} (Yesterday)`
  return base
}

export function compactAppearanceLabel(appearance, platformDate) {
  const normalized = normalizeAppearance(appearance)
  if (!normalized || normalized.pitches == null) return null

  const diff = baseballDayDiff(normalized.gameDate, platformDate)
  const subject = diff === 0
    ? 'Today'
    : diff === 1
      ? 'Yesterday'
      : displayBaseballDate(normalized.gameDate)

  if (!subject) return null
  return `Last appearance: ${subject} (${normalized.pitches})`
}

export function compactWorkloadAppearanceLabel(appearance, platformDate) {
  const normalized = normalizeAppearance(appearance)
  if (!normalized || normalized.pitches == null || normalized.pitches <= 0) return null

  const diff = baseballDayDiff(normalized.gameDate, platformDate)
  const subject = diff === 0
    ? 'Today'
    : diff === 1
      ? 'Yesterday'
      : displayBaseballDate(normalized.gameDate)

  if (!subject) return null
  return `Last workload: ${subject} (${normalized.pitches} ${pitchNoun(normalized.pitches)})`
}

export function appearanceDetailLabel(appearance, platformDate) {
  const normalized = normalizeAppearance(appearance)
  if (!normalized || normalized.pitches == null) return null

  const dateLabel = appearanceDisplayDate(normalized.gameDate, platformDate)
  if (!dateLabel) return null
  return `${dateLabel} • ${normalized.pitches} ${pitchNoun(normalized.pitches)}`
}

export function workloadAppearanceDetailLabel(appearance, platformDate) {
  const normalized = normalizeAppearance(appearance)
  if (!normalized || normalized.pitches == null || normalized.pitches <= 0) return null
  return appearanceDetailLabel(normalized, platformDate)
}

export function appearancePitchReason(count, appearanceDate, platformDate) {
  const numericCount = numericPitchCount(count)
  if (numericCount == null) return null

  const label = relativeAppearanceLabel(appearanceDate, platformDate)
  if (!label) return null
  return `${numericCount} ${pitchNoun(numericCount)} ${label}`
}

export function dayAwareAppearanceReason(reason, appearance, platformDate) {
  const normalized = normalizeAppearance(appearance)
  const match = String(reason || '').match(/^(\d+(?:\.\d+)?)\s+pitches?\s+yesterday$/i)
  if (!normalized || !match) return reason

  const count = numericPitchCount(match[1])
  if (normalized.pitches != null && count !== normalized.pitches) return reason
  return appearancePitchReason(count, normalized.gameDate, platformDate) || reason
}

export function dayAwareAppearanceReasons(reasons, appearance, platformDate) {
  return (Array.isArray(reasons) ? reasons : [])
    .map(reason => dayAwareAppearanceReason(reason, appearance, platformDate))
}

export function titleRelativeAppearanceLabel(appearanceDate, platformDate) {
  return titleCase(relativeAppearanceLabel(appearanceDate, platformDate))
}
