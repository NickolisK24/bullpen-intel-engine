import { Link } from 'react-router-dom'
import { Disclosure, EmptyState, FreshnessStamp, StaleDataNotice } from '../../UI'
import { buildComparisonHref, buildTeamBoardHref, normalizeTeamReference } from '../../../utils/evidenceLinks'
import { EVIDENCE_CARD_ORIGIN } from '../../../utils/shareCardArtifact'
import EvidenceShareMenu from '../../share/EvidenceShareMenu'
import { getComparisonView } from './teamBullpenComparisonView'

const metricValue = value => value == null ? 'Withheld' : value
const percentValue = value => value == null ? 'Withheld' : `${value}%`

// One side's canonical Team State. Descriptive only: each side is read on its
// own, and a side without a supported state shows the governed non-state message
// rather than a placeholder state or a partial winner.
function TeamStateChip({ label, teamState }) {
  return (
    <div className="flex min-w-32 flex-col items-end gap-1">
      <span className="font-mono text-xs text-chalk200">{label}</span>
      {teamState.available && (
        <span
          className="inline-flex min-h-7 items-center gap-1.5 rounded border px-2 py-1 font-mono text-[11px] uppercase tracking-wider"
          style={{ borderColor: teamState.tone.borderColor, backgroundColor: teamState.tone.backgroundColor, color: teamState.tone.color }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: teamState.tone.dot }} aria-hidden="true" />
          Team State: {teamState.publicLabel}
        </span>
      )}
      {!teamState.available && (
        <span className="max-w-48 text-right text-[11px] leading-relaxed text-chalk500">{teamState.unavailableMessage}</span>
      )}
    </div>
  )
}

function SnapshotTable({ view }) {
  return (
    <div className="card overflow-x-auto" data-testid="comparison-table-scroll">
      <table className="data-table min-w-[38rem] w-full">
        <thead>
          <tr>
            <th className="text-chalk400">Availability</th>
            <th><TeamStateChip label={view.labelA} teamState={view.teamStateA} /></th>
            <th><TeamStateChip label={view.labelB} teamState={view.teamStateB} /></th>
          </tr>
        </thead>
        <tbody>
          {view.snapshot.map(row => (
            <tr key={row.label}>
              <td className="text-chalk300">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full" style={row.badge.dotStyle} aria-hidden="true" />
                  {row.label}
                </span>
              </td>
              <td className="text-right font-mono text-chalk100">{metricValue(row.valueA)}</td>
              <td className="text-right font-mono text-chalk100">{metricValue(row.valueB)}</td>
            </tr>
          ))}
          <tr className="border-t border-dirt">
            <td className="text-chalk400 font-medium">Total relievers</td>
            <td className="text-right font-mono text-chalk200">{metricValue(view.metricsA.total_relievers)}</td>
            <td className="text-right font-mono text-chalk200">{metricValue(view.metricsB.total_relievers)}</td>
          </tr>
          <tr>
            <td className="text-chalk400">% Available</td>
            <td className="text-right font-mono text-chalk400">{percentValue(view.metricsA.pct_available)}</td>
            <td className="text-right font-mono text-chalk400">{percentValue(view.metricsB.pct_available)}</td>
          </tr>
          <tr>
            <td className="text-chalk400">% Unavailable</td>
            <td className="text-right font-mono text-chalk400">{percentValue(view.metricsA.pct_restricted)}</td>
            <td className="text-right font-mono text-chalk400">{percentValue(view.metricsB.pct_restricted)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function Observation({ observation }) {
  return (
    <div className="rounded border border-dirt bg-field/60 p-3">
      <p className="text-sm leading-relaxed text-chalk200" style={observation.leaderTone}>
        {observation.statement}
      </p>
      {observation.reasons.length > 0 && (
        <Disclosure label="Why?" className="mt-2">
          <ul className="mt-2 space-y-1">
            {observation.reasons.map((reason, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk300">• {reason}</li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  )
}

export default function BullpenComparisonView({ payload }) {
  const view = getComparisonView(payload)
  if (!view.hasComparison) {
    return <EmptyState title="Pick two teams to compare" subtitle="Choose Team A and Team B above." />
  }
  const teamA = payload?.team_a?.team || payload?.comparison?.teams?.team_a?.team
  const teamB = payload?.team_b?.team || payload?.comparison?.teams?.team_b?.team
  const teamARef = normalizeTeamReference(teamA)
  const teamBRef = normalizeTeamReference(teamB)
  const destinationPath = buildComparisonHref(teamARef, teamBRef, { section: 'comparison-evidence' })
  // SC-03A cutover: comparison Team State artifacts are not yet part of the
  // immutable Share Artifact architecture, so no canonical card is available.
  // The share menu renders its controlled unavailable state (copy-exact-link
  // stays available); we never compose a comparison card client-side.
  const cardModel = null
  const destinationUrl = cardModel?.destinationUrl
    || (teamARef && teamBRef ? `${EVIDENCE_CARD_ORIGIN}${destinationPath}` : null)
  const comparisonShareText = cardModel?.shareText
    || `Current ${view.labelA} and ${view.labelB} bullpen availability comparison on BaseballOS.`
  const sharedDataThrough = view.freshnessA?.dataThroughRaw === view.freshnessB?.dataThroughRaw
    ? view.freshnessA?.dataThroughRaw
    : null
  const rawFreshnessA = payload?.comparison?.freshness?.team_a || {}
  const freshnessDiffers = Boolean(
    view.freshnessA?.dataThroughRaw
    && view.freshnessB?.dataThroughRaw
    && !sharedDataThrough,
  )
  const freshnessDegraded = view.freshnessA?.isStale || view.freshnessB?.isStale

  return (
    <div className="space-y-8">
      {/* Team State belongs to the team headers; normal freshness is one quiet
          page-level line before the first baseball number. */}
      <section aria-label="Side-by-side bullpen read">
        <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Side-by-side Bullpen Read</h2>
        {sharedDataThrough && (
          <FreshnessStamp freshness={{ ...rawFreshnessA, data_through: sharedDataThrough }} showExceptional={false} className="mb-3" />
        )}
        {(freshnessDiffers || freshnessDegraded) && (
          <StaleDataNotice
            dataThrough={sharedDataThrough || view.freshnessA?.dataThroughRaw || view.freshnessB?.dataThroughRaw}
            message={freshnessDiffers
              ? `${view.labelA} and ${view.labelB} do not share the same data-through date, so compare with caution.`
              : 'One or both bullpens have degraded freshness, so compare with caution.'}
          />
        )}
        <SnapshotTable view={view} />
      </section>

      {/* Context comparison observations */}
      <section
        id="comparison-evidence"
        tabIndex={-1}
        aria-label="Bullpen comparison observations"
        className="scroll-mt-24 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
      >
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-mono text-xs uppercase tracking-widest text-chalk400">Comparison</h2>
          {view.showConfidence && (
            <span className="font-mono text-[10px] uppercase tracking-widest text-amber">
              Read Confidence: {view.confidenceLabel}
            </span>
          )}
        </div>
        {view.showConfidence && !freshnessDegraded && (
          <p className="mb-3 font-mono text-[11px] uppercase tracking-wider text-amber">
            Comparison confidence is limited; review the supporting observations.
          </p>
        )}
        <div className="grid gap-3 md:grid-cols-3">
          {view.observations.map(observation => (
            <Observation key={observation.dimension} observation={observation} />
          ))}
        </div>
        {view.limitations.length > 0 && (
          <Disclosure label="Limits on this comparison" className="mt-3">
            <ul className="space-y-1">
              {view.limitations.map((limitation, index) => (
                <li key={index} className="text-xs leading-relaxed text-chalk400">• {limitation}</li>
              ))}
            </ul>
          </Disclosure>
        )}
      </section>

      {/* Team board links. The comparison compares; each full board lives
          on the Team Board tab instead of being embedded twice here. */}
      <section aria-label="Open a full team board">
        <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Full Team Boards</h2>
        <div className="flex flex-wrap gap-3">
          <TeamBoardLink team={payload?.team_a?.team} label={view.labelA} />
          <TeamBoardLink team={payload?.team_b?.team} label={view.labelB} />
        </div>
      </section>

      <div className="flex justify-end border-t border-dirt pt-4">
        <EvidenceShareMenu
          cardModel={cardModel}
          destinationUrl={destinationUrl}
          shareText={comparisonShareText}
          context={{
            surface: 'compare_bullpens',
            cardType: 'comparison',
            team_a_ref: teamARef,
            team_b_ref: teamBRef,
            evidence_target: 'comparison_evidence',
            data_through: sharedDataThrough,
          }}
        />
      </div>
    </div>
  )
}

function TeamBoardLink({ team, label }) {
  const href = buildTeamBoardHref(team, { source: 'comparison' })
  if (!team?.team_abbreviation && team?.team_id == null) return null
  return (
    <Link
      to={href}
      className="inline-flex min-h-10 items-center rounded border border-dirt bg-field/60 px-4 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
    >
      Open the {label} board →
    </Link>
  )
}
