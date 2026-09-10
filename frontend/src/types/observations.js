export const BULLPEN_OBSERVATIONS_ROUTE = '/observations'

export const OBSERVATION_RESPONSE_REQUIRED_FIELDS = [
  'status',
  'collection_id',
  'observation_count',
  'observations',
  'freshness',
  'confidence',
  'limitations',
  'trust_status',
  'ranking_applied',
  'selection_made',
]

export const OBSERVATION_ITEM_REQUIRED_FIELDS = [
  'observation_id',
  'observation_type',
  'family',
  'severity',
  'title',
  'summary',
  'evidence',
  'limitations',
  'confidence',
  'freshness',
  'trust_status',
  'explanation_reference',
  'ranking_applied',
  'selection_made',
]

export const OBSERVATION_GOVERNANCE_FIELD_EXCEPTIONS = new Set([
  'ranking_applied',
  'selection_made',
])

export const OBSERVATION_FORBIDDEN_FIELD_KEYS = new Set([
  'best',
  'best_arm',
  'best_candidate',
  'best_pitcher',
  'bestPitcher',
  'best_pitcher_id',
  'closer',
  'closer_choice',
  'game_prediction',
  'game_outcome_prediction',
  'hidden_priority_ordering',
  'injury_prediction',
  'matchup',
  'matchup_advice',
  'matchup_advantage',
  'outcome_prediction',
  'performance_forecast',
  'performance_prediction',
  'pitcher_choice',
  'prediction',
  'predictions',
  'preferred',
  'preferred_arm',
  'preferred_option',
  'preferred_pitcher',
  'priority',
  'priority_order',
  'priority_score',
  'projected_outcome',
  'rank',
  'ranked_candidates',
  'ranking',
  'rankings',
  'recommendation',
  'recommendations',
  'recommended',
  'recommended_arm',
  'recommended_option',
  'recommended_pitcher',
  'save_prediction',
  'score',
  'score_ordering',
  'selected_candidate',
  'selected_pitcher',
  'selection',
  'setup_choice',
  'top_candidate',
  'top_option',
  'use_this_pitcher',
  'winner',
])

export const OBSERVATION_FORBIDDEN_TEXT_TERMS = [
  /\bbest arm\b/i,
  /\bbest option\b/i,
  /\bpreferred arm\b/i,
  /\brecommended arm\b/i,
  /\buse pitcher\b/i,
  /\buse this pitcher\b/i,
  /\bmanager should\b/i,
  /\bmatchup advantage\b/i,
  /\bshould close\b/i,
  /\bsetup choice\b/i,
]

export const OBSERVATION_EMPTY_COPY =
  'No bullpen observations have enough trusted movement to show yet.'

export const OBSERVATION_GOVERNANCE_COPY =
  'Observations describe bullpen movement and decision context without choosing an arm.'
