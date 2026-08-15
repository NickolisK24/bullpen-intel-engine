import { useFetch } from '../../hooks/useFetch'
import { getTeamReliefWork } from '../../utils/api'

const asArray = (value) => (Array.isArray(value) ? value : [])
const isFilled = (value) => value !== undefined && value !== null && value !== ''
const textValue = (value) => (typeof value === 'string' && value.trim() ? value : null)

function Section({ title, children, compact = false }) {
  return (
    <section className={`rounded border border-dirt bg-field/45 ${compact ? 'p-2.5' : 'p-3'}`}>
      <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">{title}</div>
      <div className={`mt-2 ${compact ? 'space-y-1.5' : 'space-y-2'}`}>{children}</div>
    </section>
  )
}

function Sentence({ children }) {
  if (!textValue(children)) return null
  return <p className="font-mono text-sm leading-relaxed text-chalk200">{children}</p>
}

// The server-authored currency sentence stays visible verbatim, but as a
// quiet metadata line instead of its own bordered panel, so it supports the
// workload sections below it without competing at equal visual weight.
function DataCurrency({ payload, hideRoutine = false }) {
  const freshness = payload?.freshness || {}
  const label = textValue(payload?.freshness?.label)
  if (!label) return null
  const state = String(freshness.freshness_state || freshness.state || '').trim().toLowerCase()
  const exceptional = freshness.is_current === false || freshness.is_stale === true || freshness.fail_closed === true || (state && state !== 'current')
  if (hideRoutine && !exceptional) return null

  return (
    <p className="text-[11px] leading-snug text-chalk500">
      <span className="font-mono text-[10px] uppercase tracking-wider text-chalk600">
        Data Currency:
      </span>{' '}
      {label}
    </p>
  )
}

const displayValue = (value) => (value === undefined || value === null || value === '' ? '--' : value)

export function formatBaseballIpFromOuts(outs) {
  if (!Number.isFinite(outs)) return '--'
  return `${Math.floor(outs / 3)}.${outs % 3}`
}

function inningsValue(appearance) {
  if (Number.isFinite(appearance?.innings_pitched_outs)) {
    return formatBaseballIpFromOuts(appearance.innings_pitched_outs)
  }

  if (!isFilled(appearance?.innings_pitched)) return '--'
  const numericInnings = Number(appearance.innings_pitched)
  if (!Number.isFinite(numericInnings)) return String(appearance.innings_pitched)

  const rawText = String(appearance.innings_pitched)
  if (/^\d+\.[012]$/.test(rawText)) return rawText

  return formatBaseballIpFromOuts(Math.round(numericInnings * 3))
}

function DateSummary({ children }) {
  if (!textValue(children)) return null
  return <span className="font-mono text-sm leading-snug text-chalk100">{children}</span>
}

function AppearanceRow({ appearance, rosterContextLimited = false }) {
  const status = rosterContextLimited ? null : textValue(appearance?.roster_status_sentence)
  return (
    <li
      className="grid gap-1.5 px-2 py-1.5 text-xs text-chalk300 sm:grid-cols-[minmax(9rem,1.5fr)_repeat(6,minmax(2.25rem,auto))_minmax(8rem,1fr)] sm:items-center"
      title={textValue(appearance?.sentence) || undefined}
    >
      <span className="font-mono text-chalk200">{displayValue(appearance?.pitcher_full_name)}</span>
      <span className="font-mono"><span className="text-chalk600">IP </span>{inningsValue(appearance)}</span>
      <span className="font-mono"><span className="text-chalk600">P </span>{displayValue(appearance?.pitches_thrown)}</span>
      <span className="font-mono"><span className="text-chalk600">K </span>{displayValue(appearance?.strikeouts)}</span>
      <span className="font-mono"><span className="text-chalk600">BB </span>{displayValue(appearance?.walks)}</span>
      <span className="font-mono"><span className="text-chalk600">H </span>{displayValue(appearance?.hits_allowed)}</span>
      <span className="font-mono"><span className="text-chalk600">R </span>{displayValue(appearance?.runs_allowed)}</span>
      {status && (
        <span className="font-mono text-[11px] leading-snug text-chalk500 sm:text-right">
          {status}
        </span>
      )}
    </li>
  )
}

// A game-level note is a starter-dependent claim. It renders only when the
// backend has affirmatively marked it reconciled against official starter
// authority; the frontend never infers starter or reliever meaning itself.
function GameContextNote({ game }) {
  if (game?.reconciled !== true) return null
  if (game?.starter_authority !== 'official_completed_game_starter') return null
  const label = textValue(game?.context_label)
  if (!label) return null
  const sentences = asArray(game?.context_sentences).filter((sentence) => textValue(sentence))

  return (
    <div
      className="space-y-1 border-t border-dirt/60 bg-chalk/25 px-3 py-2"
      data-testid="team-relief-game-context"
    >
      <div className="font-mono text-[10px] uppercase tracking-wider text-amber/80">{label}</div>
      {sentences.map((sentence, index) => (
        <Sentence key={`${sentence}:${index}`}>{sentence}</Sentence>
      ))}
    </div>
  )
}

// Split a date's appearance rows into game-scoped sections so a game-level
// narrative can never sit above another game's rows. Grouping uses the
// mlb_game_pk the server stamps on every row and on every game block; the
// frontend derives no baseball meaning of its own. Section order follows the
// server's already-ordered games (official MLB game number, then game_pk), and
// any game that has rows but no published narrative keeps its own section
// rather than being folded into a sibling.
function groupGameSections(group) {
  const appearances = asArray(group?.appearances)
  const blocks = asArray(group?.games)
  const rowsByGame = new Map()
  const order = []

  for (const block of blocks) {
    const pk = block?.mlb_game_pk
    if (pk === undefined || pk === null || rowsByGame.has(pk)) continue
    rowsByGame.set(pk, { key: String(pk), gamePk: pk, game: block, rows: [] })
    order.push(pk)
  }
  // A row that carries no game id cannot be split out on its own when this
  // date has exactly one published game — that would invent a second game.
  // With two or more games it stays separate and is disclosed, never guessed
  // into one of them.
  const soleGamePk = order.length === 1 ? order[0] : null

  for (const appearance of appearances) {
    const rawPk = appearance?.mlb_game_pk
    const pk = rawPk === undefined || rawPk === null ? soleGamePk : rawPk
    const key = pk === undefined || pk === null ? '__ungrouped__' : pk
    if (!rowsByGame.has(key)) {
      rowsByGame.set(key, {
        key: String(key),
        gamePk: pk ?? null,
        game: null,
        rows: [],
      })
      order.push(key)
    }
    rowsByGame.get(key).rows.push(appearance)
  }

  return order
    .map((key) => rowsByGame.get(key))
    .filter((section) => section && (section.rows.length > 0 || section.game))
}

// Label authority, strongest first: MLB's own gameNumber from the schedule
// ledger, then the official opponent. A position in the list is never promoted
// into a "Game 1 / Game 2" claim, and the raw game_pk stays metadata.
function gameSectionLabel(section) {
  const number = section?.game?.game_number
  if (Number.isInteger(number)) return `Game ${number}`
  const opponent = textValue(section?.game?.opponent_abbreviation)
    || textValue(section?.game?.opponent)
  if (opponent) return `vs ${opponent}`
  return 'Game'
}

function GameSection({ section, multiGame, rosterContextLimited }) {
  const rows = asArray(section?.rows)
  const hasNarrative = Boolean(section?.game)
  // A game with rows but no published narrative says so plainly instead of
  // silently inheriting the sibling game's meaning.
  const disclosure = multiGame && !hasNarrative && rows.length > 0

  return (
    <div
      className="border-t border-dirt/60"
      data-testid="team-relief-game-section"
      data-game-pk={section?.gamePk ?? undefined}
    >
      {multiGame && (
        <div
          className="bg-dugout/40 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-chalk500"
          data-testid="team-relief-game-label"
        >
          {gameSectionLabel(section)}
        </div>
      )}
      {hasNarrative && <GameContextNote game={section.game} />}
      {disclosure && (
        <Sentence>Game context for this game is unavailable.</Sentence>
      )}
      {rows.length > 0 && (
        <ul className="divide-y divide-dirt/60 border-t border-dirt/60">
          {rows.map((appearance, index) => (
            <AppearanceRow
              key={`${appearance?.pitcher_id || 'pitcher'}:${appearance?.mlb_game_pk || 'game'}:${index}`}
              appearance={appearance}
              rosterContextLimited={rosterContextLimited}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

function ReliefWorkByDate({ groups, absenceSentence, rosterContextLimited = false }) {
  const dateGroups = asArray(groups)
  const hasAbsence = Boolean(textValue(absenceSentence))
  if (dateGroups.length === 0 && !hasAbsence) return null

  return (
    <Section title="Relief Work by Date" compact>
      <Sentence>{absenceSentence}</Sentence>
      {dateGroups.map((group, groupIndex) => (
        <details
          key={`${group?.game_date || 'group'}:${groupIndex}`}
          className="overflow-hidden rounded border border-dirt/70 bg-chalk/20"
          aria-label={textValue(group?.sentence) || `Relief work date ${groupIndex + 1}`}
          open={groupIndex === 0}
        >
          <summary
            className="cursor-pointer list-none border-l-2 border-l-amber/40 bg-dugout/70 px-3 py-2.5 marker:hidden transition-colors hover:bg-dugout focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/50"
            data-testid="team-relief-date-summary"
          >
            <DateSummary>{group?.sentence}</DateSummary>
          </summary>
          {groupGameSections(group).map((section, index) => (
            <GameSection
              key={`${section.key}:${index}`}
              section={section}
              multiGame={groupGameSections(group).length > 1}
              rosterContextLimited={rosterContextLimited}
            />
          ))}
        </details>
      ))}
    </Section>
  )
}

function WorkWindow({ value }) {
  if (
    !textValue(value?.sentence)
    && !textValue(value?.pitchers_sentence)
    && !textValue(value?.pitches_sentence)
    && !textValue(value?.start_relief_unknown_sentence)
  ) {
    return null
  }

  return (
    <div className="rounded border border-dirt/60 bg-chalk/25 p-2">
      <Sentence>{value?.sentence}</Sentence>
      <Sentence>{value?.pitchers_sentence}</Sentence>
      <Sentence>{value?.pitches_sentence}</Sentence>
      <Sentence>{value?.start_relief_unknown_sentence}</Sentence>
    </div>
  )
}

function ReliefWorkWindows({ windows }) {
  const window7 = windows?.window_7
  const window14 = windows?.window_14
  if (!window7 && !window14) return null

  return (
    <Section title="Relief Work Windows" compact>
      <div className="grid gap-2 md:grid-cols-2">
        <WorkWindow value={window7} />
        <WorkWindow value={window14} />
      </div>
    </Section>
  )
}

function PanelShell({ children }) {
  return (
    <section
      id="team-relief-work"
      className="scroll-mt-24 space-y-2.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/50"
      aria-labelledby="team-relief-work-title"
      tabIndex={-1}
    >
      <div>
        <div id="team-relief-work-title" className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">
          Recent Bullpen Work
        </div>
      </div>
      {children}
    </section>
  )
}

function ScopeSentence({ payload, rosterContextLimited = false }) {
  if (rosterContextLimited) {
    return <Sentence>Recent workload remains visible, but current roster coverage is not verified.</Sentence>
  }
  return <Sentence>{payload?.scope_sentence}</Sentence>
}

export default function TeamReliefWorkPanel({
  teamId,
  payload,
  loading: loadingOverride,
  error: errorOverride,
  rosterContextLimited = false,
  hideRoutineFreshness = false,
}) {
  const fetched = useFetch(
    () => (payload !== undefined || !isFilled(teamId)
      ? Promise.resolve(payload ?? null)
      : getTeamReliefWork(teamId)),
    [teamId, payload],
  )
  const data = payload !== undefined ? payload : fetched.data
  const error = errorOverride ?? (payload !== undefined ? null : fetched.error)
  const loading = loadingOverride ?? (error ? false : (payload !== undefined ? false : fetched.loading))

  if (loading) {
    return (
      <PanelShell>
        <section className="rounded border border-dirt bg-field/45 p-3">
          <div className="font-mono text-sm text-chalk400">Loading recent bullpen work…</div>
        </section>
      </PanelShell>
    )
  }

  if (error) {
    return (
      <PanelShell>
        <section className="rounded border border-dirt bg-field/45 p-3">
          <div className="font-mono text-sm text-chalk400">Recent bullpen work is unavailable.</div>
        </section>
      </PanelShell>
    )
  }

  return (
    <PanelShell>
      <ScopeSentence payload={data} rosterContextLimited={rosterContextLimited} />
      <DataCurrency payload={data} hideRoutine={hideRoutineFreshness} />
      <ReliefWorkWindows windows={data?.windows} />
      <ReliefWorkByDate
        groups={data?.relief_by_date}
        absenceSentence={data?.absence_sentence}
        rosterContextLimited={rosterContextLimited}
      />
    </PanelShell>
  )
}
