import {
  buildComparisonHref,
  buildTeamBoardHref,
  EVIDENCE_SECTIONS,
  normalizeTeamReference,
} from './evidenceLinks'
import {
  fitCompleteCardText,
  normalizeCardText,
  wrapCardText,
} from './evidenceCardText'
import {
  COMPARISON_CARD_VERSION,
  COMPARISON_SUPPORTING_LAYOUT,
  comparisonDimensionSentence,
  rankComparisonRows,
  selectComparisonStory,
  selectTeamStory,
  TEAM_CARD_VERSION,
  TEAM_STORY_EVIDENCE_SECTIONS,
  TEAM_SUPPORTING_LAYOUT,
} from './evidenceCardStory'

export { rankComparisonRows } from './evidenceCardStory'

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
const TEAM_EVIDENCE_CTA_LABELS = Object.freeze({
  [EVIDENCE_SECTIONS.PITCHER_LANES]: 'SEE THE PITCHER AVAILABILITY EVIDENCE',
  [EVIDENCE_SECTIONS.TEAM_RELIEF_WORK]: 'SEE THE RECENT RELIEF WORK EVIDENCE',
})
const COMPARISON_EVIDENCE_CTA_LABEL = 'SEE THE SIDE-BY-SIDE EVIDENCE'

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

// Finer-grained receipt subtype. Distinct subtypes inside the same broad family
// (Available vs On Watch vs Limited; starter summary vs short starts; injured
// list vs inactive vs unknown roster status) are kept apart so storytelling can
// choose the exact supporting fact instead of collapsing to one per family.
export function classifyTeamReceiptSubtype(receipt) {
  const family = classifyTeamReceiptFamily(receipt)
  const text = normalizeCardText(receipt).toLowerCase()
  if (family === 'availability') {
    if (/\bon watch\b/.test(text)) return 'availability_on_watch'
    if (/\blimited or unavailable\b/.test(text)) return 'availability_limited_unavailable'
    return 'availability_available'
  }
  if (family === 'starter_support') {
    if (/\banalyzed starts? ended before five innings\b/.test(text)) return 'starter_short_starts'
    return 'starter_summary'
  }
  if (family === 'roster_context') {
    if (/\binjured list\b/.test(text)) return 'roster_injured_list'
    if (/\binactive or unavailable\b/.test(text)) return 'roster_inactive'
    if (/\bunconfirmed roster status\b/.test(text)) return 'roster_unknown'
    return 'roster_context'
  }
  return family
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

export function distinctTeamReceiptCandidates(evidence) {
  const candidates = (Array.isArray(evidence) ? evidence : [])
    .map((item, index) => {
      const raw = normalizeCardText(item)
      const family = classifyTeamReceiptFamily(raw)
      const subtype = classifyTeamReceiptSubtype(raw)
      const formatted = formatTeamReceipt(raw, family)
      const text = !INTERNAL_TERMS.test(formatted) && !LOW_VALUE_ZERO.test(formatted)
        ? fitCompleteCardText(formatted, { maxWidth: 420, maxLines: 2, fontSize: 18 })
        : null
      return { text, family, subtype, index, precision: availabilityPrecision(formatted) }
    })
    .filter(candidate => candidate.text)

  // Dedupe by subtype so distinct facts inside a family survive, while semantic
  // duplicates within one subtype still collapse to their most precise form.
  const bestBySubtype = new Map()
  for (const candidate of candidates) {
    const subtypeKey = candidate.subtype === 'other'
      ? `other:${candidate.text.toLowerCase()}`
      : candidate.subtype
    const current = bestBySubtype.get(subtypeKey)
    if (!current || candidate.precision > current.precision) bestBySubtype.set(subtypeKey, candidate)
  }

  const distinct = [...bestBySubtype.values()]
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

// The receipt that directly supports the headline always leads; up to two
// additional distinct receipts follow in the established evidence priority.
function selectStoryReceipts(candidates, story) {
  const support = candidates.find(candidate => candidate.text === story.supportReceipt)
  if (!support) return []
  const selected = [support]
  for (const candidate of candidates) {
    if (selected.length === 3) break
    if (!selected.includes(candidate)) selected.push(candidate)
  }
  return selected.map(candidate => candidate.text)
}

function selectSupportingLine(story, readModel) {
  const stateSummary = normalizeCardText(readModel?.stateSummary).toLowerCase()
  for (const candidate of story.supportingCandidates) {
    const fitted = fitSafeCardText(candidate, TEAM_SUPPORTING_LAYOUT)
    if (!fitted) continue
    const lowered = fitted.toLowerCase()
    if (lowered === story.sentence.toLowerCase()) continue
    if (stateSummary && lowered === stateSummary) continue
    return fitted
  }
  return null
}

function teamAltText({ teamName, stateLabel, story, receipts, dateLabel }) {
  const receiptsPhrase = `${receipts.length} ${receipts.length === 1 ? 'receipt' : 'receipts'}`
  return cleanText(
    `BaseballOS evidence card. ${story.sentence} ${teamName} bullpen state: ${stateLabel}. ${receiptsPhrase} shown, data through ${dateLabel}. Describes current workload; does not predict usage or outcomes.`,
    320,
  ) || cleanText(
    `BaseballOS evidence card for the ${teamName} bullpen. State: ${stateLabel}. ${receiptsPhrase} shown, data through ${dateLabel}. Describes current workload; does not predict usage or outcomes.`,
    320,
  )
}

export function buildTeamEvidenceCard(readModel) {
  const teamName = cleanText(readModel?.teamName || readModel?.teamLabel, 48)
  const teamAbbreviation = normalizeTeamReference(readModel?.teamAbbreviation)
  const stateLabel = cleanText(readModel?.stateLabel, 28)
  const summary = [readModel?.stateSummary, readModel?.stateDetail]
    .map(value => fitSafeCardText(value, { maxWidth: 548, maxLines: 3, fontSize: 23 }))
    .find(Boolean) || null
  const concentrationSummary = normalizeCardText(readModel?.workloadConcentration?.summary)
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
    || (concentrationSummary && INTERNAL_TERMS.test(concentrationSummary))
  ) return null

  const candidates = distinctTeamReceiptCandidates(readModel?.evidence)
  const story = selectTeamStory({ readModel, candidates })
  if (!story || INTERNAL_TERMS.test(story.sentence)) return null

  const receipts = selectStoryReceipts(candidates, story)
  if (receipts.length === 0 || receipts[0] !== story.supportReceipt) return null

  const evidenceSection = TEAM_STORY_EVIDENCE_SECTIONS[story.storyAngle]
  const destination = canonicalUrl(buildTeamBoardHref(teamAbbreviation, { section: evidenceSection }))
  if (!evidenceSection || !destination?.startsWith(EVIDENCE_CARD_ORIGIN)) return null

  const supportingLine = selectSupportingLine(story, readModel)
  const limitation = 'Describes current workload. Does not predict usage or outcomes.'
  const dateLabel = formatCardDate(dataThrough)
  return {
    cardType: 'team',
    cardVersion: TEAM_CARD_VERSION,
    storyAngle: story.storyAngle,
    headline: story.headline,
    supportingLine,
    teamName,
    teamAbbreviation,
    stateLabel,
    summary,
    receipts,
    dataThrough,
    dataThroughLabel: dateLabel,
    limitation,
    evidenceSection,
    evidenceTarget: evidenceSection === EVIDENCE_SECTIONS.PITCHER_LANES ? 'pitcher_lanes' : 'team_relief_work',
    evidenceCtaLabel: TEAM_EVIDENCE_CTA_LABELS[evidenceSection],
    destinationUrl: destination,
    displayUrl: destination.replace(/^https?:\/\//, ''),
    shareText: `${story.sentence} See the current BaseballOS evidence.`,
    altText: teamAltText({ teamName, stateLabel, story, receipts, dateLabel }),
    fileName: `baseballos-${safeFilePart(teamAbbreviation)}-bullpen-${dataThrough}.png`,
  }
}

function comparisonAltText({ teamAName, teamBName, story, freshnessLabel }) {
  return cleanText(
    `BaseballOS comparison card. ${story.sentence} Shows Available, On Watch, Limited, and Unavailable reliever counts for the ${teamAName} and ${teamBName}, data through ${freshnessLabel}. Descriptive current workload only; BaseballOS does not take a side.`,
    320,
  ) || cleanText(
    `BaseballOS comparison card for the ${teamAName} and ${teamBName} bullpens, data through ${freshnessLabel}. Descriptive current workload only; BaseballOS does not take a side.`,
    320,
  )
}

export function buildComparisonEvidenceCard(view, { teamA, teamB } = {}) {
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
  const rows = (Array.isArray(view?.snapshot) ? view.snapshot : []).slice(0, 4).map(row => ({
    label: cleanText(row?.label, 24),
    valueA: Number.isFinite(Number(row?.valueA)) ? Math.max(0, Math.floor(Number(row.valueA))) : null,
    valueB: Number.isFinite(Number(row?.valueB)) ? Math.max(0, Math.floor(Number(row.valueB))) : null,
  })).filter(row => row.label && row.valueA != null && row.valueB != null)
  const story = selectComparisonStory({
    rows: rankComparisonRows(view?.snapshot),
    labelA: teamAName,
    labelB: teamBName,
    statements,
  })
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
    || !story
    || UNSAFE_COMPARISON_TERMS.test(story.sentence)
  ) return null

  const supportingLine = story.supportingCandidates
    .map(candidate => normalizeCardText(candidate))
    .find(text => (
      text
      && !INTERNAL_TERMS.test(text)
      && !UNSAFE_COMPARISON_TERMS.test(text)
      && text.toLowerCase() !== story.sentence.toLowerCase()
      && Boolean(wrapCardText(text, COMPARISON_SUPPORTING_LAYOUT))
    )) || null

  const destination = canonicalUrl(buildComparisonHref(
    teamARef,
    teamBRef,
    { section: EVIDENCE_SECTIONS.COMPARISON_EVIDENCE },
  ))
  if (!destination?.startsWith(EVIDENCE_CARD_ORIGIN)) return null
  const limitation = 'Current workload comparison. BaseballOS does not select a winner.'
  const freshnessALabel = formatCardDate(freshnessA)
  const freshnessBLabel = formatCardDate(freshnessB)
  const freshnessLabel = freshnessA === freshnessB
    ? freshnessALabel
    : `${freshnessALabel} and ${freshnessBLabel}`
  return {
    cardType: 'comparison',
    cardVersion: COMPARISON_CARD_VERSION,
    storyAngle: story.storyAngle,
    headline: story.headline,
    supportingLine,
    teamA: { name: teamAName, abbreviation: teamARef },
    teamB: { name: teamBName, abbreviation: teamBRef },
    rows,
    freshnessA,
    freshnessB,
    freshnessALabel,
    freshnessBLabel,
    limitation,
    evidenceSection: EVIDENCE_SECTIONS.COMPARISON_EVIDENCE,
    evidenceTarget: 'comparison_evidence',
    evidenceCtaLabel: COMPARISON_EVIDENCE_CTA_LABEL,
    destinationUrl: destination,
    displayUrl: destination.replace(/^https?:\/\//, ''),
    shareText: `${story.sentence} See the current BaseballOS evidence.`,
    altText: comparisonAltText({ teamAName, teamBName, story, freshnessLabel }),
    fileName: `baseballos-${safeFilePart(teamARef)}-vs-${safeFilePart(teamBRef)}-${freshnessA}.png`,
  }
}
