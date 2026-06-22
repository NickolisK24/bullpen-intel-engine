import { fmtDataDate } from '../../dashboard/syncStatusView'

export const STORY_TYPE_DISPLAY = {
  route_change: {
    label: 'Route Change',
    helper: 'Who is handling the important outs now.',
  },
  coverage_pressure: {
    label: 'Coverage Pressure',
    helper: 'Why the bullpen is carrying extra innings.',
  },
  depth_constraint: {
    label: 'Depth Constraint',
    helper: 'Why the practical path is thinner than the roster suggests.',
  },
  sustainability_question: {
    label: 'Sustainability Question',
    helper: 'Whether the current usage pattern can keep functioning.',
  },
  availability_depth: {
    label: 'More Options',
    helper: 'How much rested late-inning depth the bullpen has to work with.',
  },
  trust_lane: {
    label: 'Trust Lane',
    helper: 'How few rested, trusted arms the late-game plan really leans on.',
  },
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
  return STORY_TYPE_DISPLAY[raw]?.label || fallback
}

function helperFromKey(value) {
  const raw = cleanText(value)
  return STORY_TYPE_DISPLAY[raw]?.helper || null
}

function dataThroughLabel(freshness) {
  const dataThrough = freshness.data_through || freshness.data_through_date
  const formatted = fmtDataDate(dataThrough)
  return formatted ? `Data through ${formatted}` : null
}

function trustLabel(trustMetadata) {
  if (trustMetadata.external_generation_used === false) {
    return 'Written from BaseballOS data'
  }
  return null
}

function paragraphs(story) {
  return [
    { key: 'observation', label: 'What changed', text: cleanText(story.observation) },
    { key: 'baseline', label: 'Comparison point', text: cleanText(story.baseline) },
    { key: 'cause', label: 'Why it happened', text: cleanText(story.cause) },
    { key: 'constraint', label: 'What it creates', text: cleanText(story.constraint) },
  ].filter(item => item.text)
}

export function getStoryCardView(story) {
  const payload = asObject(story)
  const freshness = asObject(payload.freshness)
  const trustMetadata = asObject(payload.trust_metadata)
  const available = payload.story_available === true
  const headline = cleanText(payload.headline)
  const storyType = labelFromKey(payload.story_type)
  const storyTypeHelper = helperFromKey(payload.story_type)
  const meta = [
    storyType,
    dataThroughLabel(freshness),
    trustLabel(trustMetadata),
  ].filter(Boolean)

  if (!available) {
    return {
      hasPayload: Boolean(story),
      available: false,
      title: 'Story note is quiet right now',
      message: neutralMessage(payload.neutral_reason),
      storyType,
      storyTypeHelper: null,
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
    storyTypeHelper,
    meta,
    paragraphs: paragraphs(payload),
  }
}

export function neutralMessage(reason) {
  const key = cleanText(reason)
  if (key === 'no_story_observations') {
    return 'BaseballOS is holding this note until the bullpen context has a clear enough signal.'
  }
  if (key === 'no_valid_story_frame') {
    return 'BaseballOS has team context here, but not enough complete evidence to write the note safely.'
  }
  return 'BaseballOS is keeping this note neutral until enough trusted context is available.'
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
    'context indicates',
    'observation type',
    'constraint facts',
    'baseline facts',
    'optionality band',
    'depth pressure band',
    'the frame shows',
    'the frame marks',
    'deterministic',
    'manager should',
    'should use',
  ].some(term => text.includes(term))
}
