import { readPublicTeamState } from '../../../adapters/publicTeamState'
import { formatFreshnessDate, isSampleFreshness } from '../../UI/Freshness'
import { SkeletonBlock } from '../../UI/Skeleton'
import SectionState from '../../UI/SectionState'
import { getTeamGameContextView } from './teamGameContextView'

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
  const gameContext = getTeamGameContextView(read?.gameContext)

  return {
    teamName: team.team_name || team.team_abbreviation || 'Team bullpen',
    teamAbbreviation: team.team_abbreviation || null,
    teamState,
    summary: teamState.available && typeof read?.summary === 'string' && read.summary.trim()
      ? read.summary
      : null,
    representedDate: read?.representedDate || teamState.dataThrough || read?.freshness?.data_through || null,
    isSample: isSampleFreshness(read?.freshness),
    isStale: read?.freshness?.is_current === false || read?.freshness?.fail_closed === true,
    gameContext: gameContext.isPresent ? gameContext : null,
    limitation: firstLimitation(read?.sectionStatus, teamState.unavailableMessage),
  }
}

export function getBullpenSummaryView(read) {
  const activeAvailable = read?.sectionStatus?.active_bullpen?.status === 'available'
  const restAvailable = read?.sectionStatus?.rest_status?.status === 'available'
    && read?.restStatus?.available === true
  const sevenDayWindow = Array.isArray(read?.workloadOverview?.windows)
    ? read.workloadOverview.windows.find(window => window?.window_days === 7)
    : null
  const activeArms = activeAvailable ? countOrNull(read?.activeBullpen?.arm_count) : null
  const restedOptions = restAvailable ? countOrNull(read?.restStatus?.rested_arm_count) : null
  const sevenDayPitches = countOrNull(sevenDayWindow?.pitches_total)

  return [
    {
      key: 'active-arms',
      label: 'Active arms',
      value: activeArms,
      qualifier: activeArms === null ? 'Not published' : 'Current eligible bullpen',
    },
    {
      key: 'rested-options',
      label: 'Rested options',
      value: restedOptions,
      qualifier: restedOptions === null ? 'Not published' : 'Backend rest read',
    },
    {
      key: 'recently-used-arms',
      label: 'Recently used arms',
      value: null,
      qualifier: 'Public window not defined',
    },
    {
      key: 'off-active-count',
      label: 'Off-active count',
      value: null,
      qualifier: 'Exact count not published',
    },
    {
      key: 'seven-day-workload',
      label: '7-day workload',
      value: sevenDayPitches,
      qualifier: sevenDayPitches === null ? 'Pitches not published' : 'Pitches',
    },
  ]
}

function AnswerHeading({ teamName, teamAbbreviation, teamSwitcher = null }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-panel tablet:flex-row tablet:items-end">
      <div className="min-w-0 flex-1">
        <div className="type-overline">Team Board</div>
        <h2 id="team-board-answer-title" className="mt-meta break-words font-board text-2xl font-semibold leading-tight text-text-primary tablet:text-[1.75rem] lg:text-3xl">
          {teamName}
        </h2>
        {teamAbbreviation && teamAbbreviation !== teamName && (
          <div className="type-metadata mt-meta">{teamAbbreviation}</div>
        )}
      </div>
      {teamSwitcher}
    </div>
  )
}

export function TeamBoardAnswerSkeleton({ team, teamSwitcher = null }) {
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
        <AnswerHeading teamName={teamName} teamAbbreviation={teamAbbreviation} teamSwitcher={teamSwitcher} />
        <SkeletonBlock className="h-8 w-28 shrink-0" />
      </div>
      <SkeletonBlock className="mt-section h-5 w-full max-w-2xl" />
      <SkeletonBlock className="mt-panel h-3 w-36" />
    </section>
  )
}

function BullpenSummary({ read }) {
  const figures = getBullpenSummaryView(read)

  return (
    <section className="foundation-panel mt-section" aria-labelledby="bullpen-summary-title" data-testid="bullpen-summary">
      <h3 id="bullpen-summary-title" className="type-section-title">Bullpen Summary</h3>
      <dl className="mt-panel grid grid-cols-2 gap-x-panel gap-y-section border-t border-dirt pt-panel tablet:grid-cols-3 desktop:grid-cols-5">
        {figures.map((figure, index) => (
          <div
            key={figure.key}
            className={`min-w-0 ${index === figures.length - 1 ? 'col-span-2 tablet:col-span-1' : ''}`}
          >
            <dt className="type-overline break-words">{figure.label}</dt>
            <dd className={`type-data mt-meta text-2xl ${figure.value === null ? 'text-text-withheld' : 'text-text-primary'}`}>
              {figure.value ?? '—'}
            </dd>
            <p className="type-metadata mt-meta break-words">{figure.qualifier}</p>
          </div>
        ))}
      </dl>
    </section>
  )
}

export default function TeamBoardAnswerBlock({
  read,
  team,
  loading = false,
  error = null,
  onRetry,
  teamSwitcher = null,
  evidenceDisclosure = null,
}) {
  if (loading) return <TeamBoardAnswerSkeleton team={team} teamSwitcher={teamSwitcher} />

  const view = getTeamBoardAnswerView(read, team)
  const hasError = Boolean(error)

  return (
    <>
      <section className="foundation-panel" aria-labelledby="team-board-answer-title" data-testid="team-board-answer-block">
      <div className="flex min-w-0 flex-col gap-panel tablet:flex-row tablet:items-start tablet:justify-between">
        <AnswerHeading teamName={view.teamName} teamAbbreviation={view.teamAbbreviation} teamSwitcher={teamSwitcher} />
        {view.teamState.available && (
          <div
            className="inline-flex min-h-8 w-fit items-center gap-2 rounded-sm border px-3 py-1.5 font-board text-board-metadata"
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
          <div className="mt-section min-w-0 desktop:grid desktop:grid-cols-[minmax(0,42rem)_minmax(14rem,1fr)] desktop:gap-section-lg">
            <div className="min-w-0">
              {view.teamState.available ? (
                view.summary && <p className="type-body max-w-3xl text-chalk200">{view.summary}</p>
              ) : (
                <p className="type-body max-w-3xl text-chalk300" role="status">
                  {view.teamState.unavailableMessage}
                </p>
              )}
            </div>

            <div className="mt-panel min-w-0 border-t border-dirt pt-panel desktop:mt-0 desktop:border-l desktop:border-t-0 desktop:pl-section desktop:pt-0">
              {view.representedDate && (
                <p className="type-metadata flex items-center gap-2">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${view.isStale ? 'bg-warning' : 'bg-gold'}`} aria-hidden="true" />
                  <span>{view.isStale ? 'Stale · data through ' : 'Data through '}</span>
                  <time dateTime={view.representedDate}>
                    {formatFreshnessDate(view.representedDate) || view.representedDate}
                  </time>
                </p>
              )}
              {view.gameContext && (
                <p className="type-metadata mt-meta break-words" aria-label="Game context">
                  {view.gameContext.statusLabel}
                  {view.gameContext.opponent ? ` vs ${view.gameContext.opponent}` : ''}
                  {view.gameContext.gameDate ? ` · ${view.gameContext.gameDate}` : ''}
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

          {evidenceDisclosure}
        </>
      )}
      </section>
      {!hasError && read && <BullpenSummary read={read} />}
    </>
  )
}
