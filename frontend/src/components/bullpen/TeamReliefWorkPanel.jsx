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

function gameSections(group) {
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

  const soleGameId = order.length === 1 ? order[0] : null
  for (const appearance of appearances) {
    const suppliedGameId = appearance?.mlb_game_pk
    const gameId = suppliedGameId == null ? soleGameId : suppliedGameId
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
  const labels = []
  if (multipleGames && Number.isInteger(gameNumber)) labels.push(`Game ${gameNumber}`)
  if (opponent) labels.push(`vs. ${opponent}`)
  return labels.join(' · ') || (multipleGames ? 'Game context unavailable' : null)
}

export function getReliefLedgerGroups(recentReliefWork) {
  const payload = recentReliefWork?.read
  return asArray(payload?.relief_by_date).map((group, index) => ({
    key: `${textValue(group?.game_date) || 'relief-date'}-${index}`,
    gameDate: textValue(group?.game_date),
    dateLabel: formatDateOnly(group?.game_date, { month: 'short' }),
    summary: textValue(group?.sentence),
    unavailable: group?.unavailable === true || group?.available === false,
    sections: gameSections(group),
  }))
}

function ReliefWorkSkeleton() {
  return (
    <section id="team-relief-work" className="foundation-section scroll-mt-24" aria-labelledby="team-relief-work-title" aria-busy="true" tabIndex={-1} data-testid="recent-relief-work-skeleton">
      <h2 id="team-relief-work-title" className="type-section-title">Recent Relief Work</h2>
      <span className="sr-only">Loading recent relief work.</span>
      <div className="mt-row border-y border-dirt">
        {[0, 1].map(index => (
          <div key={index} className="border-b border-dirt px-panel py-row last:border-b-0">
            <SkeletonBlock className="h-5 w-40 max-w-full" />
            <div className="mt-row grid gap-row tablet:grid-cols-[minmax(12rem,1.5fr)_minmax(9rem,1fr)_minmax(8rem,0.8fr)]">
              <SkeletonBlock className="h-5 w-48 max-w-full" />
              <SkeletonBlock className="h-4 w-28 max-w-full" />
              <SkeletonBlock className="h-4 w-24 max-w-full" />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function GameContext({ game }) {
  if (game?.reconciled !== true) return null
  if (game?.starter_authority !== 'official_completed_game_starter') return null
  const label = textValue(game?.context_label)
  const sentences = asArray(game?.context_sentences).map(textValue).filter(Boolean)
  if (!label && sentences.length === 0) return null

  return (
    <div className="border-t border-dirt px-panel py-row" data-testid="team-relief-game-context">
      {label && <div className="type-overline text-amber/80">{label}</div>}
      {sentences.map((sentence, index) => (
        <p key={`${sentence}-${index}`} className="type-compact mt-meta text-chalk300">{sentence}</p>
      ))}
    </div>
  )
}

function AppearanceRow({ appearance }) {
  const outs = countValue(appearance?.innings_pitched_outs)
  const innings = formatBaseballIpFromOuts(outs)
  const pitches = countValue(appearance?.pitches_thrown)
  const name = textValue(appearance?.pitcher_full_name) || 'Pitcher unavailable'

  return (
    <li className="grid min-w-0 gap-row border-t border-dirt px-panel py-row tablet:grid-cols-[minmax(12rem,1.5fr)_minmax(9rem,1fr)_minmax(8rem,0.8fr)] tablet:items-center">
      <div className="min-w-0">
        <h4 className="type-data break-words text-chalk100">{name}</h4>
      </div>
      <div className="min-w-0">
        <div className="type-overline">Recorded</div>
        <div className="type-data mt-meta">
          {outs == null ? 'Outs unavailable' : `${outs} ${outs === 1 ? 'out' : 'outs'} · ${innings} IP`}
        </div>
      </div>
      <div className="min-w-0">
        <div className="type-overline">Pitches</div>
        <div className="type-data mt-meta">{pitches == null ? 'Unavailable' : pitches}</div>
      </div>
    </li>
  )
}

function GameGroup({ section, multipleGames, groupKey, sectionIndex }) {
  const label = gameLabel(section, multipleGames)
  const heading = label || 'Relief appearances'
  const appearances = asArray(section?.appearances)

  return (
    <section aria-labelledby={`${groupKey}-game-${sectionIndex}`}>
      <h3 id={`${groupKey}-game-${sectionIndex}`} className="type-overline border-t border-dirt bg-dugout/35 px-panel py-row text-chalk400">
        {heading}
      </h3>
      <GameContext game={section?.game} />
      {appearances.length > 0 && (
        <ul aria-label={`${heading} relief appearances`}>
          {appearances.map((appearance, index) => (
            <AppearanceRow key={`${appearance?.pitcher_id ?? 'pitcher'}-${appearance?.mlb_game_pk ?? 'game'}-${index}`} appearance={appearance} />
          ))}
        </ul>
      )}
    </section>
  )
}

function firstLimitation(status, payload) {
  return [
    ...asArray(status?.limitations),
    textValue(payload?.unattributed_sentence),
  ].map(textValue).find(Boolean) || null
}

export default function TeamReliefWorkPanel({ read, loading = false, error = null, onRetry }) {
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

  return (
    <section id="team-relief-work" className="foundation-section scroll-mt-24 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/50" aria-labelledby="team-relief-work-title" tabIndex={-1} data-testid="team-board-recent-relief-work">
      <header className="mb-row flex min-w-0 flex-wrap items-end justify-between gap-meta">
        <div className="min-w-0">
          <h2 id="team-relief-work-title" className="type-section-title">Recent Relief Work</h2>
          {textValue(payload?.scope_sentence) && <p className="type-compact mt-meta max-w-3xl text-chalk300">{payload.scope_sentence}</p>}
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
            <div className="border-y border-dirt" aria-label="Recent relief work by game date">
              {groups.map(group => (
                <section key={group.key} className="border-b border-dirt last:border-b-0" aria-labelledby={`${group.key}-title`}>
                  <header className="px-panel py-row">
                    <h3 id={`${group.key}-title`} className="type-data text-chalk100">
                      {group.gameDate && group.dateLabel
                        ? <time dateTime={group.gameDate}>{group.dateLabel}</time>
                        : 'Date unavailable'}
                    </h3>
                    {group.summary && <p className="type-metadata mt-meta">{group.summary}</p>}
                  </header>
                  {group.unavailable ? (
                    <SectionState status="unavailable" title="Game relief work unavailable" message={group.summary || 'This game group did not reconcile with its appearance records.'} className="m-panel mt-0" />
                  ) : group.sections.length > 0 ? (
                    group.sections.map((section, sectionIndex) => (
                      <GameGroup key={`${group.key}-${section?.gameId ?? sectionIndex}`} section={section} multipleGames={group.sections.length > 1} groupKey={group.key} sectionIndex={sectionIndex} />
                    ))
                  ) : null}
                </section>
              ))}
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
