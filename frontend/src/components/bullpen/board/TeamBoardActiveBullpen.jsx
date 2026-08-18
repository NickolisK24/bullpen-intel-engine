import SectionState from '../../UI/SectionState'
import ActiveArmRow, { ActiveArmRowSkeleton } from './ActiveArmRow'

const READ_TONES = Object.freeze({
  clean_option: 'available',
  watch_arm: 'watch',
  rest_restricted: 'limited',
  unavailable: 'unavailable',
})

function textValue(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function countValue(value) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null
}

function formatDaysSince(value) {
  const days = countValue(value)
  if (days == null) return null
  if (days === 0) return 'Today'
  return `${days} day${days === 1 ? '' : 's'} ago`
}

function readTone(arm) {
  const key = textValue(arm?.public_labels?.read?.key)?.toLowerCase()
  return READ_TONES[key] || 'neutral'
}

export function getActiveBullpenRows(activeBullpen) {
  const arms = Array.isArray(activeBullpen?.arms) ? activeBullpen.arms : []
  return arms.map(arm => {
    const workload = arm?.workload || {}
    const lastAppearance = arm?.last_appearance || {}
    const lastGamePitches = countValue(lastAppearance.pitches)
    const appearancesLast7 = countValue(workload.appearances_last_7)
    const pitchesLast7 = countValue(workload.pitches_last_7_days)
    const facts = [
      { label: 'Last Used', value: formatDaysSince(workload.days_since_last_appearance) },
      { label: 'Last Game', value: lastGamePitches == null ? null : `${lastGamePitches} pitches` },
      { label: '7D App', value: appearancesLast7 },
      { label: '7D Pitches', value: pitchesLast7 },
      { label: 'Pattern', value: workload.back_to_back === true ? 'Back-to-back' : null },
    ].filter(fact => fact.value != null)

    return {
      pitcherId: countValue(arm?.pitcher_id),
      name: textValue(arm?.name) || 'Reliever',
      roleLabel: textValue(arm?.public_role_read?.label) || textValue(arm?.public_labels?.role?.label),
      readLabel: textValue(arm?.public_labels?.read?.label) || textValue(arm?.availability?.label),
      readTone: readTone(arm),
      facts,
    }
  })
}

function firstLimitation(status) {
  return Array.isArray(status?.limitations)
    ? status.limitations.find(item => textValue(item))?.trim() || null
    : null
}

export function ActiveBullpenSkeleton() {
  return (
    <section
      id="pitcher-lanes"
      className="foundation-section scroll-mt-24"
      aria-labelledby="active-bullpen-title"
      aria-busy="true"
      data-testid="active-bullpen-skeleton"
    >
      <h2 id="active-bullpen-title" className="type-section-title">Active Bullpen</h2>
      <span className="sr-only">Loading the active bullpen.</span>
      <div className="mt-row border-y border-dirt">
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
  const rows = getActiveBullpenRows(activeBullpen)
  const limitation = firstLimitation(status)
  const hasError = Boolean(error)
  const teamName = textValue(read?.team?.team_name) || textValue(read?.team?.team_abbreviation)

  return (
    <section
      id="pitcher-lanes"
      tabIndex={-1}
      className="foundation-section scroll-mt-24 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal/70"
      aria-labelledby="active-bullpen-title"
      data-testid="team-board-active-bullpen"
    >
      <header className="mb-row flex min-w-0 flex-wrap items-end justify-between gap-meta">
        <h2 id="active-bullpen-title" className="type-section-title">
          Active Bullpen
          {teamName ? <span className="sr-only"> — {teamName}</span> : null}
        </h2>
        {activeBullpen?.population_basis && (
          <p className="type-metadata">Current visible active-bullpen population</p>
        )}
      </header>

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
            <div className="border-y border-dirt" role="list" aria-label="Active bullpen pitchers">
              {rows.map((row, index) => (
                <div key={row.pitcherId ?? `${row.name}-${index}`} role="listitem">
                  <ActiveArmRow
                    name={row.name}
                    roleLabel={row.roleLabel}
                    readLabel={row.readLabel}
                    readTone={row.readTone}
                    facts={row.facts}
                    onAction={row.pitcherId != null && typeof onSelectPitcher === 'function'
                      ? () => onSelectPitcher(row.pitcherId)
                      : null}
                    actionLabel="Open pitcher"
                    actionAriaLabel={`Open pitcher context for ${row.name}`}
                  />
                </div>
              ))}
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
