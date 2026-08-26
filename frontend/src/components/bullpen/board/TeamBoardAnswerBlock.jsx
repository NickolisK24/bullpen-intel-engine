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
  const recentlyUsedAvailable = read?.sectionStatus?.recently_used_arms?.status === 'available'
    && read?.recentlyUsedArms?.status === 'available'
  const recentlyUsedArms = recentlyUsedAvailable
    ? countOrNull(read?.recentlyUsedArms?.value)
    : null
  const recentlyUsedQualifier = recentlyUsedArms === null
    ? 'Not published'
    : read?.recentlyUsedArms?.window_label
  const offActiveAvailable = read?.sectionStatus?.off_active_count?.status === 'available'
    && read?.offActiveCount?.status === 'available'
  const offActiveCount = offActiveAvailable
    ? countOrNull(read?.offActiveCount?.value)
    : null
  const offActiveQualifier = offActiveCount === null
    ? 'Not published'
    : read?.offActiveCount?.context_label

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
      value: recentlyUsedArms,
      qualifier: recentlyUsedQualifier || 'Not published',
    },
    {
      key: 'off-active-count',
      label: 'Off-active count',
      value: offActiveCount,
      qualifier: offActiveQualifier || 'Not published',
    },
    {
      key: 'seven-day-workload',
      label: '7-day workload',
      value: sevenDayPitches,
      qualifier: sevenDayPitches === null ? 'Pitches not published' : 'Pitches',
    },
  ]
}

function AnswerHeading({ teamName, teamAbbreviation, teamSwitcher = null, historyHref = null }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-panel tablet:flex-row tablet:items-end">
      <div className="min-w-0 flex-1">
        <div className="type-overline text-brand-blue">Team Board</div>
        <div className="mt-meta flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 id="team-board-answer-title" className="break-words font-board text-[1.75rem] font-semibold leading-[1.08] tracking-[-0.02em] text-text-primary tablet:text-[2rem] desktop:text-[2.25rem]">
            {teamName}
          </h2>
          {teamAbbreviation && teamAbbreviation !== teamName && (
            <span className="type-overline text-text-withheld" aria-hidden="true">{teamAbbreviation}</span>
          )}
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-2 tablet:items-end">
        {teamSwitcher}
        {historyHref && (
          <a
            href={historyHref}
            className="inline-flex min-h-11 items-center font-board text-board-metadata font-semibold text-brand-blue underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
          >
            View History
          </a>
        )}
      </div>
    </div>
  )
}

const answerSurfaceClass = [
  'foundation-panel -mx-4 overflow-hidden border-y border-line-default bg-surface-raised/55 px-4 py-5',
  'md:-mx-6 md:px-6 md:py-6',
  'xl:-mx-8 xl:px-8',
  'desktop:mx-0 desktop:rounded-md desktop:border desktop:px-7 desktop:py-7',
].join(' ')

export function TeamBoardAnswerSkeleton({ team, teamSwitcher = null }) {
  const teamName = team?.team_name || team?.team_abbreviation || 'Team bullpen'
  const teamAbbreviation = team?.team_abbreviation || null
  return (
    <section
      className={answerSurfaceClass}
      aria-labelledby="team-board-answer-title"
      aria-busy="true"
      aria-live="polite"
      data-testid="team-board-answer-skeleton"
    >
      <span className="sr-only">Loading the current Team Board answer.</span>
      <div className="flex min-w-0 flex-col gap-panel tablet:flex-row tablet:items-end tablet:justify-between">
        <AnswerHeading teamName={teamName} teamAbbreviation={teamAbbreviation} teamSwitcher={teamSwitcher} />
        <SkeletonBlock className="h-9 w-32 shrink-0" />
      </div>
      <SkeletonBlock className="mt-section h-6 w-full max-w-2xl" />
      <div className="mt-section border-t border-line-subtle pt-panel">
        <SkeletonBlock className="h-3 w-40" />
      </div>
    </section>
  )
}

function BullpenSummary({ read }) {
  const figures = getBullpenSummaryView(read)

  return (
    <section
      className="foundation-panel -mx-4 border-b border-line-default bg-surface-nav/45 px-4 pb-5 pt-4 md:-mx-6 md:px-6 xl:-mx-8 xl:px-8 desktop:mx-0 desktop:mt-2 desktop:rounded-md desktop:border desktop:px-6 desktop:py-5"
      aria-labelledby="bullpen-summary-title"
      data-testid="bullpen-summary"
    >
      <div className="flex items-center justify-between gap-panel">
        <h3 id="bullpen-summary-title" className="type-overline text-text-secondary">Bullpen Summary</h3>
        <span className="type-metadata hidden text-text-withheld tablet:inline">Current bullpen snapshot</span>
      </div>
      <dl className="mt-panel grid grid-cols-2 border-t border-line-subtle tablet:grid-cols-3 desktop:grid-cols-5 desktop:divide-x desktop:divide-line-subtle">
        {figures.map((figure, index) => (
          <div
            key={figure.key}
            className={`min-w-0 border-b border-line-subtle py-panel pr-panel desktop:border-b-0 desktop:px-panel desktop:first:pl-0 desktop:last:pr-0 ${index % 2 === 1 ? 'border-l pl-panel tablet:border-l-0 tablet:pl-0' : ''} ${index === figures.length - 1 ? 'col-span-2 tablet:col-span-1' : ''}`}
          >
            <dt className="type-overline break-words text-text-tertiary">{figure.label}</dt>
            <dd className={`mt-meta font-board text-[1.65rem] font-semibold leading-none tabular-nums ${figure.value === null ? 'text-text-withheld' : 'text-text-primary'}`}>
              {figure.value ?? '—'}
            </dd>
            <p className="type-metadata mt-meta break-words text-text-withheld">{figure.qualifier}</p>
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
  historyHref = null,
}) {
  if (loading) return <TeamBoardAnswerSkeleton team={team} teamSwitcher={teamSwitcher} />

  const view = getTeamBoardAnswerView(read, team)
  const hasError = Boolean(error)

  return (
    <>
      <section className={answerSurfaceClass} aria-labelledby="team-board-answer-title" data-testid="team-board-answer-block">
        <div className="flex min-w-0 flex-col gap-panel tablet:flex-row tablet:items-end tablet:justify-between">
          <AnswerHeading teamName={view.teamName} teamAbbreviation={view.teamAbbreviation} teamSwitcher={teamSwitcher} historyHref={historyHref} />
          {view.teamState.available && (
            <div
              className="inline-flex min-h-9 w-fit shrink-0 items-center gap-2 rounded-sm border px-3 py-2 font-board text-board-metadata font-semibold"
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
            <div className="mt-section min-w-0 desktop:grid desktop:grid-cols-[minmax(0,1fr)_minmax(16rem,0.42fr)] desktop:gap-section-lg">
              <div className="min-w-0">
                {view.teamState.available ? (
                  view.summary && <p className="max-w-3xl font-board text-[1rem] font-medium leading-[1.6] text-text-primary tablet:text-[1.0625rem]">{view.summary}</p>
                ) : (
                  <p className="type-body max-w-3xl text-text-secondary" role="status">
                    {view.teamState.unavailableMessage}
                  </p>
                )}
              </div>

              <div className="mt-section min-w-0 border-t border-line-subtle pt-panel desktop:mt-0 desktop:border-l desktop:border-t-0 desktop:pl-section desktop:pt-0">
                {view.representedDate && (
                  <p className="type-metadata flex items-center gap-2 text-text-secondary">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${view.isStale ? 'bg-warning' : 'bg-brand-gold'}`} aria-hidden="true" />
                    <span>{view.isStale ? 'Stale · data through ' : 'Data through '}</span>
                    <time dateTime={view.representedDate}>
                      {formatFreshnessDate(view.representedDate) || view.representedDate}
                    </time>
                  </p>
                )}
                {view.gameContext && (
                  <p className="type-metadata mt-meta break-words text-text-tertiary" aria-label="Game context">
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

            {evidenceDisclosure && (
              <div className="mt-section border-t border-line-subtle pt-panel">
                {evidenceDisclosure}
              </div>
            )}
          </>
        )}
      </section>
      {!hasError && read && <BullpenSummary read={read} />}
    </>
  )
}
