"""Record the request scopes and receipts consulted by an isolated historical calculation."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class EvidenceReads:
    cursor: object
    requests: set = field(default_factory=set)
    receipts: set = field(default_factory=set)


_active = ContextVar('candidate_evidence_reads', default=None)


@contextmanager
def capture_reads(cur):
    reads = EvidenceReads(cur)
    token = _active.set(reads)
    try:
        yield reads
    finally:
        _active.reset(token)


def consult(cur, endpoint, params, *receipts):
    reads = _active.get()
    if reads is not None and reads.cursor is cur:
        reads.requests.add((endpoint, tuple(sorted(params.items()))))
        reads.receipts.update(r for r in receipts if r is not None)


def include_reads(cur, previous):
    reads = _active.get()
    if reads is not None and reads.cursor is cur and previous.cursor is cur:
        reads.requests.update(previous.requests)
        reads.receipts.update(previous.receipts)
