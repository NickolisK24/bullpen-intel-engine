"""Durable, atomic summary output for the production sync runners.

Both runners already print one complete JSON summary object to stdout. That
stream is mixed with logging, so it is fine for a human reading a workflow log
and wrong as the source of durable evidence — an evidence file must never be
produced by parsing interleaved output with shell tools.

``write_summary`` writes the *same object* to a file: deterministic, sorted
keys, atomically replaced, with the temporary file removed on every path. The
caller keeps its stdout contract exactly as it was.

Failure is loud. A runner that was asked for durable evidence and could not
produce it must not exit zero, because a missing artifact and a clean run would
otherwise be indistinguishable.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class SummaryOutputError(RuntimeError):
    """Raised when a requested summary file could not be written.

    Carries a safe classification only. The originating message may contain a
    filesystem path, so it is deliberately not propagated into the report; the
    caller reports the class and the runner exits non-zero.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def serialize_summary(summary) -> str:
    """Render the summary exactly as the runners render it to stdout."""
    return json.dumps(summary, sort_keys=True, default=str)


def write_summary(summary, path) -> None:
    """Atomically write ``summary`` as deterministic JSON to ``path``.

    The temporary file is created in the destination directory so the final
    ``os.replace`` is a same-filesystem rename, which is atomic: a reader can
    only ever observe the complete previous file or the complete new one, never
    a half-written artifact.
    """
    if not path:
        raise SummaryOutputError('summary_output_path_missing')

    destination = Path(path)
    payload = serialize_summary(summary)

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise SummaryOutputError('summary_output_directory_unavailable') from None

    handle = None
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=str(destination.parent),
            prefix=f'.{destination.name}.',
            suffix='.tmp',
        )
        handle = os.fdopen(descriptor, 'w', encoding='utf-8')
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(temporary, destination)
        temporary = None
    except OSError:
        raise SummaryOutputError('summary_output_write_failed') from None
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if temporary is not None:
            # Never leave a partial sibling behind for a later reader to find.
            try:
                os.unlink(temporary)
            except OSError:
                pass
