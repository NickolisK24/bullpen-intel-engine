# Current-Read Integrity: Founder Decisions DEC-01 and DEC-02

**Date:** 2026-10-31
**Owner:** Nickolis Kacludis
**Package:** Phase 0 / WP-0.1 Current-Read Integrity (findings EOS-001 to EOS-004
of the 2026 end-of-season audit)
**Status:** Approved by the founder. Recorded here as a durable decision record.
Reconciling these decisions into the Decision Ledger table of
`docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md` as numbered D-entries
remains the separate, reviewed roadmap-reconciliation step; this record does
not edit any canonical document.

## Context

In October 2026 idle and eliminated clubs drifted toward Vulnerable for weeks.
Relievers with no appearance inside the freshness window were counted as a
workload constraint, no Team State read knew whether its club was still
playing, and the per-publication Team State share artifacts froze those reads.
Evidence: `docs/audits/2026-end-of-season/` and
`docs/audits/2026-end-of-season/wp01/WP-0.1_CURRENT_READ_INTEGRITY.md`.

The audit left two questions for the founder: how to treat already-published
artifacts (DEC-01), and what a club that is not in active competition shows
instead of a current read (DEC-02).

## DEC-01: Historical share artifacts

**Approved.**

1. Historically accurate share artifacts are preserved unchanged.
2. A demonstrably incorrect artifact is corrected only through auditable,
   versioned supersession: a corrected replacement from governed source state,
   linked to the original, with the original preserved and marked superseded
   with a plain-language reason.
3. No artifact is ever silently rewritten or automatically withdrawn.
4. Each production correction batch requires separate founder approval, given
   after the founder reviews a verified correction manifest.

Canonical basis: Editorial & Distribution Standard
(`06_EDITORIAL_DISTRIBUTION_STANDARD.md`) section 21 "Correction workflow" and
section 25 "Corrections and Public Accountability" (a material conclusion error
is superseded and explained, never deleted); Bullpen Intelligence Standard
(`02_BULLPEN_INTELLIGENCE_STANDARD.md`) section 10 (a stale value is never
presented as current).

Implementation consequence for WP-0.1: the correction manifest
(`backend/services/team_state_correction_manifest.py`,
`backend/scripts/build_team_state_correction_manifest.py`) is a deterministic,
read-only dry run. It proposes `propose_supersede_with_correction`, `retain`,
or `review_required`, never withdrawal, and has no execute mode. Executing any
batch is outside WP-0.1 and needs the separate approval in point 4.

## DEC-02: Clubs not in active competition

**Approved.**

1. A season-complete club shows "Season Complete", its final recorded date, and
   access to its historical intelligence.
2. A club whose competition status is uncertain shows "Status Unconfirmed" and
   no definitive current bullpen assessment.
3. An active postseason club keeps its current read through legitimate
   scheduling gaps (for example, a series winner waiting for the next round).
4. No arbitrary activity rule (such as "no game in three days") may replace
   authoritative competition evidence.

Canonical basis: Bullpen Intelligence Standard section 8 "Public Vocabulary"
(Team State is owned by `backend/services/team_state_public_vocabulary.py`;
the frontend renders the label it is supplied) and section 10 "Freshness and
Failure Scope" (staleness degrades scope, never accuracy; fail closed); Product
Experience Standard (`03_PRODUCT_EXPERIENCE_STANDARD.md`) section 8 "Loading,
Empty, Stale, Error, and Integrity States".

Implementation consequence for WP-0.1:

- `backend/services/club_competition_status.py` classifies each club from
  stored schedule and official game results only. A club stays active while a
  game is scheduled, while the regular season is in progress, or after it
  clinched a postseason series whose next round is not yet listed. It is
  season-complete only on positive evidence (a lost series, a decided World
  Series, or a postseason already past its first round without the club).
  Anything else is undetermined, and a failed lookup fails closed. Every
  evaluation is as of the read's reference date.
- Known limit of point 3: stored authority has no seeding and the schedule
  reaches three days ahead, so a first-round bye club reads "Status
  Unconfirmed" until its first Division Series game is stored. That is the
  fail-closed behaviour this decision requires, not a definitive claim;
  removing the gap needs full postseason schedule ingestion (WP-1.1).
- `season_complete` and `competition_status_unconfirmed` are governed
  non-states in the Team State vocabulary owner. They carry
  `status_label` ("Season Complete" / "Status Unconfirmed"); the season-complete
  block also carries `final_recorded_date`. Neither is a fourth Team State.
- The frontend only accepts the backend's exact outcome/label pair and renders
  it; the Team Board keeps its History link for historical intelligence.

## What this decision does not do

It does not change Contract A thresholds, the three public Team States, the
canonical standards, or any production data. It authorizes no deployment and no
correction batch.
