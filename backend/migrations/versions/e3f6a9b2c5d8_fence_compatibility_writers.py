"""Fence compatibility writers, including older deployed processes.

Revision ID: e3f6a9b2c5d8
Revises: d2e5f8a1b4c7
"""

from alembic import op
import sqlalchemy as sa

revision = 'e3f6a9b2c5d8'
down_revision = 'd2e5f8a1b4c7'
branch_labels = None
depends_on = None


POSTGRES_GUARDS = r"""
CREATE FUNCTION baseballos_guard_pitcher_projection() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  owner_team text := current_setting('baseballos.roster_owner', true);
  protected text[] := ARRAY[
    'team_id','team_name','team_abbreviation','active',
    'team_assignment_status','team_assignment_source','team_assignment_updated_at',
    'roster_status','roster_status_source','roster_status_raw_code',
    'roster_status_raw_description','roster_status_updated_at'];
  old_fields jsonb;
  new_fields jsonb;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM roster_membership_intervals r
    WHERE r.pitcher_id=OLD.id AND r.is_current_version AND NOT r.is_void
      AND r.effective_end_date IS NULL
      AND r.membership_type IN ('active_roster','forty_man_roster')
  ) THEN RETURN NEW; END IF;
  IF owner_team IS NOT NULL AND owner_team <> '' AND NEW.team_id::text=owner_team
    THEN RETURN NEW; END IF;
  SELECT jsonb_object_agg(key,value) INTO old_fields
    FROM jsonb_each(to_jsonb(OLD)) WHERE key=ANY(protected);
  SELECT jsonb_object_agg(key,value) INTO new_fields
    FROM jsonb_each(to_jsonb(NEW)) WHERE key=ANY(protected);
  IF (old_fields - ARRAY['team_assignment_updated_at','roster_status_updated_at'])
      IS DISTINCT FROM
     (new_fields - ARRAY['team_assignment_updated_at','roster_status_updated_at']) THEN
    INSERT INTO compatibility_write_events(resource_type,resource_key,outcome,details_json,created_at)
    VALUES ('pitcher_projection',OLD.id::text,'stale_suppressed',
      json_build_object('retained_team_id',OLD.team_id,'incoming_team_id',NEW.team_id,
        'incoming_source',NEW.team_assignment_source),clock_timestamp() AT TIME ZONE 'UTC');
  END IF;
  NEW := jsonb_populate_record(NEW, old_fields);
  RETURN NEW;
END $$;

CREATE TRIGGER baseballos_pitcher_projection_fence
BEFORE UPDATE ON pitchers FOR EACH ROW EXECUTE FUNCTION baseballos_guard_pitcher_projection();

CREATE FUNCTION baseballos_guard_roster_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE owner_team text := current_setting('baseballos.roster_owner', true);
BEGIN
  -- Older binaries already hold the snapshot row here. Do not wait for
  -- a pitcher row held by a new owner following pitcher -> snapshot order.
  BEGIN
    PERFORM id FROM pitchers WHERE id=NEW.pitcher_id FOR UPDATE NOWAIT;
  EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION 'roster semantic fence busy: %',NEW.pitcher_id USING ERRCODE='55P03';
  END;
  IF OLD.active_roster_observation_id IS NULL OR OLD.forty_man_roster_observation_id IS NULL
    THEN RETURN NEW; END IF;
  IF owner_team IS NOT NULL AND owner_team <> '' AND NEW.team_id::text=owner_team
    THEN RETURN NEW; END IF;
  IF (to_jsonb(OLD) - ARRAY['updated_at','sync_run_id']) IS DISTINCT FROM
     (to_jsonb(NEW) - ARRAY['updated_at','sync_run_id']) THEN
    INSERT INTO compatibility_write_events(resource_type,resource_key,outcome,details_json,created_at)
    VALUES ('roster_snapshot',OLD.id::text,'stale_suppressed',
      json_build_object('pitcher_id',OLD.pitcher_id,'snapshot_date',OLD.snapshot_date),
      clock_timestamp() AT TIME ZONE 'UTC');
  END IF;
  RETURN OLD;
END $$;

CREATE TRIGGER baseballos_roster_snapshot_fence
BEFORE UPDATE ON roster_status_snapshots FOR EACH ROW EXECUTE FUNCTION baseballos_guard_roster_snapshot();

CREATE FUNCTION baseballos_guard_final_compatibility() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  target_game bigint;
  owner_game text := current_setting('baseballos.final_game_owner', true);
BEGIN
  IF TG_OP='DELETE' THEN target_game := OLD.mlb_game_pk;
  ELSE target_game := NEW.mlb_game_pk; END IF;
  -- Old binaries enter here after taking their row lock. Never wait on an
  -- advisory lock in that order: fail retryably instead of creating a cycle.
  IF NOT pg_try_advisory_xact_lock(507000000000 + target_game) THEN
    RAISE EXCEPTION 'game semantic fence busy: %', target_game USING ERRCODE='55P03';
  END IF;
  IF owner_game=target_game::text OR NOT EXISTS (
    SELECT 1 FROM final_game_versions WHERE game_pk=target_game AND is_current
  ) THEN
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
  END IF;
  IF TG_OP='INSERT' THEN
    RAISE EXCEPTION 'final owner excludes compatibility insertion for game %',target_game
      USING ERRCODE='55000';
  END IF;
  IF TG_OP='UPDATE' AND to_jsonb(NEW)=to_jsonb(OLD) THEN RETURN NEW; END IF;
  INSERT INTO compatibility_write_events(resource_type,resource_key,outcome,details_json,created_at)
  VALUES ('final_compatibility',target_game::text,'final_superseded',
    json_build_object('table',TG_TABLE_NAME,'operation',TG_OP),
    clock_timestamp() AT TIME ZONE 'UTC');
  IF TG_OP='DELETE' THEN RETURN NULL; ELSE RETURN OLD; END IF;
END $$;

CREATE TRIGGER baseballos_final_compatibility_fence
BEFORE INSERT OR UPDATE OR DELETE ON game_logs
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_final_compatibility();
CREATE TRIGGER baseballos_final_compatibility_fence
BEFORE INSERT OR UPDATE OR DELETE ON game_play_by_play_events
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_final_compatibility();
CREATE TRIGGER baseballos_final_compatibility_fence
BEFORE INSERT OR UPDATE OR DELETE ON game_pitch_events
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_final_compatibility();
CREATE TRIGGER baseballos_final_compatibility_fence
BEFORE INSERT OR UPDATE OR DELETE ON play_by_play_processed_games
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_final_compatibility();
CREATE TRIGGER baseballos_final_compatibility_fence
BEFORE INSERT OR UPDATE OR DELETE ON postgame_processed_games
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_final_compatibility();

CREATE FUNCTION baseballos_guard_game_observation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE validated_owner boolean :=
  current_setting('baseballos.observation_owner',true)=NEW.mlb_game_pk::text;
BEGIN
  IF NOT pg_try_advisory_xact_lock(507000000000 + NEW.mlb_game_pk) THEN
    RAISE EXCEPTION 'game semantic fence busy: %',NEW.mlb_game_pk USING ERRCODE='55P03';
  END IF;
  IF TG_OP='INSERT' THEN
    IF NEW.finality_state<>'final_and_usable' AND EXISTS (
      SELECT 1 FROM final_game_versions WHERE game_pk=NEW.mlb_game_pk AND is_current
    ) THEN
      RAISE EXCEPTION 'final owner excludes provisional observation for game %',NEW.mlb_game_pk
        USING ERRCODE='55000';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.observation_fingerprint=OLD.observation_fingerprint THEN RETURN NEW; END IF;
  IF NEW.previous_observation_fingerprint IS DISTINCT FROM OLD.observation_fingerprint
    OR NEW.source_authority IS DISTINCT FROM OLD.source_authority
    OR (OLD.finality_state='final_and_usable' AND NEW.finality_state<>'final_and_usable')
    OR (NEW.finality_state<>'final_and_usable' AND EXISTS (
      SELECT 1 FROM final_game_versions WHERE game_pk=NEW.mlb_game_pk AND is_current))
    OR NEW.source_observed_at IS NULL
    OR (OLD.source_observed_at IS NOT NULL AND NEW.source_observed_at<OLD.source_observed_at)
    OR (NEW.source_observed_at=OLD.source_observed_at AND NOT coalesce(validated_owner,false))
  THEN
    INSERT INTO compatibility_write_events(resource_type,resource_key,outcome,details_json,created_at)
    VALUES ('game_observation',NEW.mlb_game_pk::text,'stale_suppressed',
      json_build_object('retained_observation_id',OLD.source_observation_id,
        'incoming_observation_id',NEW.source_observation_id),clock_timestamp() AT TIME ZONE 'UTC');
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER baseballos_game_observation_fence
BEFORE INSERT OR UPDATE ON game_observation_states
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_game_observation();

CREATE FUNCTION baseballos_guard_transaction_projection() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE target_key text;
BEGIN
  IF TG_OP='DELETE' THEN target_key:=OLD.transaction_key;
  ELSE target_key:=NEW.transaction_key; END IF;
  IF NOT pg_try_advisory_xact_lock(509000000,hashtext(target_key)) THEN
    RAISE EXCEPTION 'transaction semantic fence busy: %',target_key USING ERRCODE='55P03';
  END IF;
  IF TG_OP='INSERT' OR coalesce(OLD.current_version_number,0)=0
      OR current_setting('baseballos.transaction_owner',true)=target_key THEN
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
  END IF;
  IF TG_OP='UPDATE' AND to_jsonb(OLD)=to_jsonb(NEW) THEN RETURN NEW; END IF;
  INSERT INTO compatibility_write_events(resource_type,resource_key,outcome,details_json,created_at)
  VALUES ('transaction',left(target_key,100),'stale_suppressed',
    json_build_object('current_version',OLD.current_version_number,'operation',TG_OP),
    clock_timestamp() AT TIME ZONE 'UTC');
  IF TG_OP='DELETE' THEN RETURN NULL; ELSE RETURN OLD; END IF;
END $$;
CREATE TRIGGER baseballos_transaction_projection_fence
BEFORE INSERT OR UPDATE OR DELETE ON player_transactions
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_transaction_projection();

CREATE FUNCTION baseballos_guard_schedule_projection() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE owners jsonb := coalesce(nullif(current_setting('baseballos.schedule_owners',true),''),'[]')::jsonb;
BEGIN
  IF NOT pg_try_advisory_xact_lock(507000000000 + NEW.game_pk) THEN
    RAISE EXCEPTION 'game semantic fence busy: %',NEW.game_pk USING ERRCODE='55P03';
  END IF;
  IF owners ? NEW.game_pk::text OR NOT EXISTS (
    SELECT 1 FROM scheduled_games WHERE game_pk=NEW.game_pk AND operational_state IS NOT NULL
  ) THEN RETURN NEW; END IF;
  IF TG_OP='INSERT' THEN
    RAISE EXCEPTION 'schedule owner excludes compatibility insertion for game %',NEW.game_pk USING ERRCODE='55000';
  END IF;
  IF (to_jsonb(OLD)-ARRAY['updated_at','last_synced']) IS DISTINCT FROM
     (to_jsonb(NEW)-ARRAY['updated_at','last_synced']) THEN
    INSERT INTO compatibility_write_events(resource_type,resource_key,outcome,details_json,created_at)
    VALUES ('schedule',NEW.game_pk::text,'stale_suppressed',
      json_build_object('table',TG_TABLE_NAME),clock_timestamp() AT TIME ZONE 'UTC');
  END IF;
  RETURN OLD;
END $$;
CREATE TRIGGER baseballos_schedule_projection_fence
BEFORE INSERT OR UPDATE ON scheduled_games
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_schedule_projection();
CREATE TRIGGER baseballos_schedule_projection_fence
BEFORE INSERT OR UPDATE ON slate_games
FOR EACH ROW EXECUTE FUNCTION baseballos_guard_schedule_projection();
"""


def upgrade():
    # A repeated fact set is a later event revision, not a duplicate version.
    # Legacy adoption may retain an explicitly unattributed pre-SP baseline.
    with op.batch_alter_table('player_transaction_versions') as batch:
        batch.drop_constraint('uq_player_transaction_versions_transaction_fingerprint', type_='unique')
        batch.alter_column('source_observation_id', existing_type=sa.Integer(), nullable=True)
        batch.create_index('ix_player_transaction_versions_transaction_fingerprint',
                           ['player_transaction_id', 'fact_fingerprint'])
    op.create_table(
        'compatibility_write_events',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), primary_key=True),
        sa.Column('resource_type', sa.String(40), nullable=False),
        sa.Column('resource_key', sa.String(100), nullable=False),
        sa.Column('outcome', sa.String(60), nullable=False),
        sa.Column('details_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_compatibility_write_events_created', 'compatibility_write_events', ['created_at'])
    op.create_index('ix_compatibility_write_events_resource', 'compatibility_write_events',
                    ['resource_type', 'resource_key', 'created_at'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(POSTGRES_GUARDS)


def downgrade():
    connection = op.get_bind()
    incompatible = connection.execute(sa.text('''
        SELECT EXISTS (SELECT 1 FROM compatibility_write_events)
          OR EXISTS (SELECT 1 FROM player_transaction_versions WHERE source_observation_id IS NULL)
          OR EXISTS (SELECT 1 FROM player_transaction_versions
                     GROUP BY player_transaction_id, fact_fingerprint HAVING count(*) > 1)
    ''')).scalar()
    if incompatible:
        raise RuntimeError('Writer ownership downgrade would discard retained history; explicit recovery is required')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER baseballos_schedule_projection_fence ON scheduled_games')
        op.execute('DROP TRIGGER baseballos_schedule_projection_fence ON slate_games')
        op.execute('DROP FUNCTION baseballos_guard_schedule_projection()')
        op.execute('DROP TRIGGER baseballos_transaction_projection_fence ON player_transactions')
        op.execute('DROP FUNCTION baseballos_guard_transaction_projection()')
        op.execute('DROP TRIGGER baseballos_game_observation_fence ON game_observation_states')
        op.execute('DROP FUNCTION baseballos_guard_game_observation()')
        for table in ('game_logs', 'game_play_by_play_events', 'game_pitch_events', 'play_by_play_processed_games',
                      'postgame_processed_games'):
            op.execute(f'DROP TRIGGER baseballos_final_compatibility_fence ON {table}')
        op.execute('DROP FUNCTION baseballos_guard_final_compatibility()')
        op.execute('DROP TRIGGER baseballos_roster_snapshot_fence ON roster_status_snapshots')
        op.execute('DROP FUNCTION baseballos_guard_roster_snapshot()')
        op.execute('DROP TRIGGER baseballos_pitcher_projection_fence ON pitchers')
        op.execute('DROP FUNCTION baseballos_guard_pitcher_projection()')
    op.drop_table('compatibility_write_events')
    with op.batch_alter_table('player_transaction_versions') as batch:
        batch.drop_index('ix_player_transaction_versions_transaction_fingerprint')
        batch.alter_column('source_observation_id', existing_type=sa.Integer(), nullable=False)
        batch.create_unique_constraint('uq_player_transaction_versions_transaction_fingerprint',
                                        ['player_transaction_id', 'fact_fingerprint'])
