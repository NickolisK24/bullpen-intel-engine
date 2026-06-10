import { useState } from 'react'

import RecommendationV2BullpenStatePanel, {
  getRecommendationV2BullpenStateView,
} from '../recommendations/RecommendationV2BullpenStatePanel'
import TeamOperationsBullpenReadinessPanel, {
  getTeamOperationsBullpenReadinessView,
} from '../teamOperations/TeamOperationsBullpenReadinessPanel'
import ExplanationDisclosure from '../explanations/ExplanationDisclosure'
import { getTeamReadinessExplanation } from '../../utils/api'

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function displayValue(value, fallback = 'Not provided') {
  if (value === false) return 'false'
  if (value === true) return 'true'
  if (value === 0) return '0'
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function countValue(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : displayValue(value)
}

function readinessTone(state) {
  if (state === 'loading') return 'border-ice/30 bg-ice/5 text-ice'
  if (state === 'error') return 'border-red-400/40 bg-red-400/10 text-red-300'
  if (state === 'protected') return 'border-amber/40 bg-amber/10 text-amber'
  return 'border-emerald-400/35 bg-emerald-400/10 text-emerald-300'
}

function metricLabel(value) {
  return displayValue(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function rowValue(rows, label) {
  return asArray(rows).find(row => row.label === label)?.value
}

// Baseball-facing visibility labels for the bullpen visibility snapshot.
// Raw trust-metadata confidence values stay untouched in the contract rows.
const VISIBILITY_LABELS = {
  high: 'Clear Visibility',
  medium: 'Limited Visibility',
  low: 'Limited Visibility',
  unknown: 'Visibility Unknown',
}

function visibilityValue(rawValue) {
  return VISIBILITY_LABELS[String(rawValue || '').trim().toLowerCase()] || metricLabel(rawValue)
}

function availabilityShape(availability) {
  const rows = [
    ['Available', availability.available],
    ['Monitor', availability.monitor],
    ['Limited', availability.limited],
    ['Avoid', availability.avoid],
    ['Unavailable', availability.unavailable],
  ].map(([label, value]) => ({
    label,
    count: Number.isFinite(Number(value)) ? Number(value) : 0,
  }))
  const total = Number.isFinite(Number(availability.total))
    ? Number(availability.total)
    : rows.reduce((sum, row) => sum + row.count, 0)
  const largest = rows.reduce((current, row) => (
    row.count > current.count ? row : current
  ), rows[0])

  return {
    largest,
    total,
    label: largest.count > 0
      ? `${largest.label}: ${countValue(largest.count)} / ${countValue(total)} total`
      : `0 / ${countValue(total)} total`,
  }
}

function teamReadinessExplanationParams(readinessView) {
  const team = asObject(readinessView.team)
  return {
    team_id: team.team_id,
    team_abbreviation: team.team_abbreviation,
  }
}

function HeroMetric({
  label,
  value,
  subtext = null,
  eyebrow = null,
  tone = 'border-dirt bg-field/60 text-chalk100',
}) {
  return (
    <div className={`min-w-0 rounded-lg border p-4 ${tone}`}>
      {eyebrow && (
        <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
          {eyebrow}
        </div>
      )}
      <div className="mt-1 font-mono text-xs uppercase tracking-widest text-chalk400">{label}</div>
      <div className="mt-2 break-words font-display text-3xl tracking-wide text-chalk100 md:text-4xl">
        {value}
      </div>
      {subtext && <div className="mt-2 text-sm leading-relaxed text-chalk500">{subtext}</div>}
    </div>
  )
}

function SnapshotMetric({ label, value, subtext = null, tone = 'border-dirt bg-chalk/30 text-chalk200' }) {
  return (
    <div className={`min-w-0 rounded border px-3 py-2 ${tone}`}>
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</div>
      <div className="mt-1 break-words font-mono text-sm font-semibold">{value}</div>
      {subtext && <div className="mt-1 text-[11px] leading-relaxed text-chalk500">{subtext}</div>}
    </div>
  )
}

function DetailDisclosure({
  title,
  summary,
  expanded,
  onToggle,
  children,
}) {
  const id = `operational-readiness-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`

  return (
    <section className="rounded border border-dirt bg-field/45 p-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="font-mono text-xs uppercase tracking-widest text-chalk300">{title}</h3>
          {summary && <p className="mt-1 text-xs leading-relaxed text-chalk600">{summary}</p>}
        </div>
        <button
          type="button"
          className="rounded border border-dirt bg-dugout px-3 py-2 text-left font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus:ring-2 focus:ring-amber/60 focus:ring-offset-2 focus:ring-offset-dugout"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={onToggle}
        >
          {expanded ? `Hide ${title}` : `View ${title}`}
        </button>
      </div>
      {expanded && (
        <div id={id} className="mt-4">
          {children}
        </div>
      )}
    </section>
  )
}

export default function OperationalReadinessSection({
  v2State,
  v2Loading = false,
  v2Error = null,
  onRetryV2,
  readinessState,
  readinessLoading = false,
  readinessError = null,
  onRetryReadiness,
  initialReadinessDetailsOpen = false,
  initialEvidenceOpen = false,
}) {
  const [readinessDetailsOpen, setReadinessDetailsOpen] = useState(initialReadinessDetailsOpen)
  const [evidenceOpen, setEvidenceOpen] = useState(initialEvidenceOpen)
  const v2View = getRecommendationV2BullpenStateView(v2State)
  const readinessView = getTeamOperationsBullpenReadinessView(readinessState)
  const availability = asObject(readinessView.availabilityDistribution)
  const workload = asObject(readinessView.workloadPressure)
  const freshness = asObject(readinessView.freshness)
  const trustMetadata = asObject(readinessView.trustMetadata)
  const v2Governance = asObject(v2State?.governance)
  const readinessGovernance = asObject(readinessView.governance)
  const rankingApplied = v2Governance.rankingApplied ?? readinessGovernance.rankingApplied
  const selectionMade = v2Governance.selectionMade ?? readinessGovernance.selectionMade
  const v2LoadState = v2Loading ? 'loading' : v2Error ? 'error' : v2View.isFailClosed ? 'protected' : 'ready'
  const readinessLoadState = readinessLoading ? 'loading' : readinessError ? 'error' : readinessView.isRefused || readinessView.isFailClosed ? 'protected' : 'ready'
  const bullpenStateLabel = v2Loading
    ? 'Loading'
    : v2Error
      ? 'Unavailable'
      : v2View.statusLabel
  const bullpenStateDetail = v2View.bullpenState?.status
    ? `State source: ${metricLabel(v2View.bullpenState.status)}`
    : 'V2 bullpen state context'
  const teamReadinessLabel = readinessLoading
    ? 'Loading'
    : readinessError
      ? 'Unavailable'
      : readinessView.statusLabel
  const teamReadinessDetail = readinessView.summary || 'Team readiness context'
  const pressureLabel = metricLabel(
    v2View.bullpenState?.stress_level
    || workload.pressure_state
    || workload.pressure_level,
  )
  const availabilitySnapshot = availabilityShape(availability)
  const freshnessLabel = metricLabel(
    freshness.freshness_state
    || freshness.state
    || rowValue(v2View.freshnessRows, 'Freshness'),
  )
  const freshnessDetail = freshness.data_through
    ? `Data through ${freshness.data_through}`
    : 'Freshness metadata visible'
  const trustLabel = visibilityValue(
    trustMetadata.confidence
    || rowValue(v2View.trustRows, 'Workload Read'),
  )
  const trustDetail = `Data state ${metricLabel(
    trustMetadata.data_state
    || rowValue(v2View.trustRows, 'Data State'),
  )}`

  return (
    <section
      className="card mb-5 overflow-hidden animate-fade-up opacity-0"
      style={{ animationFillMode: 'forwards' }}
      aria-labelledby="operational-readiness-heading"
    >
      <div className="border-b border-dirt bg-chalk/20 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="font-mono text-xs uppercase tracking-widest text-chalk400">Operational Readiness</div>
            <h2 id="operational-readiness-heading" className="mt-1 font-display text-2xl tracking-wider text-chalk100">
              Bullpen State + Team Readiness
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk500">
              Governed bullpen context in one dashboard surface. Team-level context only. The user remains responsible for bullpen decisions.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className={`rounded border px-3 py-2 font-mono text-xs uppercase tracking-widest ${readinessTone(v2LoadState)}`}>
              V2 {v2Loading ? 'Loading' : v2Error ? 'Unavailable' : v2View.statusLabel}
            </span>
            <span className={`rounded border px-3 py-2 font-mono text-xs uppercase tracking-widest ${readinessTone(readinessLoadState)}`}>
              V3 {readinessLoading ? 'Loading' : readinessError ? 'Unavailable' : readinessView.statusCopy.label}
            </span>
          </div>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <div className="rounded-lg border border-dirt bg-field/45 p-4">
          <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
                Operational Snapshot
              </div>
              <p className="mt-1 text-sm leading-relaxed text-chalk500">
                Current bullpen state, readiness, pressure, availability shape, freshness, and visibility in one governed view.
              </p>
            </div>
            <div className="font-mono text-[11px] uppercase tracking-wider text-chalk600">
              Observational context only
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <HeroMetric
              eyebrow="Current State"
              label="Bullpen State"
              value={bullpenStateLabel}
              subtext={bullpenStateDetail}
              tone="border-emerald-400/25 bg-emerald-400/5 text-emerald-300"
            />
            <HeroMetric
              eyebrow="Current Readiness"
              label="Team Readiness"
              value={teamReadinessLabel}
              subtext={teamReadinessDetail}
              tone={readinessTone(readinessLoadState)}
            />
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <SnapshotMetric
              label="Workload Pressure"
              value={pressureLabel}
              subtext={workload.summary}
            />
            <SnapshotMetric
              label="Availability Concentration"
              value={availabilitySnapshot.label}
              subtext="Largest current availability category"
            />
            <SnapshotMetric
              label="Freshness Status"
              value={freshnessLabel}
              subtext={freshnessDetail}
            />
            <SnapshotMetric
              label="Bullpen Visibility"
              value={trustLabel}
              subtext={trustDetail}
              tone="border-amber/35 bg-amber/10 text-amber"
            />
          </div>
        </div>

        <div className="rounded border border-dirt bg-dugout/70 p-3">
          <div className="rounded border border-dirt bg-chalk/20 px-3 py-2 font-mono text-xs text-emerald-300">
            {rankingApplied === false && selectionMade === false
              ? 'Context only — no pitcher is ranked or selected.'
              : 'Governance state unavailable for this surface; treat as context only.'}
          </div>
        </div>

        <ExplanationDisclosure
          buttonLabel="Why this state?"
          contextLabel="Team Operations readiness explanation"
          disabled={readinessLoading}
          fetchExplanation={() => getTeamReadinessExplanation(
            teamReadinessExplanationParams(readinessView),
          )}
        />

        {(v2Error || readinessError) && (
          <div className="rounded border border-red-400/35 bg-red-400/10 p-3" role="status" aria-live="polite">
            <div className="font-mono text-xs uppercase tracking-widest text-red-300">Operational readiness partially unavailable</div>
            <p className="mt-1 text-sm leading-relaxed text-chalk400">
              One or more governed readiness surfaces could not be loaded. Existing fail-closed and refusal behavior remains controlled by each source surface.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {v2Error && (
                <button type="button" className="rounded border border-dirt bg-field px-3 py-2 font-mono text-xs text-chalk300 hover:border-amber/40 hover:text-amber" onClick={onRetryV2}>
                  Retry V2
                </button>
              )}
              {readinessError && (
                <button type="button" className="rounded border border-dirt bg-field px-3 py-2 font-mono text-xs text-chalk300 hover:border-amber/40 hover:text-amber" onClick={onRetryReadiness}>
                  Retry V3
                </button>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <DetailDisclosure
            title="Readiness Details"
            summary="Team Operations readiness context, constraints, and coverage remain available on demand."
            expanded={readinessDetailsOpen}
            onToggle={() => setReadinessDetailsOpen(current => !current)}
          >
            <TeamOperationsBullpenReadinessPanel
              state={readinessState}
              loading={readinessLoading}
              error={readinessError}
              onRetry={onRetryReadiness}
              compact
              embedded
            />
          </DetailDisclosure>

          <DetailDisclosure
            title="Evidence & Metadata"
            summary="V2 trust, freshness, fail-closed, inventory, neutral groups, and governance evidence remain available on demand."
            expanded={evidenceOpen}
            onToggle={() => setEvidenceOpen(current => !current)}
          >
            <RecommendationV2BullpenStatePanel
              state={v2State}
              loading={v2Loading}
              error={v2Error}
              onRetry={onRetryV2}
              compact
              embedded
            />
          </DetailDisclosure>
        </div>
      </div>
    </section>
  )
}
