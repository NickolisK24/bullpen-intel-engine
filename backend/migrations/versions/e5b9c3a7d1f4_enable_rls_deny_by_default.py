"""SEC-01: deny direct PostgREST table access with row level security.

BaseballOS serves every client through its own API. No client reads or writes
Supabase tables directly, and identity is BaseballOS magic-link auth, not
Supabase Auth. The public-schema tables are therefore a private storage layer,
not a client contract.

This revision:

- enables (not forces) row level security on every application table, by
  explicit name, with no policies. PostgREST client roles see no rows and
  cannot write. The table owner and BYPASSRLS roles are unaffected, as
  PostgreSQL defines;
- revokes the Supabase-default privileges of the ``anon`` and
  ``authenticated`` client roles on those tables and on the sequences they
  own, when those roles exist;
- pins ``search_path`` on the nine BaseballOS functions to ``public, pg_temp``.
  Their bodies are unchanged, and they resolve names exactly as before.

It refuses, changing nothing, if any role that is not a PostgREST client, a
superuser, a BYPASSRLS role or the table owner holds privileges on these
tables. Such a role would be silently restricted by RLS, so the catalog must
prove that no trusted backend role is affected before RLS is enabled.

Revision ID: e5b9c3a7d1f4
Revises: c3e7a1d9f5b2
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5b9c3a7d1f4'
down_revision = 'c3e7a1d9f5b2'
branch_labels = None
depends_on = None


# Every table has the same posture (RLS, no policy). The classification records
# why no category is a direct-access contract; see
# docs/audits/sec-01-supabase-rls-hardening.md.
STRICT_INTERNAL_TABLES = (
    'atomic_publication_cache_handoffs',
    'availability_backtest_results',
    'baseball_date_closure_blockers',
    'baseball_date_closure_versions',
    'baseball_date_closures',
    'canonical_impact_plan_entities',
    'canonical_impact_plan_mutations',
    'canonical_impact_plans',
    'compatibility_write_events',
    'derived_cohort_inputs',
    'editorial_post_history',
    'final_game_mutations',
    'game_ingestion_work_items',
    'game_observation_states',
    'legacy_read_audit_runs',
    'legacy_read_divergences',
    'live_game_mutations',
    'official_pitching_line_repair_executions',
    'pitcher_season_ledger_coverage',
    'play_by_play_processed_games',
    'player_transaction_sync_windows',
    'postgame_processed_games',
    'pregame_context_mutations',
    'provisional_pitching_appearance_states',
    'repair_request_blockers',
    'repair_request_chunks',
    'repair_requests',
    'roster_membership_mutations',
    'share_artifact_generation_audits',
    'source_fetch_attempts',
    'source_observations',
    'source_payload_artifacts',
    'source_subjects',
    'sync_certification_checks',
    'sync_certification_runs',
    'sync_failures',
    'sync_job_attempts',
    'sync_jobs',
    'sync_legacy_transition_states',
    'sync_run_scopes',
    'sync_runs',
    'sync_schedule_attempts',
    'team_state_publication_proofs',
)
USER_PRIVATE_TABLES = (
    'audience_subscribers',
    'traffic_internal_visitors',
    'traffic_page_views',
    'traffic_share_actions',
    'user_followed_teams',
    'users',
)
PUBLIC_PRODUCT_TABLES = (
    'atomic_publication_artifacts',
    'atomic_publication_current',
    'atomic_publications',
    'completed_game_contexts',
    'composed_read_components',
    'composed_read_evidence_citations',
    'composed_reads',
    'dashboard_snapshots',
    'derived_cohort_snapshots',
    'derived_intelligence_cohort_domains',
    'derived_intelligence_cohorts',
    'evidence_citations',
    'evidence_objects',
    'fatigue_scores',
    'final_game_versions',
    'final_pitching_appearance_versions',
    'game_logs',
    'game_pitch_events',
    'game_play_by_play_events',
    'game_pregame_context_versions',
    'intelligence_surface_snapshots',
    'pitchers',
    'player_transaction_versions',
    'player_transactions',
    'prospects',
    'roster_membership_intervals',
    'roster_status_snapshots',
    'scheduled_games',
    'share_artifact_assets',
    'share_artifact_evidence',
    'share_artifact_relations',
    'share_artifacts',
    'slate_games',
    'team_game_pitching_splits',
    'team_progressive_publications',
    'team_public_current_pointers',
    'team_public_publications',
    'tonight_intelligence_snapshots',
    'tonight_publications',
)
METADATA_TABLES = ('alembic_version',)

PROTECTED_TABLES = tuple(sorted(
    STRICT_INTERNAL_TABLES + USER_PRIVATE_TABLES + PUBLIC_PRODUCT_TABLES + METADATA_TABLES
))

# Supabase's PostgREST client roles. Denying them is the purpose of this
# revision. service_role is Supabase's BYPASSRLS admin role and is left as is.
POSTGREST_CLIENT_ROLES = ('anon', 'authenticated')

HARDENED_SEARCH_PATH = 'public, pg_temp'
FUNCTION_SIGNATURES = (
    'baseballos_guard_canonical_selector()',
    'baseballos_guard_final_compatibility()',
    'baseballos_guard_game_observation()',
    'baseballos_guard_pitcher_projection()',
    'baseballos_guard_roster_snapshot()',
    'baseballos_guard_schedule_projection()',
    'baseballos_guard_selector_generation()',
    'baseballos_guard_transaction_projection()',
    'baseballos_selector_resources(text, jsonb)',
)

# Roles RLS would newly restrict: any role holding table or column privileges
# on a protected table that is not a superuser, BYPASSRLS, a member of the
# table owner (PostgreSQL's owner exemption), a predefined pg_* group role, or
# a PostgREST client role.
RESTRICTED_TRUSTED_ROLES_SQL = sa.text("""
    SELECT r.rolname
    FROM pg_roles r
    WHERE NOT r.rolsuper
      AND NOT r.rolbypassrls
      AND r.rolname NOT LIKE 'pg\\_%'
      AND r.rolname <> ALL(CAST(:client_roles AS text[]))
      AND EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND c.relname = ANY(CAST(:tables AS text[]))
          AND NOT pg_has_role(r.oid, c.relowner, 'USAGE')
          AND (
            has_table_privilege(r.oid, c.oid, 'SELECT,INSERT,UPDATE,DELETE')
            OR has_any_column_privilege(r.oid, c.oid, 'SELECT,INSERT,UPDATE')
          )
      )
    ORDER BY r.rolname
""")


def _quoted_tables():
    return ', '.join(f'public."{name}"' for name in PROTECTED_TABLES)


def _owned_sequences(connection):
    # Serial/identity sequences owned by the protected tables, derived from the
    # explicit table list.
    return list(connection.execute(sa.text("""
        SELECT DISTINCT format('%I.%I', sn.nspname, s.relname)
        FROM pg_class s
        JOIN pg_namespace sn ON sn.oid = s.relnamespace
        JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
             AND d.refclassid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_namespace tn ON tn.oid = t.relnamespace
        WHERE s.relkind = 'S' AND tn.nspname = 'public'
          AND t.relname = ANY(CAST(:tables AS text[]))
        ORDER BY 1
    """), {'tables': list(PROTECTED_TABLES)}).scalars())


def _existing_client_roles(connection):
    return list(connection.execute(
        sa.text('SELECT rolname FROM pg_roles WHERE rolname = ANY(CAST(:roles AS text[])) '
                'ORDER BY rolname'),
        {'roles': list(POSTGREST_CLIENT_ROLES)},
    ).scalars())


def _require_every_protected_table(connection):
    present = set(connection.execute(sa.text(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r'"
    )).scalars())
    missing = sorted(set(PROTECTED_TABLES) - present)
    if missing:
        raise RuntimeError(f'sec01_protected_tables_missing: {missing}')


def _require_no_restricted_trusted_role(connection):
    restricted = list(connection.execute(RESTRICTED_TRUSTED_ROLES_SQL, {
        'client_roles': list(POSTGREST_CLIENT_ROLES),
        'tables': list(PROTECTED_TABLES),
    }).scalars())
    if restricted:
        raise RuntimeError(
            'sec01_rls_would_restrict_trusted_roles: '
            f'{restricted}. Each role must own the tables, be BYPASSRLS, or lose '
            'its table privileges before row level security is enabled.'
        )


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != 'postgresql':
        return
    _require_every_protected_table(connection)
    _require_no_restricted_trusted_role(connection)
    for name in PROTECTED_TABLES:
        op.execute(f'ALTER TABLE public."{name}" ENABLE ROW LEVEL SECURITY')
    clients = _existing_client_roles(connection)
    if clients:
        op.execute(f'REVOKE ALL ON TABLE {_quoted_tables()} FROM {", ".join(clients)}')
        sequences = _owned_sequences(connection)
        if sequences:
            op.execute(f'REVOKE ALL ON SEQUENCE {", ".join(sequences)} FROM {", ".join(clients)}')
    for signature in FUNCTION_SIGNATURES:
        op.execute(f'ALTER FUNCTION public.{signature} SET search_path = {HARDENED_SEARCH_PATH}')


def downgrade():
    # Emergency rollback only: this restores the pre-SEC-01 exposure, i.e. the
    # Supabase default grants to the PostgREST client roles with RLS disabled.
    connection = op.get_bind()
    if connection.dialect.name != 'postgresql':
        return
    for signature in FUNCTION_SIGNATURES:
        op.execute(f'ALTER FUNCTION public.{signature} RESET search_path')
    clients = _existing_client_roles(connection)
    if clients:
        op.execute(f'GRANT ALL ON TABLE {_quoted_tables()} TO {", ".join(clients)}')
        sequences = _owned_sequences(connection)
        if sequences:
            op.execute(f'GRANT ALL ON SEQUENCE {", ".join(sequences)} TO {", ".join(clients)}')
    for name in PROTECTED_TABLES:
        op.execute(f'ALTER TABLE public."{name}" DISABLE ROW LEVEL SECURITY')
