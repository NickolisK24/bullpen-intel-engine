// The BaseballOS vocabulary layer — four named reads that describe bullpen
// state in plain baseball language: Bullpen Pressure, Recovery Window,
// Workload Concentration, and Clean Options.
//
// These are descriptive product concepts, not metrics. Every label derives
// from the same availability counts the rest of the frontend already shows
// (rested / watch / needing-rest / total), with fixed, inspectable tiers —
// no scoring, no model, nothing the page can't explain in a sentence.

export const CONCEPT_DEFINITIONS = {
  pressure: {
    name: 'Bullpen Pressure',
    definition: 'How much workload strain the pen is carrying today.',
  },
  recovery: {
    name: 'Recovery Window',
    definition: 'How much clean rest the bullpen has available.',
  },
  concentration: {
    name: 'Workload Concentration',
    definition: 'Whether recent work is spread around or clustered on fewer arms.',
  },
  cleanOptions: {
    name: 'Clean Options',
    definition: 'How many arms enter today without major recent workload restriction.',
  },
}

export const LIMITED_READ_LABEL = 'Limited Read'

// Count-led phrase helpers — every read's detail leads with the arms that
// drive it, so a tooltip reads like "3 of 8 arms need rest; 2 more on watch."
const needRestPhrase = (needRest, total) =>
  `${needRest} of ${total} ${needRest === 1 ? 'arm needs' : 'arms need'} rest`
const restedPhrase = (ready, total) =>
  `${ready} of ${total} ${ready === 1 ? 'arm comes' : 'arms come'} in rested`
const unrestrictedPhrase = (ready, total) =>
  `${ready} of ${total} ${ready === 1 ? 'arm enters' : 'arms enter'} without major workload limits`
const onWatchPhrase = (watch, total) => `${watch} of ${total} on watch`

function normalizeCounts(counts = {}) {
  const num = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : 0)
  const total = num(counts.total)
  return {
    total,
    ready: num(counts.ready),
    watch: num(counts.watch),
    needRest: num(counts.needRest),
    limitedRead: Boolean(counts.limitedRead) || total === 0,
  }
}

function limitedRead(key) {
  return {
    key,
    concept: CONCEPT_DEFINITIONS[key].name,
    definition: CONCEPT_DEFINITIONS[key].definition,
    label: LIMITED_READ_LABEL,
    display: LIMITED_READ_LABEL,
    tone: 'neutral',
    detail: 'Not enough current data for this read.',
  }
}

function pressureRead({ total, watch, needRest }) {
  const base = {
    key: 'pressure',
    concept: CONCEPT_DEFINITIONS.pressure.name,
    definition: CONCEPT_DEFINITIONS.pressure.definition,
  }
  // Lead with arms needing rest, then add the watch tail when it applies.
  const restAndWatch = watch > 0
    ? `${needRestPhrase(needRest, total)}; ${watch} more on watch.`
    : `${needRestPhrase(needRest, total)}.`
  if (needRest >= 3 || needRest / total >= 0.4) {
    return {
      ...base, label: 'High', display: 'High Bullpen Pressure', tone: 'stress', detail: restAndWatch,
    }
  }
  if (needRest === 2 || (needRest >= 1 && watch >= 2)) {
    return {
      ...base, label: 'Elevated', display: 'Elevated Bullpen Pressure', tone: 'watch', detail: restAndWatch,
    }
  }
  if (needRest === 1 || watch >= 2) {
    return {
      ...base,
      label: 'Manageable',
      display: 'Manageable Bullpen Pressure',
      tone: 'rest',
      detail: needRest === 1 ? `${needRestPhrase(needRest, total)}.` : `${onWatchPhrase(watch, total)}.`,
    }
  }
  return {
    ...base,
    label: 'Low',
    display: 'Low Bullpen Pressure',
    tone: 'rest',
    detail: watch > 0 ? `No arms need rest; ${watch} of ${total} on watch.` : 'No arms need rest today.',
  }
}

function recoveryRead({ total, ready }) {
  const base = {
    key: 'recovery',
    concept: CONCEPT_DEFINITIONS.recovery.name,
    definition: CONCEPT_DEFINITIONS.recovery.definition,
  }
  const share = ready / total
  const detail = `${restedPhrase(ready, total)}.`
  if (ready >= 6 || share >= 0.65) {
    return { ...base, label: 'Wide', display: 'Wide Recovery Window', tone: 'rest', detail }
  }
  if (share >= 0.45) {
    return { ...base, label: 'Stable', display: 'Stable Recovery Window', tone: 'rest', detail }
  }
  if (share >= 0.25) {
    return { ...base, label: 'Narrow', display: 'Narrow Recovery Window', tone: 'watch', detail }
  }
  return { ...base, label: 'Limited', display: 'Limited Recovery Window', tone: 'stress', detail }
}

function concentrationRead({ total, watch, needRest }) {
  const base = {
    key: 'concentration',
    concept: CONCEPT_DEFINITIONS.concentration.name,
    definition: CONCEPT_DEFINITIONS.concentration.definition,
  }
  if (watch >= 3 || (watch >= 2 && needRest >= 2)) {
    return {
      ...base, label: 'Concentrated', display: 'Concentrated Workload', tone: 'watch',
      detail: `${onWatchPhrase(watch, total)} — the heavy work is falling on a few arms.`,
    }
  }
  if (watch === 2 || (watch >= 1 && needRest >= 1)) {
    return {
      ...base, label: 'Some Concentration', display: 'Some Concentration', tone: 'neutral',
      detail: `${onWatchPhrase(watch, total)} carrying more than their share.`,
    }
  }
  return {
    ...base, label: 'Spread-Out', display: 'Spread-Out Workload', tone: 'rest',
    detail: watch > 0 ? `Just ${watch} of ${total} on watch; work otherwise spread.` : 'No arms on watch.',
  }
}

function cleanOptionsRead({ total, ready }) {
  const base = {
    key: 'cleanOptions',
    concept: CONCEPT_DEFINITIONS.cleanOptions.name,
    definition: CONCEPT_DEFINITIONS.cleanOptions.definition,
  }
  const detail = `${unrestrictedPhrase(ready, total)}.`
  if (ready >= 6 || ready / total >= 0.7) {
    return { ...base, label: 'Deep', display: 'Deep Clean Options', tone: 'rest', detail }
  }
  if (ready >= 4 || ready / total >= 0.5) {
    return { ...base, label: 'Enough', display: 'Enough Clean Options', tone: 'rest', detail }
  }
  if (ready >= 2) {
    return { ...base, label: 'Thin', display: 'Thin Clean Options', tone: 'watch', detail }
  }
  return { ...base, label: 'Very Thin', display: 'Very Thin Clean Options', tone: 'stress', detail }
}

// All four reads from one set of counts:
// { total, ready, watch, needRest, limitedRead? }.
export function getBullpenReads(counts) {
  const normalized = normalizeCounts(counts)
  const keys = ['pressure', 'recovery', 'concentration', 'cleanOptions']

  if (normalized.limitedRead) {
    const reads = keys.map(key => limitedRead(key))
    return { reads, byKey: Object.fromEntries(reads.map(read => [read.key, read])) }
  }

  const reads = [
    pressureRead(normalized),
    recoveryRead(normalized),
    concentrationRead(normalized),
    cleanOptionsRead(normalized),
  ]
  return { reads, byKey: Object.fromEntries(reads.map(read => [read.key, read])) }
}

// Adapter for the landscape entry shape the homepage view-model uses
// ({ available, monitor, restricted, total }). The landscape's restricted
// bucket folds roster-unavailable arms in with workload restriction, which is
// fine for a descriptive read.
export function getReadsForLandscapeEntry(entry) {
  if (!entry) return getBullpenReads({ total: 0 })
  return getBullpenReads({
    total: entry.total,
    ready: entry.available,
    watch: entry.monitor,
    needRest: entry.restricted,
  })
}
