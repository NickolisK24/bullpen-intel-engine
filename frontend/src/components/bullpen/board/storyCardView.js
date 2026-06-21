import { fmtDataDate } from '../../dashboard/syncStatusView'

const STORY_TYPE_LABELS = {
  rotation_pressure: 'Rotation pressure',
  concentration_pressure: 'Concentration pressure',
  optionality_strength: 'Optionality strength',
  stable_core: 'Stable core',
  core_transition: 'Core transition',
  depth_pressure: 'Depth pressure',
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function labelFromKey(value, fallback = 'Bullpen story') {
  const raw = cleanText(value)
  if (!raw) return fallback
  if (STORY_TYPE_LABELS[raw]) return STORY_TYPE_LABELS[raw]
  return raw
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase())
}

function dataThroughLabel(freshness) {
  const dataThrough = freshness.data_through || freshness.data_through_date
  const formatted = fmtDataDate(dataThrough)
  return formatted ? `Data through ${formatted}` : null
}

function trustLabel(trustMetadata) {
  if (trustMetadata.external_generation_used === false) {
    return 'Deterministic BaseballOS note'
  }
  return null
}

function paragraphs(story) {
  return [
    { key: 'observation', label: 'What happened', text: cleanText(story.observation) },
    { key: 'baseline', label: 'Baseline', text: cleanText(story.baseline) },
    { key: 'cause', label: 'Why it happened', text: cleanText(story.cause) },
    { key: 'constraint', label: 'Constraint', text: cleanText(story.constraint) },
  ].filter(item => item.text)
}

export function getStoryCardView(story) {
  const payload = asObject(story)
  const freshness = asObject(payload.freshness)
  const trustMetadata = asObject(payload.trust_metadata)
  const available = payload.story_available === true
  const headline = cleanText(payload.headline)
  const storyType = labelFromKey(payload.story_type)
  const meta = [
    storyType,
    dataThroughLabel(freshness),
    trustLabel(trustMetadata),
  ].filter(Boolean)

  if (!available) {
    return {
      hasPayload: Boolean(story),
      available: false,
      title: 'No bullpen story note available',
      message: neutralMessage(payload.neutral_reason),
      storyType,
      meta,
      paragraphs: [],
    }
  }

  return {
    hasPayload: true,
    available: true,
    title: headline || 'Bullpen story note',
    message: '',
    storyType,
    meta,
    paragraphs: paragraphs(payload),
  }
}

export function neutralMessage(reason) {
  const key = cleanText(reason)
  if (key === 'no_story_observations') {
    return 'BaseballOS does not have a strong enough bullpen story signal for this team right now.'
  }
  if (key === 'no_valid_story_frame') {
    return 'BaseballOS has context for this team, but not enough complete story evidence to write a note safely.'
  }
  return 'BaseballOS is holding this story surface neutral until enough trusted context is available.'
}

export function storyCardHasBannedLanguage(html) {
  const text = String(html || '').toLowerCase()
  return [
    'betting',
    'odds',
    'parlay',
    'prediction',
    'predict',
    'probability',
    'ranked',
    'ranking',
    'best option',
    'manager should',
    'should use',
  ].some(term => text.includes(term))
}
