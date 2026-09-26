import { TONIGHT_COPY } from './tonightView'

function TeamStateBadge({ teamState }) {
  const tone = {
    borderColor: teamState.tone.borderColor,
    backgroundColor: teamState.tone.backgroundColor,
    color: teamState.tone.color,
  }
  if (!teamState.available) {
    return (
      <span
        className="inline-flex min-h-8 max-w-full items-center rounded border px-2.5 py-1 font-mono text-xs uppercase tracking-wider"
        style={tone}
        data-team-state="withheld"
      >
        {TONIGHT_COPY.teamStateWithheld}
      </span>
    )
  }
  return (
    <span
      className="inline-flex min-h-8 items-center gap-2 whitespace-nowrap rounded border px-2.5 py-1 font-mono text-sm uppercase tracking-wider"
      style={tone}
      data-team-state={teamState.publicState}
    >
      <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: teamState.tone.dot }} />
      <span className="sr-only">Team State: </span>
      {teamState.publicLabel}
    </span>
  )
}

// One club's side of a game card, in reading order: identity, Team State,
// rest/usage, key arms, rotation. Supporting facts are plain text so only
// Team State reads as a status. Actions live in the card's shared action row.
export default function TonightTeamSide({ side }) {
  return (
    <div className="min-w-0" data-testid="tonight-team-side" data-team={side.abbreviation || ''}>
      <p className="min-w-0 break-words font-mono text-[11px] uppercase tracking-widest text-chalk400">
        {side.role}
        {side.abbreviation && <span className="text-chalk200"> · {side.abbreviation}</span>}
      </p>
      <div className="mt-1.5">
        <TeamStateBadge teamState={side.teamState} />
      </div>

      {!side.available ? (
        <p className="mt-2 text-xs leading-relaxed text-chalk400">{TONIGHT_COPY.sideUnavailable}</p>
      ) : (
        <>
          {side.facts.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-xs text-chalk300" aria-label={`${side.name} bullpen rest`}>
              {side.facts.map(fact => (
                <li key={fact.key} className="whitespace-nowrap" data-fact={fact.key}>{fact.text}</li>
              ))}
            </ul>
          )}
          {!side.restAvailable && (
            <p className="mt-2 font-mono text-xs text-chalk400" data-fact="rest-unavailable">
              {TONIGHT_COPY.restUnavailable}
            </p>
          )}
          {side.keyArms.length > 0 && (
            <div className="mt-2.5">
              <p className="font-mono text-[11px] uppercase tracking-widest text-chalk400">Key arms</p>
              <ul className="mt-1 space-y-1 text-sm leading-snug">
                {side.keyArms.map(arm => (
                  <li key={arm.key} className="min-w-0 break-words" data-testid="tonight-key-arm">
                    <span className="text-chalk100">{arm.name}</span>
                    {arm.roleLabel && <span className="text-xs text-chalk400"> · {arm.roleLabel}</span>}
                    {arm.pattern && <span className="whitespace-nowrap font-mono text-xs text-amber"> · {arm.pattern}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {side.rotation && (
            <p className="mt-2 break-words text-xs text-chalk400" data-testid="tonight-rotation">{side.rotation}</p>
          )}
        </>
      )}
    </div>
  )
}
