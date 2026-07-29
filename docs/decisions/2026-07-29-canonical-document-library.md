# Decision: Six-Document Canonical Library

**Date:** July 29, 2026  
**Owner:** Nickolis Kacludis  
**Status:** Adopted

## Decision

BaseballOS will maintain six living canonical documents:

1. BaseballOS Constitution
2. Bullpen Intelligence Standard
3. Product Experience Standard
4. Platform Architecture & Operations Manual
5. Product Roadmap & Decision Ledger
6. Editorial & Distribution Standard

No new master plan, operating system, product-vision master, or competing roadmap will be created for a monthly planning pass, audit, subsystem, or redesign.

## Why

The platform had accumulated several strong documents whose scopes overlapped. Mission, vocabulary, page strategy, implementation sequence, trust rules, and subsystem detail were being restated in multiple places. That made a newer document look authoritative merely because it was newer and increased the chance of stale vocabulary or conflicting priorities.

The six-document system gives every durable decision one canonical home while preserving historical audits, specifications, and implementation records.

## Precedence

1. Constitution
2. Bullpen Intelligence Standard
3. Product Experience Standard
4. Platform Architecture & Operations Manual
5. Editorial & Distribution Standard
6. Product Roadmap & Decision Ledger
7. Active subsystem specifications
8. Work packages and implementation notes
9. Historical records

The Roadmap determines sequence. It cannot override a higher authority.

## Consequences

- `docs/canonical/` becomes the documentation front door.
- `docs/README.md` becomes an authority index rather than a list of competing plans.
- The former standalone current roadmap redirects to the canonical Roadmap & Decision Ledger.
- The former product-vision specification redirects to the Product Experience Standard.
- Existing audits, runbooks, subsystem records, and historical plans remain in Git history or their current support locations.
- A subsystem specification is temporary: after production stabilization, permanent rules migrate into the relevant canonical documents.
- Exact runtime mappings remain owned by canonical code and tests; documentation owns purpose and public contracts.

## Reversal Standard

Reversing this decision requires a new Decision Record that identifies which recurring conflict the six-document system cannot resolve and why a different structure would reduce, rather than increase, authority drift.
