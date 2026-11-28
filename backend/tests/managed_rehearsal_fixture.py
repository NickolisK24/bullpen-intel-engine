"""Run the managed copy and product checks on two disposable PostgreSQL servers."""

from contextlib import closing
import os
from pathlib import Path
import tempfile

import psycopg2

from scripts.managed_replacement_rehearsal import SOURCE_USER, cluster, rehearse
from sync_v3.rehearse import isolated_cluster
from tests.production_writer_rehearsal import REVISION, exercise


def run():
    bin_dir = os.environ['SYNC_V3_TEST_PG_BIN']
    with isolated_cluster(bin_dir) as (source_owner, _), isolated_cluster(bin_dir) as (target_owner, _):
        def restored_product(host):
            source = dict(host=host, port=5432, user='postgres', dbname='postgres')
            target = dict(source, host=target_owner.info.host)
            with closing(psycopg2.connect(**source)) as admin, admin, admin.cursor() as cur:
                cur.execute('CREATE ROLE baseballos_v3_export LOGIN BYPASSRLS')
                cur.execute('GRANT pg_read_all_data TO baseballos_v3_export')
                cur.execute('GRANT EXECUTE ON FUNCTION pg_control_system() TO baseballos_v3_export')
            source['user'] = SOURCE_USER
            with target_owner, target_owner.cursor() as cur:
                cur.execute('CREATE ROLE fixture_setup LOGIN SUPERUSER')
            with closing(psycopg2.connect(**dict(target, user='fixture_setup'))) as bootstrap, bootstrap, bootstrap.cursor() as cur:
                cur.execute('ALTER ROLE rehearsal_owner RENAME TO postgres')
            with closing(psycopg2.connect(**target)) as bootstrap, bootstrap, bootstrap.cursor() as cur:
                cur.execute('DROP ROLE fixture_setup')
                cur.execute('ALTER ROLE sync_v3_worker RENAME TO fixture_worker')
                cur.execute('ALTER ROLE sync_v3_reviewer RENAME TO fixture_reviewer')
                cur.execute('CREATE ROLE anon')
                cur.execute('CREATE ROLE authenticated')
                cur.execute('CREATE ROLE service_role BYPASSRLS')
            # The fixture disables PUBLIC CONNECT on both clusters.
            with closing(psycopg2.connect(**dict(source, user='postgres'))) as admin, admin, admin.cursor() as cur:
                cur.execute('GRANT CONNECT ON DATABASE postgres TO baseballos_v3_export')
            with closing(psycopg2.connect(**source)) as reader, closing(psycopg2.connect(**target)) as dst:
                original, replacement = cluster(reader, SOURCE_USER), cluster(dst, 'postgres')
            with tempfile.TemporaryDirectory() as tmp:
                rehearse(source, target, original, replacement, Path(tmp), REVISION,
                         lambda stage, **metrics: print(stage, metrics, flush=True))
        exercise(source_owner.info.host, restored_product=restored_product)


if __name__ == '__main__':
    run()
