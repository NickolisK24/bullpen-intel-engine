import { Link } from 'react-router-dom'
import { EmptyState } from '../../UI'
import { buildTeamBoardHref } from '../../../utils/evidenceLinks'
import { getComparisonView } from './teamBullpenComparisonView'

function FreshnessChip({ label, freshness }) {
  return (
    <div className="rounded border border-dirt bg-field/50 px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-xs text-chalk300">{label}</span>
        <span
          className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-chalk400"
          title={freshness.throughHint}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: freshness.dot }} aria-hidden="true" />
          {freshness.healthLabel}
        </span>
      </div>
      {freshness.completedGamesLine && (
        <div className="mt-1 font-mono text-[11px] text-chalk500" title={freshness.throughHint}>
          {freshness.completedGamesLine}
        </div>
      )}
      {freshness.isStale && (
        <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-amber">
          Recent workload unclear — read with caution
        </div>
      )}
    </div>
  )
}

function SnapshotTable({ view }) {
  return (
    <div className="card overflow-hidden">
      <table className="data-table w-full">
        <thead>
          <tr>
            <th className="text-chalk400">Availability</th>
            <th className="text-chalk200 text-right">{view.labelA}</th>
            <th className="text-chalk200 text-right">{view.labelB}</th>
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
              <td className="text-right font-mono text-chalk100">{row.valueA}</td>
              <td className="text-right font-mono text-chalk100">{row.valueB}</td>
            </tr>
          ))}
          <tr className="border-t border-dirt">
            <td className="text-chalk400 font-medium">Total relievers</td>
            <td className="text-right font-mono text-chalk200">{view.metricsA.total_relievers}</td>
            <td className="text-right font-mono text-chalk200">{view.metricsB.total_relievers}</td>
          </tr>
          <tr>
            <td className="text-chalk400">% Available</td>
            <td className="text-right font-mono text-chalk400">{view.metricsA.pct_available}%</td>
            <td className="text-right font-mono text-chalk400">{view.metricsB.pct_available}%</td>
          </tr>
          <tr>
            <td className="text-chalk400">% Unavailable</td>
            <td className="text-right font-mono text-chalk400">{view.metricsA.pct_unavailable}%</td>
            <td className="text-right font-mono text-chalk400">{view.metricsB.pct_unavailable}%</td>
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
        <details className="mt-2 rounded border border-dirt/60 bg-dugout/50 p-2">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
            Why?
          </summary>
          <ul className="mt-2 space-y-1">
            {observation.reasons.map((reason, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk300">• {reason}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export default function BullpenComparisonView({ payload }) {
  const view = getComparisonView(payload)
  if (!view.hasComparison) {
    return <EmptyState title="Pick two teams to compare" subtitle="Choose Team A and Team B above." />
  }

  return (
    <div className="space-y-8">
      {/* 2. Freshness information */}
      <section aria-label="Comparison freshness">
        <h3 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Freshness</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <FreshnessChip label={view.labelA} freshness={view.freshnessA} />
          <FreshnessChip label={view.labelB} freshness={view.freshnessB} />
        </div>
      </section>

      {/* 3. Side-by-side bullpen read */}
      <section aria-label="Side-by-side bullpen read">
        <h3 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Side-by-side Bullpen Read</h3>
        <SnapshotTable view={view} />
      </section>

      {/* 4. Context comparison observations */}
      <section
        id="comparison-evidence"
        tabIndex={-1}
        aria-label="Bullpen comparison observations"
        className="scroll-mt-24 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
      >
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-mono text-xs uppercase tracking-widest text-chalk400">Comparison</h3>
          <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Workload Read: {view.confidenceLabel}
          </span>
        </div>
        {view.summary.statement && (
          <p className="mb-3 text-sm font-medium text-chalk100">{view.summary.statement}</p>
        )}
        {view.isDegraded && (
          <p className="mb-3 font-mono text-[11px] uppercase tracking-wider text-amber">
            Unclear read — one or both bullpens have degraded freshness.
          </p>
        )}
        <div className="grid gap-3 md:grid-cols-3">
          {view.observations.map(observation => (
            <Observation key={observation.dimension} observation={observation} />
          ))}
        </div>
        {view.limitations.length > 0 && (
          <ul className="mt-3 space-y-1">
            {view.limitations.map((limitation, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk400">• {limitation}</li>
            ))}
          </ul>
        )}
      </section>

      {/* 5. Team board links. The comparison compares; each full board lives
          on the Team Board tab instead of being embedded twice here. */}
      <section aria-label="Open a full team board">
        <h3 className="mb-2 font-mono text-xs uppercase tracking-widest text-chalk400">Full Team Boards</h3>
        <div className="flex flex-wrap gap-3">
          <TeamBoardLink team={payload?.team_a?.team} label={view.labelA} />
          <TeamBoardLink team={payload?.team_b?.team} label={view.labelB} />
        </div>
      </section>
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
