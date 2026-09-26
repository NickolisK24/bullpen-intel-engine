import { Link } from 'react-router-dom'
import { TONIGHT_COPY } from './tonightView'

function TeamStateBadge({ teamState }) {
  if (!teamState.available) {
    return (
      <span
        className="inline-flex min-h-8 items-center rounded border px-2.5 py-1 font-mono text-xs uppercase tracking-wider"
        style={{
          borderColor: teamState.tone.borderColor,
          backgroundColor: teamState.tone.backgroundColor,
          color: teamState.tone.color,
        }}
        data-team-state="withheld"
      >
        {TONIGHT_COPY.teamStateWithheld}
      </span>
    )
  }
  return (
    <span
      className="inline-flex min-h-8 items-center gap-2 rounded border px-2.5 py-1 font-mono text-sm uppercase tracking-wider"
      style={{
        borderColor: teamState.tone.borderColor,
        backgroundColor: teamState.tone.backgroundColor,
        color: teamState.tone.color,
      }}
      data-team-state={teamState.publicState}
    >
      <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ backgroundColor: teamState.tone.dot }} />
      <span className="sr-only">Team State: </span>
      {teamState.publicLabel}
    </span>
  )
}

export default function TonightTeamSide({ side }) {
  return (
    <div className="min-w-0" data-testid="tonight-team-side" data-team={side.abbreviation || ''}>
      <p className="font-mono text-[11px] uppercase tracking-widest text-chalk400">{side.role}</p>
      <p className="mt-0.5 min-w-0 break-words text-base font-medium text-chalk100">
        {side.name}
        {side.abbreviation && (
          <span className="ml-1.5 font-mono text-xs text-chalk400">{side.abbreviation}</span>
        )}
      </p>
      <div className="mt-2">
        <TeamStateBadge teamState={side.teamState} />
      </div>

      {!side.available ? (
        <p className="mt-2 text-xs leading-relaxed text-chalk400">{TONIGHT_COPY.sideUnavailable}</p>
      ) : (
        <>
          {side.facts.length > 0 ? (
            <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs text-chalk200" aria-label={`${side.name} bullpen rest`}>
              {side.facts.map(fact => (
                <li key={fact.key} className="whitespace-nowrap" data-fact={fact.key}>{fact.text}</li>
              ))}
            </ul>
          ) : null}
          {!side.restAvailable && (
            <p className="mt-2 font-mono text-xs text-chalk400" data-fact="rest-unavailable">
              {TONIGHT_COPY.restUnavailable}
            </p>
          )}
          {side.keyArms.length > 0 && (
            <div className="mt-3">
              <p className="font-mono text-[11px] uppercase tracking-widest text-chalk400">Key arms</p>
              <ul className="mt-1 space-y-1 text-sm text-chalk200">
                {side.keyArms.map(arm => (
                  <li key={arm.key} className="min-w-0 break-words" data-testid="tonight-key-arm">
                    <span className="font-medium text-chalk100">{arm.name}</span>
                    {arm.roleLabel && <span className="text-chalk300"> · {arm.roleLabel}</span>}
                    {arm.pattern && <span className="whitespace-nowrap font-mono text-xs text-amber"> · {arm.pattern}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {side.rotation && (
            <p className="mt-2 text-xs text-chalk300" data-testid="tonight-rotation">{side.rotation}</p>
          )}
        </>
      )}
      {side.boardHref && (
        <Link
          to={side.boardHref}
          className="mt-3 inline-flex min-h-11 items-center rounded border border-dirt px-3 font-mono text-xs uppercase tracking-wider text-chalk200 transition-colors hover:border-amber hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
          data-link="team-board"
        >
          {side.abbreviation ? `${side.abbreviation} Team Board` : `${side.role} Team Board`}
        </Link>
      )}
    </div>
  )
}
