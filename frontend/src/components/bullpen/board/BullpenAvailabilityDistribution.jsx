import { getBoardGroups, getBoardTotals } from './tonightsBullpenBoardView'

// Compact answer-zone distribution of the published availability groups for
// the selected team. It reads the same board authority the grouped board uses
// (getBoardGroups / getBoardTotals), so the counts always reconcile with the
// board group headers and the eligible-reliever total. It never recomputes a
// classification, never folds anything new, and never turns a withheld count
// into zero — a withheld population shows "Withheld", not "0".
export default function BullpenAvailabilityDistribution({ board }) {
  const groups = getBoardGroups(board)
  const totals = getBoardTotals(board)
  const withheld = totals.countWithheld

  // Composed as a hairline-separated count row rather than five bordered tiles.
  // The distribution supports the read directly above it; boxed and centred, it
  // read as five independent metrics competing with the state for attention,
  // which is the dashboard-tile failure the Team Board is meant to avoid.
  return (
    <section
      aria-label="Bullpen availability distribution"
      className="bos-panel mt-3 p-4 sm:px-6 sm:py-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <p className="bos-micro">Availability</p>
        <p className="bos-meta normal-case">
          {withheld ? (
            'Eligible relievers: withheld'
          ) : (
            <>
              Eligible relievers <span className="text-chalk200">{totals.total}</span>
            </>
          )}
        </p>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
        {groups.map(group => (
          <div key={group.status} className="min-w-0">
            <dt className="flex items-center gap-1.5 bos-micro">
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={group.badge.dotStyle}
                aria-hidden="true"
              />
              <span className="min-w-0 break-words">{group.label}</span>
            </dt>
            <dd className="bos-value mt-1 text-lg leading-none text-chalk100">
              {group.count == null ? '—' : group.count}
            </dd>
          </div>
        ))}
      </dl>

      {withheld && (
        <p className="bos-meta mt-3 max-w-measure normal-case">
          Current usable bullpen depth is withheld until roster status is verified.
        </p>
      )}
    </section>
  )
}
