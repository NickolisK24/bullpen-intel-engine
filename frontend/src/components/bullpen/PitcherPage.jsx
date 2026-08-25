import { useParams } from 'react-router-dom'
import { ErrorState } from '../UI'
import { buildAllPitchersHref, normalizePitcherId } from '../../utils/evidenceLinks'
import PitcherDetail from './PitcherDetail'

export default function PitcherPage() {
  const { id } = useParams()
  const pitcherId = normalizePitcherId(id)

  if (pitcherId == null) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <section className="card p-5 sm:p-8" aria-labelledby="pitcher-unavailable-title">
          <h1 id="pitcher-unavailable-title" className="font-display text-2xl tracking-wider text-chalk100">
            Pitcher unavailable
          </h1>
          <ErrorState message="This Pitcher destination does not contain a valid pitcher ID." />
          <a
            href={buildAllPitchersHref()}
            className="inline-flex min-h-11 items-center rounded border border-dirt px-3 font-mono text-xs font-semibold text-chalk300 hover:border-amber/60 hover:text-amber focus-visible:ring-2 focus-visible:ring-amber/70"
          >
            Find a reliever
          </a>
        </section>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <PitcherDetail pitcherId={pitcherId} />
    </div>
  )
}
