import { evaluateRecommendationCandidate } from '../../utils/api'

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function firstPresent(...values) {
  return values.find(value => value !== undefined && value !== null && value !== '')
}

function compactObject(value) {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== ''),
  )
}

export function buildRecommendationCandidateFromPitcherDetail(pitcherDetail = {}) {
  if (Array.isArray(pitcherDetail)) {
    throw new TypeError('Candidate evaluation accepts one pitcher detail payload.')
  }

  const detail = asObject(pitcherDetail)
  const pitcher = asObject(detail.pitcher)
  const availability = asObject(detail.availability)
  const availabilityInputs = asObject(availability.inputs)
  const currentFatigue = asObject(detail.current_fatigue)

  const metadata = compactObject({
    data_through: firstPresent(
      availability.data_through,
      availabilityInputs.latest_game_date,
      currentFatigue.calculated_at,
    ),
    last_successful_sync: firstPresent(
      availability.last_successful_sync,
      detail.last_successful_sync,
    ),
    latest_sync_status: firstPresent(
      availability.latest_sync_status,
      detail.latest_sync_status,
    ),
  })

  return compactObject({
    pitcher_id: firstPresent(pitcher.id, pitcher.pitcher_id, detail.pitcher_id),
    pitcher_name: firstPresent(
      pitcher.full_name,
      pitcher.pitcher_name,
      pitcher.name,
      detail.pitcher_name,
    ),
    team_id: firstPresent(pitcher.team_id, detail.team_id),
    team_name: firstPresent(pitcher.team_name, detail.team_name),
    availability,
    metadata,
  })
}

export function evaluatePitcherDetailRecommendation(
  pitcherDetail,
  {
    evaluateCandidate = evaluateRecommendationCandidate,
    requestMetadata = {},
  } = {},
) {
  const candidate = buildRecommendationCandidateFromPitcherDetail(pitcherDetail)

  return evaluateCandidate(candidate, {
    source: 'pitcher_detail',
    ...requestMetadata,
  })
}
