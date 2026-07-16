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
const UNSAFE_COMPARISON_TERMS = /\b(winner|wins?|advantage|better|best|stronger|rank(?:ing)?|score|edge|pick|prediction|likely|should)\b/i
const LOW_VALUE_ZERO = /^(?:0 of \d+ .*|no relievers? (?:are )?(?:marked|classified) (?:unavailable|on watch))\.?$/i
const TEAM_RECEIPT_PRIORITY = new Map([
  ['availability', 0],
  ['workload_concentration', 1],
  ['recent_work_volume', 2],
  ['repeated_appearances', 3],
  ['clean_options', 4],
  ['roster_context', 5],
  ['starter_support', 6],
  ['other', 7],
])
const STATE_SUPPORT_FAMILIES = ['availability', 'clean_options']
const WHY_WORKLOAD_FAMILIES = ['workload_concentration', 'recent_work_volume', 'repeated_appearances']
const PUBLIC_TEAM_STATES = /^(?:stable|usable|worth watching|monitor|thin|stretched|stressed|recovering)$/i
const COMPARISON_DIMENSION_PRIORITY = new Map([
  ['Available', 0],
  ['Limited', 1],
  ['Unavailable', 2],
  ['On Watch', 3],
])

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

function comparisonCountPhrase(label, count) {
  const singular = count === 1
  if (label === 'On Watch') return `${count} ${singular ? 'arm' : 'arms'} On Watch`
  return `${count} ${label.toLowerCase()} ${singular ? 'arm' : 'arms'}`
}

function comparisonDimensionSentence(row, labelA, labelB) {
  const aLeads = row.valueA > row.valueB
  const leaderLabel = aLeads ? labelA : labelB
  const otherLabel = aLeads ? labelB : labelA
  const leaderValue = aLeads ? row.valueA : row.valueB
  const otherValue = aLeads ? row.valueB : row.valueA
  return `The ${leaderLabel} have ${comparisonCountPhrase(row.label, leaderValue)}; the ${otherLabel} have ${otherValue}.`
}

export function rankComparisonRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter(row => COMPARISON_DIMENSION_PRIORITY.has(row?.label))
    .map(row => ({
      ...row,
      valueA: Number(row.valueA),
      valueB: Number(row.valueB),
      difference: Math.abs(Number(row.valueA) - Number(row.valueB)),
    }))
    .filter(row => Number.isFinite(row.valueA) && Number.isFinite(row.valueB))
    .sort((left, right) => (
      Number(left.difference === 0) - Number(right.difference === 0)
      || right.difference - left.difference
      || COMPARISON_DIMENSION_PRIORITY.get(left.label) - COMPARISON_DIMENSION_PRIORITY.get(right.label)
    ))
}

export function comparisonObservationCandidates(rows, labelA, labelB) {
  const differences = rankComparisonRows(rows).filter(row => row.difference > 0)
  if (differences.length === 0) {
    return ['The bullpens match across every availability group in the current read.']
  }

  const primary = comparisonDimensionSentence(differences[0], labelA, labelB)
  if (differences.length === 1) return [primary]

  const secondary = comparisonDimensionSentence(differences[1], labelA, labelB)
  return [`${primary} ${secondary}`, primary]
}

export function classifyTeamReceiptFamily(receipt) {
  const text = normalizeCardText(receipt).toLowerCase()
  if (!text) return 'other'
  if (/\b(?:injured list|inactive or unavailable|unconfirmed roster status|roster status)\b/.test(text)) return 'roster_context'
  if (/\b(?:starters? averaged|analyzed starts?|starter-length|bullpen covered)\b/.test(text)) return 'starter_support'
  if (/\b(?:classified available|relievers? (?:are|is) available from the latest completed workload data|relievers? are (?:limited or unavailable|in the on watch (?:group|lane)))\b/.test(text)) return 'availability'
  if (/\b(?:clean options?|cleanly available)\b/.test(text)) return 'clean_options'
  if (/\b(?:consecutive days|appeared at least twice|worked at least twice|repeated appearances?)\b/.test(text)) return 'repeated_appearances'
  if (/\b(?:workload (?:is )?concentrated|worked yesterday|worked today|recent work|recent (?:relief )?work (?:is|was) (?:spread|distributed|shared))\b/.test(text)) return 'workload_concentration'
  if (/\b(?:appearances? in the recent window|recent relief work|relief innings|innings in relief)\b/.test(text)) return 'recent_work_volume'
  return 'other'
}

function availabilityPrecision(text) {
  if (/\b\d+ of \d+ active relievers? are classified Available\./i.test(text)) return 3
  if (/\b\d+ of \d+ relievers? are classified Available\./i.test(text)) return 2
  if (/\brelievers? (?:are|is) available from the latest completed workload data\./i.test(text)) return 1
  return 0
}

function formatTeamReceipt(receipt, family) {
  let text = receipt
  if (family === 'availability') {
    text = text.replace(/^(\d+ of \d+) relievers?( are classified Available\.)$/i, '$1 active relievers$2')
  }
  if (family === 'roster_context' && !/^Roster context:/i.test(text)) {
    text = `Roster context: ${text}`
  }
  return text
}

function distinctTeamReceiptCandidates(evidence) {
  const candidates = (Array.isArray(evidence) ? evidence : [])
    .map((item, index) => {
      const raw = normalizeCardText(item)
      const family = classifyTeamReceiptFamily(raw)
      const formatted = formatTeamReceipt(raw, family)
      const text = !INTERNAL_TERMS.test(formatted) && !LOW_VALUE_ZERO.test(formatted)
        ? fitCompleteCardText(formatted, { maxWidth: 420, maxLines: 2, fontSize: 18 })
        : null
      return { text, family, index, precision: availabilityPrecision(formatted) }
    })
    .filter(candidate => candidate.text)

  const bestByFamily = new Map()
  for (const candidate of candidates) {
    const familyKey = candidate.family === 'other'
      ? `other:${candidate.text.toLowerCase()}`
      : candidate.family
    const current = bestByFamily.get(familyKey)
    if (!current || candidate.precision > current.precision) bestByFamily.set(familyKey, candidate)
  }

  const distinct = [...bestByFamily.values()]
    .sort((left, right) => (
      TEAM_RECEIPT_PRIORITY.get(left.family) - TEAM_RECEIPT_PRIORITY.get(right.family)
      || left.index - right.index
    ))
  return distinct
}

export function selectTeamReceipts(evidence) {
  const distinct = distinctTeamReceiptCandidates(evidence)
  const selected = []
  const takeFirst = families => {
    const match = distinct.find(candidate => families.includes(candidate.family) && !selected.includes(candidate))
    if (match) selected.push(match)
  }
  takeFirst(['availability'])
  takeFirst(['workload_concentration', 'recent_work_volume', 'repeated_appearances'])
  takeFirst(['roster_context', 'starter_support'])
  for (const candidate of distinct) {
    if (selected.length === 3) break
    if (!selected.includes(candidate)) selected.push(candidate)
  }
  return selected.map(candidate => candidate.text)
}

function receiptSupportsState(candidate, readModel) {
  if (!PUBLIC_TEAM_STATES.test(normalizeCardText(readModel?.stateLabel))) return false
  if (candidate.family === 'availability') return true
  return candidate.family === 'clean_options' && Boolean(readModel?.cleanOptions)
}

function whySupportFamilies(readModel) {
  if (readModel?.workloadConcentration?.summary) return WHY_WORKLOAD_FAMILIES
  if (readModel?.primaryConcern?.body) return STATE_SUPPORT_FAMILIES
  return []
}

function supportedWhyCopy(readModel) {
  if (readModel?.workloadConcentration?.summary) return readModel.workloadConcentration.summary
  if (readModel?.primaryConcern?.body) return readModel.primaryConcern.body
  return null
}

function receiptSupportsWhy(candidate, readModel) {
  return whySupportFamilies(readModel).includes(candidate.family)
}

export function classifyTeamReceiptRole(receipt, readModel) {
  const candidate = { family: classifyTeamReceiptFamily(receipt) }
  if (receiptSupportsState(candidate, readModel)) return 'primary_state'
  if (receiptSupportsWhy(candidate, readModel)) return 'primary_why'
  if (WHY_WORKLOAD_FAMILIES.includes(candidate.family)) return 'secondary_workload'
  if (candidate.family === 'roster_context') return 'context_roster'
  if (candidate.family === 'starter_support') return 'context_starter'
  return 'context_other'
}

export function selectAlignedTeamReceipts(readModel) {
  const candidates = distinctTeamReceiptCandidates(readModel?.evidence).map(candidate => ({
    ...candidate,
    supportsState: receiptSupportsState(candidate, readModel),
    supportsWhy: receiptSupportsWhy(candidate, readModel),
  }))
  const selected = []
  const take = predicate => {
    const match = candidates.find(candidate => predicate(candidate) && !selected.includes(candidate))
    if (match) selected.push(match)
  }

  take(candidate => candidate.supportsState)
  take(candidate => candidate.supportsWhy)
  if (selected.length > 0) {
    take(candidate => ['roster_context', 'starter_support', 'other'].includes(candidate.family))
  }

  const hasStateSupport = selected.some(candidate => candidate.supportsState)
  const hasWhySupport = selected.some(candidate => candidate.supportsWhy)
  return {
    receipts: selected.slice(0, 3).map(candidate => candidate.text),
    hasStateSupport,
    hasWhySupport,
  }
}

export function buildTeamEvidenceCard(readModel, { destinationUrl = null } = {}) {
  const teamName = cleanText(readModel?.teamName || readModel?.teamLabel, 48)
  const teamAbbreviation = normalizeTeamReference(readModel?.teamAbbreviation)
  const stateLabel = cleanText(readModel?.stateLabel, 28)
  const summary = [readModel?.stateSummary, readModel?.stateDetail]
    .map(value => fitSafeCardText(value, { maxWidth: 548, maxLines: 3, fontSize: 23 }))
    .find(Boolean) || null
  const selection = selectAlignedTeamReceipts(readModel)
  const why = selection.hasWhySupport
    ? fitSafeCardText(supportedWhyCopy(readModel), { maxWidth: 548, maxLines: 3, fontSize: 20 })
    : null
  const receipts = selection.receipts
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
    || !dataThrough
    || (!selection.hasStateSupport && !(selection.hasWhySupport && why))
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
  const rankedStatements = comparisonObservationCandidates(view?.snapshot, teamAName, teamBName)
  const observation = selectCompleteCardStatement({
    preferred: rankedStatements[0],
    alternatives: [...rankedStatements.slice(1), ...statements],
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
