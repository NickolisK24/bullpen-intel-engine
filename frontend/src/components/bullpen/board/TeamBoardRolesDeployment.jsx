import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'

const countValue = value => Number.isInteger(value) && value >= 0 ? value : null
const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null

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

function RoleCompositionSkeleton() {
  return (
    <section className="foundation-section" aria-labelledby="roles-deployment-title" aria-busy="true" data-testid="roles-deployment-skeleton">
      <h2 id="roles-deployment-title" className="type-section-title">Roles &amp; Deployment</h2>
      <span className="sr-only">Loading role composition.</span>
      <div className="mt-row divide-y divide-line-subtle">
        {[0, 1, 2].map(index => (
          <div key={index} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-row py-row">
            <SkeletonBlock className="h-5 w-36 max-w-full" />
            <SkeletonBlock className="h-5 w-14 max-w-full" />
          </div>
        ))}
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
  const deployment = rolesDeployment?.deployment_profile
  const deploymentSummary = textValue(deployment?.summary)
  const limitation = firstLimitation(status)

  return (
    <section className="foundation-section" aria-labelledby="roles-deployment-title" data-testid="team-board-roles-deployment">
      <header className="mb-row">
        <h2 id="roles-deployment-title" className="type-section-title">Roles &amp; Deployment</h2>
        <p className="type-metadata mt-meta">Current role mix</p>
      </header>

      {error ? (
        <SectionState status="error" title="Roles & Deployment unavailable" message="Current role composition could not be loaded." onRetry={onRetry} />
      ) : !read || !rolesDeployment ? (
        <SectionState status="unavailable" title="Roles & Deployment unavailable" message="A current backend-authored role composition is not available." onRetry={onRetry} />
      ) : (
        <>
          {rows.length > 0 && (
            <dl className="divide-y divide-line-subtle" aria-label="Current active bullpen role composition">
              {rows.map(row => (
                <div key={row.key} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-row py-row tablet:grid-cols-[minmax(12rem,1fr)_minmax(8rem,auto)]">
                  <dt className={`type-data min-w-0 break-words ${row.key === 'limited_read' || row.key === 'role-unavailable' ? 'text-text-withheld' : 'text-text-primary'}`}>{row.label}</dt>
                  <dd className="type-data whitespace-nowrap text-right tabular-nums text-text-secondary">
                    {row.count} {row.count === 1 ? 'arm' : 'arms'}
                  </dd>
                </div>
              ))}
            </dl>
          )}

          {deploymentRows.length > 0 ? (
            <div className={rows.length > 0 ? 'mt-section' : ''} aria-label="Observed bullpen deployment">
              <h3 className="type-section-title">Observed deployment</h3>
              {deploymentSummary && <p className="type-compact mt-meta text-text-secondary">{deploymentSummary}</p>}
              <ul className="mt-row divide-y divide-line-subtle">
                {deploymentRows.map(row => (
                  <li key={row.key} className="py-row">
                    <p className="type-data text-text-primary">{row.name}</p>
                    <p className="type-compact mt-meta text-text-secondary">{row.summary}</p>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <SectionState
              status="unavailable"
              title="Deployment detail unavailable"
              message="Observed deployment detail is not available for the represented window."
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
