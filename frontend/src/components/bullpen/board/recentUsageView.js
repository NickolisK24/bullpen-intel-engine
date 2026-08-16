const textValue = (value) => (
  typeof value === 'string' && value.trim() ? value.trim() : null
)

const nonNegativeInteger = (value) => Number.isInteger(value) && value >= 0

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
  const window = payload?.windows?.window_7
  if (!validWindow(window)) return { available: false }

  const firstGroup = Array.isArray(payload?.relief_by_date)
    ? payload.relief_by_date[0]
    : null
  const mostRecentSentence = (
    firstGroup && typeof firstGroup === 'object'
      ? textValue(firstGroup.sentence)
      : null
  )
  const limitation = window.start_relief_unknown > 0
    ? textValue(window.start_relief_unknown_sentence)
    : null

  return {
    available: true,
    summaryLines: [
      textValue(window.sentence),
      textValue(window.pitchers_sentence),
      textValue(window.pitches_sentence),
    ],
    limitation,
    mostRecentSentence,
  }
}
