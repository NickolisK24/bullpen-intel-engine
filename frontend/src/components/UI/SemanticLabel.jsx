const TONES = new Set([
  'neutral',
  'fresh',
  'stretched',
  'vulnerable',
  'available',
  'watch',
  'limited',
  'unavailable',
])

export default function SemanticLabel({ label, tone = 'neutral', className = '' }) {
  const text = typeof label === 'string' ? label.trim() : ''
  if (!text) return null
  const resolvedTone = TONES.has(tone) ? tone : 'neutral'

  return (
    <span className={`semantic-label semantic-label--${resolvedTone} ${className}`.trim()}>
      {text}
    </span>
  )
}
