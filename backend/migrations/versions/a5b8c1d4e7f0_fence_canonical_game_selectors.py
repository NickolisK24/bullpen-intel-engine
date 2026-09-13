"""Fence canonical game selectors through cohort completion.

Revision ID: a5b8c1d4e7f0
Revises: f4a7b0c3d6e9
"""
from alembic import op
import sqlalchemy as sa

revision = 'a5b8c1d4e7f0'
down_revision = 'f4a7b0c3d6e9'
branch_labels = None
depends_on = None

TABLES = ('final_game_versions', 'final_pitching_appearance_versions',
          'provisional_pitching_appearance_states', 'game_pregame_context_versions',
          'roster_membership_intervals')

GUARD = """
CREATE OR REPLACE FUNCTION baseballos_guard_canonical_selector() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE old_game bigint; new_game bigint; game bigint;
        before_row jsonb; after_row jsonb; subject integer; domain integer;
BEGIN
  IF TG_OP = 'TRUNCATE' THEN
    RAISE EXCEPTION 'Canonical selector truncation is not a governed writer operation'
      USING ERRCODE='40001';
  END IF;
  IF TG_OP <> 'INSERT' THEN before_row := to_jsonb(OLD); END IF;
  IF TG_OP <> 'DELETE' THEN after_row := to_jsonb(NEW); END IF;
  IF TG_TABLE_NAME = 'roster_membership_intervals' THEN
    FOR subject IN SELECT DISTINCT value FROM unnest(ARRAY[
      (before_row->>'team_id')::integer,(after_row->>'team_id')::integer]) value
      WHERE value IS NOT NULL ORDER BY value LOOP
      IF NOT pg_try_advisory_xact_lock(505000000::bigint + subject) THEN
        RAISE EXCEPTION 'Canonical roster selector fence conflict: %', subject USING ERRCODE='40001';
      END IF;
    END LOOP;
    domain := 510000004;
  ELSE
    old_game := (before_row->>'game_pk')::bigint;
    new_game := (after_row->>'game_pk')::bigint;
    IF TG_TABLE_NAME = 'final_pitching_appearance_versions' THEN domain := 510000005; END IF;
  END IF;
  FOR game IN SELECT DISTINCT value FROM unnest(ARRAY[old_game,new_game]) value
              WHERE value IS NOT NULL ORDER BY value LOOP
    -- Identical one-bigint resource to R2 lock_game. A trigger can run after
    -- row locks: never wait in reverse order; reject the transaction for retry.
    IF NOT pg_try_advisory_xact_lock(507000000000::bigint + game) THEN
      RAISE EXCEPTION 'Canonical game selector fence conflict: %', game
        USING ERRCODE='40001';
    END IF;
  END LOOP;
  IF domain IS NOT NULL THEN
    FOR subject IN SELECT DISTINCT value FROM unnest(ARRAY[
      (before_row->>'pitcher_id')::integer,(after_row->>'pitcher_id')::integer]) value
      WHERE value IS NOT NULL ORDER BY value LOOP
      IF NOT pg_try_advisory_xact_lock(domain, subject) THEN
        RAISE EXCEPTION 'Canonical pitcher selector fence conflict: %/%', domain, subject USING ERRCODE='40001';
      END IF;
    END LOOP;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
"""


def install(connection):
    connection.execute(sa.text(GUARD))
    for table in TABLES:
        connection.execute(sa.text(f'''
            CREATE TRIGGER canonical_selector_write BEFORE INSERT OR UPDATE OR DELETE
            ON {table} FOR EACH ROW EXECUTE FUNCTION baseballos_guard_canonical_selector();
            CREATE TRIGGER canonical_selector_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION baseballos_guard_canonical_selector();
        '''))


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        install(connection)


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION baseballos_guard_canonical_selector() CASCADE')
