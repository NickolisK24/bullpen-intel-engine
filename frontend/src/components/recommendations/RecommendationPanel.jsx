import { ErrorState, LoadingPane } from '../UI'
import { getRecommendationCandidateTrustFields } from '../../utils/api'

const EMPTY_RESULT = {
  mode: 'empty',
  candidateName: 'Candidate not selected',
  statusLabel: 'No candidate evaluation available',
  statusDetail: 'Use Evaluate Candidate to inspect this pitcher without ranking the bullpen.',
  statusTone: 'neutral',
  assignedCategories: [],
  blockedCategories: [],
  explanations: [],
  limitations: [
    'No final pitcher selection is made in this surface.',
    'No bullpen ranking is applied in this surface.',
  ],
  trust: {
    confidence: 'Pending candidate input',
    freshness: 'Pending data freshness',
    availability: 'Pending availability',
  },
  refusalReason: 'No refusal reason available until a candidate response exists.',
  metadata: {
    rankingApplied: false,
    selectionMade: false,
  },
}

const CATEGORY_LABELS = {
  BEST_AVAILABLE_ARM: 'Best Available Arm',
  FRESHEST_HIGH_LEVERAGE_ARM: 'Freshest High-Leverage Arm',
  LOWEST_CURRENT_WORKLOAD_RISK: 'Lowest Current Workload Risk',
  USE_WITH_CAUTION: 'Use With Caution',
  AVOID_TONIGHT: 'Avoid Tonight',
  BULLPEN_STRESS_ALERT: 'Bullpen Stress Alert',
}

function titleize(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, char => char.toUpperCase())
}

function firstPresent(...values) {
  return values.find(value => value !== undefined && value !== null && value !== '')
}

function itemMessage(item, fallback = 'Detail unavailable') {
  if (!item) return fallback
  if (typeof item === 'string') return item
  return firstPresent(item.message, item.reason, item.description, item.code, fallback)
}

function categoryLabel(category) {
  if (!category) return 'Category unavailable'
  if (typeof category === 'string') {
    return CATEGORY_LABELS[category] || titleize(category)
  }
  const code = category.category_code || category.code
  return firstPresent(
    category.label,
    CATEGORY_LABELS[code],
    category.category ? titleize(category.category) : null,
    titleize(code),
    'Category unavailable',
  )
}

function categoryReason(category) {
  if (!category || typeof category === 'string') return null
  if (Array.isArray(category.reasons) && category.reasons.length > 0) {
    return category.reasons.map(reason => itemMessage(reason)).join('; ')
  }
  return firstPresent(category.reason, category.message, null)
}

function confidenceLabel(confidence = {}) {
  return firstPresent(
    confidence.label,
    confidence.level,
    confidence.level_code,
    confidence.confidence,
    'Unknown',
  )
}

function freshnessLabel(freshness = {}) {
  const state = firstPresent(freshness.label, freshness.state, freshness.state_code, freshness.data_state, 'Unknown')
  const dataThrough = freshness.data_through || freshness.dataThrough
  return dataThrough ? `${state} · Data Through ${dataThrough}` : state
}

function availabilityLabel(availability = {}) {
  return firstPresent(
    availability.label,
    availability.availability_status,
    availability.status,
    availability.state,
    'Unknown',
  )
}

function candidateNameFrom(candidate = {}, data = {}) {
  return firstPresent(
    candidate.pitcher_name,
    candidate.pitcherName,
    candidate.name,
    data.pitcher_name,
    data.pitcherName,
    data.candidate_name,
    'Candidate not selected',
  )
}

function responseStatus({ data, assignedCategories, refusal }) {
  if (refusal) {
    return {
      mode: 'refusal',
      statusLabel: firstPresent(refusal.message, itemMessage(refusal), 'Insufficient trusted data'),
      statusDetail: firstPresent(refusal.reason, refusal.reason_code, 'Recommendation refused by trust policy.'),
      statusTone: 'refusal',
    }
  }

  const hasCaution = assignedCategories.some(category => {
    const code = typeof category === 'string' ? category : category.category_code || category.code
    const label = categoryLabel(category)
    return code === 'USE_WITH_CAUTION' || label === 'Use With Caution'
  })

  if (hasCaution) {
    return {
      mode: 'caution',
      statusLabel: 'Use With Caution',
      statusDetail: 'Candidate passed with cautionary evidence that must remain visible.',
      statusTone: 'caution',
    }
  }

  return {
    mode: 'success',
    statusLabel: firstPresent(data.category, data.outcome, 'Candidate Evaluation Ready'),
    statusDetail: 'Eligible category output is candidate-level only.',
    statusTone: 'success',
  }
}

export function getRecommendationPanelView({
  response,
  candidate,
  isLoading = false,
  error = null,
  model = null,
} = {}) {
  if (isLoading) {
    return {
      ...EMPTY_RESULT,
      mode: 'loading',
      statusLabel: 'Loading candidate evaluation',
      statusDetail: 'One candidate evaluation is in progress.',
    }
  }

  if (error) {
    return {
      ...EMPTY_RESULT,
      mode: 'error',
      statusLabel: 'Candidate evaluation unavailable',
      statusDetail: 'The recommendation request could not be completed.',
    }
  }

  if (!response && model) {
    return {
      ...EMPTY_RESULT,
      mode: model.mode || 'success',
      candidateName: model.candidateName || EMPTY_RESULT.candidateName,
      statusLabel: model.statusLabel || EMPTY_RESULT.statusLabel,
      statusDetail: model.statusDetail || EMPTY_RESULT.statusDetail,
      assignedCategories: (model.categories || []).map(category => ({ label: category })),
      explanations: model.explanations || [],
      limitations: model.limitations || EMPTY_RESULT.limitations,
      trust: {
        confidence: model.trust?.confidence || EMPTY_RESULT.trust.confidence,
        freshness: model.trust?.freshness || EMPTY_RESULT.trust.freshness,
        availability: model.trust?.availability || EMPTY_RESULT.trust.availability,
      },
      refusalReason: model.refusal?.reason || EMPTY_RESULT.refusalReason,
      metadata: {
        rankingApplied: model.metadata?.rankingApplied ?? false,
        selectionMade: model.metadata?.selectionMade ?? false,
      },
    }
  }

  if (!response) return EMPTY_RESULT

  const data = response.data || {}
  const fields = getRecommendationCandidateTrustFields(response)
  const assignedCategories = fields.assignedCategories || []
  const blockedCategories = fields.blockedCategories || []
  const refusal = fields.refusal
  const status = responseStatus({ data, assignedCategories, refusal })

  return {
    ...EMPTY_RESULT,
    ...status,
    candidateName: candidateNameFrom(candidate, data),
    assignedCategories: assignedCategories.map(category => ({
      label: categoryLabel(category),
      reason: categoryReason(category),
    })),
    blockedCategories: blockedCategories.map(category => ({
      label: categoryLabel(category),
      reason: categoryReason(category),
    })),
    explanations: fields.explanations.map(item => itemMessage(item, 'Explanation unavailable')),
    limitations: fields.limitations.map(item => itemMessage(item, 'Limitation unavailable')),
    trust: {
      confidence: confidenceLabel(fields.confidence),
      freshness: freshnessLabel(fields.freshness),
      availability: availabilityLabel(fields.availability),
    },
    refusalReason: refusal
      ? firstPresent(refusal.message, refusal.reason, refusal.reason_code, 'Insufficient trusted data')
      : 'No refusal for this candidate response.',
    metadata: {
      rankingApplied: fields.rankingApplied ?? false,
      selectionMade: fields.selectionMade ?? false,
    },
  }
}

function FieldBadge({ label, value }) {
  return (
    <div className="recommendation-panel__text min-w-0 rounded border border-dirt bg-chalk/30 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">{label}</div>
      <div className="mt-1 text-sm font-semibold text-chalk100">{value}</div>
    </div>
  )
}

function SectionCard({ title, children }) {
  const id = `${title.replace(/\s+/g, '-').toLowerCase()}-heading`

  return (
    <section className="min-w-0 rounded border border-dirt bg-field/40 p-4" aria-labelledby={id}>
      <h3 id={id} className="font-mono text-xs uppercase tracking-widest text-chalk400">
        {title}
      </h3>
      <div className="recommendation-panel__text mt-3 text-sm leading-relaxed text-chalk200">{children}</div>
    </section>
  )
}

function TextList({ items, fallback }) {
  const values = Array.isArray(items) && items.length > 0 ? items : [fallback]

  return (
    <ul className="space-y-2">
      {values.map((item) => (
        <li key={item} className="recommendation-panel__text rounded border border-dirt bg-chalk/20 px-3 py-2">
          {item}
        </li>
      ))}
    </ul>
  )
}

function CategoryList({ items, fallback }) {
  if (!Array.isArray(items) || items.length === 0) {
    return (
      <div className="recommendation-panel__text rounded border border-dirt bg-chalk/20 px-3 py-2 text-chalk400">
        {fallback}
      </div>
    )
  }

  return (
    <div className="grid min-w-0 gap-2">
      {items.map((item) => (
        <div key={`${item.label}-${item.reason || 'none'}`} className="recommendation-panel__text rounded border border-dirt bg-chalk/20 px-3 py-2">
          <div className="font-mono text-xs text-chalk100">{item.label}</div>
          {item.reason && <div className="mt-1 text-xs text-chalk500">{item.reason}</div>}
        </div>
      ))}
    </div>
  )
}

function StatusContent({ view, error, onRetry }) {
  if (view.mode === 'loading') {
    return (
      <div role="status" aria-live="polite" data-recommendation-state="loading">
        <LoadingPane message="Loading candidate evaluation" />
      </div>
    )
  }

  if (view.mode === 'error') {
    return (
      <div role="alert" data-recommendation-state="error">
        <ErrorState
          message="Candidate evaluation could not be loaded."
          onRetry={onRetry}
        />
      </div>
    )
  }

  const toneClass = {
    success: 'border-green-500/30 bg-green-500/5',
    caution: 'border-amber/35 bg-amber/5',
    refusal: 'border-red-500/30 bg-red-500/5',
    empty: 'border-dirt bg-chalk/20',
  }[view.statusTone || view.mode] || 'border-dirt bg-chalk/20'

  return (
    <div
      className={`recommendation-panel__text rounded border px-4 py-3 ${toneClass}`}
      data-recommendation-state={view.mode}
      role={view.mode === 'refusal' ? 'alert' : 'status'}
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="font-mono text-[11px] uppercase tracking-wider text-chalk400">Recommendation Status Area</div>
      <div className="mt-1 text-lg font-semibold text-chalk100">{view.statusLabel}</div>
      <div className="mt-1 text-chalk400">{view.statusDetail}</div>
      {view.mode === 'refusal' && (
        <div className="recommendation-panel__text mt-3 rounded border border-dirt bg-chalk/20 px-3 py-2 text-chalk200">
          <span className="sr-only">Refusal Reason: </span>
          {view.refusalReason}
        </div>
      )}
      {view.mode === 'caution' && (
        <div className="recommendation-panel__text mt-3 rounded border border-amber/30 bg-amber/5 px-3 py-2 text-chalk200">
          Caution reasons are shown in explanations and limitations below.
        </div>
      )}
      {error && view.mode !== 'error' && (
        <div className="mt-3 text-xs text-chalk500">Error details are intentionally not displayed.</div>
      )}
      <div className="mt-3 font-mono text-xs text-chalk500">Candidate: {view.candidateName}</div>
    </div>
  )
}

// NOTE (Phase 1 audit): In the running app this component is only ever mounted
// embedded, via RecommendationPitcherDetailSection (variant="embedded",
// showHeader={false}). The default standalone/header configuration below is not
// currently reachable from any screen; it is retained because the test suite
// renders it directly and it documents the component's public surface. Promoting
// the embedded mount to the canonical path (and trimming the standalone layout)
// is deferred to a separate, test-coupled cleanup pass — see
// docs/PHASE_1_AUDIT_REMEDIATION_REPORT_2026_06.md.
export default function RecommendationPanel({
  response = null,
  candidate = null,
  isLoading = false,
  error = null,
  onRetry,
  model = null,
  variant = 'standalone',
  showHeader = true,
}) {
  const view = getRecommendationPanelView({
    response,
    candidate,
    isLoading,
    error,
    model,
  })
  const isEmbedded = variant === 'embedded'
  const wrapperClass = isEmbedded
    ? 'recommendation-panel recommendation-panel--embedded min-w-0 max-w-full space-y-4'
    : 'recommendation-panel recommendation-panel--standalone min-w-0 max-w-full card p-5 lg:p-6'

  return (
    <article
      className={wrapperClass}
      aria-labelledby={showHeader ? 'recommendation-engine-v1-heading' : undefined}
      aria-label={!showHeader ? 'Recommendation Engine V1 Candidate Evaluation' : undefined}
    >
      {showHeader && (
        <header className="mb-6 flex flex-col gap-3 border-b border-dirt pb-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <p className="font-mono text-xs uppercase tracking-widest text-chalk400">Recommendation Engine V1</p>
            <h2 id="recommendation-engine-v1-heading" className="section-title mt-1">Candidate Evaluation</h2>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
              Candidate-level display for Recommendation Engine V1 output. This surface renders
              trust-first response state without ranking the bullpen or selecting a final pitcher.
            </p>
          </div>
          <div className="grid min-w-0 gap-2 sm:grid-cols-2 lg:min-w-[22rem]">
            <FieldBadge label="Ranking" value="No Bullpen Ranking Applied" />
            <FieldBadge label="Selection" value="No Final Pitcher Selection Made" />
          </div>
        </header>
      )}

      <div className={`recommendation-panel__layout gap-4 ${isEmbedded ? 'recommendation-panel__layout--embedded' : 'recommendation-panel__layout--standalone'}`}>
        <div className="min-w-0 space-y-4">
          <SectionCard title="Recommendation Status">
            <StatusContent view={view} error={error} onRetry={onRetry} />
          </SectionCard>

          <SectionCard title="Eligible Categories">
            <div className="mb-3 text-chalk400">
              Category eligibility is displayed as candidate-level guidance only.
            </div>
            <CategoryList
              items={view.assignedCategories}
              fallback="No eligible categories available for this state."
            />
          </SectionCard>

          <SectionCard title="Blocked Categories">
            <CategoryList
              items={view.blockedCategories}
              fallback="No blocked categories available for this state."
            />
          </SectionCard>

          <SectionCard title="Explanation">
            <TextList
              items={view.explanations}
              fallback="Explanation details will appear when a candidate response is available."
            />
          </SectionCard>

          <SectionCard title="Limitation">
            <TextList
              items={view.limitations}
              fallback="Limitation details must remain visible with the result."
            />
          </SectionCard>
        </div>

        <aside className="min-w-0 space-y-4" aria-label="Recommendation trust freshness refusal and metadata">
          <SectionCard title="Trust And Freshness">
            <div className="recommendation-panel__trust-grid gap-3">
              <FieldBadge label="Confidence" value={view.trust.confidence} />
              <FieldBadge label="Data Freshness" value={view.trust.freshness} />
              <FieldBadge label="Availability" value={view.trust.availability} />
            </div>
          </SectionCard>

          <SectionCard title="Refusal Reason">
            <div className="recommendation-panel__text rounded border border-dirt bg-chalk/20 px-3 py-2 text-chalk300">
              {view.refusalReason}
            </div>
          </SectionCard>

          <SectionCard title="Metadata">
            <dl className="grid min-w-0 gap-3">
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded border border-dirt bg-chalk/20 px-3 py-2">
                <dt className="font-mono text-xs text-chalk500">ranking_applied</dt>
                <dd className="font-mono text-sm font-semibold text-chalk100">{String(view.metadata.rankingApplied)}</dd>
              </div>
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded border border-dirt bg-chalk/20 px-3 py-2">
                <dt className="font-mono text-xs text-chalk500">selection_made</dt>
                <dd className="font-mono text-sm font-semibold text-chalk100">{String(view.metadata.selectionMade)}</dd>
              </div>
            </dl>
          </SectionCard>
        </aside>
      </div>
    </article>
  )
}
