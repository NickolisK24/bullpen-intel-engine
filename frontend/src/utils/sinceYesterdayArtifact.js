import { getSinceYesterdayShareArtifact } from './api'
import { PUBLIC_SHARE_ORIGIN } from './shareActions'

export async function loadSinceYesterdayCitation(
  item,
  { fetchArtifact = getSinceYesterdayShareArtifact } = {},
) {
  if (!item?.teamId || !item?.currentDate || !item?.previousDate) return null
  const response = await fetchArtifact(item.teamId, {
    current_date: item.currentDate,
    prior_date: item.previousDate,
  })
  const artifact = response?.artifact
  const path = artifact?.routes?.share_url
  if (
    response?.available !== true
    || artifact?.artifact_type !== 'since_yesterday_change'
    || !artifact?.public_id
    || typeof path !== 'string'
    || path !== `/share/${artifact.public_id}`
  ) return null
  return {
    destinationUrl: `${PUBLIC_SHARE_ORIGIN}${path}`,
    shareText: artifact.copy?.description || artifact.copy?.headline || '',
    evidenceTarget: 'team_read',
    dataThrough: artifact.freshness?.current_data_through || item.currentDate,
    artifactPublicId: artifact.public_id,
    source: 'immutable_since_yesterday_artifact',
  }
}
