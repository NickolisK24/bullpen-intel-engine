import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { formatDateOnly } from '../../../utils/dateDisplay'
import { getRosterAuthorityView } from './tonightsBullpenBoardView'

const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null

export function getRecentTransactionRows(recentTransactions) {
  const events = Array.isArray(recentTransactions?.events) ? recentTransactions.events : []
  return events.map((event, index) => ({
    key: textValue(event?.event_id) || `transaction-${index}`,
    playerId: event?.player_id ?? null,
    playerName: textValue(event?.player_name),
    eventDate: textValue(event?.date),
    dateLabel: formatDateOnly(event?.date, { month: 'short' }),
    label: textValue(event?.label),
    description: textValue(event?.description),
  }))
}

function firstLimitation(status, recentTransactions) {
  return [
    ...(Array.isArray(status?.limitations) ? status.limitations : []),
    ...(Array.isArray(recentTransactions?.limitations) ? recentTransactions.limitations : []),
  ].find(value => textValue(value))?.trim() || null
}

function TransactionsSkeleton() {
  return (
    <section className="foundation-section min-w-0" aria-labelledby="recent-transactions-title" aria-busy="true" data-testid="recent-transactions-skeleton">
      <div className="rounded-sm border border-line-subtle bg-surface-raised/20 p-panel tablet:p-section">
        <h2 id="recent-transactions-title" className="type-section-title">Recent Transactions</h2>
        <span className="sr-only">Loading recent transactions.</span>
        <div className="mt-panel divide-y divide-line-subtle">
          {[0, 1].map(index => (
            <div key={index} className="grid min-w-0 grid-cols-[minmax(5.5rem,auto)_minmax(0,1fr)] gap-panel py-row">
              <SkeletonBlock className="h-4 w-24 max-w-full" />
              <div className="min-w-0 space-y-meta">
                <SkeletonBlock className="h-5 w-40 max-w-full" />
                <SkeletonBlock className="h-4 w-28 max-w-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function PitcherHandoff({ pitcherId, name, onSelectPitcher, className = '' }) {
  if (pitcherId == null || typeof onSelectPitcher !== 'function') {
    return <span className={className}>{name}</span>
  }
  return (
    <button
      type="button"
      className={`${className} min-h-11 text-left text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus`.trim()}
      onClick={event => onSelectPitcher(pitcherId, event.currentTarget)}
    >
      {name}
    </button>
  )
}

function RosterEvidence({ heading, entries, onSelectPitcher }) {
  if (!entries.length) return null
  return (
    <div className="min-w-0">
      <h4 className="type-overline text-text-tertiary">{heading}</h4>
      <ul className="mt-meta space-y-meta">
        {entries.map((entry, index) => (
          <li key={entry.pitcherId ?? `${entry.name}-${index}`} className="type-compact flex min-w-0 flex-wrap items-center gap-x-meta text-text-secondary">
            <PitcherHandoff pitcherId={entry.pitcherId} name={entry.name} onSelectPitcher={onSelectPitcher} className="break-words font-medium" />
            <span aria-hidden="true" className="text-text-tertiary">·</span>
            <span className="text-text-tertiary">{entry.rosterStatusLabel}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RosterContext({ rosterContext, onSelectPitcher }) {
  const view = getRosterAuthorityView(rosterContext)
  if (!view.shouldShow) return null
  const readiness = rosterContext?.readiness || {}
  const representedDate = textValue(readiness.data_through) || textValue(rosterContext?.reference_date)
  const limitation = view.limitations.find(value => textValue(value))?.trim() || null

  return (
    <div className="mt-panel rounded-sm border border-line-subtle bg-surface-raised/20 p-panel" aria-labelledby="recent-transactions-roster-context-title">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-panel border-b border-line-subtle pb-panel">
        <div className="min-w-0">
          <div className="type-overline text-text-tertiary">Roster context</div>
          <h3 id="recent-transactions-roster-context-title" className="type-section-title mt-meta text-base">Current roster status</h3>
        </div>
        <p className="type-metadata text-text-tertiary">
          {view.statusLabel}
          {representedDate ? <> · Through <time dateTime={representedDate}>{representedDate}</time></> : null}
        </p>
      </div>
      {(view.evidence.offActiveRoster.length > 0 || view.evidence.rosterStatusPending.length > 0) && (
        <div className="mt-panel grid gap-panel tablet:grid-cols-2">
          <RosterEvidence heading="Off the active roster" entries={view.evidence.offActiveRoster} onSelectPitcher={onSelectPitcher} />
          <RosterEvidence heading="Roster status pending" entries={view.evidence.rosterStatusPending} onSelectPitcher={onSelectPitcher} />
        </div>
      )}
      {limitation && <p className="type-compact mt-panel border-t border-line-subtle pt-panel text-text-tertiary">{limitation}</p>}
    </div>
  )
}

export default function TeamBoardRecentTransactions({ read, loading = false, error = null, onRetry, onSelectPitcher }) {
  if (loading) return <TransactionsSkeleton />

  const recentTransactions = read?.recentTransactions
  const status = read?.sectionStatus?.recent_transactions
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const rows = getRecentTransactionRows(recentTransactions)
  const limitation = firstLimitation(status, recentTransactions)

  return (
    <section className="foundation-section min-w-0" aria-labelledby="recent-transactions-title" data-testid="team-board-recent-transactions">
      <header className="mb-panel border-b border-line-default pb-panel">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-panel">
          <div className="min-w-0">
            <div className="type-overline text-text-tertiary">Roster movement</div>
            <h2 id="recent-transactions-title" className="type-section-title mt-meta">Recent Transactions</h2>
            <p className="type-metadata mt-meta max-w-reading text-text-tertiary">Verified pitching movement and current roster-status context.</p>
          </div>
          {recentTransactions?.window_start_date && recentTransactions?.window_end_date && (
            <p className="type-metadata text-text-tertiary">Latest official transaction window</p>
          )}
        </div>
      </header>

      {error ? (
        <SectionState status="error" title="Recent Transactions unavailable" message="Recent transaction records could not be loaded." onRetry={onRetry} />
      ) : !read || !recentTransactions || statusName === 'unavailable' ? (
        <SectionState status="unavailable" title="Recent Transactions unavailable" message={limitation || 'Recent official transaction records are unavailable.'} onRetry={!read ? onRetry : undefined} />
      ) : (
        <>
          {rows.length > 0 && (
            <div className="overflow-hidden rounded-sm border border-line-subtle bg-surface-raised/20" role="list" aria-label="Recent pitching transactions">
              <div className="border-b border-line-subtle px-panel py-meta">
                <h3 className="type-overline text-text-tertiary">Recent movement</h3>
              </div>
              <div className="divide-y divide-line-subtle">
                {rows.map(row => (
                  <article key={row.key} role="listitem" className="grid min-w-0 grid-cols-[minmax(5.5rem,auto)_minmax(0,1fr)] gap-panel px-panel py-row tablet:grid-cols-[minmax(6rem,auto)_minmax(0,1fr)] tablet:items-center">
                    <div className="min-w-0">
                      <div className="font-board text-board-metadata font-medium tabular-nums text-text-tertiary">
                        {row.eventDate && row.dateLabel
                          ? <time dateTime={row.eventDate}>{row.dateLabel}</time>
                          : <span className="text-text-withheld">—</span>}
                      </div>
                    </div>
                    <div className="flex min-w-0 flex-wrap items-center gap-x-row gap-y-meta">
                      <PitcherHandoff
                        pitcherId={row.playerId}
                        name={row.description || row.playerName || 'Player unavailable'}
                        onSelectPitcher={onSelectPitcher}
                        className={`font-board text-board-body font-medium break-words ${row.description || row.playerName ? 'text-text-primary' : 'text-text-withheld'}`}
                      />
                      {!row.description && row.playerName && (
                        <span className={`type-compact break-words ${row.label ? 'text-text-secondary' : 'text-text-withheld'}`}>{row.label || '—'}</span>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}

          {statusName === 'partial' && (
            <SectionState status="partial" title="Recent Transactions are partially available" message={limitation || 'Some recent transaction records are unavailable.'} className={rows.length > 0 ? 'mt-panel' : ''} />
          )}
          {statusName === 'available' && rows.length === 0 && (
            <div className="section-state" role="status" data-state="empty">
              <h3 className="type-section-title">No recent transactions</h3>
              <p className="type-compact mt-meta">No verified pitching transactions appear in the latest official source window.</p>
            </div>
          )}
        </>
      )}

      <RosterContext rosterContext={read?.rosterContext} onSelectPitcher={onSelectPitcher} />
    </section>
  )
}
