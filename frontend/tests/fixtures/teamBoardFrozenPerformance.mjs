export const frozenPerformanceFixture = (through = '2026-09-02') => ({
  capability: 'public_team_performance',
  contract_version: 'public_team_performance_v1',
  status: 'available',
  through,
  window: { policy: 'current_mlb_regular_season_through_represented_date', season: 2026, start: '2026-01-01', through },
  population_basis: 'represented_default_visible_active_bullpen',
  sample: { recorded_outs: 126, innings_pitched: '42.0', minimum_recorded_outs: 30, meets_minimum: true },
  metrics: [
    { key: 'active_bullpen_era', metric_id: 'M-001', label: 'Active Bullpen ERA', value: '3.42', evidence_state: { status: 'complete', reason_codes: [] }, qualification: { status: 'qualified' } },
    { key: 'active_bullpen_whip', metric_id: 'M-002', label: 'Active Bullpen WHIP', value: '1.18', evidence_state: { status: 'complete', reason_codes: [] }, qualification: { status: 'qualified' } },
  ],
  summary: 'Active Bullpen ERA and Active Bullpen WHIP describe recorded results for the current active bullpen.',
  sample_summary: 'Current regular season · 8 active arms · 7 with a sample · 31 relief appearances · 42.0 innings · Through Sep 2, 2026',
  limitations: [],
  capabilities: {
    k_bb_percent: { status: 'unavailable', reason_code: 'source_completeness_not_certified', value: null },
    home_runs_allowed: { status: 'unavailable', reason_code: 'official_comparison_not_publication_bound', value: null },
    inherited_runner_context: { status: 'unavailable', reason_code: 'source_completeness_not_certified', value: null },
  },
})
