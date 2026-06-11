import { EmptyState } from '../../UI'
import BullpenStressSummary from './BullpenStressSummary'
import BullpenContextSummary from './BullpenContextSummary'
import TeamBullpenStoryPanel from './TeamBullpenStoryPanel'
import {
  getBoardCardView,
  getBoardFreshnessView,
  getBoardGroups,
  getBoardTotals,
  getDataProvenance,
  getRosterStatusSummaryView,
} from './tonightsBullpenBoardView'
import {
  PITCHER_LABEL_KEY_COPY,
  PITCHER_READ_LABELS,
  PITCHER_ROLE_LABELS,
} from '../../../utils/pitcherLabels'

function FreshnessBanner({ freshness }) {
  const view = getBoardFreshnessView(freshness)
  const provenance = getDataProvenance(freshness)
  return (
    <div
      className="mb-6 rounded-lg border p-4"
      style={view.tone}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <span
          className="inline-flex items-center gap-2 rounded border px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest"
          style={provenance.tone}
          title={provenance.throughHint}
        >
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: provenance.tone.dot }} aria-hidden="true" />
          {provenance.dataThrough
            ? `Latest completed MLB data: ${provenance.dataThrough}`
            : 'No completed MLB data loaded'}
        </span>
        {view.lastSync && (
          <span className="font-mono text-xs">
            <span className="text-chalk500">Last synced:</span> {view.lastSync}
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

function RosterStatusBanner({ summary }) {
  const view = getRosterStatusSummaryView(summary)
  if (!view.shouldShow) return null
  return (
    <div
      className="mb-6 rounded-lg border p-4"
      style={view.tone}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="font-mono text-[11px] uppercase tracking-widest">{view.label}</span>
        <span className="font-mono text-xs">
          <span className="text-chalk500">Bullpen Arms</span> {view.activeMlbCount}
        </span>
        <span
          className="font-mono text-xs"
          title="Pitchers not currently available for bullpen planning due to roster status."
        >
          <span className="text-chalk500">Unavailable Pitchers</span> {view.unavailablePitchersCount}
        </span>
        <span className="font-mono text-xs">
          <span className="text-chalk500">Roster Status Coverage</span> {view.coverageLabel}
        </span>
        <span className="font-mono text-xs">
          <span className="text-chalk500">Roster Unknown</span> {view.unknownCount}
        </span>
      </div>
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

function PitcherLabelChip({ label }) {
  if (!label) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide"
      style={label.tone}
      title={label.definition}
      aria-label={`${label.label}. ${label.definition}`}
    >
      {label.label}
    </span>
  )
}

function PitcherLabelChips({ labels }) {
  if (!labels?.role && !labels?.read) return null
  return (
    <>
      <PitcherLabelChip label={labels.role} />
      <PitcherLabelChip label={labels.read} />
    </>
  )
}

function EligibilityChip({ eligibility }) {
  if (!eligibility) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide"
      style={eligibility.tone}
      title={eligibility.reason || eligibility.label}
      aria-label={`${eligibility.label}, workload read ${eligibility.confidenceLabel}`}
    >
      {eligibility.label}
      <span className="opacity-70">· {eligibility.confidenceLabel}</span>
    </span>
  )
}

function RosterStatusChip({ rosterStatus }) {
  if (!rosterStatus) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide"
      style={rosterStatus.tone}
      title={`Roster status: ${rosterStatus.label} (workload read: ${rosterStatus.confidenceLabel})`}
      aria-label={`Roster status: ${rosterStatus.label}, workload read ${rosterStatus.confidenceLabel}`}
    >
      {rosterStatus.label}
      <span className="opacity-70">· {rosterStatus.confidenceLabel}</span>
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
          <span className="ml-1 text-chalk500">({role.confidenceLabel})</span>
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

function PitcherLabelKey() {
  const roleLabels = Object.values(PITCHER_ROLE_LABELS)
  const readLabels = Object.values(PITCHER_READ_LABELS)
  const roleLabelText = roleLabels.map(label => label.label).join(' · ')
  const readLabelText = readLabels.map(label => label.label).join(' · ')
  return (
    <section className="mb-5 rounded-lg border border-dirt bg-dugout/40 p-3" aria-label={PITCHER_LABEL_KEY_COPY.title}>
      <h3 className="font-mono text-[11px] uppercase tracking-widest text-chalk300">
        {PITCHER_LABEL_KEY_COPY.title}
      </h3>
      <p className="mt-1 text-xs leading-relaxed text-chalk500">
        {PITCHER_LABEL_KEY_COPY.roleSummary} {PITCHER_LABEL_KEY_COPY.readSummary}
      </p>
      <div className="mt-3 grid gap-3 text-xs leading-relaxed text-chalk300 lg:grid-cols-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
            {PITCHER_LABEL_KEY_COPY.roleLayer}
          </div>
          <p className="mt-1 text-chalk400">{PITCHER_LABEL_KEY_COPY.roleQuestion}</p>
          <p className="mt-1 text-chalk200">{roleLabelText}</p>
        </div>
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
            {PITCHER_LABEL_KEY_COPY.readLayer}
          </div>
          <p className="mt-1 text-chalk400">{PITCHER_LABEL_KEY_COPY.readQuestion}</p>
          <p className="mt-1 text-chalk200">{readLabelText}</p>
        </div>
      </div>
    </section>
  )
}

function PitcherCard({ card, onViewDetails }) {
  const view = getBoardCardView(card)
  const canView = typeof onViewDetails === 'function' && view.pitcherId != null
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

      {(view.pitcherLabels || view.eligibility || view.rosterStatus) && (
        <div className="mt-2 flex flex-wrap gap-2">
          <PitcherLabelChips labels={view.pitcherLabels} />
          <RosterStatusChip rosterStatus={view.rosterStatus} />
          <EligibilityChip eligibility={view.eligibility} />
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-chalk500">
        <span title="Fatigue score: 0–100 · higher = heavier recent workload">
          <span className="text-chalk600">Fatigue</span>{' '}
          <span className="text-chalk200">{view.fatigueScore != null ? view.fatigueScore : '—'}</span>
        </span>
        <span>
          <span className="text-chalk600">Workload Read</span>{' '}
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

      {canView && (
        <button
          type="button"
          onClick={() => onViewDetails(view.pitcherId)}
          className="mt-3 w-full rounded border border-dirt bg-dugout px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
          aria-label={`View pitcher details for ${view.name}`}
        >
          View details →
        </button>
      )}
    </div>
  )
}

function BoardGroup({ group, onViewDetails }) {
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
              <PitcherCard key={card.pitcher_id ?? card.name} card={card} onViewDetails={onViewDetails} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

// `showStoryPanel` mounts Today's Bullpen Story between the context strips and
// the board. Tonight's Board (the homepage destination) opts in; embedded uses
// like the side-by-side comparison stay as they are.
export default function BullpenBoardView({ board, onSelectPitcher, showStoryPanel = false }) {
  const groups = getBoardGroups(board)
  const totals = getBoardTotals(board)
  const teamName = board?.team?.team_name || board?.team?.team_abbreviation
  const hasStress = Boolean(board?.stress)

  return (
    <div>
      <FreshnessBanner freshness={board?.freshness} />
      <RosterStatusBanner summary={board?.roster_status} />
      {showStoryPanel && <TeamBullpenStoryPanel board={board} />}

      <div className="mb-5">
        <h2 className="font-display text-2xl tracking-wide text-chalk100">
          Tonight's Bullpen Board{teamName ? ` — ${teamName}` : ''}
        </h2>
        <p className="mt-1 text-sm text-chalk400">
          What this bullpen looks like tonight, grouped by availability. {totals.total} pitcher
          {totals.total === 1 ? '' : 's'} shown. Fatigue score: higher = heavier recent workload.
        </p>
      </div>

      <BullpenStressSummary stress={board?.stress} />

      <BullpenContextSummary board={board} showHealthSummary={!hasStress} />

      {totals.isEmpty ? (
        <EmptyState
          title="No pitchers to show for this team"
          subtitle="No active bullpen options are available under the current roster and freshness filters."
        />
      ) : (
        <>
          <PitcherLabelKey />
          <div className="grid gap-5 xl:grid-cols-2">
            {groups.map(group => (
              <BoardGroup key={group.status} group={group} onViewDetails={onSelectPitcher} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
