"""Coordinate selector writers with cohort completion, including old binaries.

Revision ID: f4a7b0c3d6e9
Revises: e3f6a9b2c5d8
"""
from alembic import op
import sqlalchemy as sa

revision = 'f4a7b0c3d6e9'
down_revision = 'e3f6a9b2c5d8'
branch_labels = None
depends_on = None


POSTGRES_GUARDS = r"""
CREATE INDEX ix_selector_sidecar_source_snapshot ON dashboard_snapshots
  ((payload::jsonb->'source'->>'snapshot_id'))
  WHERE snapshot_type='team_board_delta' AND source ~ '^tb_delta:team:[0-9]+$';
CREATE INDEX ix_selector_sidecar_source_artifact ON dashboard_snapshots
  ((payload::jsonb->'source'->>'artifact_id'))
  WHERE snapshot_type='team_board_delta' AND source ~ '^tb_delta:team:[0-9]+$';
CREATE FUNCTION baseballos_selector_resources(resource_table text, value jsonb)
RETURNS TABLE(domain integer, subject integer)
LANGUAGE plpgsql AS $$
DECLARE authority_group integer; offset_key integer; item text; field_name text;
BEGIN
  IF value IS NULL THEN RETURN; END IF;
  IF resource_table = 'dashboard_snapshots' THEN
    IF value->>'snapshot_type' = 'bullpen_dashboard' THEN
      RETURN QUERY SELECT 510000001, 0;
    ELSIF value->>'snapshot_type' = 'team_board_delta' THEN
      item := substring(value->>'source' from '^tb_delta:team:([0-9]+)$');
      IF item IS NOT NULL THEN
        RETURN QUERY SELECT 510000002, item::integer;
      END IF;
    END IF;
    -- Legacy rest fallback resolves sidecar source IDs directly, without a
    -- snapshot-type predicate. Fence the actual references, including an
    -- unusual historical source type or a previously missing source row.
    RETURN QUERY SELECT DISTINCT 510000002,
      substring(s.source from '^tb_delta:team:([0-9]+)$')::integer
      FROM dashboard_snapshots s WHERE s.snapshot_type='team_board_delta'
      AND s.source ~ '^tb_delta:team:[0-9]+$'
      AND s.payload::jsonb->'source'->>'snapshot_id'=value->>'id';
  ELSIF resource_table = 'share_artifacts' THEN
    RETURN QUERY SELECT 510000002, (value->>'team_id')::integer;
    -- Use the actual sidecar references as well as the artifact's team. Do not
    -- assume a malformed/historical cross-team reference is impossible.
    RETURN QUERY SELECT DISTINCT 510000002,
      substring(s.source from '^tb_delta:team:([0-9]+)$')::integer
      FROM dashboard_snapshots s WHERE s.snapshot_type='team_board_delta'
      AND s.source ~ '^tb_delta:team:[0-9]+$'
      AND s.payload::jsonb->'source'->>'artifact_id'=value->>'id';
  ELSIF resource_table IN ('atomic_publications', 'atomic_publication_current',
                          'atomic_publication_artifacts') THEN
    RETURN QUERY SELECT 510000003, 0;
  ELSIF resource_table = 'derived_cohort_snapshots' THEN
    IF EXISTS (SELECT 1 FROM atomic_publication_artifacts a
               WHERE a.source_snapshot_id=(value->>'id')::integer) THEN
      RETURN QUERY SELECT 510000003, 0;
    END IF;
  ELSIF resource_table = 'derived_intelligence_cohorts'
        AND value->>'status' IN ('complete', 'partial') THEN
    authority_group := CASE value->>'authority_class'
      WHEN 'live' THEN 0 WHEN 'final' THEN 1 WHEN 'corrected_final' THEN 1
      WHEN 'roster_authoritative' THEN 2 WHEN 'pregame_authoritative' THEN 3 END;
    IF authority_group IS NULL THEN
      RAISE EXCEPTION 'Unknown predecessor authority' USING ERRCODE='22023';
    END IF;
    FOR offset_key IN 0..2 LOOP
      field_name := (ARRAY['affected_game_ids_json','affected_team_ids_json',
                           'affected_pitcher_ids_json'])[offset_key+1];
      FOR item IN SELECT jsonb_array_elements_text(value->field_name) LOOP
        RETURN QUERY SELECT 510000100+authority_group*3+offset_key, item::integer;
      END LOOP;
    END LOOP;
  END IF;
END $$;

CREATE FUNCTION baseballos_guard_selector_generation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE previous_value jsonb; next_value jsonb; resource record;
BEGIN
  IF TG_OP='TRUNCATE' THEN
    RAISE EXCEPTION 'Selector tables require scoped writes, not TRUNCATE'
      USING ERRCODE='55000';
  END IF;
  IF TG_OP <> 'INSERT' THEN previous_value := to_jsonb(OLD); END IF;
  IF TG_OP <> 'DELETE' THEN next_value := to_jsonb(NEW); END IF;
  FOR resource IN
    SELECT * FROM baseballos_selector_resources(TG_TABLE_NAME, previous_value)
    UNION SELECT * FROM baseballos_selector_resources(TG_TABLE_NAME, next_value)
    ORDER BY 1,2
  LOOP
    -- Row-level triggers can run after a writer obtained a row/R2 lock. Never
    -- wait in that reverse order. Abort the entire statement/transaction with
    -- a retryable serialization conflict if a completion is already fenced.
    IF resource.subject IS NULL OR NOT pg_try_advisory_xact_lock(resource.domain, resource.subject) THEN
      RAISE EXCEPTION 'Selector generation fence conflict: %/%', resource.domain, resource.subject
        USING ERRCODE='40001';
    END IF;
  END LOOP;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
"""

TABLES = ('dashboard_snapshots', 'share_artifacts', 'atomic_publications',
          'atomic_publication_current', 'atomic_publication_artifacts',
          'derived_intelligence_cohorts', 'derived_cohort_snapshots')


def install(connection):
    connection.execute(sa.text(POSTGRES_GUARDS))
    for table in TABLES:
        connection.execute(sa.text(f'''
            CREATE TRIGGER selector_generation_write BEFORE INSERT OR UPDATE OR DELETE
            ON {table} FOR EACH ROW EXECUTE FUNCTION baseballos_guard_selector_generation();
            CREATE TRIGGER selector_generation_truncate BEFORE TRUNCATE
            ON {table} FOR EACH STATEMENT EXECUTE FUNCTION baseballos_guard_selector_generation();
        '''))


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        install(connection)


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION baseballos_guard_selector_generation() CASCADE')
        op.execute('DROP FUNCTION baseballos_selector_resources(text,jsonb)')
        op.execute('DROP INDEX ix_selector_sidecar_source_snapshot')
        op.execute('DROP INDEX ix_selector_sidecar_source_artifact')
