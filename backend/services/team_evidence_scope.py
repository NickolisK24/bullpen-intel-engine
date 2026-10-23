"""Team-level evidence-quality scope for the active bullpen (P1-4 disclosure).

Operating state and evidence quality are separate dimensions
(docs/decisions/2026-10-07-evidence-quality-operating-state-separation.md).
When some active arms have no current modeled workload read, a reader must be
able to see that scope without the read turning into an alarm. This module
counts the frozen evidence quality of one team's active bullpen records and
authors at most two compact, evidence-first sentences. It classifies nothing:
it reads the availability authority's ``data_state`` and ``operating_basis``.

It is frozen into each published team package, so a snapshot published before
this carrier existed simply has no disclosure: history is never re-described.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from services.availability import (
    ACTIVE_WINDOW_DAYS,
    AVAILABILITY_METHOD_VERSION,
    OPERATING_BASIS_LEDGER_CONFIRMED_REST,
    OPERATING_BASIS_PARTIAL_WORKLOAD,
)


CONTRACT = 'team_board_evidence_scope_v1'
METHOD_VERSION = 'team_board_evidence_scope_v1'


def _availability(record) -> Mapping:
    availability = record.get('availability') if isinstance(record, Mapping) else None
    return availability if isinstance(availability, Mapping) else {}


def _relievers(count: int) -> str:
    return 'active reliever' if count == 1 else 'active relievers'


def _verb(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def author_evidence_scope(records: Iterable[Mapping]) -> dict:
    """Count the evidence quality of the active records and author the note."""
    records = [record for record in records or () if isinstance(record, Mapping)]
    active = len(records)
    current = confirmed_rest = partial = without_operating = 0
    for record in records:
        availability = _availability(record)
        basis = availability.get('operating_basis')
        if not availability.get('availability_status'):
            without_operating += 1
        elif basis == OPERATING_BASIS_LEDGER_CONFIRMED_REST:
            confirmed_rest += 1
        elif basis == OPERATING_BASIS_PARTIAL_WORKLOAD:
            partial += 1
        elif availability.get('data_state') == 'fresh':
            current += 1
    uncertain = partial + without_operating

    sentences = []
    if confirmed_rest:
        sentences.append(
            f'{confirmed_rest} of {active} {_relievers(active)} '
            f'{_verb(confirmed_rest, "has", "have")} not pitched in the last '
            f'{ACTIVE_WINDOW_DAYS} days; complete game records confirm '
            f'{_verb(confirmed_rest, "that rest", "their rest")}, without a current '
            'workload score.'
        )
    if without_operating:
        sentences.append(
            f'{without_operating} of {active} {_relievers(active)} '
            f'{_verb(without_operating, "has", "have")} incomplete current workload '
            'evidence and '
            f'{_verb(without_operating, "is", "are")} not counted as available or on watch.'
        )
    if partial:
        sentences.append(
            f'{partial} of {active} {_relievers(active)} '
            f'{_verb(partial, "is", "are")} read from partial workload records, '
            'which can only understate recent work.'
        )
    return {
        'contract': CONTRACT,
        'method_version': METHOD_VERSION,
        'availability_method_version': AVAILABILITY_METHOD_VERSION,
        'active_bullpen_count': active,
        'current_workload_count': current,
        'ledger_confirmed_rest_count': confirmed_rest,
        'partial_workload_count': partial,
        'without_operating_evidence_count': without_operating,
        'uncertain_count': uncertain,
        'degraded': bool(confirmed_rest or uncertain),
        'note': ' '.join(sentences) or None,
    }


def valid_evidence_scope(value) -> dict | None:
    """The frozen carrier when it is well formed; otherwise None (no disclosure)."""
    if not isinstance(value, Mapping) or value.get('contract') != CONTRACT:
        return None
    counts = (
        'active_bullpen_count', 'current_workload_count', 'ledger_confirmed_rest_count',
        'partial_workload_count', 'without_operating_evidence_count', 'uncertain_count',
    )
    if any(type(value.get(key)) is not int or value.get(key) < 0 for key in counts):
        return None
    note = value.get('note')
    if note is not None and not isinstance(note, str):
        return None
    return dict(value)
