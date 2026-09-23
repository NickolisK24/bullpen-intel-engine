import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { formatDateOnly } from '../../../utils/dateDisplay'
import CompactSectionState from './CompactSectionState'

const eventGroups = [
  { key: 'addition', title: 'Recent additions' },
  { key: 'removal', title: 'Recent removals' },
  { key: 'other', title: 'Other roster moves' },
]

export function getRecentTransactionRows(recentTransactions) {
  return (recentTransactions?.events || []).map(event => ({
    ...event,
    dateLabel: formatDateOnly(event.date, { month: 'short' }),
  }))
}

function PitcherHandoff({ pitcherId, name, onSelectPitcher }) {
  if (pitcherId == null || typeof onSelectPitcher !== 'function') return <span>{name}</span>
  return (
    <button
      type="button"
      className="min-h-11 break-words text-left font-medium text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus"
      onClick={event => onSelectPitcher(pitcherId, event.currentTarget)}
    >
      {name}
    </button>
  )
}

function TransactionsSkeleton() {
  return (
    <section className="foundation-section min-w-0" aria-labelledby="recent-transactions-title" aria-busy="true" data-testid="recent-transactions-skeleton">
      <div className="rounded-sm border border-line-subtle bg-surface-raised/20 p-panel tablet:p-section">
        <h2 id="recent-transactions-title" className="type-section-title">Roster &amp; Transactions</h2>
        <span className="sr-only">Loading roster and transactions.</span>
        <SkeletonBlock className="mt-panel h-4 w-48 max-w-full" />
        <SkeletonBlock className="mt-panel h-5 w-64 max-w-full" />
      </div>
    </section>
  )
}

function EventList({ title, events, onSelectPitcher }) {
  if (!events.length) return null
  return (
    <div className="min-w-0">
      <h3 className="type-overline text-text-tertiary">{title}</h3>
      <ul className="mt-meta divide-y divide-line-subtle">
        {events.map((event, index) => (
          <li key={`${event.eventId || event.pitcherId}-${event.date}-${index}`} className="grid min-w-0 gap-meta py-row tablet:grid-cols-[6rem_minmax(0,1fr)] tablet:gap-panel">
            <time dateTime={event.date} className="type-metadata tabular-nums text-text-tertiary">{event.dateLabel}</time>
            <div className="min-w-0">
              <p className="type-compact break-words text-text-primary">
                <PitcherHandoff pitcherId={event.pitcherId} name={event.name} onSelectPitcher={onSelectPitcher} />
                <span className="text-text-secondary"> · {event.label}</span>
              </p>
              <p className="type-metadata mt-meta text-text-tertiary">Current roster: {event.currentRoster.label}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function TeamBoardRecentTransactions({ read, loading = false, error = null, onRetry, onSelectPitcher }) {
  if (loading) return <TransactionsSkeleton />

  const transactions = read?.recentTransactions
  const rows = getRecentTransactionRows(transactions)
  const offActive = transactions?.offActiveRecentContributors

  return (
    <section className="foundation-section min-w-0" aria-labelledby="recent-transactions-title" data-testid="team-board-recent-transactions">
      <header className="mb-panel border-b border-line-default pb-panel">
        <div className="type-overline text-text-tertiary">Bullpen personnel</div>
        <h2 id="recent-transactions-title" className="type-section-title mt-meta">Roster &amp; Transactions</h2>
        <p className="type-metadata mt-meta max-w-reading text-text-tertiary">Dated, verified pitching moves beside the represented active bullpen.</p>
      </header>

      {error ? (
        <SectionState status="error" title="Roster movement unavailable" message="Roster and transaction details could not be loaded." onRetry={onRetry} />
      ) : !transactions ? (
        <CompactSectionState title="Roster movement not published" message="This trusted Team Board does not contain frozen transaction context." />
      ) : (
        <>
          <p className="type-compact text-text-secondary">
            <span className="font-medium text-text-primary">{transactions.currentGroup.activeCount}</span> pitchers in the represented active bullpen. See Active Bullpen for the current group.
          </p>
          {transactions.windowStart && transactions.windowEnd && (
            <p className="type-metadata mt-meta text-text-tertiary">Official transaction window: <time dateTime={transactions.windowStart}>{transactions.windowStart}</time>–<time dateTime={transactions.windowEnd}>{transactions.windowEnd}</time></p>
          )}
          {transactions.status === 'unavailable' ? (
            <SectionState status="unavailable" title="Recent moves unavailable" message={transactions.limitations[0] || 'Recent official transaction records are unavailable.'} className="mt-panel" />
          ) : rows.length ? (
            <div className="mt-panel grid min-w-0 gap-panel rounded-sm border border-line-subtle bg-surface-raised/20 p-panel desktop:grid-cols-2">
              {eventGroups.map(group => <EventList key={group.key} title={group.title} events={rows.filter(row => row.direction === group.key)} onSelectPitcher={onSelectPitcher} />)}
            </div>
          ) : transactions.status === 'available' ? (
            <p className="type-compact mt-panel text-text-secondary">No verified pitching moves in the covered official transaction window.</p>
          ) : null}
          {transactions.status === 'partial' && (
            <SectionState status="partial" title="Some moves withheld" message={transactions.limitations[0] || 'Some recent transaction records could not be verified.'} className="mt-panel" />
          )}
          {offActive?.status === 'complete' && offActive.contributors.length > 0 && (
            <div className="mt-panel border-t border-line-subtle pt-panel">
              <h3 className="type-overline text-text-tertiary">Recent team workload, outside the active group</h3>
              <ul className="mt-meta flex flex-wrap gap-x-panel gap-y-meta">
                {offActive.contributors.map(item => (
                  <li key={item.pitcherId} className="type-compact text-text-secondary">
                    <PitcherHandoff pitcherId={item.pitcherId} name={item.name} onSelectPitcher={onSelectPitcher} />
                    <span className="text-text-tertiary"> · {item.currentRoster.label}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {offActive && offActive.status !== 'complete' && (
            <p className="type-metadata mt-panel text-text-tertiary">Recent off-active contributor context is {offActive.status}.</p>
          )}
        </>
      )}
    </section>
  )
}
