export function normalizeCardText(value) {
  return typeof value === 'string' ? value.trim().replace(/\s+/g, ' ') : ''
}

export function measureCardText(value, fontSize = 16) {
  return [...normalizeCardText(value)].reduce((width, character) => {
    if (/\s/.test(character)) return width + fontSize * 0.32
    if (/[ilI1.,'!:;]/.test(character)) return width + fontSize * 0.3
    if (/[MW@%&]/.test(character)) return width + fontSize * 0.88
    if (/[A-Z0-9]/.test(character)) return width + fontSize * 0.64
    return width + fontSize * 0.54
  }, 0)
}

export function wrapCardText(value, {
  maxWidth,
  maxLines,
  fontSize,
} = {}) {
  const text = normalizeCardText(value)
  if (!text || !maxWidth || !maxLines || !fontSize) return null
  const words = text.split(' ')
  const lines = []
  for (const word of words) {
    if (measureCardText(word, fontSize) > maxWidth) return null
    const current = lines.at(-1)
    const candidate = current ? `${current} ${word}` : word
    if (measureCardText(candidate, fontSize) <= maxWidth) {
      if (current) lines[lines.length - 1] = candidate
      else lines.push(candidate)
      continue
    }
    if (lines.length >= maxLines) return null
    lines.push(word)
  }
  return lines.length <= maxLines ? lines : null
}

export function isCompleteCardSentence(value) {
  const text = normalizeCardText(value)
  return Boolean(text) && /[.!?]$/.test(text) && !/(?:\.{3}|…)$/.test(text)
}

export function fitCompleteCardText(value, options) {
  const text = normalizeCardText(value)
  if (!text) return null
  if (wrapCardText(text, options)) return text
  const sentences = text.match(/(?:\d+\.\d+|[^.!?])+[.!?]+/g) || []
  for (const sentence of sentences) {
    const candidate = normalizeCardText(sentence)
    if (isCompleteCardSentence(candidate) && wrapCardText(candidate, options)) return candidate
  }
  return null
}

export function selectCompleteCardStatement({
  preferred,
  alternatives = [],
  summary,
  fallback,
  fit,
}) {
  const preferredText = normalizeCardText(preferred)
  if (isCompleteCardSentence(preferredText) && fit(preferredText)) return preferredText

  const shortest = [...new Set(alternatives.map(normalizeCardText))]
    .filter(text => text && text !== preferredText && isCompleteCardSentence(text))
    .sort((left, right) => left.length - right.length || left.localeCompare(right))
    .find(fit)
  if (shortest) return shortest

  const summaryText = normalizeCardText(summary)
  if (isCompleteCardSentence(summaryText) && fit(summaryText)) return summaryText
  return fit(fallback) ? fallback : null
}
