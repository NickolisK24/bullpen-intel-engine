import { readPublicTeamState } from '../../../adapters/publicTeamState'
import { formatFreshnessDate, isSampleFreshness } from '../../UI/Freshness'
import { SkeletonBlock } from '../../UI/Skeleton'
import SectionState from '../../UI/SectionState'

function countOrNull(value) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
    ? value
    : null
}

function firstLimitation(sectionStatus, excludedMessage = null) {
  const sections = ['team_state', 'active_bullpen']
  for (const key of sections) {
    const section = sectionStatus?.[key]
    if (!section || section.status === 'available') continue
    const limitation = Array.isArray(section.limitations)
      ? section.limitations.find(item => typeof item === 'string' && item.trim())
      : null
    if (key === 'team_state' && section.status === 'unavailable') continue
    if (limitation?.trim() === excludedMessage) continue
    return {
      status: section.status === 'unavailable' ? 'unavailable' : 'partial',
      limitation: limitation?.trim() || null,
    }
  }
  return null
}

export function getTeamBoardAnswerView(read, fallbackTeam = null) {
  const team = read?.team || fallbackTeam || {}
  const teamState = readPublicTeamState(read?.teamState)
  const restStatus = read?.restStatus || {}
  const signals = [
    ['Active arms', countOrNull(read?.activeBullpen?.arm_count)],
    ['Rested arms', restStatus.available === true ? countOrNull(restStatus.rested_arm_count) : null],
    ['Worked yesterday', restStatus.available === true ? countOrNull(restStatus.worked_yesterday_count) : null],
  ]
    .filter(([, value]) => value !== null)
    .map(([label, value]) => ({ label, value }))

  return {
    teamName: team.team_name || team.team_abbreviation || 'Team bullpen',
    teamAbbreviation: team.team_abbreviation || null,
    teamState,
    summary: teamState.available && typeof read?.summary === 'string' && read.summary.trim()
      ? read.summary
      : null,
    representedDate: read?.representedDate || teamState.dataThrough || read?.freshness?.data_through || null,
    isSample: isSampleFreshness(read?.freshness),
    signals,
    limitation: firstLimitation(read?.sectionStatus, teamState.unavailableMessage),
  }
}

function AnswerHeading({ teamName, teamAbbreviation }) {
  return (
    <div className="min-w-0">
      <div className="type-overline">Team Board</div>
      <h2 id="team-board-answer-title" className="mt-meta break-words font-display text-3xl leading-none tracking-wide text-chalk100 tablet:text-4xl">
        {teamName}
      </h2>
      {teamAbbreviation && teamAbbreviation !== teamName && (
        <div className="type-metadata mt-meta">{teamAbbreviation}</div>
      )}
    </div>
  )
}

export function TeamBoardAnswerSkeleton({ team }) {
  const teamName = team?.team_name || team?.team_abbreviation || 'Team bullpen'
  const teamAbbreviation = team?.team_abbreviation || null
  return (
    <section
      className="foundation-panel"
      aria-labelledby="team-board-answer-title"
      aria-busy="true"
      aria-live="polite"
      data-testid="team-board-answer-skeleton"
    >
      <span className="sr-only">Loading the current Team Board answer.</span>
      <div className="flex min-w-0 flex-col gap-panel tablet:flex-row tablet:items-start tablet:justify-between">
        <AnswerHeading teamName={teamName} teamAbbreviation={teamAbbreviation} />
        <SkeletonBlock className="h-8 w-28 shrink-0" />
      </div>
      <SkeletonBlock className="mt-section h-5 w-full max-w-2xl" />
      <div className="mt-section grid grid-cols-1 gap-pair border-t border-dirt pt-panel tablet:grid-cols-3">
        {[0, 1, 2].map(index => <SkeletonBlock key={index} className="h-10 w-full" />)}
      </div>
      <SkeletonBlock className="mt-panel h-3 w-36" />
    </section>
  )
}

export default function TeamBoardAnswerBlock({
  read,
  team,
  loading = false,
  error = null,
  onRetry,
}) {
  if (loading) return <TeamBoardAnswerSkeleton team={team} />

  const view = getTeamBoardAnswerView(read, team)
  const hasError = Boolean(error)

  return (
    <section className="foundation-panel" aria-labelledby="team-board-answer-title" data-testid="team-board-answer-block">
      <div className="flex min-w-0 flex-col gap-panel tablet:flex-row tablet:items-start tablet:justify-between">
        <AnswerHeading teamName={view.teamName} teamAbbreviation={view.teamAbbreviation} />
        {view.teamState.available && (
          <div
            className="inline-flex min-h-8 w-fit items-center gap-2 rounded-sm border px-3 py-1.5 font-mono text-metadata uppercase tracking-widest"
            style={{
              borderColor: view.teamState.tone.borderColor,
              backgroundColor: view.teamState.tone.backgroundColor,
              color: view.teamState.tone.color,
            }}
            aria-label={`Team State: ${view.teamState.publicLabel}`}
          >
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: view.teamState.tone.dot }} aria-hidden="true" />
            <span>Team State: {view.teamState.publicLabel}</span>
          </div>
        )}
      </div>

      {hasError ? (
        <SectionState
          status="error"
          title="Team Board answer unavailable"
          message="The current Team Board answer could not be loaded."
          onRetry={onRetry}
          className="mt-section"
        />
      ) : !read ? (
        <SectionState
          status="unavailable"
          title="Team Board answer unavailable"
          message="A current Team Board answer is not available."
          onRetry={onRetry}
          className="mt-section"
        />
      ) : (
        <>
          <div className="mt-section min-w-0 desktop:grid desktop:grid-cols-[minmax(0,2fr)_minmax(16rem,0.8fr)] desktop:gap-section-lg">
            <div className="min-w-0">
              {view.teamState.available ? (
                view.summary && <p className="type-body max-w-3xl text-chalk200">{view.summary}</p>
              ) : (
                <p className="type-body max-w-3xl text-chalk300" role="status">
                  {view.teamState.unavailableMessage}
                </p>
              )}
            </div>

            <div className="mt-section min-w-0 desktop:mt-0 desktop:border-l desktop:border-dirt desktop:pl-section">
              {view.signals.length > 0 && (
                <dl className="grid grid-cols-1 border-t border-dirt tablet:grid-cols-3 desktop:border-t-0" aria-label="Current bullpen signals">
                  {view.signals.map(signal => (
                    <div key={signal.label} className="min-w-0 border-b border-dirt py-panel last:border-b-0 tablet:border-b-0 tablet:border-r tablet:px-panel tablet:first:pl-0 tablet:last:border-r-0 desktop:border-r-0 desktop:px-0 desktop:first:pt-0">
                      <dt className="type-overline">{signal.label}</dt>
                      <dd className="type-data mt-meta text-lg text-chalk100">{signal.value}</dd>
                    </div>
                  ))}
                </dl>
              )}

              {view.representedDate && (
                <p className="type-metadata mt-panel">
                  Data through{' '}
                  <time dateTime={view.representedDate}>
                    {formatFreshnessDate(view.representedDate) || view.representedDate}
                  </time>
                </p>
              )}
            </div>
          </div>

          {view.isSample && (
            <p className="type-compact mt-panel text-warning" role="status">
              Sample data — not live MLB data.
            </p>
          )}

          {view.limitation && (
            <SectionState
              status={view.limitation.status}
              title="Limited read"
              message={view.limitation.limitation}
              className="mt-panel"
            />
          )}
        </>
      )}
    </section>
  )
}
