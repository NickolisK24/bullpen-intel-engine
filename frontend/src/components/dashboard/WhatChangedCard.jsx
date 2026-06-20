function teamLabel(team) {
  return team?.team_name || team?.team_abbreviation || 'your team'
}

function formatShortDate(value) {
  if (!value) return null
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function freshnessDate(changes) {
  return (
    changes?.freshness?.latest_workload_date
    || changes?.freshness?.data_through
    || changes?.comparison?.current_game_date
  )
}

function teamBehindLeagueNote(changes) {
  const reasonCodes = Array.isArray(changes?.state_reason_codes) ? changes.state_reason_codes : []
  if (!reasonCodes.includes('team_data_behind_league')) return null
  const limitations = Array.isArray(changes?.limitations) ? changes.limitations : []
  return limitations.find(note => note.includes('league data is current through')) || null
}

function CardStatus({ children }) {
  return (
    <div className="rounded border border-dirt bg-field/50 p-3" role="status" aria-live="polite">
      <p className="text-sm leading-relaxed text-chalk400">{children}</p>
    </div>
  )
}

function ChangesList({ changes }) {
  const items = Array.isArray(changes?.pitcher_changes) ? changes.pitcher_changes : []
  const visible = items.slice(0, 4)
  const hidden = Math.max(items.length - visible.length, 0)

  return (
    <div className="space-y-3">
      {changes?.team_summary?.summary && (
        <div className="rounded border border-amber/25 bg-amber/10 p-3 font-mono text-xs leading-relaxed text-amber">
          {changes.team_summary.summary}
        </div>
      )}

      {visible.length > 0 && (
        <ul className="space-y-2">
          {visible.map((item, index) => (
            <li key={`${item.type}-${item.pitcher_id}-${item.game_date || index}`} className="rounded border border-dirt/80 bg-dugout/70 p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-chalk500">
                {item.type === 'appearance' ? 'Appearance' : 'Availability'}
              </div>
              <div className="mt-0.5 text-sm font-semibold text-chalk100">{item.pitcher_name}</div>
              {item.summary && (
                <p className="mt-1 text-xs leading-relaxed text-chalk400">{item.summary}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {hidden > 0 && (
        <p className="font-mono text-[11px] uppercase tracking-wider text-chalk500">
          +{hidden} more bullpen changes
        </p>
      )}
    </div>
  )
}

export function WhatChangedCard({
  followedTeam = null,
  changes = null,
  loading = false,
  error = null,
  onRetry = null,
}) {
  const hasFollowedTeam = !!followedTeam
  const state = changes?.state
  const latestDate = formatShortDate(freshnessDate(changes))
  const behindLeagueNote = teamBehindLeagueNote(changes)

  let body = null
  if (!hasFollowedTeam) {
    body = (
      <CardStatus>
        Follow your team to see how its bullpen changed after the last completed game.
      </CardStatus>
    )
  } else if (loading) {
    body = <CardStatus>Checking how the bullpen moved after the latest completed game...</CardStatus>
  } else if (error) {
    body = (
      <div className="rounded border border-dirt bg-field/50 p-3" role="status" aria-live="polite">
        <p className="text-sm leading-relaxed text-chalk400">The latest bullpen change read is unavailable right now.</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded border border-amber/30 bg-amber/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/15"
          >
            Retry
          </button>
        )}
      </div>
    )
  } else if (state === 'stale') {
    body = (
      <CardStatus>
        Bullpen movement is paused{latestDate ? ` - latest data is from ${latestDate}.` : '.'}
      </CardStatus>
    )
  } else if (state === 'no_baseline') {
    body = (
      <CardStatus>
        No earlier completed game is available for comparison yet. Check back after the next game.
      </CardStatus>
    )
  } else if (state === 'no_changes') {
    body = (
      <CardStatus>
        No meaningful bullpen movement since the last completed game.
      </CardStatus>
    )
  } else if (state === 'changes') {
    body = <ChangesList changes={changes} />
  } else {
    body = <CardStatus>The bullpen change read is not available for this team yet.</CardStatus>
  }

  return (
    <section className="mb-6" aria-label="What Changed Since Last Game">
      <div className="card p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
              What Changed Since Last Game
            </div>
            <h2 className="mt-1 font-display text-xl tracking-wide text-chalk100">
              {hasFollowedTeam ? teamLabel(followedTeam) : 'Followed Team'}
            </h2>
          </div>
          {changes?.comparison?.label && (
            <div className="rounded border border-dirt px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-chalk500">
              {changes.comparison.label}
            </div>
          )}
        </div>
        {body}
        {behindLeagueNote && (
          <p className="mt-3 rounded border border-dirt bg-field/40 p-3 font-mono text-[11px] leading-relaxed text-chalk400">
            {behindLeagueNote}
          </p>
        )}
      </div>
    </section>
  )
}

export default WhatChangedCard
