import { useFetch } from '../../../hooks/useFetch'
import { toOperatingStateReadModel } from '../../../adapters/operatingStateReadModel'
import { readTeamBoardV2 } from '../../../adapters/teamBoardV2'
import { getTeamBoardV2, getTeamBullpenBoard, getTeamGameContext, getTeamStory, getTeamShareCard } from '../../../utils/api'
import { TeamBoardSkeleton, ErrorState, EmptyState } from '../../UI'
import { BullpenReadDisclosure } from '../BullpenOperatingStateCard'
import TeamBoardAnswerBlock from './TeamBoardAnswerBlock'
import TeamBoardActiveBullpen from './TeamBoardActiveBullpen'
import TeamBoardRecentUsage from './TeamBoardRecentUsage'
import TeamBoardRestStatus from './TeamBoardRestStatus'
import TeamBoardWorkloadOverview from './TeamBoardWorkloadOverview'
import TeamBoardRolesDeployment from './TeamBoardRolesDeployment'
import TeamBoardRotationImpact from './TeamBoardRotationImpact'
import TeamBoardRecentTransactions from './TeamBoardRecentTransactions'
import TeamGameContextCard from './TeamGameContextCard'
import StoryCard from './StoryCard'
import TeamReliefWorkPanel from '../TeamReliefWorkPanel'
import { buildTeamBoardHref, resolveTeamId } from '../../../utils/evidenceLinks'
import { EVIDENCE_CARD_ORIGIN, buildTeamShareCardFromArtifact } from '../../../utils/shareCardArtifact'
import EvidenceShareMenu from '../../share/EvidenceShareMenu'

export { resolveTeamId } from '../../../utils/evidenceLinks'

const staticFetchState = (data) => ({
  data,
  loading: false,
  error: null,
  refetch: () => {},
})

// Tonight's Bullpen Board lives inside the Bullpen workflow. It receives the
// shared teams fetch so it does not double-load the team list, manages its own
// single-team selection, and renders the grouped board for that team. A
// `requestedTeam` deep-link (e.g. from the landscape drilldown) preselects a team.
export default function TonightsBullpenBoard({
  teams,
  requestedTeam = null,
  requestedSection = null,
  initialSelectedTeam = null,
  onSelectTeam = () => {},
  onSelectPitcher = () => {},
  boardPayload,
  teamBoardV2Payload,
  teamBoardV2Loading,
  teamBoardV2Error,
  gameContextPayload,
  storyPayload,
}) {
  const teamList = teams?.data || []
  const selectedTeam = initialSelectedTeam ?? resolveTeamId(teamList, requestedTeam)
  const selectedTeamRecord = teamList.find(team => Number(team.team_id) === Number(selectedTeam)) || boardPayload?.team || null
  const board = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamBullpenBoard(selectedTeam)),
    [selectedTeam],
  )
  const teamBoardV2 = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamBoardV2(selectedTeam)),
    [selectedTeam],
  )

  // Game context for the selected team (stored game-log only).
  const gameContext = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamGameContext(selectedTeam)),
    [selectedTeam],
  )
  const story = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamStory(selectedTeam)),
    [selectedTeam],
  )
  // SC-03A cutover: the Share Card is sourced from the canonical, published,
  // integrity-verified immutable artifact (never composed client-side).
  const shareCard = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamShareCard(selectedTeam)),
    [selectedTeam],
  )
  const boardState = boardPayload !== undefined ? staticFetchState(boardPayload) : board
  const hasTeamBoardV2Override = (
    teamBoardV2Payload !== undefined
    || teamBoardV2Loading !== undefined
    || teamBoardV2Error !== undefined
  )
  const teamBoardV2State = hasTeamBoardV2Override
    ? {
        data: teamBoardV2Payload ?? null,
        loading: teamBoardV2Loading === true,
        error: teamBoardV2Error ?? null,
        refetch: () => {},
      }
    : teamBoardV2
  const teamBoardRead = readTeamBoardV2(teamBoardV2State.data)
  const gameContextState = gameContextPayload !== undefined ? staticFetchState(gameContextPayload) : gameContext
  const storyState = storyPayload !== undefined ? staticFetchState(storyPayload) : story
  const teamOperatingRead = toOperatingStateReadModel(boardState.data || {}, {
    scope: 'team',
    team: boardState.data?.team,
    cta: { href: '#pitcher-lanes', label: 'Review pitcher lanes' },
    density: 'compact',
    // Rotation Impact now owns this Team Board fact family through v2. Keep
    // the legacy operating-state adapter available to its other consumers,
    // but do not repeat its browser-authored starter interpretation here.
    includeRotationSupport: false,
  })
  const normalizedRequestedSection = String(requestedSection || '').replace(/^#/, '')
  // Canonical artifact-backed card; null when no published artifact exists, which
  // drives the share menu's controlled unavailable state (no legacy fallback).
  const teamCard = buildTeamShareCardFromArtifact(shareCard.data)
  const teamLinkFallbackPath = buildTeamBoardHref(selectedTeamRecord, { section: normalizedRequestedSection })
  const teamDestinationUrl = teamCard?.destinationUrl
    || (teamLinkFallbackPath ? `${EVIDENCE_CARD_ORIGIN}${teamLinkFallbackPath}` : null)
  const teamEvidenceTarget = teamCard?.evidenceTarget
    || (normalizedRequestedSection === 'team-relief-work'
      ? 'team_relief_work'
      : normalizedRequestedSection === 'pitcher-lanes'
        ? 'pitcher_lanes'
        : 'team_read')
  const teamShareText = teamCard?.shareText
    || `Current ${teamOperatingRead.teamName || 'team'} bullpen evidence on BaseballOS.`

  return (
    <div>
      {/* Compact selection keeps all 30 teams to one accessible control. */}
      <div className="mb-4 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1 sm:max-w-xs">
          {teamList.length === 0 ? (
            <span className="inline-flex min-h-11 items-center font-mono text-xs text-chalk500">
              {teams?.loading ? 'Loading teams…' : 'Teams unavailable.'}
            </span>
          ) : (
            <>
              <label htmlFor="team-board-selector" className="type-overline block">Team</label>
              <select
                id="team-board-selector"
                aria-label="Select team for Team Board"
                value={selectedTeam ?? ''}
                onChange={event => onSelectTeam(event.target.value ? Number(event.target.value) : null)}
                className="mt-1 min-h-11 w-full rounded border border-dirt bg-field/70 px-3 py-2 font-mono text-xs text-chalk200 outline-none focus:border-amber/50 focus-visible:ring-2 focus-visible:ring-amber/60"
              >
                <option value="">Pick a team</option>
                {teamList.map(team => <option key={team.team_id} value={team.team_id}>{team.team_name || team.team_abbreviation}</option>)}
              </select>
            </>
          )}
        </div>
      </div>

      {selectedTeam == null ? (
        <EmptyState title="Pick a team" subtitle="Select a team above to see its current bullpen board." />
      ) : boardState.loading ? (
        <TeamBoardSkeleton message="Building current bullpen board..." />
      ) : boardState.error ? (
        <ErrorState message={boardState.error} onRetry={boardState.refetch} />
      ) : (
        // Keyed by team so a team switch fully remounts the answer: no prior
        // team's state, distribution, evidence, or disclosure state can linger.
        <div key={selectedTeam} className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
          <div className="min-w-0 flex-1">
            {/* TB-01 adopts only the v2-backed answer. Every section below this
                block remains on its legacy owner until its migration package.
                The former titleOwnedByPage operating-card handoff is retired:
                the route owns the H1 and this block owns the selected-club H2. */}
            <div className="mb-4">
              <TeamBoardAnswerBlock
                read={teamBoardRead}
                team={selectedTeamRecord}
                loading={teamBoardV2State.loading}
                error={teamBoardV2State.error}
                onRetry={teamBoardV2State.refetch}
              />
              {(gameContextState.loading || gameContextState.error || gameContextState.data) && (
                <TeamGameContextCard
                  gameContext={gameContextState.data}
                  loading={gameContextState.loading}
                  error={gameContextState.error}
                  compact
                />
              )}
            </div>
            <TeamBoardActiveBullpen
              read={teamBoardRead}
              loading={teamBoardV2State.loading}
              error={teamBoardV2State.error}
              onRetry={teamBoardV2State.refetch}
              onSelectPitcher={onSelectPitcher}
            />
            <TeamBoardRecentUsage
              read={teamBoardRead}
              loading={teamBoardV2State.loading}
              error={teamBoardV2State.error}
              onRetry={teamBoardV2State.refetch}
            />
            <TeamBoardRestStatus
              read={teamBoardRead}
              loading={teamBoardV2State.loading}
              error={teamBoardV2State.error}
              onRetry={teamBoardV2State.refetch}
            />
            <TeamBoardWorkloadOverview
              read={teamBoardRead}
              loading={teamBoardV2State.loading}
              error={teamBoardV2State.error}
              onRetry={teamBoardV2State.refetch}
            />
            <TeamBoardRolesDeployment
              read={teamBoardRead}
              loading={teamBoardV2State.loading}
              error={teamBoardV2State.error}
              onRetry={teamBoardV2State.refetch}
            />
            <TeamBoardRotationImpact
              read={teamBoardRead}
              loading={teamBoardV2State.loading}
              error={teamBoardV2State.error}
              onRetry={teamBoardV2State.refetch}
            />
            <TeamBoardRecentTransactions
              read={teamBoardRead}
              loading={teamBoardV2State.loading}
              error={teamBoardV2State.error}
              onRetry={teamBoardV2State.refetch}
            />
            {storyState.data?.story_available === true && <section className="mt-6" aria-labelledby="what-changed-title">
              <h2 id="what-changed-title" className="font-display text-xl tracking-wide text-chalk100">What Changed</h2>
              <div className="mt-2">
                <StoryCard
                  story={storyState.data}
                  loading={storyState.loading}
                  error={storyState.error}
                  onRetry={storyState.refetch}
                  hideFreshnessMeta
                />
              </div>
            </section>}
            <div className="mt-6">
              <TeamReliefWorkPanel
                read={teamBoardRead}
                loading={teamBoardV2State.loading}
                error={teamBoardV2State.error}
                onRetry={teamBoardV2State.refetch}
              />
            </div>
            <div className="mt-4 flex justify-end">
              <EvidenceShareMenu
                cardModel={teamCard}
                destinationUrl={teamDestinationUrl}
                shareText={teamShareText}
                context={{
                  surface: 'bullpen_board',
                  cardType: 'team',
                  team_ref: teamOperatingRead.teamAbbreviation,
                  evidence_target: teamEvidenceTarget,
                  data_through: teamOperatingRead.freshness?.dataThrough,
                }}
              />
            </div>
            <BullpenReadDisclosure
              readModel={teamOperatingRead}
              staleWithError={teamOperatingRead.freshness?.isStale || teamOperatingRead.freshness?.failClosed}
              className="mt-4"
            />
          </div>
        </div>
      )}
    </div>
  )
}
