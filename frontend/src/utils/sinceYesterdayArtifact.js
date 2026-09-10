import { getSinceYesterdayShareArtifact } from './api'
import { PUBLIC_SHARE_ORIGIN } from './shareActions'

export async function loadSinceYesterdayCitation(
  item,
  { fetchArtifact = getSinceYesterdayShareArtifact } = {},
) {
  const identity = item?.comparisonIdentity
  if (!item?.teamId || !identity || typeof identity !== 'object') return null
  const response = await fetchArtifact(item.teamId, {
    comparison_contract: identity.contract,
    comparison_authority: identity.comparison_authority,
    comparison_method_version: identity.method_version,
    previous_snapshot_id: identity.previous_snapshot_id,
    current_snapshot_id: identity.current_snapshot_id,
    previous_sync_run_id: identity.previous_sync_run_id,
    current_sync_run_id: identity.current_sync_run_id,
    previous_payload_version: identity.previous_payload_version,
    current_payload_version: identity.current_payload_version,
    previous_data_through: identity.previous_data_through,
    current_data_through: identity.current_data_through,
    previous_publication_state: identity.previous_publication_state,
    current_publication_state: identity.current_publication_state,
  })
  const artifact = response?.artifact
  const path = artifact?.routes?.share_url
  if (
    response?.available !== true
    || artifact?.artifact_type !== 'since_yesterday_change'
    || !artifact?.public_id
    || String(artifact?.team?.team_id) !== String(item.teamId)
    || artifact?.freshness?.previous_data_through !== identity.previous_data_through
    || artifact?.freshness?.current_data_through !== identity.current_data_through
    || typeof path !== 'string'
    || path !== `/share/${artifact.public_id}`
  ) return null
  return {
    destinationUrl: `${PUBLIC_SHARE_ORIGIN}${path}`,
    shareText: artifact.copy?.description || artifact.copy?.headline || '',
    evidenceTarget: 'team_read',
    dataThrough: artifact.freshness.current_data_through,
    artifactPublicId: artifact.public_id,
    source: 'immutable_since_yesterday_artifact',
  }
}
