import { Disclosure, EmptyState } from '../../UI'
import { LAST_DATA_UPDATE_LABEL } from '../../../utils/bullpenConcepts'
import {
  READ_CONFIDENCE_FIELD_LABEL,
  WORKLOAD_DATA_FIELD_LABEL,
} from '../availabilityView'
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
            <p><span className="text-chalk500">{LAST_DATA_UPDATE_LABEL}:</span> {view.lastSync}</p>
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
            <span className="text-chalk500">{LAST_DATA_UPDATE_LABEL}:</span> {view.lastSync}
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

export function RosterStatusBanner({ board }) {
  const renderedCards = getBoardGroups(board).flatMap(group => group.pitchers || [])
  const view = getRosterAuthorityView(board?.roster_authority, { renderedCards })
  if (!view.shouldShow) return null
  const hasNamedRosterContext = view.evidence.offActiveRoster.length > 0 || view.evidence.rosterStatusPending.length > 0
  if (!hasNamedRosterContext && !view.countsWithheld && view.limitations.length === 0) return null

  return (
    <section className="mb-6 rounded-lg border border-dirt bg-dugout/35 p-4" aria-labelledby="roster-context-title">
      <h2 id="roster-context-title" className="font-display text-xl tracking-wide text-chalk100">Roster Context</h2>
      {view.countsWithheld && (
        <p className="mt-2 text-xs leading-relaxed text-amber" role="status">
          Roster context is withheld until the current roster evidence is complete.
        </p>
      )}
      <div className="mt-3 space-y-3">
        <RosterContextEvidence heading="Off the active roster" entries={view.evidence.offActiveRoster} />
        <RosterContextEvidence heading="Roster status pending" entries={view.evidence.rosterStatusPending} />
      </div>
      {view.limitations.length > 0 && (
        <ul className="mt-2 space-y-1">
          {view.limitations.map((limitation, index) => (
            <li key={index} className="text-xs leading-relaxed text-chalk400">• {limitation}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

const BOILERPLATE_LIMITATION = /(manager intent|bullpen phone|private medical|injury information)/i

function WhyDisclosure({ reasons, limitations, role }) {
  const materialLimitations = limitations.filter(item => !BOILERPLATE_LIMITATION.test(String(item)))
  if (!reasons.length && !materialLimitations.length && !role) return null
  return (
    <Disclosure label="Why?" hint="Evidence and context" className="mt-3">
      <div className="mt-2 space-y-3">
        {reasons.length > 0 && (
          <ul className="space-y-1">
            {reasons.map((reason, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk300">• {reason}</li>
            ))}
          </ul>
        )}
        {materialLimitations.length > 0 && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">What this doesn't know</div>
            <ul className="mt-1 space-y-1">
              {materialLimitations.map((limitation, index) => (
                <li key={index} className="text-xs leading-relaxed text-chalk500">• {limitation}</li>
              ))}
            </ul>
          </div>
        )}
        {role && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">Usage role</div>
            <p className="mt-1 text-xs text-chalk300"><span className="text-chalk500">Observed role:</span> {role.label}</p>
            {role.reason && <p className="mt-1 text-xs text-chalk300">{role.reason}</p>}
            {role.evidence?.length > 0 && (
              <ul className="mt-2 space-y-1">
                {role.evidence.map((item, index) => <li key={`${index}-${item}`} className="text-xs text-chalk300">• {item}</li>)}
              </ul>
            )}
            {role.limitations?.filter(item => !BOILERPLATE_LIMITATION.test(String(item))).length > 0 && (
              <ul className="mt-2 space-y-1">
                {role.limitations.filter(item => !BOILERPLATE_LIMITATION.test(String(item))).map((item, index) => <li key={`${index}-${item}`} className="text-xs text-chalk500">• {item}</li>)}
              </ul>
            )}
          </div>
        )}
      </div>
    </Disclosure>
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

// The eligibility and roster-status chips carry only their own governed label.
// The card's read confidence renders exactly once, under its own "Read
// Confidence" field label in the metadata row below; repeating it as a suffix
// inside each chip made the same value appear up to three times per card. The
// title/aria text keeps the confidence context for hover and screen readers.
function EligibilityChip({ eligibility }) {
  if (!eligibility) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide"
      style={eligibility.tone}
      title={eligibility.reason || eligibility.label}
      aria-label={`${eligibility.label}, ${READ_CONFIDENCE_FIELD_LABEL} ${eligibility.confidenceLabel}`}
    >
      {eligibility.label}
    </span>
  )
}

function RosterStatusChip({ rosterStatus }) {
  if (!rosterStatus) return null
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide"
      style={rosterStatus.tone}
      title={`Roster status: ${rosterStatus.label} (${READ_CONFIDENCE_FIELD_LABEL}: ${rosterStatus.confidenceLabel})`}
      aria-label={`Roster status: ${rosterStatus.label}, ${READ_CONFIDENCE_FIELD_LABEL} ${rosterStatus.confidenceLabel}`}
    >
      {rosterStatus.label}
    </span>
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

function factValue(value, unit, singularUnit = unit) {
  if (value == null) return '—'
  return `${value} ${value === 1 ? singularUnit : unit}`
}

function PitcherCard({ card, freshness, onViewDetails, now }) {
  const view = getBoardCardView(card, freshness, now)
  const canView = typeof onViewDetails === 'function' && view.pitcherId != null
  return (
    <div className="rounded-lg border border-dirt bg-field/60 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words font-medium text-chalk100">{view.name}</div>
          {view.shortReason && (
            <div className="mt-0.5 text-xs leading-relaxed text-chalk400">{view.shortReason}</div>
          )}
          {view.pitcherLabels && (
            <div className="mt-2">
              <PitcherLabelChips labels={view.pitcherLabels} />
            </div>
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

      {(view.eligibility || view.rosterStatus) && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <RosterStatusChip rosterStatus={view.rosterStatus} />
          <EligibilityChip eligibility={view.eligibility} />
        </div>
      )}

      <dl className="mt-3 grid min-w-0 grid-cols-2 gap-x-4 gap-y-2 font-mono text-[11px]">
        <div className="min-w-0"><dt className="text-chalk600">Last outing</dt><dd className="mt-0.5 break-words text-chalk200">{view.lastAppearanceLabel || '—'}</dd></div>
        <div className="min-w-0"><dt className="text-chalk600">Rest</dt><dd className="mt-0.5 break-words text-chalk200">{factValue(view.workloadFacts.days_since_last_appearance, 'days', 'day')}</dd></div>
        <div className="min-w-0"><dt className="text-chalk600">Last 7 days</dt><dd className="mt-0.5 break-words text-chalk200">{factValue(view.workloadFacts.pitches_last_7_days, 'pitches')}</dd></div>
        <div className="min-w-0"><dt className="text-chalk600">Recent work</dt><dd className="mt-0.5 break-words text-chalk200">{factValue(view.workloadFacts.appearances_last_7, 'appearances', 'appearance')}</dd></div>
        {view.workloadFacts.back_to_back === true && (
          <div className="col-span-2 mt-0.5 rounded border border-amber/25 bg-amber/5 px-2 py-1 text-amber">
            <dt className="sr-only">Recent workload exception</dt><dd>Worked back-to-back</dd>
          </div>
        )}
        {view.showConfidence && <div>
          <dt className="text-chalk600">{READ_CONFIDENCE_FIELD_LABEL}</dt>
          <dd className="mt-0.5 text-chalk200">{view.confidenceLabel}</dd>
        </div>}
        {view.dataStateView && (
          <div title={view.dataStateView.message}>
            <dt className="text-chalk600">{WORKLOAD_DATA_FIELD_LABEL}</dt>
            <dd className="mt-0.5 text-chalk200">{view.dataStateView.label}</dd>
          </div>
        )}
      </dl>

      <WhyDisclosure reasons={view.reasons} limitations={view.limitations} role={view.role} />

      {canView && (
        <button
          type="button"
          onClick={() => onViewDetails(view.pitcherId)}
          className="mt-3 min-h-11 w-full rounded border border-dirt bg-dugout px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
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
  showRosterContext = true,
  emptyState = null,
  now,
}) {
  const groups = getBoardGroups(board)
  const totals = getBoardTotals(board)
  const teamName = board?.team?.team_name || board?.team?.team_abbreviation

  return (
    <div
      id="pitcher-lanes"
      tabIndex={-1}
      className="scroll-mt-24 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
      aria-labelledby="pitcher-lanes-title"
    >
      <FreshnessBanner freshness={board?.freshness} showRoutine={showRoutineFreshness} />
      {showRosterContext && <RosterStatusBanner board={board} />}

      <div className="mb-4">
        {/* The /bullpen page heading already names the club ("{Team} Bullpen"),
            so the visible board heading does not repeat it. The team stays in
            the heading text for screen readers and anyone landing on the
            #pitcher-lanes anchor out of context. */}
        <h2 id="pitcher-lanes-title" className="font-display text-xl tracking-wide text-chalk100">
          Active Bullpen
          {teamName ? <span className="sr-only"> — {teamName}</span> : null}
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
          <div className="grid gap-5 xl:grid-cols-2">
            {groups.map(group => (
              <BoardGroup key={group.status} group={group} freshness={board?.freshness} onViewDetails={onSelectPitcher} now={now} />
            ))}
          </div>
          <div className="mt-5"><PitcherLabelKey /></div>
        </>
      )}
    </div>
  )
}
