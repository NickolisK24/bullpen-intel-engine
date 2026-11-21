const timestampWithZone = /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/

export default function HistoricalPitchHand({ hand, className }) {
  if (hand?.basis !== 'official_person_attribute_at_retrieval' || hand.reason
      || !['L', 'R', 'S'].includes(hand.value) || !/^[a-f0-9]{64}$/.test(hand.citation?.facts_digest ?? '')
      || !timestampWithZone.test(hand.observed_at ?? '')) return null

  const observed = new Date(hand.observed_at)
  if (!Number.isFinite(observed.getTime())) return null
  return <span className={className}>
    Throws {hand.value} · MLB profile observed <time dateTime={hand.observed_at}>{observed.toISOString().slice(0, 10)}</time>
  </span>
}
