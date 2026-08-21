import { useFetch } from '../../../hooks/useFetch'
import { toOperatingStateReadModel } from '../../../adapters/operatingStateReadModel'
import { readTeamBoardV2 } from '../../../adapters/teamBoardV2'
import { getTeamBoardV2, getTeamBullpenBoard, getTeamChanges, getTeamShareCard } from '../../../utils/api'
import { TeamBoardSkeleton, ErrorState, EmptyState, SectionPair } from '../../UI'
import { BullpenReadDisclosure } from '../BullpenOperatingStateCard'
import TeamBoardAnswerBlock from './TeamBoardAnswerBlock'
import TeamBoardActiveBullpen from './TeamBoardActiveBullpen'
import TeamBoardRecentUsage from './TeamBoardRecentUsage'
import TeamBoardRestStatus from './TeamBoardRestStatus'
import TeamBoardWorkloadOverview from './TeamBoardWorkloadOverview'
import TeamBoardRolesDeployment from './TeamBoardRolesDeployment'
import TeamBoardPerformance from './TeamBoardPerformance'
import TeamBoardRotationImpact from './TeamBoardRotationImpact'
import TeamBoardRecentTransactions from './TeamBoardRecentTransactions'
import TeamBoardWhatChanged from './TeamBoardWhatChanged'
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
  changesPayload,
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

  const changes = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamChanges(selectedTeam)),
    [selectedTeam],
  )
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
  const teamBoardAnswerRead = teamBoardRead && gameContextPayload !== undefined
    ? { ...teamBoardRead, gameContext: gameContextPayload }
    : teamBoardRead
  const changesState = changesPayload !== undefined ? staticFetchState(changesPayload) : changes
  const teamOperatingRead = toOperatingStateReadModel(boardState.data || {}, {
    scope: 'team',
    team: boardState.data?.team,
    cta: { href: '#pitcher-lanes', label: 'Review pitcher lanes' },
    density: 'compact',
    includeRotationSupport: false,
  })
  const normalizedRequestedSection = String(requestedSection || '').replace(/^#/, '')
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
  const teamSwitcher = (
    <div className="w-full min-w-0 tablet:w-56">
      {teamList.length === 0 ? (
        <span className="inline-flex min-h-11 items-center font-board text-board-metadata text-text-tertiary">
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
            className="mt-1 min-h-11 w-full rounded-sm border border-line-default bg-surface-base px-3 py-2 font-board text-board-metadata text-text-primary outline-none focus-visible:ring-2 focus-visible:ring-line-focus"
          >
            <option value="">Pick a team</option>
            {teamList.map(team => <option key={team.team_id} value={team.team_id}>{team.team_name || team.team_abbreviation}</option>)}
          </select>
        </>
      )}
    </div>
  )

  return (
    <div>
      {selectedTeam == null ? (
        <>
          <div className="mb-4 max-w-xs">{teamSwitcher}</div>
          <EmptyState title="Pick a team" subtitle="Select a team above to see its current bullpen board." />
        </>
      ) : boardState.loading ? (
        <TeamBoardSkeleton message="Building current bullpen board..." />
      ) : boardState.error ? (
        <ErrorState message={boardState.error} onRetry={boardState.refetch} />
      ) : (
        <div key={selectedTeam} className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
          <div className="min-w-0 flex-1">
            {/* The retired titleOwnedByPage handoff remains a heading boundary:
                the route owns H1; this subtree owns the selected-club H2. */}
            <div className="mb-4">
              <TeamBoardAnswerBlock
                read={teamBoardAnswerRead}
                team={selectedTeamRecord}
                loading={teamBoardV2State.loading}
                error={teamBoardV2State.error}
                onRetry={teamBoardV2State.refetch}
                teamSwitcher={teamSwitcher}
                evidenceDisclosure={(
                  <BullpenReadDisclosure
                    readModel={teamOperatingRead}
                    staleWithError={teamOperatingRead.freshness?.isStale || teamOperatingRead.freshness?.failClosed}
                    flat
                    className="mt-panel"
                  />
                )}
              />
            </div>
            <TeamBoardActiveBullpen
              read={teamBoardRead}
              loading={teamBoardV2State.loading}
              error={teamBoardV2State.error}
              onRetry={teamBoardV2State.refetch}
              onSelectPitcher={onSelectPitcher}
            />

            <div
              className="relative left-1/2 mt-section-lg w-screen -translate-x-1/2 border-y border-line-subtle bg-surface-nav/35 px-4 py-section tablet:left-auto tablet:w-auto tablet:translate-x-0 tablet:rounded-sm tablet:border tablet:px-section tablet:py-section-lg"
              role="group"
              aria-label="Current workload picture"
            >
              <div className="mb-section border-b border-line-default pb-panel">
                <div className="type-overline text-brand-gold">Current workload picture</div>
                <p className="type-compact mt-meta max-w-reading text-text-tertiary">
                  Recent use, recovery runway, and the bullpen&apos;s accumulated group burden.
                </p>
              </div>

              <TeamBoardRecentUsage
                read={teamBoardRead}
                loading={teamBoardV2State.loading}
                error={teamBoardV2State.error}
                onRetry={teamBoardV2State.refetch}
                onSelectPitcher={onSelectPitcher}
              />
              <SectionPair label="Rest and workload" className="mt-section-lg border-t border-line-default pt-section">
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
              </SectionPair>
            </div>

            <SectionPair label="Roles and performance" ratio="7:5">
              <TeamBoardRolesDeployment
                read={teamBoardRead}
                loading={teamBoardV2State.loading}
                error={teamBoardV2State.error}
                onRetry={teamBoardV2State.refetch}
              />
              <TeamBoardPerformance />
            </SectionPair>
            <SectionPair label="Rotation and transactions">
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
                onSelectPitcher={onSelectPitcher}
              />
            </SectionPair>
            <TeamBoardWhatChanged
              changes={changesState.data}
              loading={changesState.loading}
              error={changesState.error}
              onRetry={changesState.refetch}
              onSelectPitcher={onSelectPitcher}
            />
            <div className="mt-6">
              <TeamReliefWorkPanel
                read={teamBoardRead}
                loading={teamBoardV2State.loading}
                error={teamBoardV2State.error}
                onRetry={teamBoardV2State.refetch}
                onSelectPitcher={onSelectPitcher}
              />
            </div>
            <div className="mt-4 flex justify-end">
              <EvidenceShareMenu
                variant="team-board"
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
          </div>
        </div>
      )}
    </div>
  )
}
