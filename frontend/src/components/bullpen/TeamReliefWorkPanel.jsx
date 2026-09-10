import SectionState from '../UI/SectionState'
import { SkeletonBlock } from '../UI/Skeleton'
import { formatDateOnly } from '../../utils/dateDisplay'

const asArray = value => Array.isArray(value) ? value : []
const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null
const countValue = value => Number.isInteger(value) && value >= 0 ? value : null

export function formatBaseballIpFromOuts(outs) {
  const value = countValue(outs)
  return value == null ? null : `${Math.floor(value / 3)}.${value % 3}`
}

export function groupGameSections(group) {
  const appearances = asArray(group?.appearances)
  const games = asArray(group?.games)
  const sections = new Map()
  const order = []

  for (const game of games) {
    const gameId = game?.mlb_game_pk
    if (gameId == null || sections.has(gameId)) continue
    sections.set(gameId, { gameId, game, appearances: [] })
    order.push(gameId)
  }

  for (const appearance of appearances) {
    const gameId = appearance?.mlb_game_pk
    const key = gameId == null ? '__unattributed_game__' : gameId
    if (!sections.has(key)) {
      sections.set(key, { gameId, game: null, appearances: [] })
      order.push(key)
    }
    sections.get(key).appearances.push(appearance)
  }

  return order.map(key => sections.get(key)).filter(Boolean)
}

function opponentLabel(section) {
  const appearance = section?.appearances?.[0]
  return textValue(section?.game?.opponent_abbreviation)
    || textValue(section?.game?.opponent)
    || textValue(appearance?.opponent_abbreviation)
    || textValue(appearance?.opponent)
}

function gameLabel(section, multipleGames) {
  const gameNumber = section?.game?.game_number
  const opponent = opponentLabel(section)
  if (section?.gameId == null) {
    return opponent ? `Game context unavailable · vs. ${opponent}` : 'Game context unavailable'
  }
  const labels = []
  if (multipleGames && Number.isInteger(gameNumber)) labels.push(`Game ${gameNumber}`)
  if (multipleGames && !Number.isInteger(gameNumber) && section?.gameId != null) labels.push(`MLB game ${section.gameId}`)
  if (opponent) labels.push(`vs. ${opponent}`)
  if (labels.length > 0) return labels.join(' · ')
  return null
}

export function getReliefLedgerGroups(recentReliefWork) {
  const payload = recentReliefWork?.read
  return asArray(payload?.relief_by_date).map((group, index) => ({
    key: `${textValue(group?.game_date) || 'relief-date'}-${index}`,
    gameDate: textValue(group?.game_date),
    dateLabel: formatDateOnly(group?.game_date, { month: 'short' }),
    summary: textValue(group?.sentence),
    unavailable: group?.unavailable === true || group?.available === false,
    reliefAppearances: countValue(group?.relief_appearances),
    outsTotal: countValue(group?.outs_total),
    pitchesTotal: countValue(group?.pitches_total),
    appearancesWithPitches: countValue(group?.appearances_with_pitches),
    sections: groupGameSections(group),
  }))
}

function ReliefWorkSkeleton() {
  return (
    <section id="team-relief-work" className="foundation-section scroll-mt-24" aria-labelledby="team-relief-work-title" aria-busy="true" tabIndex={-1} data-testid="recent-relief-work-skeleton">
      <h2 id="team-relief-work-title" className="type-section-title">Recent Relief Work</h2>
      <span className="sr-only">Loading recent relief work.</span>

      <div className="mt-row tablet:hidden">
        <SkeletonBlock className="h-12 w-full" />
        {[0, 1, 2].map(index => (
          <div key={index} className="min-h-16 border-b border-line-subtle py-row">
            <SkeletonBlock className="h-5 w-44 max-w-full" />
            <SkeletonBlock className="mt-meta h-4 w-64 max-w-full" />
          </div>
        ))}
      </div>

      <div className="mt-row hidden tablet:block">
        <div className="grid grid-cols-[minmax(12rem,1fr)_repeat(6,minmax(2.75rem,0.3fr))] gap-meta border-b border-line-default px-panel py-row">
          <SkeletonBlock className="h-4 w-20" />
          {[0, 1, 2, 3, 4, 5].map(index => <SkeletonBlock key={index} className="ml-auto h-4 w-7" />)}
        </div>
        <SkeletonBlock className="h-12 w-full" />
        {[0, 1, 2].map(index => (
          <div key={index} className="grid grid-cols-[minmax(12rem,1fr)_repeat(6,minmax(2.75rem,0.3fr))] gap-meta border-b border-line-subtle px-panel py-row">
            <SkeletonBlock className="h-5 w-44 max-w-full" />
            {[0, 1, 2, 3, 4, 5].map(cell => <SkeletonBlock key={cell} className="ml-auto h-5 w-7" />)}
          </div>
        ))}
      </div>
    </section>
  )
}

function PitcherName({ appearance, onSelectPitcher }) {
  const name = textValue(appearance?.pitcher_full_name) || 'Pitcher unavailable'
  const pitcherId = appearance?.pitcher_id
  if (pitcherId == null || typeof onSelectPitcher !== 'function') {
    return <span className="break-words">{name}</span>
  }
  return (
    <button
      type="button"
      className="min-h-11 break-words text-left font-board text-board-body font-semibold text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus"
      onClick={event => onSelectPitcher(pitcherId, event.currentTarget)}
    >
      {name}
    </button>
  )
}

function gameContextView(game) {
  if (game?.reconciled !== true) return null
  if (game?.starter_authority !== 'official_completed_game_starter') return null
  const label = textValue(game?.context_label)
  const sentences = asArray(game?.context_sentences).map(textValue).filter(Boolean)
  if (!label && sentences.length === 0) return null
  return { label, sentences }
}

function GameContextContent({ game }) {
  const context = gameContextView(game)
  if (!context) return null

  return (
    <div className="max-w-reading py-row" data-testid="team-relief-game-context">
      {context.label && <div className="type-overline">{context.label}</div>}
      {context.sentences.map((sentence, index) => (
        <p key={`${sentence}-${index}`} className="type-compact mt-meta">{sentence}</p>
      ))}
    </div>
  )
}

function formatCount(value) {
  return countValue(value) == null ? '—' : value
}

function statusValue(appearance) {
  return textValue(appearance?.roster_status_sentence)
}

function hasUsefulStatus(groups) {
  return groups.some(group => group.sections.some(section => section.appearances.some(appearance => {
    const status = statusValue(appearance)
    return status && status !== 'On the active roster per MLB roster data.'
  })))
}

function DateSummary({ group, headingId }) {
  const innings = formatBaseballIpFromOuts(group.outsTotal)
  const partialPitchCoverage = (
    group.reliefAppearances != null
    && group.appearancesWithPitches != null
    && group.appearancesWithPitches < group.reliefAppearances
  )

  return (
    <>
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-panel gap-y-meta">
        <h3 id={headingId} className="type-data font-semibold text-text-primary">
          {group.gameDate && group.dateLabel
            ? <time dateTime={group.gameDate}>{group.dateLabel}</time>
            : 'Date unavailable'}
        </h3>
        <div className="flex flex-wrap gap-x-panel gap-y-meta type-data">
          <span>{group.reliefAppearances == null ? '—' : group.reliefAppearances} app</span>
          <span>{innings == null ? '—' : innings} IP</span>
          <span>{group.pitchesTotal == null ? '—' : group.pitchesTotal} P</span>
        </div>
      </div>
      {group.summary && <p className="type-metadata mt-meta max-w-reading">{group.summary}</p>}
      {partialPitchCoverage && (
        <p className="type-metadata mt-meta" data-testid="relief-pitch-coverage">
          Pitch coverage: {group.appearancesWithPitches} of {group.reliefAppearances} appearances.
        </p>
      )}
    </>
  )
}

function MobileAppearance({ appearance, onSelectPitcher }) {
  const innings = formatBaseballIpFromOuts(appearance?.innings_pitched_outs)
  return (
    <li className="min-h-16 border-b border-line-subtle py-row last:border-b-0">
      <div className="flex min-w-0 items-start justify-between gap-panel">
        <div className="min-w-0 type-data font-semibold text-text-primary">
          <PitcherName appearance={appearance} onSelectPitcher={onSelectPitcher} />
        </div>
        <div className="shrink-0 type-data text-right text-text-primary">{innings == null ? '—' : innings} IP</div>
      </div>
      <p className="type-data mt-meta flex flex-wrap gap-x-meta gap-y-1 text-text-secondary">
        <span>{formatCount(appearance?.pitches_thrown)} P</span><span aria-hidden="true">·</span>
        <span>{formatCount(appearance?.strikeouts)} K</span><span aria-hidden="true">·</span>
        <span>{formatCount(appearance?.walks)} BB</span><span aria-hidden="true">·</span>
        <span>{formatCount(appearance?.hits_allowed)} H</span><span aria-hidden="true">·</span>
        <span>{formatCount(appearance?.runs_allowed)} R</span>
      </p>
    </li>
  )
}

function MobileGameGroup({ section, multipleGames, groupKey, sectionIndex, onSelectPitcher }) {
  const label = gameLabel(section, multipleGames)
  const showGameRow = multipleGames || section?.gameId == null
  const headingId = `${groupKey}-mobile-game-${sectionIndex}`
  return (
    <section aria-labelledby={showGameRow ? headingId : undefined}>
      {showGameRow && (
        <h4 id={headingId} className="type-overline border-b border-line-subtle py-row">
          {label || 'Game context unavailable'}
        </h4>
      )}
      <GameContextContent game={section?.game} />
      {section.appearances.length > 0 && (
        <ul aria-label={`${label || 'Relief'} appearances`}>
          {section.appearances.map((appearance, index) => (
            <MobileAppearance
              key={`${appearance?.pitcher_id ?? 'pitcher'}-${appearance?.mlb_game_pk ?? 'ungrouped'}-${index}`}
              appearance={appearance}
              onSelectPitcher={onSelectPitcher}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

function MobileLedger({ groups, onSelectPitcher }) {
  return (
    <div className="tablet:hidden" aria-label="Recent relief work records">
      {groups.map(group => (
        <section key={group.key} className="border-b border-line-default last:border-b-0" aria-labelledby={`${group.key}-mobile-title`}>
          <header className="bg-surface-raised px-panel py-row">
            <DateSummary group={group} headingId={`${group.key}-mobile-title`} />
          </header>
          {group.unavailable ? (
            <SectionState status="unavailable" title="Game relief work unavailable" message={group.summary || 'This game group did not reconcile with its appearance records.'} className="my-row" />
          ) : group.sections.map((section, sectionIndex) => (
            <MobileGameGroup
              key={`${group.key}-${section?.gameId ?? 'ungrouped'}-${sectionIndex}`}
              section={section}
              multipleGames={group.sections.length > 1}
              groupKey={group.key}
              sectionIndex={sectionIndex}
              onSelectPitcher={onSelectPitcher}
            />
          ))}
        </section>
      ))}
    </div>
  )
}

function TableAppearanceRow({ appearance, showStatusColumn, onSelectPitcher }) {
  const innings = formatBaseballIpFromOuts(appearance?.innings_pitched_outs)
  return (
    <tr className="border-b border-line-subtle last:border-b-0">
      <th scope="row" className="min-w-0 py-row pr-panel text-left type-data font-semibold text-text-primary">
        <PitcherName appearance={appearance} onSelectPitcher={onSelectPitcher} />
      </th>
      <td className="px-meta py-row text-right type-data text-text-primary">{innings == null ? '—' : innings}</td>
      <td className="px-meta py-row text-right type-data text-text-primary">{formatCount(appearance?.pitches_thrown)}</td>
      <td className="px-meta py-row text-right type-data text-text-primary">{formatCount(appearance?.strikeouts)}</td>
      <td className="px-meta py-row text-right type-data text-text-primary">{formatCount(appearance?.walks)}</td>
      <td className="px-meta py-row text-right type-data text-text-primary">{formatCount(appearance?.hits_allowed)}</td>
      <td className="py-row pl-meta pr-panel text-right type-data text-text-primary">{formatCount(appearance?.runs_allowed)}</td>
      {showStatusColumn && <td className="hidden min-w-52 py-row pl-panel type-metadata lg:table-cell">{statusValue(appearance) || '—'}</td>}
    </tr>
  )
}

function TableGameRows({ section, multipleGames, groupKey, sectionIndex, showStatusColumn, onSelectPitcher }) {
  const label = gameLabel(section, multipleGames)
  const showGameRow = multipleGames || section?.gameId == null
  const showGameContext = gameContextView(section?.game) != null
  const columnCount = showStatusColumn ? 8 : 7
  return (
    <>
      {showGameRow && (
        <tr className="border-b border-line-subtle">
          <th scope="rowgroup" colSpan={columnCount} className="py-row text-left type-overline" id={`${groupKey}-table-game-${sectionIndex}`}>
            {label || 'Game context unavailable'}
          </th>
        </tr>
      )}
      {showGameContext && (
        <tr className="border-b border-line-subtle">
          <td colSpan={columnCount}><GameContextContent game={section.game} /></td>
        </tr>
      )}
      {section.appearances.map((appearance, index) => (
        <TableAppearanceRow
          key={`${appearance?.pitcher_id ?? 'pitcher'}-${appearance?.mlb_game_pk ?? 'ungrouped'}-${index}`}
          appearance={appearance}
          showStatusColumn={showStatusColumn}
          onSelectPitcher={onSelectPitcher}
        />
      ))}
    </>
  )
}

function TableLedger({ groups, showStatusColumn, onSelectPitcher }) {
  const columnCount = showStatusColumn ? 8 : 7
  return (
    <table className="hidden w-full table-fixed border-collapse tablet:table" aria-label="Recent relief work table">
      <colgroup>
        <col className={showStatusColumn ? 'w-[28%]' : 'w-[34%]'} />
        <col className={showStatusColumn ? 'w-[8%]' : 'w-[11%]'} />
        <col className={showStatusColumn ? 'w-[8%]' : 'w-[11%]'} />
        <col className={showStatusColumn ? 'w-[8%]' : 'w-[11%]'} />
        <col className={showStatusColumn ? 'w-[8%]' : 'w-[11%]'} />
        <col className={showStatusColumn ? 'w-[8%]' : 'w-[11%]'} />
        <col className={showStatusColumn ? 'w-[8%]' : 'w-[11%]'} />
        {showStatusColumn && <col className="hidden lg:table-column lg:w-[24%]" />}
      </colgroup>
      <thead className="sticky top-0 z-10 bg-surface-base">
        <tr className="border-b border-line-default">
          <th scope="col" className="py-row pr-panel text-left type-overline">Arm</th>
          {['IP', 'P', 'K', 'BB', 'H', 'R'].map(label => (
            <th key={label} scope="col" className={label === 'R' ? 'py-row pl-meta pr-panel text-right type-overline' : 'px-meta py-row text-right type-overline'}>{label}</th>
          ))}
          {showStatusColumn && <th scope="col" className="hidden py-row pl-panel text-left type-overline lg:table-cell">Status</th>}
        </tr>
      </thead>
      {groups.map(group => (
        <tbody key={group.key} aria-labelledby={`${group.key}-table-title`}>
          <tr className="bg-surface-raised">
            <th colSpan={columnCount} scope="rowgroup" className="px-panel py-row text-left" id={`${group.key}-table-title`}>
              <DateSummary group={group} headingId={`${group.key}-table-heading`} />
            </th>
          </tr>
          {group.unavailable ? (
            <tr>
              <td colSpan={columnCount} className="py-row">
                <SectionState status="unavailable" title="Game relief work unavailable" message={group.summary || 'This game group did not reconcile with its appearance records.'} />
              </td>
            </tr>
          ) : group.sections.map((section, sectionIndex) => (
            <TableGameRows
              key={`${group.key}-${section?.gameId ?? 'ungrouped'}-${sectionIndex}`}
              section={section}
              multipleGames={group.sections.length > 1}
              groupKey={group.key}
              sectionIndex={sectionIndex}
              showStatusColumn={showStatusColumn}
              onSelectPitcher={onSelectPitcher}
            />
          ))}
        </tbody>
      ))}
    </table>
  )
}

function firstLimitation(status, payload) {
  return [
    ...asArray(status?.limitations),
    textValue(payload?.unattributed_sentence),
  ].map(textValue).find(Boolean) || null
}

export default function TeamReliefWorkPanel({ read, loading = false, error = null, onRetry, onSelectPitcher }) {
  if (loading) return <ReliefWorkSkeleton />

  const recentReliefWork = read?.recentReliefWork
  const payload = recentReliefWork?.read
  const status = read?.sectionStatus?.recent_relief_work
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const groups = getReliefLedgerGroups(recentReliefWork)
  const limitation = firstLimitation(status, payload)
  const representedDate = textValue(payload?.data_through) || textValue(status?.represented_date)
  const showStatusColumn = hasUsefulStatus(groups)

  return (
    <section id="team-relief-work" className="foundation-section scroll-mt-24 focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus" aria-labelledby="team-relief-work-title" tabIndex={-1} data-testid="team-board-recent-relief-work">
      <header className="mb-row flex min-w-0 flex-wrap items-end justify-between gap-meta">
        <div className="min-w-0">
          <h2 id="team-relief-work-title" className="type-section-title">Recent Relief Work</h2>
          {textValue(payload?.scope_sentence) && <p className="type-compact mt-meta max-w-reading">{payload.scope_sentence}</p>}
        </div>
        {representedDate && (
          <p className="type-metadata">Through <time dateTime={representedDate}>{formatDateOnly(representedDate, { month: 'short' })}</time></p>
        )}
      </header>

      {error ? (
        <SectionState status="error" title="Recent Relief Work unavailable" message="Recent relief-work records could not be loaded." onRetry={onRetry} />
      ) : !read || !recentReliefWork || !payload || statusName === 'unavailable' ? (
        <SectionState status="unavailable" title="Recent Relief Work unavailable" message="Official recent relief-work records are unavailable." onRetry={!read ? onRetry : undefined} />
      ) : (
        <>
          {groups.length > 0 && (
            <div aria-label="Recent relief work by game date">
              <MobileLedger groups={groups} onSelectPitcher={onSelectPitcher} />
              <TableLedger groups={groups} showStatusColumn={showStatusColumn} onSelectPitcher={onSelectPitcher} />
            </div>
          )}

          {statusName === 'partial' && (
            <SectionState status="partial" title="Recent Relief Work is partially available" message={limitation || 'Some official relief-work records are unavailable or unattributed.'} className={groups.length > 0 ? 'mt-row' : ''} />
          )}
          {statusName === 'available' && groups.length === 0 && (
            <div className="section-state" role="status" data-state="empty">
              <h3 className="type-section-title">No recent relief work</h3>
              <p className="type-compact mt-meta">{textValue(payload?.absence_sentence) || 'The governed recent relief-work population is empty.'}</p>
            </div>
          )}
        </>
      )}
    </section>
  )
}
