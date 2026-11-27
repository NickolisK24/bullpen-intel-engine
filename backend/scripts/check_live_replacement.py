"""Verify a rehearsal restore against the source snapshot still held by its exporter.

The source can stay live. Verify sequence state from the archive, since nextval is
outside MVCC. This evidence cannot be passed to production activation.
"""

import argparse
from contextlib import closing
from pathlib import Path
import re
import subprocess
import tempfile

import psycopg2

from scripts.verify_replacement_copy import manifest


def archived_sequences(archive, pg_restore='pg_restore'):
    toc = subprocess.check_output([pg_restore, '--list', archive], text=True)
    sequence_rows = [line for line in toc.splitlines() if re.match(r'^\d+; \d+ \d+ SEQUENCE SET ', line)]
    with tempfile.NamedTemporaryFile(mode='w') as entries:
        entries.write('\n'.join(sequence_rows) + '\n')
        entries.flush()
        commands = subprocess.check_output(
            [pg_restore, '--use-list', entries.name, '--file=-', archive], text=True
        )
    states = {}
    for name, value, called in re.findall(
        r"^SELECT pg_catalog\.setval\('([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)', (-?\d+), (true|false)\);$",
        commands, re.MULTILINE,
    ):
        states[name] = (int(value), called == 'true')
    if len(states) != len(sequence_rows) or not states:
        raise ValueError('Could not verify every archived BaseballOS sequence')
    return states


def check(source, destination, snapshot, archive, pg_restore='pg_restore'):
    original, before = manifest(source, snapshot=snapshot)
    target, after = manifest(destination)
    if original == target:
        raise ValueError('Expected an independently initialized destination')
    archived = archived_sequences(archive, pg_restore)
    source_sequences = {k for k, v in before.items() if isinstance(v, tuple) and isinstance(v[-1], bool)}
    if set(archived) != source_sequences:
        raise ValueError('Source and archived sequence inventory differ')
    before.update(archived)
    differences = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    if differences:
        raise ValueError('Restore differs in ' + ', '.join(differences))
    return len(archived)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-service', required=True)
    parser.add_argument('--destination-service', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--archive', required=True, type=Path)
    args = parser.parse_args()
    with closing(psycopg2.connect(service=args.source_service, sslmode='verify-full')) as source:
        with closing(psycopg2.connect(service=args.destination_service, sslmode='verify-full')) as dst:
            count = check(source, dst, args.snapshot, args.archive)
    print(f'Live rehearsal snapshot matched, including {count} archived sequences.')
