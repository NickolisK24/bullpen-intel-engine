import SectionState from '../../UI/SectionState'
import ActiveArmRow, { ActiveArmRowSkeleton } from './ActiveArmRow'

const READ_TONES = Object.freeze({
  clean_option: 'neutral',
  watch_arm: 'watch',
  rest_restricted: 'limited',
  unavailable: 'withheld',
  limited_read: 'withheld',
})

const READ_MARKERS = Object.freeze({
  clean_option: 'dot',
  watch_arm: 'dot',
  rest_restricted: 'dot',
  unavailable: 'square',
  limited_read: 'ring',
})

function textValue(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function countValue(value) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null
}

function readPresentation(arm) {
  const key = textValue(arm?.public_labels?.read?.key)?.toLowerCase()
  return {
    tone: READ_TONES[key] || 'withheld',
    marker: READ_MARKERS[key] || 'ring',
  }
}

const patterns = [
  ['backToBack', 'B2B'], ['threeStraight', '3 straight'], ['threeInFour', '3-in-4'], ['fourInSix', '4-in-6'],
  ['recentMultiInning', 'Multi-inning'], ['highPitchOuting', '25+ pitches'],
]

function armPatterns(arm, usage) {
  if (arm.arm_context?.mode !== 'current') return null
  if (!usage) return arm.workload?.back_to_back === true ? 'B2B' : null
  if (!['partial', 'complete'].includes(usage.status)) return null
  const matches = usage.activePitchers.filter(row => row.pitcherId === arm.pitcher_id)
  if (matches.length !== 1 || matches[0].rosterState !== 'active') return null
  return patterns.filter(([key]) => matches[0][key]?.status === 'complete' && matches[0][key].value === true)
    .map(([, label]) => label).join(' · ') || null
}

export function getActiveBullpenRows(activeBullpen, usage) {
  const arms = Array.isArray(activeBullpen?.arms) ? activeBullpen.arms : []
  return arms.map(arm => {
    const workload = arm?.workload || {}
    const lastAppearance = arm?.last_appearance || {}
    const lastGamePitches = countValue(lastAppearance.pitches)
    const appearancesLast7 = countValue(workload.appearances_last_7)
    const pitchesLast7 = countValue(workload.pitches_last_7_days)
    const roleKey = textValue(arm?.public_role_read?.key) || textValue(arm?.public_labels?.role?.key)
    const current = arm?.arm_context?.mode === 'current'
    const read = readPresentation(current ? arm : null)

    return {
      pitcherId: countValue(arm?.pitcher_id),
      name: textValue(arm?.name) || 'Reliever',
      roleLabel: textValue(arm?.public_role_read?.label) || textValue(arm?.public_labels?.role?.label),
      roleWithheld: roleKey === 'limited_read',
      readLabel: current
        ? textValue(arm?.public_labels?.read?.label) || textValue(arm?.availability?.label)
        : 'Current read withheld',
      recordedAppearance: !current ? textValue(lastAppearance.game_date || lastAppearance.date) : null,
      readTone: read.tone,
      readMarker: read.marker,
      daysSince: current ? countValue(arm.arm_context.days_rest) : null,
      lastGamePitches,
      appearancesLast7,
      pitchesLast7,
      pattern: armPatterns(arm, usage),
    }
  })
}

function TableHeader({ showLastGamePitches }) {
  return (
    <div className={`active-arm-table__header ${showLastGamePitches ? 'active-arm-row--with-last-p' : ''}`} aria-hidden="true">
      <span>Arm</span>
      <span className="active-arm-table__read">Read</span>
      <span className="text-right">Last / Rest</span>
      {showLastGamePitches && <span className="active-arm-table__last-p text-right">Last P</span>}
      <span className="text-right">7d App</span>
      <span className="text-right">7d P</span>
      <span className="active-arm-table__pattern">Pattern</span>
      <span className="active-arm-table__destination text-right">Destination</span>
    </div>
  )
}

function firstLimitation(status) {
  return Array.isArray(status?.limitations)
    ? status.limitations.find(item => textValue(item))?.trim() || null
    : null
}

function ActiveBullpenHeader({ teamName, through }) {
  return (
    <header className="mb-panel border-b border-line-default pb-panel tablet:flex tablet:min-w-0 tablet:items-end tablet:justify-between tablet:gap-section">
      <div className="min-w-0">
        <h2 id="active-bullpen-title" className="mt-meta font-board text-xl font-semibold leading-tight text-text-primary tablet:text-2xl">
          Active Bullpen
          {teamName ? <span className="sr-only"> — {teamName}</span> : null}
        </h2>
        <p className="type-compact mt-meta max-w-reading">
          Observed roles and workload{through ? ` through ${through}` : ''}.
        </p>
      </div>
    </header>
  )
}

export function ActiveBullpenSkeleton() {
  return (
    <section
      id="pitcher-lanes"
      className="foundation-section scroll-mt-24 border-t border-line-strong pt-section-lg"
      aria-labelledby="active-bullpen-title"
      aria-busy="true"
      data-testid="active-bullpen-skeleton"
    >
      <ActiveBullpenHeader />
      <span className="sr-only">Loading the active bullpen.</span>
      <div className="overflow-hidden rounded-sm border border-line-default bg-surface-raised/25 px-panel">
        {[0, 1, 2].map(index => <ActiveArmRowSkeleton key={index} />)}
      </div>
    </section>
  )
}

export default function TeamBoardActiveBullpen({
  read,
  loading = false,
  error = null,
  onRetry,
  onSelectPitcher,
}) {
  if (loading) return <ActiveBullpenSkeleton />

  const activeBullpen = read?.activeBullpen
  const status = read?.sectionStatus?.active_bullpen
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const rows = getActiveBullpenRows(activeBullpen, read?.recentUsageRest)
  const showLastGamePitches = rows.some(row => row.lastGamePitches != null)
  const limitation = firstLimitation(status)
  const hasError = Boolean(error)
  const teamName = textValue(read?.team?.team_name) || textValue(read?.team?.team_abbreviation)

  return (
    <section
      id="pitcher-lanes"
      tabIndex={-1}
      className="foundation-section scroll-mt-24 border-t border-line-strong pt-section-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-signal/70"
      aria-labelledby="active-bullpen-title"
      data-testid="team-board-active-bullpen"
    >
      <ActiveBullpenHeader teamName={teamName} through={read?.freshness?.data_through} />

      {hasError ? (
        <SectionState
          status="error"
          title="Active Bullpen unavailable"
          message="The current Active Bullpen could not be loaded."
          onRetry={onRetry}
        />
      ) : !read || !activeBullpen ? (
        <SectionState
          status="unavailable"
          title="Active Bullpen unavailable"
          message="A current Active Bullpen population is not available."
          onRetry={onRetry}
        />
      ) : (
        <>
          {rows.length > 0 && (
            <div className="active-arm-table overflow-hidden rounded-sm border border-line-default bg-surface-raised/20 px-panel tablet:px-section">
              <TableHeader showLastGamePitches={showLastGamePitches} />
              <div role="list" aria-label="Active bullpen pitchers">
                {rows.map((row, index) => (
                  <div key={row.pitcherId ?? `${row.name}-${index}`} role="listitem">
                    <ActiveArmRow
                      pitcherId={row.pitcherId}
                      name={row.name}
                      roleLabel={row.roleLabel}
                      roleWithheld={row.roleWithheld}
                      readLabel={row.readLabel}
                      partialMessage={row.recordedAppearance ? `Last appearance · ${row.recordedAppearance}` : null}
                      readTone={row.readTone}
                      readMarker={row.readMarker}
                      daysSince={row.daysSince}
                      lastGamePitches={row.lastGamePitches}
                      appearancesLast7={row.appearancesLast7}
                      pitchesLast7={row.pitchesLast7}
                      pattern={row.pattern}
                      showLastGamePitches={showLastGamePitches}
                      onAction={row.pitcherId != null && typeof onSelectPitcher === 'function'
                        ? event => onSelectPitcher(row.pitcherId, event.currentTarget)
                        : null}
                      actionAriaLabel={`Open pitcher context for ${row.name}`}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {statusName === 'partial' && (
            <SectionState
              status="partial"
              title="Active Bullpen is partially available"
              message={limitation || 'Some active bullpen evidence is unavailable.'}
              className={rows.length > 0 ? 'mt-row' : ''}
            />
          )}
          {statusName === 'unavailable' && (
            <SectionState
              status="unavailable"
              title="Active Bullpen unavailable"
              message={limitation || 'The active bullpen population is unavailable.'}
              className={rows.length > 0 ? 'mt-row' : ''}
            />
          )}
          {statusName === 'available' && rows.length === 0 && (
            <SectionState
              status="unavailable"
              title="No active bullpen arms"
              message="The current active-bullpen population is empty."
            />
          )}
        </>
      )}
    </section>
  )
}
