/**
 * Artifact-backed Share Card adapter (Share Cards SC-03A cutover).
 *
 * The active Share Card entry points consume a canonical, published, immutable
 * Share Artifact through the backend compatibility projection
 * (GET /api/share-cards/team-state/<team_id>) instead of composing card
 * intelligence in the browser. This module ONLY adapts that governed projection
 * into the shape the existing renderer / share menu already consume — it
 * composes no intelligence and invents no copy. When no published artifact
 * exists it yields null, so the share menu shows its controlled unavailable
 * state; it never falls back to the legacy client-side composer.
 *
 * Transitional: the existing browser PNG renderer and share controls remain for
 * now but render only immutable-artifact-backed data. This adapter is removed
 * once the SC-06/SC-07 renderer consumes the canonical payload directly.
 */

// Canonical public origin for share links. Defined here so the active entry
// points no longer depend on the deprecated client-side card composer module.
export const EVIDENCE_CARD_ORIGIN = 'https://baseballos.app'

const COMPATIBILITY_SOURCE = 'immutable_share_artifact'
const TEAM_CARD_LIMITATION = 'Describes current workload. Does not predict usage or outcomes.'
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

function formatDataThroughLabel(iso) {
  if (!iso) return null
  const parts = String(iso).split('-')
  if (parts.length !== 3) return null
  const year = parseInt(parts[0], 10)
  const month = parseInt(parts[1], 10)
  const day = parseInt(parts[2], 10)
  if (!year || !month || !day || month < 1 || month > 12) return null
  return `${MONTHS[month - 1]} ${day}, ${year}`
}

/**
 * Adapt the backend compatibility projection response into the team card model
 * consumed by the existing renderer and share menu. Returns null when no
 * published artifact backs the card (never fabricates a card).
 */
export function buildTeamShareCardFromArtifact(response) {
  if (!response || response.available !== true) return null
  const card = response.card
  if (!card || card.source !== COMPATIBILITY_SOURCE) return null

  const team = card.team || {}
  const abbr = (team.team_abbreviation || '').toString()
  const teamName = team.team_name || abbr || 'Team'
  const statusLabel = card.headline || null
  const summary = card.summary || null
  const receipts = Array.isArray(card.receipts)
    ? card.receipts.map((item) => (item ? item.detail : null)).filter(Boolean).slice(0, 3)
    : []
  const dataThrough = card.product_date || null
  const headline = (summary || statusLabel || teamName).toString().toUpperCase()
  const destinationUrl =
    `${EVIDENCE_CARD_ORIGIN}/bullpen?view=board&team=${encodeURIComponent(abbr)}#team-relief-work`

  return {
    cardType: 'team',
    headline,
    stateLabel: statusLabel,
    supportingLine: null,
    summary,
    teamName,
    teamAbbreviation: abbr,
    receipts,
    dataThrough,
    dataThroughLabel: formatDataThroughLabel(dataThrough),
    limitation: TEAM_CARD_LIMITATION,
    evidenceSection: 'team-relief-work',
    evidenceTarget: 'team_relief_work',
    evidenceCtaLabel: 'SEE THE CURRENT TEAM RELIEF WORK',
    destinationUrl,
    displayUrl: destinationUrl.replace(/^https?:\/\//, ''),
    shareText: `${teamName} current bullpen read. See the current BaseballOS evidence.`,
    altText: `BaseballOS team state card for ${teamName}. ${statusLabel || ''} ${summary || ''}`
      .trim()
      .slice(0, 320),
    fileName: `baseballos-${(abbr || 'team').toLowerCase()}-bullpen-${dataThrough || 'current'}.png`,
    artifactPublicId: card.public_id || null,
    source: card.source,
    // cardVersion / storyAngle are intentionally omitted: the governed values are
    // not in the legacy share-action tracker allowlist, so supplying them would
    // cause the tracker to reject the action. Omitting keeps share-action
    // tracking working (the action is still recorded via the caller context).
  }
}
