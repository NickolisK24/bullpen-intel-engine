# BaseballOS Repository Documentation Map

**Status:** Supporting navigation and classification guide  
**Owner:** Nickolis Kacludis  
**Reviewed:** August 13, 2026  
**Authority:** This file does not define product behavior. The six canonical documents remain authoritative.

The BaseballOS repository contains several generations of product, engineering,
audit, rollout, and governance documentation. That history is useful, but it
must not create competing authorities.

This map answers one question:

> **When I open a document in this repository, what kind of authority does it have?**

## 1. Canonical Living Authorities

Directory: [`docs/canonical/`](canonical/README.md)

These six documents are the only permanent product/system authorities:

1. `01_BASEBALLOS_CONSTITUTION.md`
2. `02_BULLPEN_INTELLIGENCE_STANDARD.md`
3. `03_PRODUCT_EXPERIENCE_STANDARD.md`
4. `04_PLATFORM_ARCHITECTURE_OPERATIONS.md`
5. `06_EDITORIAL_DISTRIBUTION_STANDARD.md`
6. `05_PRODUCT_ROADMAP_DECISION_LEDGER.md`

They own durable meaning. If a temporary implementation record discovers a new
permanent rule, that rule must eventually be absorbed here.

## 2. Current Operational / Supporting Documentation

Directory: `docs/current/`

A file belongs here only while it has an active procedural, operational, or
subsystem-support role.

Current examples include:

- `SETUP.md` — local development and configuration procedure.
- `SYNC_PIPELINE.md` — current sync/publication runbook and authority posture.
- `DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md` — current daily publication-critical contract.
- `GAME_DRIVEN_DAILY_INGESTION.md` — active game-driven ingestion qualification/subsystem record; the lane remains shadow until the Roadmap records authority transfer.
- `INTRADAY_RECONCILIATION.md` — current audit/reconciliation subsystem record.
- `PROGRESSIVE_TEAM_ARTIFACT_PUBLICATION.md` — current team-progressive publication support.
- share-artifact operations/cutover/public-page documents — current support for the immutable Share Artifact domain.
- `DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md` — current dependency-security boundary and standing obligations. Despite the date in its filename it is **current state, not point-in-time evidence**: it describes the boundary the platform operates under now and carries a live expiry date. It is superseded by a later boundary statement, not archived on a schedule.
- `CHANGELOG.md` — milestone chronology, not execution authority.

A `current/` file may be detailed, but detail does not let it override a
canonical document.

## 3. Durable Decision Records

Directory: `docs/decisions/`

Decision records preserve context, alternatives, costs, and rationale for one
focused decision. They are durable evidence of **why** a choice was made.

They do not become a second Roadmap, Constitution, Intelligence Standard, or
Architecture Manual.

## 4. Audits and Point-in-Time Evidence

Directory: `docs/audits/`

These files prove what was observed at a particular time. They may identify a
defect, validate a production result, or support a decision.

Examples include:

- visual product audits;
- source-authority investigations;
- production incident investigations;
- sync-reliability audits;
- acceptance/closeout evidence.

An audit remains historical evidence even when its recommendation is accepted.
The Roadmap owns sequence; the Architecture/Intelligence standards own durable
rules; the issue/PR owns implementation closure.

The August 6 `DAILY_SYNC_RUNTIME_BUDGET_EXHAUSTION_2026-08-06.md` investigation
is the evidence basis for OPS-002 (#620). It is not a replacement sync runbook.

## 5. Phase, Report, Methodology, Governance, and Implementation Records

Directories and top-level docs in this class include historical phase folders,
`docs/reports/`, older `docs/governance/` packets, `docs/methodology/` research,
and legacy top-level design/reconciliation documents.

### Phase 0 folder locations

Phase 0 closed July 29, 2026 (Canonical Trust Closeout). The August 13
retirement pass moved the sub-phase folders whose only remaining role is
implementation history — `phase0b`, `phase0f`, `phase0g`, `phase0h`,
`phase0i`, `phase0j` — unmodified, to `docs/archive/2026-07/`.

Three folders stayed at `docs/phase0c/`, `docs/phase0d/`, and `docs/phase0e/`
because they are **not** inert history: runtime code and tests read them.
`backend/services/evidence_classification.py` cites
`docs/phase0d/public_language_rules.md` anchors as required-language
references, and `test_phase0c_foundation_invariants.py`,
`test_phase0d_evidence_contract.py`, `test_evidence_classification.py`,
`test_phase0e_exit_docs.py`, and `test_qa_reconciliation_scenarios.py` read
those files by path. Moving them would break an evidence contract, not just a
link.

Examples include older role-authority plans, weighting investigations,
recommendation-engine certifications, bullpen-shape audits, and phase plans.

These files can still be valuable for provenance. Unless a canonical document
explicitly names one as active support, they should be read as implementation
history or research evidence rather than current product authority.

## 6. Archive

Directory: `docs/archive/`

Archived files are intentionally historical. They should not be rewritten to
match today's product vocabulary merely to make search results look cleaner.
Their historical language is part of the record.

If an archived rule still matters, the current canonical document should state
that rule independently.

### June project-state snapshot

`PROJECT_STATE_2026_06.md` previously lived under `docs/current/`, where its
location could make a June snapshot look like current platform authority. The
August 6 reconciliation moved the exact historical blob to:

`docs/archive/2026-06/PROJECT_STATE_2026_06.md`

No historical content was rewritten during the move. Current product scope,
terminology, roadmap priority, architecture, and active surfaces come from the
canonical library and current runbooks instead.

## 7. Older Top-Level Documentation

Several `docs/*.md` files predated the canonical-library cutover: weighting
foundations, reconciliation audits, role-authority plans, bullpen-shape
investigations, and the intelligence-surface design paper.

The August 13 retirement pass moved that batch, unmodified, to:

`docs/archive/pre-canonical/`

The folder is named for the boundary it sits behind — the July 29 canonical
cutover — rather than a month, because these files carry no reliable individual
authoring date in repository history. No historical terminology was rewritten
during the move.

`README.md`, `REPOSITORY_DOCUMENTATION_MAP.md`, and `local-development.md`
remain at the top level: the first two are navigation, and the third is an
active local-development procedure.

## 8. Retired Game 824487 Repair Material

The game `824487` source-revision checkpoint repair is terminally complete.
The single-purpose mutation capability was retired after verification,
application, and independent already-applied re-observation.

Rules for repository readers:

- historical audit and commit evidence may remain;
- no document should instruct an operator to dispatch the retired mutation path;
- the retired capability grants no general game-driven write authority;
- daily/postgame game-driven lanes remain shadow until a separate authority-transfer decision.

## 9. Current Operational Incident Boundary

OPS-002 (#620) concerns daily sync runtime-budget exhaustion.

The incident established two different facts that documentation must keep
separate:

- **Safety:** incomplete candidate snapshots were withheld and the previous trusted snapshot continued serving.
- **Health:** live/current surfaces could still be degraded when publication-critical GameLog ingestion was partial.

Therefore “the previous trusted snapshot served correctly” must never be used
as shorthand for “the current production picture was healthy.”

The current bounded mitigation and its production-proof requirements belong in
the canonical Roadmap and current sync runbook. The investigation remains
point-in-time evidence.

## 9A. Dependency Accepted-Risk Records

Dependency risk that cannot be removed today is accepted only as a dated,
revocable decision. Two files are involved and they are not interchangeable:

- `docs/decisions/2026-08-13-react-router-v7-security-defer.md` — the **decision
  record**. It owns the reasoning, the applicability analysis, the compensating
  control, and the revisit conditions.
- `.github/dependency-audit-accepted.json` — the **machine contract** CI reads.
  It owns the exact advisory identifiers, packages, expiry, and tracking issue.

Rules for repository readers:

- neither file may be edited to make a build pass; changing an expiry is a
  security decision, not maintenance;
- an acceptance is invalid from 00:00 UTC on its expiry date;
- when the underlying advisory is remediated, the machine entry must be
  **deleted**, while the decision record is preserved as history;
- a decision record is not an authority to accept new risk by analogy. A new
  advisory needs its own review.

## 10. Search-Result Interpretation Rules

When repository search returns several documents about the same concept:

1. Read the canonical document first.
2. Check the canonical Roadmap for current implementation state.
3. Use a current runbook for exact procedure.
4. Use decision records to understand why.
5. Use audits/reports to inspect evidence from a particular moment.
6. Treat archived/phase records as history unless explicitly reactivated.

Do not resolve a conflict by choosing the newest filename, longest document, or
most detailed explanation.

## 11. Documentation Retirement Test

A supporting document should be archived, redirected, or explicitly marked
historical when any of these becomes true:

- its implementation phase is complete;
- the workflow or mutation path it documents is retired;
- a canonical document now owns all durable rules;
- it describes a product category BaseballOS no longer occupies;
- its title/location causes readers to mistake historical state for current state;
- maintaining it would create a second place for current facts to disagree.

Preserving history does not require preserving ambiguity.
