import { EmptyState } from '../../UI'
import {
  getBoardCardView,
  getBoardFreshnessView,
  getBoardGroups,
  getBoardTotals,
  getDataProvenance,
  getRosterAuthorityView,
} from './tonightsBullpenBoardView'
import {
  PITCHER_LABEL_KEY_COPY,
  PITCHER_READ_LABELS,
  PITCHER_ROLE_LABELS,
} from '../../../utils/pitcherLabels'

function FreshnessBanner({ freshness, showRoutine = true }) {
  const view = getBoardFreshnessView(freshness)
  const provenance = getDataProvenance(freshness)
  const isProminent = view.isStale || view.limitations.length > 0 || !view.dataThrough
  const summaryLabel = provenance.completedGamesLine
    ? provenance.completedGamesLine
    : 'No completed MLB data loaded'

  if (!isProminent) {
    if (!showRoutine) return null

    return (
      <details
        className="mb-3 rounded border border-dirt bg-dugout/35 p-3"
        aria-label="Data freshness details"
      >
        <summary className="flex cursor-pointer flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-widest text-chalk500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
          <span className="inline-flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: provenance.tone.dot }} aria-hidden="true" />
            Data Freshness
          </span>
          <span className="normal-case tracking-normal text-chalk400">{summaryLabel}</span>
        </summary>
        <div className="mt-2 space-y-1 text-xs leading-relaxed text-chalk400">
          {view.lastSync && (
            <p><span className="text-chalk500">Last synced:</span> {view.lastSync}</p>
          )}
          {view.label && <p>{view.label}</p>}
        </div>
      </details>
    )
  }

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
          {summaryLabel}
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

// Roster-context banner. CRC Phase 4: this is driven entirely by the canonical
// Roster Authority (board.roster_authority) — the board displays roster truth, it no
// longer computes it. Every count is invariant across views; the only view-dependent
// value is how many off-roster arms are currently rendered as cards.
function RosterContextEvidence({ heading, entries }) {
  if (!entries.length) return null
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{heading}</div>
      <ul className="mt-1 space-y-1">
        {entries.map((entry, index) => (
          <li key={entry.pitcherId ?? `${entry.name}-${index}`} className="text-xs leading-relaxed text-chalk300">
            • {entry.name} — {entry.rosterStatusLabel}
            {entry.availability ? ` · ${entry.availability}` : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}

function RosterStatusBanner({ board }) {
  const renderedCards = getBoardGroups(board).flatMap(group => group.pitchers || [])
  const view = getRosterAuthorityView(board?.roster_authority, { renderedCards })
  if (!view.shouldShow) return null

  const shownNote = (view.shownOffActiveRoster != null && view.offActiveRoster > 0)
    ? ` · showing ${view.shownOffActiveRoster} of ${view.offActiveRoster} here`
    : ''

  const rosterFacts = (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <span className="font-mono text-[11px] uppercase tracking-widest">{view.statusLabel}</span>
      {view.countsWithheld ? (
        <span className="font-mono text-xs text-chalk300">
          Current usable bullpen depth withheld
        </span>
      ) : (
        <>
          <span
            className="font-mono text-xs"
            title="Relievers on the team's active MLB roster — the club's current bullpen."
          >
            <span className="text-chalk500">Bullpen Arms</span> {view.bullpenArms}
          </span>
          <span
            className="font-mono text-xs"
            title="Relievers off the active roster (injured list, optioned, or 40-man only). Open the list below to see every one."
          >
            <span className="text-chalk500">Off the Active Roster</span> {view.offActiveRoster}{shownNote}
          </span>
          <span
            className="font-mono text-xs"
            title="Share of bullpen candidates with a confirmed roster status."
          >
            <span className="text-chalk500">Roster Status Coverage</span> {view.coverageLabel}
          </span>
          <span
            className="font-mono text-xs"
            title="Bullpen candidates whose roster status is not yet confirmed."
          >
            <span className="text-chalk500">Roster Status Pending</span> {view.rosterStatusPending}
          </span>
        </>
      )}
    </div>
  )

  const hasEvidence = view.evidence.offActiveRoster.length > 0 || view.evidence.rosterStatusPending.length > 0
  const evidenceBlock = hasEvidence ? (
    <details className="mt-2 rounded border border-dirt/60 bg-dugout/50 p-2" aria-label="Roster context evidence">
      <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
        Who is off the active roster?
      </summary>
      <div className="mt-2 space-y-3">
        <RosterContextEvidence heading="Off the active roster" entries={view.evidence.offActiveRoster} />
        <RosterContextEvidence heading="Roster status pending" entries={view.evidence.rosterStatusPending} />
      </div>
    </details>
  ) : null

  if (!view.isProminent) {
    return (
      <details
        className="mb-3 rounded border border-dirt bg-dugout/35 p-3"
        aria-label="Roster status details"
      >
        <summary className="flex cursor-pointer flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-widest text-chalk500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
          <span>Roster Context</span>
          <span className="normal-case tracking-normal text-chalk400">
            {view.countsWithheld
              ? 'Current usable depth withheld'
              : `${view.bullpenArms} bullpen arms · ${view.coverageLabel} coverage`}
          </span>
        </summary>
        <div className="mt-2">{rosterFacts}{evidenceBlock}</div>
      </details>
    )
  }

  return (
    <div
      className="mb-6 rounded-lg border p-4"
      style={view.tone}
      role="status"
      aria-live="polite"
    >
      {rosterFacts}
      {evidenceBlock}
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

function PitcherLabelChip({ label, compact = false }) {
  if (!label) return null
  const isRole = label.kind === 'role'
  const dotColor = label.tone?.color || '#cbd5e1'
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1.5 rounded border font-mono uppercase tracking-wide ${
        isRole
          ? `${compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-[11px]'} font-semibold`
          : `${compact ? 'px-2 py-0.5' : 'px-2 py-0.5'} text-[10px] font-medium opacity-90`
      }`}
      style={label.tone}
      title={label.definition}
      aria-label={`${label.label}. ${label.definition}`}
      data-label-kind={label.kind}
    >
      {isRole && (
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: dotColor }}
          aria-hidden="true"
        />
      )}
      <span className="min-w-0 truncate sm:whitespace-nowrap">{label.label}</span>
    </span>
  )
}

function PitcherLabelChips({ labels }) {
  if (!labels?.role && !labels?.read) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Pitcher role and read labels">
      <PitcherLabelChip label={labels.role} />
      <PitcherLabelChip label={labels.read} />
    </div>
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
  return (
    <details className="mb-4 rounded-lg border border-dirt bg-dugout/35 p-3 sm:p-4" aria-label={PITCHER_LABEL_KEY_COPY.title}>
      <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2 font-mono text-[11px] uppercase tracking-widest text-chalk300 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
        <span>{PITCHER_LABEL_KEY_COPY.title}</span>
        <span className="text-[10px] text-chalk600">Role and read definitions</span>
      </summary>
      <p className="mt-1 text-xs leading-relaxed text-chalk500">
        {PITCHER_LABEL_KEY_COPY.roleSummary} {PITCHER_LABEL_KEY_COPY.readSummary}
      </p>
      <div className="mt-3 grid gap-3 text-xs leading-relaxed text-chalk300 2xl:grid-cols-2">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
            {PITCHER_LABEL_KEY_COPY.roleLayer}
          </div>
          <p className="mt-1 text-chalk400">{PITCHER_LABEL_KEY_COPY.roleQuestion}</p>
          <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
            {roleLabels.map(label => (
              <PitcherLabelChip key={label.key} label={label} compact />
            ))}
          </div>
        </div>
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
            {PITCHER_LABEL_KEY_COPY.readLayer}
          </div>
          <p className="mt-1 text-chalk400">{PITCHER_LABEL_KEY_COPY.readQuestion}</p>
          <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
            {readLabels.map(label => (
              <PitcherLabelChip key={label.key} label={label} compact />
            ))}
          </div>
        </div>
      </div>
    </details>
  )
}

function PitcherCard({ card, freshness, onViewDetails, now }) {
  const view = getBoardCardView(card, freshness, now)
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

      {view.pitcherLabels && (
        <div className="mt-2">
          <PitcherLabelChips labels={view.pitcherLabels} />
        </div>
      )}

      {(view.eligibility || view.rosterStatus) && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <RosterStatusChip rosterStatus={view.rosterStatus} />
          <EligibilityChip eligibility={view.eligibility} />
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-chalk500">
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
          Open pitcher context →
        </button>
      )}
    </div>
  )
}

function BoardGroup({ group, freshness, onViewDetails, now }) {
  return (
    <section className="card overflow-hidden" aria-label={`${group.label} group`}>
      <header className="border-b border-dirt bg-chalk/20 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 font-display text-lg tracking-wide text-chalk100">
            <span className="h-2.5 w-2.5 rounded-full" style={group.badge.dotStyle} aria-hidden="true" />
            {group.label}
          </h3>
          <span className="font-mono text-xs text-chalk400">
            {group.count == null ? 'Withheld' : group.count}
          </span>
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
              <PitcherCard key={card.pitcher_id ?? card.name} card={card} freshness={freshness} onViewDetails={onViewDetails} now={now} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

// The board renders the freshness/roster banners and the availability groups.
// The team-state read (state, explanation, context reads) lives in the single
// Team State card above the board — phase-0-clarity/03 removed the stress and
// context summary strips that restated it here.
export default function BullpenBoardView({
  board,
  onSelectPitcher,
  showRoutineFreshness = true,
  emptyState = null,
  now,
}) {
  const groups = getBoardGroups(board)
  const totals = getBoardTotals(board)
  const teamName = board?.team?.team_name || board?.team?.team_abbreviation

  return (
    <div id="pitcher-lanes">
      <FreshnessBanner freshness={board?.freshness} showRoutine={showRoutineFreshness} />
      <RosterStatusBanner board={board} />

      <div className="mb-4">
        <h2 className="font-display text-xl tracking-wide text-chalk100">
          Tonight's Bullpen Board{teamName ? ` — ${teamName}` : ''}
        </h2>
        <p className="mt-1 text-xs text-chalk500">
          {totals.countWithheld
            ? 'Recent workload evidence is available; current usable bullpen depth is withheld until roster status is verified.'
            : `Grouped by how recent usage changes tonight's options. ${totals.total} pitcher${totals.total === 1 ? '' : 's'} shown.`}
        </p>
      </div>

      {totals.isEmpty ? (
        <EmptyState
          title={emptyState?.title || 'No pitchers to show for this team'}
          subtitle={emptyState?.subtitle || 'No active bullpen options are available under the current roster and data-through filters.'}
        />
      ) : (
        <>
          <PitcherLabelKey />
          <div className="grid gap-5 xl:grid-cols-2">
            {groups.map(group => (
              <BoardGroup key={group.status} group={group} freshness={board?.freshness} onViewDetails={onSelectPitcher} now={now} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
