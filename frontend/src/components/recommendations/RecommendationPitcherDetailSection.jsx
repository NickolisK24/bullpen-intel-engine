import { useEffect, useMemo, useState } from 'react'
import RecommendationPanel from './RecommendationPanel'
import { evaluateRecommendationCandidate } from '../../utils/api'
import {
  buildRecommendationCandidateFromPitcherDetail,
  evaluatePitcherDetailRecommendation,
} from './recommendationCandidate'

function TrustMarker({ label, value }) {
  return (
    <div className="min-w-0 rounded border border-dirt bg-field/60 px-3 py-2 recommendation-detail-panel__text">
      <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{label}</div>
      <div className="mt-1 text-xs font-semibold text-chalk100">{value}</div>
    </div>
  )
}

export default function RecommendationPitcherDetailSection({
  pitcherDetail,
  evaluateCandidate = evaluateRecommendationCandidate,
  initialState = {},
}) {
  const candidate = useMemo(
    () => buildRecommendationCandidateFromPitcherDetail(pitcherDetail),
    [pitcherDetail],
  )
  const candidateKey = `${candidate.pitcher_id ?? 'unknown'}:${candidate.pitcher_name ?? ''}`
  const [response, setResponse] = useState(initialState.response ?? null)
  const [isLoading, setIsLoading] = useState(Boolean(initialState.isLoading ?? initialState.loading))
  const [error, setError] = useState(initialState.error ?? null)

  useEffect(() => {
    setResponse(initialState.response ?? null)
    setIsLoading(Boolean(initialState.isLoading ?? initialState.loading))
    setError(initialState.error ?? null)
  }, [candidateKey])

  const handleEvaluateCandidate = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await evaluatePitcherDetailRecommendation(pitcherDetail, {
        evaluateCandidate,
      })
      setResponse(result)
    } catch (err) {
      setResponse(null)
      setError(err)
    } finally {
      setIsLoading(false)
    }
  }

  const candidateName = candidate.pitcher_name || 'selected pitcher'

  return (
    <section
      className="recommendation-detail-panel min-w-0 rounded border border-dirt bg-chalk/30 p-4 sm:p-5"
      aria-labelledby="recommendation-detail-heading"
      aria-describedby="recommendation-detail-description"
      aria-busy={isLoading}
    >
      <div className="mb-4 flex gap-4 recommendation-detail-panel__header">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">Recommendation Engine V1</div>
          <h3 id="recommendation-detail-heading" className="mt-1 font-display text-lg tracking-wider text-chalk100">
            Candidate Evaluation
          </h3>
          <p id="recommendation-detail-description" className="mt-2 max-w-2xl text-xs font-mono leading-relaxed text-chalk400">
            Evaluate this pitcher only. Category eligibility does not rank the bullpen or make a final pitcher selection.
          </p>
        </div>
        <button
          type="button"
          onClick={handleEvaluateCandidate}
          disabled={isLoading}
          aria-label={`Evaluate recommendation candidate for ${candidateName}`}
          aria-controls="recommendation-detail-result"
          className="inline-flex min-h-10 w-full items-center justify-center rounded border border-amber/40 bg-amber/10 px-4 py-2 text-center font-mono text-xs font-semibold uppercase tracking-wider text-amber transition hover:bg-amber/15 disabled:cursor-wait disabled:opacity-60 sm:w-auto"
        >
          {isLoading ? 'Evaluating...' : 'Evaluate Candidate'}
        </button>
      </div>

      <div className="mb-4 recommendation-detail-panel__trust-grid gap-2">
        <TrustMarker label="Selection" value="No Final Pitcher Selection Made" />
        <TrustMarker label="Ranking" value="No Bullpen Ranking Applied" />
      </div>

      <div className="sr-only" aria-live="polite">
        {isLoading
          ? 'Candidate evaluation loading.'
          : response
            ? 'Candidate evaluation result available.'
            : error
              ? 'Candidate evaluation error.'
              : 'Candidate evaluation not requested.'}
      </div>

      <div id="recommendation-detail-result" className="min-w-0">
        <RecommendationPanel
          response={response}
          candidate={candidate}
          isLoading={isLoading}
          error={error}
          onRetry={handleEvaluateCandidate}
          variant="embedded"
          showHeader={false}
        />
      </div>
    </section>
  )
}
