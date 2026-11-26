-- Preview only. The result contains proposed SQL. Run with migration administrator catalog visibility.
WITH governed(name) AS (
    VALUES ('alembic_version'),
           ('atomic_publication_artifacts'),
           ('atomic_publication_cache_handoffs'),
           ('atomic_publication_current'),
           ('atomic_publications'),
           ('availability_backtest_results'),
           ('baseball_date_closure_blockers'),
           ('baseball_date_closure_versions'),
           ('baseball_date_closures'),
           ('canonical_impact_plan_entities'),
           ('canonical_impact_plan_mutations'),
           ('canonical_impact_plans'),
           ('compatibility_write_events'),
           ('completed_game_contexts'),
           ('composed_read_components'),
           ('composed_read_evidence_citations'),
           ('composed_reads'),
           ('dashboard_snapshots'),
           ('derived_cohort_inputs'),
           ('derived_cohort_snapshots'),
           ('derived_intelligence_cohort_domains'),
           ('derived_intelligence_cohorts'),
           ('evidence_citations'),
           ('evidence_objects'),
           ('fatigue_scores'),
           ('final_game_mutations'),
           ('final_game_versions'),
           ('final_pitching_appearance_versions'),
           ('game_ingestion_work_items'),
           ('game_logs'),
           ('game_observation_states'),
           ('game_pitch_events'),
           ('game_play_by_play_events'),
           ('game_pregame_context_versions'),
           ('intelligence_surface_snapshots'),
           ('legacy_read_audit_runs'),
           ('legacy_read_divergences'),
           ('live_game_mutations'),
           ('official_pitching_line_repair_executions'),
           ('pitcher_season_ledger_coverage'),
           ('pitchers'),
           ('play_by_play_processed_games'),
           ('player_transaction_sync_windows'),
           ('player_transaction_versions'),
           ('player_transactions'),
           ('postgame_processed_games'),
           ('pregame_context_mutations'),
           ('provisional_pitching_appearance_states'),
           ('repair_request_blockers'),
           ('repair_request_chunks'),
           ('repair_requests'),
           ('roster_membership_intervals'),
           ('roster_membership_mutations'),
           ('roster_status_snapshots'),
           ('scheduled_games'),
           ('share_artifact_assets'),
           ('share_artifact_evidence'),
           ('share_artifact_generation_audits'),
           ('share_artifact_relations'),
           ('share_artifacts'),
           ('slate_games'),
           ('source_fetch_attempts'),
           ('source_observations'),
           ('source_payload_artifacts'),
           ('source_subjects'),
           ('sync_certification_checks'),
           ('sync_certification_runs'),
           ('sync_failures'),
           ('sync_job_attempts'),
           ('sync_jobs'),
           ('sync_legacy_transition_states'),
           ('sync_run_scopes'),
           ('sync_runs'),
           ('sync_schedule_attempts'),
           ('team_game_pitching_splits'),
           ('team_progressive_publications'),
           ('team_public_current_pointers'),
           ('team_public_publications'),
           ('team_state_publication_proofs'),
           ('tonight_intelligence_snapshots'),
           ('tonight_publications')
), targets AS (
    SELECT c.oid, c.relacl, c.relname, 'TABLE' AS kind
    FROM governed g JOIN pg_class c ON c.relname = g.name
    WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p')
), objects AS (
    SELECT * FROM targets
    UNION
    SELECT s.oid, s.relacl, s.relname, 'SEQUENCE'
    FROM targets t JOIN pg_depend d ON d.refclassid = 'pg_class'::regclass AND d.refobjid = t.oid
    JOIN pg_class s ON d.classid = 'pg_class'::regclass AND s.oid = d.objid
    WHERE d.deptype IN ('a','i') AND d.refobjsubid > 0 AND s.relkind = 'S'
      AND s.relnamespace = 'public'::regnamespace
), grants AS (
    SELECT o.kind, o.relname, NULL::name AS col, a.*
    FROM objects o CROSS JOIN LATERAL aclexplode(o.relacl) a
    WHERE (o.kind = 'TABLE' AND a.privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'))
       OR (o.kind = 'SEQUENCE' AND a.privilege_type IN ('UPDATE','USAGE'))
    UNION ALL
    SELECT t.kind, t.relname, att.attname, a.*
    FROM targets t JOIN pg_attribute att ON att.attrelid = t.oid
    CROSS JOIN LATERAL aclexplode(att.attacl) a
    WHERE att.attnum > 0 AND NOT att.attisdropped AND a.privilege_type IN ('INSERT','UPDATE','REFERENCES')
)
SELECT kind, relname, col, grantor::regrole::text AS original_grantor, is_grantable,
       format('REVOKE %s%s ON %s public.%I FROM service_role RESTRICT;', privilege_type,
              CASE WHEN col IS NULL THEN '' ELSE format(' (%I)',col) END, kind, relname) AS proposed_sql
FROM grants WHERE grantee = 'service_role'::regrole
ORDER BY kind, relname, col NULLS FIRST, privilege_type;
