const PATTERN_FACTS = [
  ['back_to_back', 'Back-to-back appearances'],
  ['three_in_four', '3 appearances in 4 days'],
  ['four_in_five', '4 appearances in 5 days'],
]

const WINDOW_FACTS = [
  ['appearances_last_3_days', 'Appearances / 3d'],
  ['pitches_last_3_days', 'Pitches / 3d'],
  ['appearances_last_5_days', 'Appearances / 5d'],
  ['pitches_last_5_days', 'Pitches / 5d'],
]

const isRecord = (value) => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const isCount = (value) => Number.isInteger(value) && value >= 0

export function getWorkloadPatternsView(workloadSignal) {
  if (!isRecord(workloadSignal) || workloadSignal.data_state !== 'fresh') {
    return { available: false, facts: [] }
  }

  const inputs = isRecord(workloadSignal.inputs) ? workloadSignal.inputs : {}
  const patternFacts = PATTERN_FACTS.flatMap(([key, label]) => (
    typeof inputs[key] === 'boolean'
      ? [{ key, label, value: inputs[key] ? 'Yes' : 'No' }]
      : []
  ))
  const windowFacts = WINDOW_FACTS.flatMap(([key, label]) => (
    isCount(inputs[key])
      ? [{ key, label, value: String(inputs[key]) }]
      : []
  ))
  const facts = [...patternFacts, ...windowFacts]

  return {
    available: facts.length > 0,
    facts,
  }
}

export default function WorkloadPatterns({ workloadSignal }) {
  const view = getWorkloadPatternsView(workloadSignal)

  return (
    <section
      className="rounded border border-dirt bg-field/45 p-3 sm:p-4"
      aria-labelledby="pitcher-workload-patterns-title"
    >
      <h3 id="pitcher-workload-patterns-title" className="font-display text-base tracking-wider text-chalk100">
        Workload Patterns
      </h3>

      {view.available ? (
        <dl className="mt-3 grid min-w-0 grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
          {view.facts.map(({ key, label, value }) => (
            <div key={key} className="min-w-0 border-t border-dirt/70 pt-2">
              <dt className="break-words font-mono text-[10px] leading-tight text-chalk600">{label}</dt>
              <dd className="mt-1 break-words font-mono text-sm font-semibold text-chalk200">{value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-2 font-mono text-sm leading-relaxed text-chalk400" role="status">
          Workload patterns are unavailable.
        </p>
      )}
    </section>
  )
}
