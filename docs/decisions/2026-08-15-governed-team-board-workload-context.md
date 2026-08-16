# D-055 — Governed Team Board workload context

- **Date:** 2026-08-15
- **Status:** Adopted
- **Scope:** Additive Team Board projection of already-public pitcher workload facts and a backend-authored team Rest Status. No Team State, availability vocabulary, ranking, prediction, acquisition, or publication authority changes.

## Context

The Team Board already loads the snapshot-pinned fatigue records and governed
availability inputs needed to present a pitcher's recent workload. A later frontend
package needs richer active-bullpen rows and a team Rest Status, but a second fatigue
request, a client-side join, or client-authored counting would create mixed freshness
and a second interpretation authority.

## Decision

The Team Board may project a minimal `workload_facts` object on every represented
pitcher card by reusing values already loaded by its existing authority path:

- `days_since_last_appearance`, `appearances_last_7`, and
  `pitches_last_7_days` are the exact persisted values exposed by the existing public
  workload projection;
- `back_to_back` is the exact governed boolean already exposed as a public
  availability input; and
- missing values remain null. They are never recalculated or converted to zero.

No fatigue score, component score, risk level, score breakdown, or non-required
availability input becomes public through this extension.

The Team Board may also author one `rest_status` block from the represented active
bullpen cards. Its definitions are fixed:

- `active_arm_count` is the number of represented cards in the governed Team Board
  population;
- `rested_arm_count` counts cards whose `days_since_last_appearance` is at least 2,
  meaning at least one full calendar day elapsed between the last appearance and the
  board availability date;
- `worked_yesterday_count` counts cards whose
  `days_since_last_appearance` is exactly 1; and
- `back_to_back_count` counts cards whose existing governed `back_to_back` input is
  true.

The backend owns the counts and the bounded summary sentence. The frontend does not
join workload records, derive counts, or reinterpret the date semantics.

## Fail-closed behavior

Rest Status is unavailable when the board/read context has failed closed, the governed
board population is empty, roster counts are withheld, any represented card lacks the
date or back-to-back evidence needed by the definitions, or a represented card's
workload evidence is not fresh. In that state `available` is false, all counts and the
summary are null, and a bounded reason code describes the class of failure. Missing or
stale evidence never becomes a zero count.

## Authority boundaries

D-055 authorizes only:

1. embedding those already-public workload facts in Team Board pitcher cards;
2. adding the backend-authored Rest Status block;
3. enabling a later frontend package to remove its independent fatigue-data join; and
4. reusing data already loaded by the Team Board authority.

It authorizes no:

- Team State calculation, label, or contract change;
- availability calculation or vocabulary change;
- new workload threshold beyond the four exact Rest Status definitions above;
- frontend derivation;
- fatigue score exposure;
- prediction, recommendation, selection, or ranking;
- MLB request or other reader-path acquisition;
- write or publication-authority change; or
- role-composition contract.

The existing Team State, availability, grouping, freshness, snapshot, and public
response-stripping authorities remain unchanged.

## Frozen-path authorization

The exact production paths authorized by D-055 are:

- `backend/api/bullpen.py`
- `backend/services/bullpen_board.py`

The repository freeze policy records only those exact paths. No directory, prefix, or
global bypass is authorized. The exception follows the existing branch-diff model and
becomes inert after the authorized changes merge into `origin/main`.

## Query behavior

The projection and aggregation must use the fatigue and availability objects already
loaded by the Team Board request. D-055 authorizes no per-card query, no second fatigue
fetch, and no MLB request. Real SQL instrumentation must prove that statement count
does not grow with the represented bullpen population.

## Consequences

A later frontend package may consume one freshness-aligned Team Board response for
pitcher workload context and Rest Status, then retire its independent fatigue join.
That later presentation work is outside D-055 and outside this backend package.
