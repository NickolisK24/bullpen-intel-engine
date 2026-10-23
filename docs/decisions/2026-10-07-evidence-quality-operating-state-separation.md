# Evidence Quality Is Not Operating State

**Date:** 2026-10-07
**Package:** Truth Certification Remediation (follows #908)
**Status:** Candidate correction of the four blocking P1 findings of the
post-stabilization truth certification of snapshot 4496. Merging does not by
itself certify production; the governed Manual Publication Truth Certification
must be run against the first natural publication made under this method.

## Finding being corrected

The governed read-only certification of snapshot 4496 (data through
2026-10-06) proved that stale evidence alone became an operating claim:

```
no appearance in 14 days
  -> data_state 'stale'
  -> availability_status 'Monitor' (low confidence)
  -> public "On Watch" group and its count
  -> Contract A 'moderate'
  -> Stretched (and, as evidence keeps aging, Vulnerable)
```

WSH, COL, TEX, MIN, MIA and AZ published Stretched with every On Watch arm
stale. The trust gate meanwhile counted those same arms as usable *observed
rest* (2026-07-24 decision, DECISION 2). One arm was rested for trust and
workload concern for Team State.

## Standards interpretation

The governing text, highest level first:

* 01 Constitution: "The platform gets quieter under uncertainty, never
  wronger." A product must not "convert unknowns into zero or plausible
  values." Corrections preserve history.
* 02 Bullpen Intelligence Standard: "Staleness degrades scope. It never
  silently degrades accuracy." "A stale value is never presented as current."
  `data_limited`, stale, incomplete and unknown "are fail-closed outcomes, not a
  fourth Team State." On Watch: "recent workload deserves visible context."
  Workload Data and Read Confidence are evidence-quality families, distinct
  from baseball state. "Changing a definition creates a new version.
  Historical observations remain bound to the method that produced them."
* 03 Product Experience Standard: stale or partial reads "name the affected
  scope" without a full-page alarm.
* Availability Engine V1 methodology: "Missing inputs create unknown or
  low-confidence display, not a fake workload status." "Do not present stale or
  missing data as a workload-driven current status." "A pitcher with no recent
  appearances and fresh roster/log coverage may be Available from workload
  data. If the pitcher has no MLB logs at all, the status should be
  low-confidence or unknown rather than automatically Available."

The same V1 document also said stale/missing data "returns Monitor with low
confidence" because the public status set had five members, and asked
consumers to separate the two meanings with `data_state`. No consumer did:
the board grouped by status and Contract A partitioned by status. That
sentence is the one genuine internal contradiction; it is superseded here by
the higher rules above (stale is never current; missing is unknown; no
recent appearances with complete coverage may be Available).

The public trust copy "When the evidence is missing or stale, it withholds the
read instead of guessing" described an intent the implementation did not
follow. It is corrected to describe actual behavior (below).

Contract A remains a status-only aggregation of the availability authority's
published operating statuses. The canonical rule that no surface may build a
Team State from availability labels or counts governs presentation; the Team
State authority itself is the one place that aggregation is allowed.

## Three dimensions, kept separate

| Dimension | Field | Question |
| --- | --- | --- |
| Operating state | `availability.availability_status` (`Available`, `Monitor`, `Limited`, `Avoid`, `Unavailable`, or **absent**) plus `availability.operating_basis` | What does observed MLB workload support? |
| Evidence quality | `availability.data_state` (`fresh`, `stale`, `missing`, `incomplete`; fetch failure is `incomplete` with `inputs.workload_fetch_failed`) and `confidence` | How current and complete is the evidence? |
| Publication trust | team `trust.confidence` / `trust.data_state` from active-bullpen coverage | Is there enough evidence to publish a team read? |

Invariant: **evidence quality alone never creates workload concern, and
uncertainty is never translated into certainty of freshness.**

## Arm contract (availability engine v2)

`AVAILABILITY_METHOD_VERSION = 'availability_engine_v2'`.

| Case | Operating status | `operating_basis` | Confidence | Evidence quality |
| --- | --- | --- | --- | --- |
| A. Fresh workload evidence | Workload thresholds, unchanged | `workload` | high (medium when a restricted status has no score), unchanged | `fresh` |
| B1. Stale, and the completed-appearance ledger proves no MLB workload | `Available` | `ledger_confirmed_rest` | medium | `stale` |
| B2. Stale, ledger not proven | absent | none | low | `stale` |
| C. Missing (no score or no appearance on record) | absent | none | low | `missing` |
| D. Incomplete inputs, observed partial workload already crosses a threshold | that workload status, as a lower bound | `partial_workload` | low | `incomplete` |
| D'. Incomplete inputs, observed partial workload crosses nothing | absent | none | low | `incomplete` |
| E. Open workload fetch failure | as D / D' from the observed workload; a B1 rest proof is voided | `partial_workload` or none | low | `incomplete`, `workload_fetch_failed` |

* B1 is the case the standard names: no recent appearances with complete log
  coverage may be Available *from workload data*. The proof is the existing
  rest proof of the trust gate: the completed-appearance ledger is complete
  through the last completed day before the reference date. The ledger window
  (10 days by default) contains every workload input the model reads, so
  absence inside it is an observed zero, not a guess. The old carried fatigue
  score of a stale arm is never read ("never fall back to unverified cached
  meaning"). No score is fabricated; the arm still reports `data_state:
  'stale'`, its Pitcher Current Read stays **Limited Read**, and its limitation
  says it has no current modeled workload score.
* F (ledger proves no recent workload, modeled record stale) is B1.
* An arm with no operating evidence carries no availability status at all. It
  is not On Watch, not Available, and not counted in any availability group;
  it is shown through the Workload Data family ("Outside Freshness Window",
  "No Workload Record", "Incomplete Workload Inputs", "Fetch Failed") and the
  Limited Read.
* D keeps observed workload visible: missing data can hide more work, never
  less, so a status already reached by observed appearances is a floor.
* Unscored active-bullpen arms (#900) are unchanged: usable for team coverage
  when every per-arm proof holds, never given a record or a score.

## Team State contract (`v3_phase_6`)

`TEAM_STATE_METHOD_VERSION` advances `v3_phase_5 -> v3_phase_6`.

G. **Partition input.** Each Team State record carries its operating status and
an evidence bound: `exact` (A, B1), `lower_bound` (D/E with workload), or
`unknown` (no operating status). The clean/moderate/severe map and every
Contract A threshold are unchanged.

H. **Coverage and trust.** Unchanged authority and thresholds: usable records
are `fresh`, or `stale` with a complete ledger; #900 unscored arms as before;
everything else is unresolved. The usable records are exactly the `exact`
records of G, so the records that derive Team State are still the records
whose coverage authorizes it.

I. **Withholding.** Unchanged trust, freshness, coverage and empty-population
gates first. Then a new **evidence determinacy** gate: Contract A is evaluated
twice, with every uncertain arm at its most favorable operating value (unknown
as clean, a lower bound at its bound) and at its least favorable (severe). If
the two disagree, the uncertain arms decide the state, the evidence cannot
support one, and Team State is withheld as `data_limited`
(`decisive_rule = 'evidence_indeterminate'`). If they agree, that state is
published. With no uncertain arm, the result is identical to `v3_phase_5`.
Uncertainty can therefore never produce Stretched or Vulnerable, and never
produce Fresh.

Idle monotonicity follows: with identical membership, no new workload and a
complete ledger, advancing the reference date can only move fresh arms to B1
(clean); clean counts never fall, so Team State cannot worsen from aging.
When the ledger is not complete, aged arms become unknown, which can only
withhold Team State, never worsen it.

## Public language

J. **On Watch** and **Watch Arm** mean observed workload deserves attention,
and nothing else. Evidence uncertainty uses the Workload Data and Read
Confidence families and the Limited Read. Team-level scope is disclosed by a
frozen `evidence_scope` carrier on each team package (published from the same
active records), rendered compactly on the Team Board, e.g.:

* "3 of 11 active relievers have not pitched in the last 14 days; complete game
  records confirm their rest, without a current workload score."
* "1 of 11 active relievers has incomplete current workload evidence and is
  not counted as available or on watch."

## Postseason workload (P1-2)

Workload windows count completed MLB regular-season and postseason
appearances. A postseason appearance is real bullpen workload and stays in
fatigue, rest, recent usage, availability and Team State. Other domains keep
their documented, different bases: the observed usage role and the 14-day
deployment profile are regular season only; role movement uses regular season
plus postseason as separate phases; season aggregation, performance and
capacity are regular season only. The Methodology page now states this.

## Methodology copy (P1-3)

The false sentence is replaced by the implemented behavior: an unsupported
baseball conclusion is withheld; stale, missing or incomplete evidence is
labeled as such and is never turned into workload concern; a rested arm whose
rest is confirmed by complete game records reads as available with that basis
stated; a team read the evidence cannot determine is withheld.

## What Changed and history

* Historical snapshots are not rewritten. A `v3_phase_5` receipt stays valid
  for its own snapshot and keeps serving what was published.
* A Team State comparison across method versions is not a baseball event:
  `compare_exact_team_state` reports `unavailable` with
  `team_state_method_version_changed` (option B: suppressed). The delta
  substrate already withholds `METHOD_VERSION_MISMATCH`. No "recovered" copy
  is published because a classification defect was fixed.
* Arm reads (`pitcher_public_labels_v1`) project the same key for the same
  evidence before and after (a stale arm was and remains Limited Read), so the
  arm-read method version does not move.

## Explicitly out of scope

Days-since carry-forward for unscored arms, the San Diego `40_MAN_ONLY`
observation, and all P2/P3 certification findings are recorded in the
remediation report and left untouched.
