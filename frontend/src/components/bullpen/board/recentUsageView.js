const textValue = (value) => (
  typeof value === 'string' && value.trim() ? value.trim() : null
)

const nonNegativeInteger = (value) => Number.isInteger(value) && value >= 0

const PUBLISHED_WINDOWS = [
  ['window_7', 7],
  ['window_14', 14],
]

function validWindow(window) {
  if (!window || typeof window !== 'object' || Array.isArray(window)) return false

  const counts = [
    window.relief_appearances,
    window.pitchers_in_relief,
    window.appearances_with_pitches,
    window.start_relief_unknown,
  ]
  if (!counts.every(nonNegativeInteger)) return false
  if (window.pitches_total !== null && !nonNegativeInteger(window.pitches_total)) return false
  if (window.pitchers_in_relief > window.relief_appearances) return false
  if (window.appearances_with_pitches > window.relief_appearances) return false
  const pitchCoverageComplete = window.appearances_with_pitches === window.relief_appearances
  if (pitchCoverageComplete && window.pitches_total === null) return false
  if (!pitchCoverageComplete && window.pitches_total !== null) return false
  if (!textValue(window.through)) return false

  return Boolean(
    textValue(window.sentence)
    && textValue(window.pitchers_sentence)
    && textValue(window.pitches_sentence)
  )
}

export function getRecentUsageView(payload) {
  const sourceWindows = payload?.windows && typeof payload.windows === 'object'
    ? payload.windows
    : {}
  const windows = []

  for (const [key, days] of PUBLISHED_WINDOWS) {
    const window = sourceWindows[key]
    if (!validWindow(window)) continue

    const limitations = []
    if (window.start_relief_unknown > 0) {
      const sentence = textValue(window.start_relief_unknown_sentence)
      if (sentence) limitations.push(sentence)
    }
    if (window.appearances_with_pitches < window.relief_appearances) {
      limitations.push(textValue(window.pitches_sentence))
    }

    windows.push({
      key,
      days,
      through: textValue(window.through),
      reliefAppearances: window.relief_appearances,
      pitchersInRelief: window.pitchers_in_relief,
      pitchesTotal: window.pitches_total,
      sentence: textValue(window.sentence),
      limitations: limitations.filter(Boolean),
    })
  }

  const groups = Array.isArray(payload?.relief_by_date) ? payload.relief_by_date : []
  let latestGroup = null
  for (const group of groups) {
    if (!group || typeof group !== 'object' || group.available === false || group.unavailable === true) continue
    const gameDate = textValue(group.game_date)
    const sentence = textValue(group.sentence)
    if (!gameDate || !sentence) continue

    const arms = []
    const appearances = Array.isArray(group.appearances) ? group.appearances : []
    for (const [index, appearance] of appearances.entries()) {
      const name = textValue(appearance?.pitcher_full_name)
      if (!name) continue
      arms.push({
        key: appearance?.pitcher_id != null
          ? `${appearance.pitcher_id}-${index}`
          : `published-arm-${index}`,
        pitcherId: appearance?.pitcher_id ?? null,
        name,
      })
    }

    latestGroup = { gameDate, sentence, arms }
    break
  }

  if (windows.length === 0 && !latestGroup) return { available: false }

  const primaryWindow = windows.find(window => window.days === 7) || windows[0]

  return {
    available: true,
    windows,
    latestGroup,
    summaryLines: primaryWindow ? [
      textValue(sourceWindows[primaryWindow.key].sentence),
      textValue(sourceWindows[primaryWindow.key].pitchers_sentence),
      textValue(sourceWindows[primaryWindow.key].pitches_sentence),
    ] : [],
    limitation: primaryWindow?.limitations?.[0] || null,
    mostRecentSentence: latestGroup?.sentence || null,
  }
}
