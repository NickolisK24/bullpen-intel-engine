import { EmptyState } from '../../UI'
import BullpenContextSummary from './BullpenContextSummary'
import {
  getBoardCardView,
  getBoardFreshnessView,
  getBoardGroups,
  getBoardTotals,
} from './tonightsBullpenBoardView'

function FreshnessBanner({ freshness }) {
  const view = getBoardFreshnessView(freshness)
  return (
    <div
      className="mb-6 rounded-lg border p-4"
      style={view.tone}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <span className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-widest">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: view.dot }} aria-hidden="true" />
          {view.healthLabel}
        </span>
        {view.dataThrough && (
          <span className="font-mono text-xs">
            <span className="text-chalk500">Data through</span> {view.dataThrough}
          </span>
        )}
        {view.lastSync && (
          <span className="font-mono text-xs">
            <span className="text-chalk500">Synced</span> {view.lastSync}
          </span>
        )}
      </div>
      {view.label && (
        <p className="mt-2 text-sm leading-relaxed text-chalk300">{view.label}</p>
      )}
      {view.isStale && (
        <p className="mt-1 font-mono text-[11px] uppercase tracking-wider">
          Latest workload data is outside the active freshness window — read with caution.
        </p>
      )}
      {view.limitations.length > 0 && (
        <ul className="mt-2 space-y-1">
          {view.limitations.map((limitation, index) => (
            <li key={index} className="text-xs leading-relaxed text-chalk400">• {limitation}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function WhyDisclosure({ reasons, limitations }) {
  if (!reasons.length && !limitations.length) return null
  return (
    <details className="mt-3 rounded border border-dirt bg-dugout/60 p-2">
      <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
        Why?
      </summary>
      <div className="mt-2 space-y-3">
        {reasons.length > 0 && (
          <ul className="space-y-1">
            {reasons.map((reason, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk300">• {reason}</li>
            ))}
          </ul>
        )}
        {limitations.length > 0 && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">What this doesn't know</div>
            <ul className="mt-1 space-y-1">
              {limitations.map((limitation, index) => (
                <li key={index} className="text-xs leading-relaxed text-chalk500">• {limitation}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  )
}

function RoleChip({ role }) {
  if (!role) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide"
      style={role.tone}
      title={`Observed usage role: ${role.label} (confidence: ${role.confidenceLabel})`}
      aria-label={`Observed usage role: ${role.label}, confidence ${role.confidenceLabel}`}
    >
      {role.shortLabel}
      <span className="opacity-70">· {role.confidenceLabel}</span>
    </span>
  )
}

function RoleDisclosure({ role }) {
  if (!role) return null
  return (
    <details className="mt-2 rounded border border-dirt/60 bg-dugout/50 p-2">
      <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
        Usage role
      </summary>
      <div className="mt-2 space-y-2">
        <div className="text-xs leading-relaxed text-chalk200">
          <span className="text-chalk500">Observed role:</span> {role.label}
          <span className="ml-1 text-chalk500">({role.confidenceLabel} confidence)</span>
        </div>
        {role.reason && <p className="text-xs leading-relaxed text-chalk300">{role.reason}</p>}
        {role.evidence.length > 0 && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">Evidence</div>
            <ul className="mt-1 space-y-1">
              {role.evidence.map((item, index) => (
                <li key={index} className="text-xs leading-relaxed text-chalk300">• {item}</li>
              ))}
            </ul>
          </div>
        )}
        {role.limitations.length > 0 && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">What this doesn't know</div>
            <ul className="mt-1 space-y-1">
              {role.limitations.map((item, index) => (
                <li key={index} className="text-xs leading-relaxed text-chalk500">• {item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  )
}

function PitcherCard({ card }) {
  const view = getBoardCardView(card)
  return (
    <div className="rounded-lg border border-dirt bg-field/60 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-medium text-chalk100">{view.name}</div>
          {view.shortReason && (
            <div className="mt-0.5 text-xs leading-relaxed text-chalk400">{view.shortReason}</div>
          )}
        </div>
        <span
          className="inline-flex shrink-0 items-center gap-1.5 rounded border px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wide"
          style={view.badge.style}
          title={view.badge.tone}
          aria-label={`Availability status: ${view.badge.label}`}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={view.badge.dotStyle} aria-hidden="true" />
          {view.badge.label}
        </span>
      </div>

      {view.role && (
        <div className="mt-2">
          <RoleChip role={view.role} />
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-chalk500">
        <span>
          <span className="text-chalk600">Fatigue</span>{' '}
          <span className="text-chalk200">{view.fatigueScore != null ? view.fatigueScore : '—'}</span>
        </span>
        <span>
          <span className="text-chalk600">Confidence</span>{' '}
          <span className="text-chalk200">{view.confidenceLabel}</span>
        </span>
        {view.dataStateView && (
          <span title={view.dataStateView.message}>
            <span className="text-chalk600">Data</span>{' '}
            <span className="text-chalk200">{view.dataStateView.label}</span>
          </span>
        )}
      </div>

      <WhyDisclosure reasons={view.reasons} limitations={view.limitations} />
      <RoleDisclosure role={view.role} />
    </div>
  )
}

function BoardGroup({ group }) {
  return (
    <section className="card overflow-hidden" aria-label={`${group.label} group`}>
      <header className="border-b border-dirt bg-chalk/20 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 font-display text-lg tracking-wide text-chalk100">
            <span className="h-2.5 w-2.5 rounded-full" style={group.badge.dotStyle} aria-hidden="true" />
            {group.label}
          </h3>
          <span className="font-mono text-xs text-chalk400">{group.count}</span>
        </div>
        {group.description && (
          <p className="mt-1 text-xs leading-relaxed text-chalk500">{group.description}</p>
        )}
      </header>
      <div className="p-3">
        {group.pitchers.length === 0 ? (
          <p className="px-1 py-4 text-center text-xs text-chalk600">{group.emptyCopy}</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {group.pitchers.map(card => (
              <PitcherCard key={card.pitcher_id ?? card.name} card={card} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

export default function BullpenBoardView({ board }) {
  const groups = getBoardGroups(board)
  const totals = getBoardTotals(board)
  const teamName = board?.team?.team_name || board?.team?.team_abbreviation

  return (
    <div>
      <FreshnessBanner freshness={board?.freshness} />

      <div className="mb-5">
        <h2 className="font-display text-2xl tracking-wide text-chalk100">
          Tonight's Bullpen Board{teamName ? ` — ${teamName}` : ''}
        </h2>
        <p className="mt-1 text-sm text-chalk400">
          What this bullpen looks like tonight, grouped by availability. {totals.total} pitcher
          {totals.total === 1 ? '' : 's'} shown.
        </p>
      </div>

      <BullpenContextSummary board={board} />

      {totals.isEmpty ? (
        <EmptyState
          title="No pitchers to show for this team"
          subtitle="No active pitchers fall inside the current freshness window. Try including inactive pitchers, or pick another team."
        />
      ) : (
        <div className="grid gap-5 xl:grid-cols-2">
          {groups.map(group => (
            <BoardGroup key={group.status} group={group} />
          ))}
        </div>
      )}
    </div>
  )
}
