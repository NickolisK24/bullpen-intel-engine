import { ProductPageHeader, STATE_DEFINITIONS, StateRead } from './ProductPrimitives'

const PIPELINE = [
  ['01', 'Source', 'Official MLB game and roster data.'],
  ['02', 'Record', 'One canonical appearance ledger per game.'],
  ['03', 'Derivation', 'Deterministic workload and rest calculation.'],
  ['04', 'Evidence', 'Named facts attached to every claim.'],
  ['05', 'Observation', 'A plain sentence the evidence supports.'],
  ['06', 'Publication', 'Released only when the trust gates pass.'],
]

const LIMITS = [
  'BaseballOS does not know a pitcher’s medical condition, and never infers one from workload.',
  'BaseballOS does not know manager or pitching-coach intent for tonight.',
  'A Team State describes an observable operating picture, not the quality of a bullpen.',
  'Missing evidence narrows or withholds the dependent claim; it never becomes a zero.',
  'A published historical read is never silently recalculated from current data.',
]

export default function ProductMethodology() {
  return (
    <div className="bos-page bos-page--reading py-8 md:py-10">
      <ProductPageHeader eyebrow="Methodology" title="How a BaseballOS Read Is Built" description="Every public label is the end of a fixed path. Nothing is inferred from private information, and no step invents a value the source did not carry." />

      <section className="grid gap-0 py-9 sm:grid-cols-2 lg:grid-cols-3">
        {PIPELINE.map(([number, label, note]) => (
          <div key={number} className="grid min-h-[8rem] grid-cols-[2rem_1fr] gap-3 border-b border-line py-5 sm:px-5 sm:first:pl-0 lg:border-r lg:[&:nth-child(3n)]:border-r-0">
            <span className="font-mono text-[10px] text-brass">{number}</span>
            <div><h2 className="font-display text-lg font-semibold text-chalk100">{label}</h2><p className="mt-2 text-sm leading-6 text-chalk500">{note}</p></div>
          </div>
        ))}
      </section>

      <section className="border-t border-line py-9">
        <h2 className="font-display text-2xl font-semibold text-chalk100">Team State definitions</h2>
        <div className="mt-6 grid gap-6 md:grid-cols-3">
          {['fresh', 'stretched', 'vulnerable'].map(state => (
            <div key={state} className="border-t border-line pt-4"><StateRead state={state} label={state} /><p className="mt-3 text-sm leading-6 text-chalk400">{STATE_DEFINITIONS[state]}</p></div>
          ))}
        </div>
        <p className="mt-6 max-w-definition text-sm leading-6 text-chalk500">There is no fourth Team State. When evidence is missing, BaseballOS withholds the read rather than issuing a softer label — a withheld read is a state of the publication, not a state of the bullpen.</p>
      </section>

      <section className="border-t border-line py-9">
        <h2 className="font-display text-2xl font-semibold text-chalk100">What BaseballOS cannot see</h2>
        <div className="mt-5 divide-y divide-line-quiet border-y border-line">
          {LIMITS.map((limit, index) => <p key={limit} className="grid grid-cols-[2rem_1fr] gap-3 py-4 text-sm leading-6 text-chalk400"><span className="font-mono text-[10px] text-chalk600">{String(index + 1).padStart(2, '0')}</span>{limit}</p>)}
        </div>
      </section>
    </div>
  )
}
