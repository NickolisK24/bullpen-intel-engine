/**
 * Canonical Team State Share Artifact adapter.
 *
 * The Team Board resolves one published, integrity-verified public artifact
 * lazily. This module only adapts that immutable public projection into the
 * existing browser renderer model; it does not author or recalculate baseball
 * meaning.
 */

import { PUBLIC_TEAM_STATE_LABELS } from '../adapters/publicTeamState'

export const EVIDENCE_CARD_ORIGIN = 'https://baseballos.app'
const TEAM_STATE_CARD_VERSION = 'team-state-1.2.0'

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

function artifactShareUrl(artifact) {
  const publicId = artifact?.public_id
  const path = artifact?.routes?.share_url
  if (!publicId || typeof path !== 'string') return null
  if (!path.startsWith('/share/') || !path.endsWith(`/${publicId}`)) return null
  return `${EVIDENCE_CARD_ORIGIN}${path}`
}

export function buildTeamShareCardFromArtifact(response) {
  if (!response || response.available !== true) return null
  const artifact = response.artifact
  if (
    !artifact
    || artifact.artifact_type !== 'team_state'
    || artifact.lifecycle_state !== 'published'
  ) return null

  const card = artifact.card
  const team = card?.team || {}
  const state = card?.state || {}
  const statusLabel = state.public_label || null
  const destinationUrl = artifactShareUrl(artifact)
  if (
    !card
    || card.card_version !== TEAM_STATE_CARD_VERSION
    || !PUBLIC_TEAM_STATE_LABELS.includes(statusLabel)
    || !destinationUrl
  ) return null

  const abbr = String(team.abbreviation || '')
  const teamName = team.canonical_name || abbr || 'Team'
  const summary = state.why || state.headline || null
  const receipts = Array.isArray(artifact.evidence)
    ? artifact.evidence.map((item) => item?.detail).filter(Boolean).slice(0, 3)
    : []
  const dataThrough = card.artifact_context?.data_through || artifact.product_date || null
  const limitations = Array.isArray(card.limitations)
    ? card.limitations.filter(Boolean)
    : []

  return {
    cardType: 'team',
    headline: String(state.headline || statusLabel || teamName).toUpperCase(),
    stateLabel: statusLabel,
    supportingLine: null,
    summary,
    teamName,
    teamAbbreviation: abbr,
    receipts,
    dataThrough,
    dataThroughLabel: formatDataThroughLabel(dataThrough),
    limitation: limitations[0] || null,
    evidenceSection: 'team-relief-work',
    evidenceTarget: 'team_relief_work',
    evidenceCtaLabel: 'OPEN THE PUBLISHED OBSERVATION',
    destinationUrl,
    displayUrl: destinationUrl.replace(/^https?:\/\//, ''),
    shareText: artifact.copy?.description || state.headline || statusLabel,
    altText: artifact.copy?.alt_text || `${teamName} published Team State: ${statusLabel}`,
    fileName: `baseballos-${(abbr || 'team').toLowerCase()}-team-state-${dataThrough || 'published'}.png`,
    artifactPublicId: artifact.public_id,
    source: 'immutable_share_artifact',
  }
}
