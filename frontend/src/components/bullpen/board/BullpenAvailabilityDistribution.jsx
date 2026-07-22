import { getBoardGroups, getBoardTotals } from './tonightsBullpenBoardView'

// Compact answer-zone distribution of the four public availability states for
// the selected team. It reads the same board authority the grouped board uses
// (getBoardGroups / getBoardTotals), so the counts always reconcile with the
// board group headers and the eligible-reliever total. It never recomputes a
// classification, never folds anything new, and never turns a withheld count
// into zero — a withheld population shows "Withheld", not "0".
export default function BullpenAvailabilityDistribution({ board }) {
  const groups = getBoardGroups(board)
  const totals = getBoardTotals(board)
  const withheld = totals.countWithheld

  return (
    <section
      aria-label="Bullpen availability distribution"
      className="mt-3 rounded-lg border border-dirt bg-field/40 p-3 sm:p-3.5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Availability
        </div>
        <div className="font-mono text-[11px] text-chalk400">
          {withheld ? (
            <span className="text-chalk500">Eligible relievers: withheld</span>
          ) : (
            <>
              <span className="text-chalk500">Eligible relievers</span>{' '}
              <span className="text-chalk200">{totals.total}</span>
            </>
          )}
        </div>
      </div>

      <dl className="mt-2 grid grid-cols-4 gap-1.5">
        {groups.map(group => (
          <div
            key={group.status}
            className="min-w-0 rounded border border-dirt/70 bg-dugout/50 px-1.5 py-1.5 text-center"
          >
            <dt className="flex items-center justify-center gap-1 font-mono text-[9px] uppercase tracking-wide text-chalk500">
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={group.badge.dotStyle}
                aria-hidden="true"
              />
              <span className="min-w-0 truncate">{group.label}</span>
            </dt>
            <dd className="mt-0.5 font-display text-xl leading-none tracking-wide text-chalk100">
              {group.count == null ? '—' : group.count}
            </dd>
          </div>
        ))}
      </dl>

      {withheld && (
        <p className="mt-2 text-[11px] leading-snug text-chalk500">
          Current usable bullpen depth is withheld until roster status is verified.
        </p>
      )}
    </section>
  )
}
