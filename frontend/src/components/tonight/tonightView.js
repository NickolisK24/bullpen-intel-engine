// Tonight v1 view model — presentation only.
//
// The backend tonight_v1 edition is the sole owner of every baseball fact on
// /tonight: Team State, rest and multi-day counts, key arms, rotation, the
// context sentence, featured selection, the lead and league changes. This
// module never computes, ranks, reorders or infers any of them. It only:
//
//   1. classifies the response (available / quiet / unavailable);
//   2. turns already-decided values into display strings;
//   3. keeps backend order (games, featured_game_pks, league_changes).
//
// A null or non-integer count is never shown as zero, and an unexpected Team
// State fails closed through the shared public Team State adapter.

import { readPublicTeamState } from '../../adapters/publicTeamState.js'
import { formatDateOnly, formatUtcDateTimeEt } from '../../utils/dateDisplay.js'

export const TONIGHT_CONTRACT = 'tonight_v1'
export const PREGAME_CONTEXT = 'pregame_context'

export const TONIGHT_COPY = Object.freeze({
  title: 'Tonight in MLB Bullpens',
  quiet: "No MLB games are on tonight's slate.",
  unavailable: "Tonight's trusted bullpen edition isn't available yet.",
  error: "Tonight's bullpen view couldn't be loaded.",
  loading: "Loading tonight's bullpen view",
  pregame: 'Pregame context',
  teamStateWithheld: 'Team State withheld',
  restUnavailable: 'Rest read unavailable',
  sideUnavailable: 'Bullpen read unavailable for this club.',
  inProgress: 'In Progress',
  upcoming: 'Upcoming',
  completedGames: 'Completed Games',
  showCompleted: 'Show completed games',
  hideCompleted: 'Hide completed games',
  allFinal: "All of tonight's games are complete.",
})

// Served game state -> public status text. Scheduled uses the first pitch time;
// uncertain is conservative and never implies the game is on or off.
const STATE_LABELS = Object.freeze({
  live: 'In progress',
  final: 'Final',
  postponed: 'Postponed',
  suspended: 'Suspended',
  uncertain: 'Status not confirmed',
})

const SCHEDULED_TIME_UNCONFIRMED = 'Start time not confirmed'

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function text(value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

function count(value) {
  return Number.isInteger(value) && value >= 0 ? value : null
}

function list(value) {
  return Array.isArray(value) ? value : []
}

// Edition dates are ISO dates; a timestamp is read by its date part only.
function isoDate(value) {
  const match = /^(\d{4}-\d{2}-\d{2})(?:$|T)/.exec(typeof value === 'string' ? value.trim() : '')
  return match ? match[1] : null
}

function plural(n, singular, pluralForm = `${singular}s`) {
  return `${n} ${n === 1 ? singular : pluralForm}`
}

export function classifyTonightResponse(payload) {
  if (!isObject(payload)) return 'unavailable'
  if (payload.contract !== TONIGHT_CONTRACT) return 'unavailable'
  if (payload.status === 'unavailable' || !isObject(payload.edition)) return 'unavailable'
  const gameCount = payload.summary?.game_count
  if (gameCount === 0 && list(payload.games).length === 0) return 'quiet'
  return 'available'
}

export function gameStatusLabel(game) {
  const state = game?.state
  if (state === 'scheduled') {
    return formatUtcDateTimeEt(game.first_pitch_utc, { includeDate: false }) || SCHEDULED_TIME_UNCONFIRMED
  }
  return STATE_LABELS[state] || STATE_LABELS.uncertain
}

export function summaryItems(summary) {
  if (!isObject(summary)) return []
  const items = []
  const games = count(summary.game_count)
  if (games) items.push({ key: 'games', text: plural(games, 'game') })

  const states = isObject(summary.team_state_counts) ? summary.team_state_counts : null
  if (states) {
    const parts = [
      ['fresh', 'Fresh'],
      ['stretched', 'Stretched'],
      ['vulnerable', 'Vulnerable'],
    ]
      .map(([key, label]) => [count(states[key]), label])
      .filter(([n]) => n)
      .map(([n, label]) => `${n} ${label}`)
    const withheld = count(states.withheld)
    if (withheld) parts.push(`${withheld} withheld`)
    if (parts.length) items.push({ key: 'team_states', text: `Team State: ${parts.join(' · ')}` })
  }

  const b2bClubs = count(summary.clubs_with_back_to_back_arms)
  if (b2bClubs) {
    items.push({
      key: 'b2b_clubs',
      text: `${plural(b2bClubs, 'club')} with back-to-back arms`,
    })
  }

  const changes = count(summary.change_count)
  if (changes) items.push({ key: 'changes', text: plural(changes, 'bullpen change') })
  return items
}

export function editionHeader(edition) {
  if (!isObject(edition)) return { dateLabel: null, dataThroughLabel: null }
  const date = formatDateOnly(isoDate(edition.baseball_date))
  const through = formatDateOnly(isoDate(edition.data_through), { month: 'short' })
  return {
    dateLabel: date,
    dataThroughLabel: through ? `Data through ${through}` : null,
  }
}

export function unavailableDetail(payload) {
  const publication = isObject(payload?.current_publication) ? payload.current_publication : null
  const date = formatDateOnly(isoDate(publication?.availability_reference_date), { month: 'short' })
    || formatDateOnly(isoDate(publication?.data_through), { month: 'short' })
  return date ? `Latest publication: ${date}` : null
}

function rotationText(rotation) {
  if (!isObject(rotation)) return null
  const starts = count(rotation.short_start_count)
  if (!starts) return null
  const parts = [`${plural(starts, 'recent short start')}`]
  const innings = typeof rotation.bullpen_innings === 'number' || typeof rotation.bullpen_innings === 'string'
    ? text(String(rotation.bullpen_innings))
    : null
  if (innings) parts.push(`${innings} bullpen IP`)
  return parts.join(' · ')
}

function restFacts(side) {
  const rest = isObject(side?.rest) ? side.rest : null
  const facts = []
  if (rest?.available === true) {
    const rested = count(rest.rested_arm_count)
    if (rested !== null) facts.push({ key: 'rested', text: `${rested} rested` })
    const b2b = count(rest.back_to_back_count)
    if (b2b) facts.push({ key: 'b2b', text: `${b2b} B2B` })
  }
  const threeInFour = count(side?.multi_day_usage?.three_in_four_count)
  if (threeInFour) facts.push({ key: 'three_in_four', text: `${threeInFour} in 3-in-4` })
  return { restAvailable: rest?.available === true, facts }
}

function keyArms(side) {
  return list(side?.key_arms)
    .filter(arm => isObject(arm) && text(arm.name))
    .map((arm, index) => ({
      key: arm.pitcher_id ?? `${index}-${arm.name}`,
      name: text(arm.name),
      roleLabel: text(arm.role_label),
      pattern: arm.pattern === 'B2B' || arm.pattern === '3-in-4' ? arm.pattern : null,
    }))
}

export function teamSideView(side, { role, boardHref } = {}) {
  const block = isObject(side) ? side : {}
  const { restAvailable, facts } = restFacts(block)
  return {
    role,
    abbreviation: text(block.abbreviation),
    name: text(block.name) || text(block.abbreviation) || 'Team',
    available: block.available === true,
    teamState: readPublicTeamState(block.team_state),
    restAvailable,
    facts,
    keyArms: keyArms(block),
    rotation: rotationText(block.rotation),
    boardHref: text(boardHref),
  }
}

export function gameView(game) {
  const links = isObject(game?.links) ? game.links : {}
  const context = isObject(game?.context) ? game.context : {}
  const codes = list(context.reason_codes)
  const sentence = text(context.sentence)
  const away = teamSideView(game?.away, { role: 'Away', boardHref: links.away_team_board })
  const home = teamSideView(game?.home, { role: 'Home', boardHref: links.home_team_board })
  return {
    gamePk: game?.game_pk ?? null,
    gameNumber: Number.isInteger(game?.game_number) ? game.game_number : null,
    state: typeof game?.state === 'string' ? game.state : 'uncertain',
    statusLabel: gameStatusLabel(game),
    away,
    home,
    contextSentence: sentence,
    contextPregame: Boolean(sentence) && codes.includes(PREGAME_CONTEXT),
    matchupHref: text(links.matchup),
  }
}

export function featuredGames(payload) {
  const byPk = new Map(list(payload?.games).map(game => [game?.game_pk, game]))
  return list(payload?.featured_game_pks)
    .filter(pk => byPk.has(pk))
    .map(pk => byPk.get(pk))
}

export function leadView(lead) {
  if (!isObject(lead)) return null
  const headline = text(lead.headline)
  if (!headline) return null
  return {
    headline,
    detail: text(lead.detail),
    pregame: list(lead.reason_codes).includes(PREGAME_CONTEXT),
    gamePk: lead.game_pk ?? null,
  }
}

// Only public presentation fields are copied; change_id and source_ref are
// identity/provenance and are never rendered.
export function leagueChangeView(change, boardHref) {
  if (!isObject(change)) return null
  const headline = text(change.headline)
  if (!headline) return null
  return {
    key: text(change.change_id) || headline,
    team: text(change.team_abbreviation),
    headline,
    detail: text(change.detail),
    occurredOn: formatDateOnly(isoDate(change.occurred_on), { month: 'short' }),
    boardHref: text(boardHref),
  }
}

// Slate lifecycle presentation (TN-11.5). The only input is the served
// game.state; nothing else is inferred. Unfinished states never read as
// complete: an unknown or unexpected state falls to Upcoming, the same
// conservative reading as its "Status not confirmed" label.
export const LIFECYCLE_BY_STATE = Object.freeze({
  live: 'inProgress',
  suspended: 'inProgress',
  scheduled: 'upcoming',
  uncertain: 'upcoming',
  postponed: 'upcoming',
  final: 'completed',
})

// One pass in backend order; each game is appended to its bucket, so the
// served order is preserved inside every bucket. No sorting.
export function groupGamesByLifecycle(games) {
  const groups = { inProgress: [], upcoming: [], completed: [] }
  for (const game of list(games)) {
    groups[LIFECYCLE_BY_STATE[game?.state] || 'upcoming'].push(game)
  }
  return groups
}
