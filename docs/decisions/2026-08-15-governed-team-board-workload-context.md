# D-055 — Governed Team Board workload context

- **Date:** 2026-08-15
- **Status:** Production-proven
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

### Production carrier clarification — August 16, 2026

In production, the D-051 `trusted_team_boards` package is the carrier for the D-055
Team Board contract. Each frozen board record therefore carries the exact existing
public workload projection from the `FatigueScore` object already loaded while the
candidate snapshot is built. The frozen carrier performs no query, recalculation, or
fallback and grants no new read, write, or publication authority.

This clarification is additive within the existing
`trusted_team_board_publication_v1` package and Dashboard payload version. Previously
published snapshots may legitimately omit `workload_facts`; they remain immutable and
continue to fail closed until a later naturally scheduled publication carries the
field.

## Frozen-path authorization

The exact production paths authorized by D-055 are:

- `backend/api/bullpen.py`
- `backend/services/bullpen_board.py`
- `backend/services/public_serving_authority.py`

The repository freeze policy records exact exceptions only for the protected route and
legacy presentation paths. `backend/services/public_serving_authority.py` is not in a
frozen-path list, so this carrier correction needs no exemption.
No directory, prefix, or global bypass is authorized.
Existing exact-path exceptions follow the branch-diff model and become inert after
their authorized changes merge into `origin/main`.

## Query behavior

The projection and aggregation must use the fatigue and availability objects already
loaded by the Team Board request. D-055 authorizes no per-card query, no second fatigue
fetch, and no MLB request. Real SQL instrumentation must prove that statement count
does not grow with the represented bullpen population.

## Persistence integrity

The persistence layer must preserve nullable `pitches_last_7_days` evidence exactly.
When a qualifying appearance lacks pitch-count evidence, the calculator's null must
remain null through the production fatigue-score writer and public workload projection;
an ORM/client-side zero default must not coerce that unknown state into a reported zero.
A legitimate calculated zero remains zero. This restores the existing D-055 null
semantics and creates no new calculation, read, write, or publication authority.

## Production proof — August 16, 2026

D-055 and Team Board Phase 2 are production-proven.

The null-persistence correction (PR #672) and trusted Team Board carrier correction
(PR #673) were both merged before governed `BaseballOS Intraday Roster Repair` runs
rebuilt the publication candidate. The scheduled intraday producer recalculated fatigue
under the corrected nullable persistence semantics and published replacement Dashboard
snapshots through the existing D-051 ledger-gated publication path.

Snapshot 426 was published by intraday run `31970550823` from post-fix main, and snapshot
427 was subsequently published by scheduled intraday run `31985029067`. Snapshot 427 was
the serving authority during the production observation. Both snapshots retained
`data_through = 2026-08-15` because that field reflects completed-game evidence rather
than snapshot recency.

Production observation on the New York Yankees Team Board confirmed the D-055 contract
through the trusted snapshot authority:

- pitcher cards rendered populated `days_since_last_appearance`,
  `pitches_last_7_days`, and `appearances_last_7` values;
- visible rest values were coherent with the governed 2026-08-16 availability reference
  date, including Aug. 11 -> 5 days, Aug. 13 -> 3 days, and Aug. 15 -> 1 day;
- Rest Status passed its fail-closed evidence gate and rendered `rested = 4`,
  `worked_yesterday = 4`, and `back_to_back = 3` across eight default-visible active
  bullpen arms;
- the governed distinction between nine represented eligible relievers and eight
  default-visible active arms remained intact; and
- no request-time reconstruction, snapshot mutation, cache substitution, publication
  authority drift, Team State change, or availability change was found.

The production-authority audit classified the observed behavior as
`EXPECTED — OTHER GOVERNED PUBLICATION PATH`: the intraday repair lane is an authorized
scheduled Dashboard snapshot producer, so production proof did not require waiting for
the next full daily sync. D-051 snapshot immutability and trusted-serving authority
remained intact.

No further D-055 backend remediation is required. Team Board Phase 2 is considered
production-proven as of this evidence.

## Consequences

A later frontend package may consume one freshness-aligned Team Board response for
pitcher workload context and Rest Status, then retire its independent fatigue join.
That later presentation work is outside D-055 and outside this backend package.
