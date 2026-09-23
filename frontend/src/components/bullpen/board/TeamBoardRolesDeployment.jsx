import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'

const countValue = value => Number.isInteger(value) && value >= 0 ? value : null
const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null
const counted = (value, singular, plural = `${singular}s`) => `${value} ${value === 1 ? singular : plural}`

export function getRoleCompositionRows(rolesDeployment) {
  const roles = Array.isArray(rolesDeployment?.roles) ? rolesDeployment.roles : []
  const rows = roles.map((role, index) => ({
    key: textValue(role?.role_key) || `role-${index}`,
    label: textValue(role?.label),
    count: countValue(role?.arm_count),
  })).filter(role => role.label && role.count != null)

  const missingCount = countValue(rolesDeployment?.missing_role_count)
  if (missingCount > 0) {
    rows.push({ key: 'role-unavailable', label: 'Role unavailable', count: missingCount })
  }
  return rows
}

export function getDeploymentRows(rolesDeployment) {
  const deployment = rolesDeployment?.deployment_profile
  if (deployment?.status !== 'complete' || !Array.isArray(deployment?.profiles)) return []
  return deployment.profiles.map((profile, index) => ({
    key: Number.isInteger(profile?.pitcher_id) ? `pitcher-${profile.pitcher_id}` : `deployment-${index}`,
    name: textValue(profile?.pitcher_name),
    summary: textValue(profile?.summary),
  })).filter(profile => profile.name && profile.summary)
}

function firstLimitation(status) {
  return Array.isArray(status?.limitations)
    ? status.limitations.find(value => textValue(value))?.trim() || null
    : null
}

function EvidenceNote({ evidence }) {
  if (!evidence || evidence.status === 'complete') return null
  return <span className="ml-1 text-text-withheld">({evidence.status}{evidence.status === 'partial' ? `, ${evidence.knownAppearances} of ${evidence.appearances} known` : ''})</span>
}

function DeploymentFact({ label, evidence, children }) {
  return (
    <div className="min-w-0">
      <dt className="type-overline text-text-tertiary">{label}</dt>
      <dd className="type-compact mt-meta break-words text-text-secondary">
        {evidence?.status === 'unknown' || evidence?.status === 'unavailable' ? '—' : children}
        <EvidenceNote evidence={evidence} />
      </dd>
    </div>
  )
}

function FrozenDeployment({ deployment }) {
  const leverageBroadlyUnavailable = deployment.profiles.length > 1 && deployment.profiles.every(
    profile => profile.leverage?.status === 'unknown' || profile.leverage?.status === 'unavailable',
  )
  return (
    <div className="mt-section border-t border-line-default pt-section" aria-label="Frozen observed bullpen deployment">
      <div className="type-overline">Observed deployment · 14 baseball days</div>
      <p className="type-compact mt-meta text-text-tertiary">Through {deployment.dataThrough}. Recorded leverage refers to the appearance-level index, not necessarily leverage at entry.</p>
      {leverageBroadlyUnavailable && (
        <p className="type-metadata mt-row text-text-withheld" role="note">Recorded leverage is not published for the arms in this snapshot.</p>
      )}
      {deployment.profiles.length === 0 ? (
        <p className="type-compact mt-panel text-text-tertiary">No current arms have a published deployment profile.</p>
      ) : (
        <ol className="mt-panel divide-y divide-line-subtle border-y border-line-subtle" aria-label="Named-arm deployment evidence">
          {deployment.profiles.map(profile => (
            <li key={profile.pitcherId} className="min-w-0 py-row">
              <div className="flex flex-wrap items-baseline gap-x-row gap-y-1">
                <h3 className="font-board text-board-body font-semibold text-text-primary">{profile.name}</h3>
                <span className="type-compact text-text-secondary">{profile.role.label}</span>
                {profile.role.confidence && <span className="type-compact text-text-tertiary">Role confidence: {profile.role.confidence}</span>}
              </div>
              {profile.observed && (
                <p className="type-compact mt-row text-text-secondary">
                  {counted(profile.observed.appearances, 'appearance')} · {counted(profile.observed.saves, 'save')} · {counted(profile.observed.holds, 'hold')} ·{' '}
                  {counted(profile.observed.gamesFinished, 'game finished', 'games finished')} · {counted(profile.observed.multiInning, 'multi-inning appearance')}
                </p>
              )}
              <p className="type-metadata mt-meta text-text-secondary">
                {profile.entry?.status === 'complete' || profile.entry?.status === 'partial'
                  ? `${profile.entry.eighth_or_later_appearances} entries in the 8th or later`
                  : 'Entry context not published'}
                {' · '}
                {profile.score?.status === 'complete' || profile.score?.status === 'partial'
                  ? `${profile.score.leading} leading · ${profile.score.tied} tied · ${profile.score.trailing} trailing`
                  : 'Score context not published'}
              </p>
              <details className="mt-meta" data-testid="deployment-detail">
                <summary className="inline-flex min-h-11 cursor-pointer items-center font-board text-board-metadata font-semibold text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus">View deployment detail</summary>
                <dl className="mt-meta grid min-w-0 gap-x-panel gap-y-row rounded-sm bg-surface-raised/30 p-row tablet:grid-cols-3">
                  <DeploymentFact label="Entry innings" evidence={profile.entry}>
                    {profile.entry.byInning.map(row => `Inning ${row.inning}: ${row.appearances}`).join(' · ') || 'No recorded entries'}
                    {' · '}{profile.entry.eighth_or_later_appearances} entered 8th or later
                    {profile.entry.extra_inning_appearances > 0 && ` · ${counted(profile.entry.extra_inning_appearances, 'extra-inning entry', 'extra-inning entries')}`}
                  </DeploymentFact>
                  <DeploymentFact label="Score at entry" evidence={profile.score}>
                    {profile.score.leading} leading · {profile.score.tied} tied · {profile.score.trailing} trailing
                  </DeploymentFact>
                  {!leverageBroadlyUnavailable && (
                    <DeploymentFact label="Recorded leverage" evidence={profile.leverage}>
                      {profile.leverage.high} high · {profile.leverage.middle} middle · {profile.leverage.low} low
                    </DeploymentFact>
                  )}
                </dl>
              </details>
              {profile.observed?.limitations?.length > 0 && <p className="type-compact mt-row text-text-withheld">{profile.observed.limitations.join(' ')}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function RoleCompositionSkeleton() {
  return (
    <section className="foundation-section min-w-0" aria-labelledby="roles-deployment-title" aria-busy="true" data-testid="roles-deployment-skeleton">
      <div className="rounded-sm border border-line-subtle bg-surface-raised/30 p-panel tablet:p-section">
        <h2 id="roles-deployment-title" className="type-section-title">Roles &amp; Deployment</h2>
        <span className="sr-only">Loading role composition.</span>
        <div className="mt-panel divide-y divide-line-subtle">
          {[0, 1, 2].map(index => (
            <div key={index} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-row py-row">
              <SkeletonBlock className="h-5 w-36 max-w-full" />
              <SkeletonBlock className="h-5 w-14 max-w-full" />
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default function TeamBoardRolesDeployment({ read, loading = false, error = null, onRetry }) {
  if (loading) return <RoleCompositionSkeleton />

  const rolesDeployment = read?.rolesDeployment
  const status = read?.sectionStatus?.roles_deployment
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const rows = getRoleCompositionRows(rolesDeployment)
  const deploymentRows = getDeploymentRows(rolesDeployment)
  const frozenDeployment = read?.frozenPublicDeployment
  const deployment = rolesDeployment?.deployment_profile
  const deploymentSummary = textValue(deployment?.summary)
  const limitation = firstLimitation(status)

  return (
    <section className="foundation-section min-w-0" aria-labelledby="roles-deployment-title" data-testid="team-board-roles-deployment">
      <header className="mb-panel border-b border-line-default pb-panel">
        <div className="type-overline text-brand-gold">Bullpen structure</div>
        <h2 id="roles-deployment-title" className="type-section-title mt-meta">Roles &amp; Deployment</h2>
        <p className="type-metadata mt-meta max-w-reading text-text-tertiary">Current role mix and observed usage patterns.</p>
      </header>

      {error ? (
        <SectionState status="error" title="Roles & Deployment unavailable" message="Current role composition could not be loaded." onRetry={onRetry} />
      ) : read?.frozenPublicDeploymentRejected || read?.detailsRejected ? (
        <SectionState status="unavailable" title="Roles & Deployment unavailable" message="Deployment identity does not match this Team Board." />
      ) : !read || !rolesDeployment ? (
        <SectionState status="unavailable" title="Roles & Deployment unavailable" message="A current backend-authored role composition is not available." onRetry={onRetry} />
      ) : (
        <>
          {rows.length > 0 && (
            <div className="rounded-sm border border-line-subtle bg-surface-raised/30 p-row" aria-label="Current role mix">
              <dl className="flex flex-wrap gap-x-panel gap-y-meta" aria-label="Current active bullpen role composition">
                {rows.map(row => (
                  <div key={row.key} className="inline-flex min-w-0 items-baseline gap-meta">
                    <dt className={`type-compact min-w-0 break-words ${row.key === 'limited_read' || row.key === 'role-unavailable' ? 'text-text-withheld' : 'text-text-secondary'}`}>{row.label}</dt>
                    <dd className="font-board text-board-body whitespace-nowrap font-semibold tabular-nums text-text-primary">
                      {row.count} {row.count === 1 ? 'arm' : 'arms'}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {frozenDeployment ? (
            <FrozenDeployment deployment={frozenDeployment} />
          ) : deploymentRows.length > 0 ? (
            <div className={rows.length > 0 ? 'mt-section border-t border-line-default pt-section' : ''} aria-label="Observed bullpen deployment">
              <div className="type-overline">Observed deployment</div>
              {deploymentSummary && <p className="type-compact mt-meta max-w-reading text-text-secondary">{deploymentSummary}</p>}
              <ul className="mt-panel divide-y divide-line-subtle border-y border-line-subtle">
                {deploymentRows.map(row => (
                  <li key={row.key} className="py-panel">
                    <p className="font-board text-board-body font-semibold text-text-primary">{row.name}</p>
                    <p className="type-compact mt-meta max-w-reading text-text-secondary">{row.summary}</p>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <SectionState
              status="unavailable"
              title="Deployment detail unavailable"
              message="Frozen observed deployment detail is not published for this Team Board."
              className={rows.length > 0 ? 'mt-section' : ''}
            />
          )}

          {statusName === 'partial' && (
            <SectionState status="partial" title="Role composition is partially available" message={limitation || 'Some current role reads are unavailable.'} className={rows.length > 0 ? 'mt-row' : ''} />
          )}
          {statusName === 'unavailable' && (
            <SectionState status="unavailable" title="Roles & Deployment unavailable" message="Current role composition is unavailable." className={rows.length > 0 ? 'mt-row' : ''} />
          )}
          {statusName === 'available' && rows.length === 0 && (
            <div className="section-state" role="status" data-state="empty">
              <h3 className="type-section-title">No current role reads</h3>
              <p className="type-compact mt-meta">The current active-bullpen role population is empty.</p>
            </div>
          )}
        </>
      )}
    </section>
  )
}
