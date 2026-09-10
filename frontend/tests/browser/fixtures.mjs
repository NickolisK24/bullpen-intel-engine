export const teams = [
  { team_id: 111, team_name: 'Boston Red Sox', team_abbreviation: 'BOS' },
  { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
]

export const dailyEditionPayload = {
  status: 'ok', reference_date: '2026-09-03', candidates_considered: 9,
  publishable_candidates: 8, errors: 0, empty_reason: null,
  lead_story: {
    team_id: 138, game_pk: 823907,
    claim_evidence: { relief_appearances: [{ name: 'Fixture Cardinals Reliever' }] },
    publication_identity: {
      publication_id: 'daily-edition-2026-09-03-138-823907-fixture',
      data_through: '2026-09-03', generated_at: '2026-09-04T06:09:28Z',
      reference_date: '2026-09-03', game_pk: 823907, team_id: 138,
      semantic_gate_version: 'daily_edition_claim_evidence_v1',
      dashboard_snapshot_id: 2054, dashboard_sync_run_id: 3838,
    },
    package: {
      primary_story: 'lost_game_shape',
      completed_game_context: { team_id: 138, team_name: 'St. Louis Cardinals' },
    },
    drafts: {
      team_story: {
        writer: 'team_story', headline: 'Lead disappeared late',
        body: 'St. Louis carried a lead into the late innings before the bullpen story changed.',
      },
    },
  },
}

export const identity = {
  contract: 'team_board_publication_identity_v1',
  team_id: 111,
  team_abbreviation: 'BOS',
  snapshot_id: 1900,
  sync_run_id: 2900,
  represented_date: '2026-09-02',
  availability_reference_date: '2026-09-03',
  published_at: '2026-09-03T12:01:00Z',
  snapshot_generated_at: '2026-09-03T12:00:00Z',
  dashboard_payload_version: 1,
  publication_authority_contract: 'trusted_dashboard_publication_v1',
  team_board_package_contract: 'trusted_team_board_publication_v1',
  team_board_contract_version: 'team-board-2.0.0',
  team_state_contract: 'team_state_public_v1',
  bullpen_membership_method_version: 'team_board_default_bullpen_membership_v1',
  rest_status_method_version: 'rest_status_v1',
  workload_windows_method_version: 'workload_windows_v1',
  deployment_profile_method_version: 'deployment_profile_v1',
  rotation_impact_method_version: 'rotation_support_pressure_v1',
}

const arm = {
  pitcher_id: 101,
  name: 'Fixture Reliever',
  public_role_read: { key: 'trust_arm', label: 'Trusted Arm', headline: 'Trusted Arm', confidence: 'high' },
  public_labels: {
    role: { key: 'trust_arm', label: 'Trusted Arm' },
    read: { key: 'clean_option', label: 'Clean Option' },
  },
  availability: {
    status: 'Available', label: 'Available', confidence: 'high', data_state: 'fresh',
    short_reason: 'Three days rest with a light recent workload.', reasons: ['Three days rest'], limitations: [],
  },
  last_appearance: { date: '2026-09-01', opponent: 'NYY', pitches: 12, outs_recorded: 3 },
  workload: { pitches_last_7_days: 12, appearances_last_7: 1, days_since_last_appearance: 2 },
  roster_status: { label: 'Active', is_active_mlb: true },
  visibility: { is_visible_by_default: true },
}

const sectionStatus = {
  team_state: { status: 'available' }, active_bullpen: { status: 'available' },
  recent_usage: { status: 'available' }, recently_used_arms: { status: 'available' },
  rest_status: { status: 'available' }, workload_overview: { status: 'available' },
  roles_deployment: { status: 'available' }, rotation_impact: { status: 'available' },
  recent_transactions: { status: 'available' }, recent_relief_work: { status: 'available' },
  performance: { status: 'available' }, what_changed: { status: 'available' },
}

export const teamBoardCore = {
  capability: 'team_board_answer_core',
  contract_version: 'team_board_answer_core_v1',
  publication_identity: identity,
  team: teams[0],
  represented_date: '2026-09-02',
  freshness: { data_through: '2026-09-02', is_current: true, freshness_state: 'current' },
  team_state: { available: true, public_state: 'fresh', public_label: 'Fresh', summary: 'Boston has several rested bullpen options.', data_through: '2026-09-02' },
  summary: 'Boston has several rested bullpen options.',
  active_bullpen: { population_basis: 'fixture', arm_count: 1, arms: [arm] },
  rest_status: { available: true, active_arm_count: 1, rested_arm_count: 1 },
  workload_overview: { windows: [], limitations: [] },
  roles_deployment: { arm_count: 1, roles: [{ role_key: 'trust_arm', label: 'Trusted Arm', arm_count: 1 }] },
  rotation_impact: { read: {} }, roster_context: {},
  operating_state: { team: teams[0], team_state: { public_state: 'fresh', public_label: 'Fresh' } },
  section_status: sectionStatus, limitations: [],
}

export const teamBoardDetails = {
  capability: 'team_board_deferred_details', contract_version: 'team_board_deferred_details_v1',
  publication_identity: identity, represented_date: '2026-09-02',
  recent_usage: { appearances: [], limitations: [] },
  recently_used_arms: { status: 'available', value: 0, summary: 'No recent appearances.' },
  workload_overview: { windows: [], limitations: [] }, roles_deployment: teamBoardCore.roles_deployment,
  recent_transactions: { status: 'available', events: [] }, recent_relief_work: { read: { relief_by_date: [] } },
  game_context: null, performance: { status: 'available' }, what_changed: { state: 'no_change', items: [] },
  section_status: sectionStatus,
}

export const finderPayload = {
  data: [{
    pitcher: { id: 101, mlb_id: 101, full_name: 'Fixture Reliever', team_id: 111, team_name: 'Boston Red Sox', team_abbreviation: 'BOS' },
    availability: { availability_status: 'Available', availability_public_label: 'Available', confidence: 'high', data_state: 'fresh' },
    pitches_last_7_days: 12, days_since_last_appearance: 2, appearances_last_7: 1,
  }],
  meta: { page: 1, total_pages: 2, total_results: 21, limit: 20 },
}

export const discoveryPayload = {
  status: 'ok', result_count: 2,
  groups: [
    { entity_type: 'team', status: 'available', results: [{ entity_type: 'team', id: 111, primary_label: 'Boston Red Sox', secondary_label: 'BOS', metadata: teams[0] }] },
    { entity_type: 'pitcher', status: 'available', results: [{ entity_type: 'pitcher', id: 101, primary_label: 'Fixture Reliever', metadata: { team_name: 'Boston Red Sox', position: 'P' } }] },
    { entity_type: 'matchup', status: 'available', results: [] },
  ],
}

export const pitcherPayload = {
  pitcher: { id: 101, full_name: 'Fixture Reliever', team_id: 111, team_name: 'Boston Red Sox', team_abbreviation: 'BOS', position: 'P', throws: 'R' },
  current_fatigue: { days_since_last_appearance: 2, appearances_last_7: 1, pitches_last_7_days: 12 },
  availability: { availability_status: 'Available', availability_public_label: 'Available', confidence: 'high', data_state: 'fresh', reasons: ['Three days rest'], limitations: [] },
  roster_status: { label: 'Active' }, freshness: { data_through: '2026-09-02', is_current: true },
  pitcher_labels: { role: { label: 'Trusted Arm' }, read: { label: 'Clean Option' } },
  recent_work: { status: 'available', appearances: [] }, recent_work_status: { status: 'available' },
}

export const matchupPayload = {
  game: { game_pk: 999, reference_date: '2026-09-03', game_time_utc: '2026-09-03T23:10:00Z', status: { detailed: 'Scheduled' }, away: teams[1], home: teams[0] },
  comparison: null,
}

export const historyPayload = {
  team: { ...teams[0], team_board_href: '/bullpen?team=BOS' }, season: 2026,
  coverage: { start: '2026-09-01', end: '2026-09-02', is_partial: false }, entries: [],
}

export const shareArtifact = {
  public_id: 'fixture-share', lifecycle_state: 'published', artifact_type: 'team_state', payload_version: 'team-state-1.1.0',
  product_date: '2026-09-02', generated_at: '2026-09-03T12:00:00Z', published_at: '2026-09-03T12:01:00Z',
  team: { team_id: 111, team_name: 'Boston Red Sox', team_abbreviation: 'BOS' },
  team_state: { public_state: 'fresh', public_label: 'Fresh', summary: 'Several rested bullpen options remain.' },
  copy: { why: 'Several rested bullpen options remain.', trust_line: 'Built from completed-game evidence.' },
  freshness: { data_through: '2026-09-02' }, trust: { confidence: 'high' },
  evidence: [{ evidence_id: 'e1', label: 'Rested options', detail: 'Four relievers have at least two days rest.', severity: 'informational' }],
  limitations: [], routes: { methodology_url: '/methodology', data_trust_url: '/trust', team_url: '/bullpen?team=BOS' },
}

export const teamShareProjection = {
  available: true,
  artifact: {
    public_id: 'fixture-team-share', artifact_type: 'team_state', lifecycle_state: 'published',
    product_date: '2026-09-02',
    copy: { description: 'Boston bullpen evidence.', alt_text: 'Published Team State for Boston Red Sox: Fresh.' },
    evidence: [{ category: 'rest', detail: 'Several rested bullpen options remain.' }],
    routes: { share_url: '/share/fixture-team-share' },
    card: {
      card_version: 'team-state-1.2.0', artifact_context: { data_through: '2026-09-02' },
      team: { team_id: 111, canonical_name: 'Boston Red Sox', abbreviation: 'BOS' },
      state: { public_state: 'fresh', public_label: 'Fresh', headline: 'Boston Red Sox bullpen — Fresh', why: 'Several rested bullpen options remain.' },
      limitations: ['Describes observed workload; does not predict usage.'],
    },
  },
}
