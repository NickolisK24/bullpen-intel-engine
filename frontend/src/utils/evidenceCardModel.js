import {
  buildComparisonHref,
  buildTeamBoardHref,
  normalizeTeamReference,
} from './evidenceLinks'
import {
  fitCompleteCardText,
  normalizeCardText,
  selectCompleteCardStatement,
  wrapCardText,
} from './evidenceCardText'

export const EVIDENCE_CARD_ORIGIN = 'https://baseballos.app'
const INTERNAL_TERMS = /\b(endpoint|backend|snapshot|governance|threshold|model score|ranking_applied|selection_made|reason_codes?|private medical|bullpen phone)\b/i
const UNSAFE_COMPARISON_TERMS = /\b(winner|wins?|advantage|better|best|rank(?:ing)?|score|edge|pick|prediction)\b/i
const LOW_VALUE_ZERO = /^(?:0 of \d+ .*|no relievers? (?:are )?(?:marked|classified) (?:unavailable|on watch))\.?$/i

function cleanText(value, limit) {
  const text = normalizeCardText(value)
  if (!text || INTERNAL_TERMS.test(text)) return null
  return text.length <= limit ? text : null
}

function validDate(value) {
  const text = String(value || '').trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null
  const date = new Date(`${text}T00:00:00Z`)
  return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== text ? null : text
}

export function formatCardDate(value) {
  const date = validDate(value)
  if (!date) return null
  const [year, month, day] = date.split('-').map(Number)
  return new Intl.DateTimeFormat('en-US', {
    month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)))
}

function canonicalUrl(path) {
  return path ? `${EVIDENCE_CARD_ORIGIN}${path}` : null
}

function safeFilePart(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

function fitSafeCardText(value, options) {
  const text = normalizeCardText(value)
  return text && !INTERNAL_TERMS.test(text) ? fitCompleteCardText(text, options) : null
}

export function selectTeamReceipts(evidence) {
  const seen = new Set()
  const receipts = []
  for (const item of Array.isArray(evidence) ? evidence : []) {
    const raw = normalizeCardText(item)
    const text = !INTERNAL_TERMS.test(raw)
      ? fitCompleteCardText(raw, { maxWidth: 420, maxLines: 2, fontSize: 18 })
      : null
    const key = text?.toLowerCase()
    if (!text || LOW_VALUE_ZERO.test(text) || seen.has(key)) continue
    seen.add(key)
    receipts.push(text)
    if (receipts.length === 3) break
  }
  return receipts
}

export function buildTeamEvidenceCard(readModel, { destinationUrl = null } = {}) {
  const teamName = cleanText(readModel?.teamName || readModel?.teamLabel, 48)
  const teamAbbreviation = normalizeTeamReference(readModel?.teamAbbreviation)
  const stateLabel = cleanText(readModel?.stateLabel, 28)
  const summary = [readModel?.stateSummary, readModel?.stateDetail]
    .map(value => fitSafeCardText(value, { maxWidth: 548, maxLines: 3, fontSize: 23 }))
    .find(Boolean) || null
  const why = [
    readModel?.workloadConcentration?.summary,
    readModel?.primaryConcern?.body,
    readModel?.why,
  ].map(value => fitSafeCardText(value, { maxWidth: 548, maxLines: 3, fontSize: 20 }))
    .find(Boolean) || null
  const receipts = selectTeamReceipts(readModel?.evidence)
  const dataThrough = validDate(readModel?.freshness?.dataThrough || readModel?.freshness?.data_through)
  const freshnessUnsafe = (
    !readModel?.freshness?.isCurrent
    || readModel?.freshness?.isStale
    || readModel?.freshness?.failClosed
    || readModel?.freshness?.isSample
  )
  if (
    readModel?.isUnavailable
    || readModel?.reviewOnly
    || freshnessUnsafe
    || !teamName
    || !teamAbbreviation
    || !stateLabel
    || !summary
    || !why
    || !dataThrough
    || receipts.length === 0
  ) return null

  const destination = destinationUrl || canonicalUrl(buildTeamBoardHref(teamAbbreviation))
  if (!destination?.startsWith(EVIDENCE_CARD_ORIGIN)) return null
  const limitation = 'Describes current workload. Does not predict usage or outcomes.'
  const dateLabel = formatCardDate(dataThrough)
  return {
    cardType: 'team',
    teamName,
    teamAbbreviation,
    stateLabel,
    summary,
    why,
    receipts,
    dataThrough,
    dataThroughLabel: dateLabel,
    limitation,
    destinationUrl: destination,
    displayUrl: `${EVIDENCE_CARD_ORIGIN.replace(/^https?:\/\//, '')}/team/${teamAbbreviation}`,
    altText: cleanText(
      `BaseballOS card for the ${teamName} bullpen. Current state: ${stateLabel}. The card lists ${receipts.length} recent-work ${receipts.length === 1 ? 'receipt' : 'receipts'}, data through ${dateLabel}, and notes that the read describes workload rather than predicting usage.`,
      320,
    ),
    fileName: `baseballos-${safeFilePart(teamAbbreviation)}-bullpen-${dataThrough}.png`,
  }
}

export function buildComparisonEvidenceCard(view, { teamA, teamB, destinationUrl = null } = {}) {
  const teamARef = normalizeTeamReference(teamA)
  const teamBRef = normalizeTeamReference(teamB)
  const teamAName = cleanText(view?.labelA, 42)
  const teamBName = cleanText(view?.labelB, 42)
  const freshnessA = validDate(view?.freshnessA?.dataThroughRaw || view?.freshnessA?.dataThrough)
  const freshnessB = validDate(view?.freshnessB?.dataThroughRaw || view?.freshnessB?.dataThrough)
  const statements = (Array.isArray(view?.observations) ? view.observations : [])
    .map(item => normalizeCardText(item?.statement))
    .filter(text => text && !INTERNAL_TERMS.test(text) && !UNSAFE_COMPARISON_TERMS.test(text))
  const summaryStatement = normalizeCardText(view?.summary?.statement)
  const summaryUnsafe = UNSAFE_COMPARISON_TERMS.test(summaryStatement)
  const observationFits = text => Boolean(wrapCardText(text, {
    maxWidth: 328,
    maxLines: 6,
    fontSize: 20,
  }))
  const observation = selectCompleteCardStatement({
    preferred: statements[0],
    alternatives: statements.slice(1),
    summary: !summaryUnsafe ? summaryStatement : null,
    fallback: 'The current side-by-side counts are shown at left.',
    fit: observationFits,
  })
  const rows = (Array.isArray(view?.snapshot) ? view.snapshot : []).slice(0, 4).map(row => ({
    label: cleanText(row?.label, 24),
    valueA: Number.isFinite(Number(row?.valueA)) ? Math.max(0, Math.floor(Number(row.valueA))) : null,
    valueB: Number.isFinite(Number(row?.valueB)) ? Math.max(0, Math.floor(Number(row.valueB))) : null,
  })).filter(row => row.label && row.valueA != null && row.valueB != null)
  const freshnessUnsafe = (
    view?.isDegraded
    || !view?.freshnessA?.isCurrent
    || !view?.freshnessB?.isCurrent
    || view?.freshnessA?.isStale
    || view?.freshnessB?.isStale
  )
  if (
    !view?.hasComparison
    || !teamARef
    || !teamBRef
    || teamARef === teamBRef
    || !teamAName
    || !teamBName
    || freshnessUnsafe
    || !freshnessA
    || !freshnessB
    || rows.length !== 4
    || summaryUnsafe
    || !observation
    || UNSAFE_COMPARISON_TERMS.test(observation)
  ) return null

  const destination = destinationUrl || canonicalUrl(buildComparisonHref(
    teamARef,
    teamBRef,
    { section: 'comparison-evidence' },
  ))
  if (!destination?.startsWith(EVIDENCE_CARD_ORIGIN)) return null
  const limitation = 'Current workload comparison. BaseballOS does not select a winner.'
  return {
    cardType: 'comparison',
    teamA: { name: teamAName, abbreviation: teamARef },
    teamB: { name: teamBName, abbreviation: teamBRef },
    rows,
    observation,
    freshnessA,
    freshnessB,
    freshnessALabel: formatCardDate(freshnessA),
    freshnessBLabel: formatCardDate(freshnessB),
    limitation,
    destinationUrl: destination,
    displayUrl: `${EVIDENCE_CARD_ORIGIN.replace(/^https?:\/\//, '')} · Compare ${teamARef} vs ${teamBRef}`,
    altText: cleanText(
      `BaseballOS comparison card for the ${teamAName} and ${teamBName} bullpens. The card compares Available, On Watch, Limited, and Unavailable reliever counts, includes a neutral workload observation, and shows current data dates.`,
      320,
    ),
    fileName: `baseballos-${safeFilePart(teamARef)}-vs-${safeFilePart(teamBRef)}-${freshnessA}.png`,
  }
}
