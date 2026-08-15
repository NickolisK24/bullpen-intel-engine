import { Link } from 'react-router-dom'
import { LoadingPane, StaleDataNotice, UnavailableDataState } from '../UI'
import { freshnessDataThrough } from './syncStatusView'

function TeamStateChip({ teamState }) {
  return (
    <span
      className="inline-flex min-h-7 shrink-0 items-center rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-wider"
      style={{
        borderColor: teamState.tone.borderColor,
        backgroundColor: teamState.tone.backgroundColor,
        color: teamState.tone.color,
      }}
    >
      {teamState.publicLabel}
    </span>
  )
}

function TeamRow({ team, showState = true }) {
  return (
    <li>
      <Link
        to={team.teamHref}
        className="group flex min-h-11 items-center justify-between gap-2 rounded border border-transparent px-2 py-1.5 transition-colors hover:border-dirt hover:bg-field/45 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
        aria-label={`Open the Team Board for ${team.teamName}`}
      >
        <span className="min-w-0 text-sm leading-snug text-chalk200 group-hover:text-amber">
          <span className="break-words font-medium">{team.teamName}</span>
          <span className="ml-1.5 font-mono text-[10px] text-chalk600">{team.teamAbbreviation}</span>
        </span>
        {showState ? (
          <TeamStateChip teamState={team.teamState} />
        ) : (
          <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-chalk500">Read unavailable</span>
        )}
      </Link>
      {!showState && (
        <p className="px-2 pb-2 text-[11px] leading-relaxed text-chalk600">
          {team.teamState.unavailableMessage}
        </p>
      )}
    </li>
  )
}

function StateGroup({ group }) {
  return (
    <div className="card min-w-0 p-3 sm:p-4">
      <div className="flex items-center justify-between gap-2 border-b border-dirt/70 pb-2">
        <h3 className="font-mono text-xs uppercase tracking-widest text-chalk300">{group.label}</h3>
        <span className="font-mono text-xs text-chalk500">{group.teams.length}</span>
      </div>
      {group.teams.length > 0 ? (
        <ul className="mt-1 divide-y divide-dirt/60">
          {group.teams.map(team => <TeamRow key={team.teamId} team={team} />)}
        </ul>
      ) : (
        <p className="py-3 text-xs text-chalk600">No published club reads in this group.</p>
      )}
    </div>
  )
}

export default function LeagueTeamStateLandscape({ view, loading = false, error = null, staleWithError = false, onRetry }) {
  return (
    <section className="mb-6" aria-labelledby="current-bullpen-state-title">
      <div className="mb-3">
        <h2 id="current-bullpen-state-title" className="font-mono text-xs uppercase tracking-widest text-chalk400">
          Current Bullpen State
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-chalk600">
          {view.valid && !view.globalUnavailable
            ? '30 MLB clubs · grouped by published Team State'
            : 'League-wide published Team State view'}
        </p>
      </div>

      {loading && !view.valid ? (
        <LoadingPane message="Loading the current league Team State view..." />
      ) : error && !view.valid ? (
        <UnavailableDataState
          title="League Team State unavailable"
          message="The current league Team State view is unavailable."
          onRetry={onRetry}
        />
      ) : !view.valid || view.globalUnavailable ? (
        <UnavailableDataState
          title="League Team State unavailable"
          message="The current league Team State view is unavailable."
          onRetry={onRetry}
        />
      ) : (
        <>
          {staleWithError && (
            <StaleDataNotice dataThrough={freshnessDataThrough(view.freshness)} onRetry={onRetry} />
          )}
          <p className="mb-3 font-mono text-[11px] text-chalk500">
            {view.representedTeamCount} published read{view.representedTeamCount === 1 ? '' : 's'}
            {' · '}
            {view.withheldTeamCount} unavailable
          </p>
          <div className="grid min-w-0 grid-cols-1 gap-3 lg:grid-cols-3">
            {view.groups.map(group => <StateGroup key={group.key} group={group} />)}
          </div>

          {view.exceptions.length > 0 && (
            <div className="mt-4 rounded border border-dirt/80 bg-dugout/60 p-3 sm:p-4" aria-label="Publication exceptions">
              <div className="border-b border-dirt/70 pb-2">
                <h3 className="font-mono text-xs uppercase tracking-widest text-chalk500">Publication exceptions</h3>
                <p className="mt-1 text-xs leading-relaxed text-chalk600">
                  These clubs remain in the league denominator, but a current published Team State read is unavailable.
                </p>
              </div>
              <ul className="mt-1 grid min-w-0 grid-cols-1 divide-y divide-dirt/60 sm:grid-cols-2 sm:gap-x-4 sm:divide-y-0">
                {view.exceptions.map(team => <TeamRow key={team.teamId} team={team} showState={false} />)}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  )
}
