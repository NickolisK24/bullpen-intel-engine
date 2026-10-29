# 06 — Decision Register

**Decisions requiring founder approval.** Nothing here is adopted until it is recorded in the canonical Roadmap & Decision Ledger (`docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md`) with a D-ID. This register does **not** supersede any governing decision.

**Columns:**
- **Policy change?** — whether implementation changes canonical product policy, as opposed to correcting implementation to match existing policy.
- **Ordering:** decisions are listed in the order they are needed. DEC-01 through DEC-05 are needed in Phase 0.

---

## DEC-01 — What a current bullpen read means across the season (season-phase contract)

| | |
|---|---|
| **Decision** | Adopt a backend-owned season-phase contract (`REGULAR_SEASON`, `POSTSEASON`, `SEASON_COMPLETE`, `OFFSEASON`, `SPRING_TRAINING`, `OPENING`) and a per-club competitive status (`active`, `eliminated`, `not_qualified`, `champion`). **Current Team State and arm reads are published only for active clubs in REGULAR_SEASON or POSTSEASON.** Every other club gets a season-complete or offseason representation dated with *its own* last game |
| **Evidence** | EOS-001, EOS-002. Production published 28 of 30 Vulnerable on 2026-10-28, including clubs idle since 09-27 (`02` §5). No standard defines behaviour for idle or eliminated clubs (`02` §2.2 C8) |
| **Alternatives** | **(a)** Keep publishing for all 30 and fix only EOS-001. Idle clubs then drift to "Fresh" all winter, which is also a meaningless current claim. **(b)** Stop all publication after the regular season. This loses the postseason, the product's highest-attention bullpen period. **(c)** The recommended per-club gating. **(d)** Show reads for idle clubs with a "stale" badge. This conflicts with 02:685 ("A stale value is never presented as current") |
| **Trade-offs** | (c) adds a small state model and touches publication proofs, which currently require exactly 30 Team States. It removes a whole class of false claims and gives the offseason a meaningful product |
| **Recommendation** | **(c)**, with an interim rule for WP-0.1 shipping immediately: a club is active if it has a final game in the last 3 days or a scheduled game in the next 3 days |
| **Impact on canonical standards** | 02: new section "Season phase and club status"; amend Team State (535-543) to "published for active clubs". 03: offseason and season-complete page states. 04: the publication proof requires one read per active club plus one archive record per inactive club. 01: none (it implements "quieter under uncertainty") |
| **Proceed without a policy change?** | **The interim gate, yes.** It enforces existing rules 01:140 and 02:685. **The full phase model needs a 02/03 amendment** |

## DEC-02 — Inactivity is rest, not constraint

| | |
|---|---|
| **Decision** | An arm whose last appearance is older than the staleness window, while its club is active, is classified as **rested by absence**. It counts as clean coverage with a "no recent appearances" qualifier, not as Monitor / On Watch. `missing` (no workload record at all) stays excluded from both clean and constrained counts and narrows scope |
| **Evidence** | EOS-001: `availability.py:391-399` (stale → Monitor); `bullpen_readiness.py:599` (clean ≤ 2 → Vulnerable). The trust gate already treats an old appearance as valid observed rest (decision 2026-07-24 "Rest ≠ stale"), so the two layers disagree |
| **Alternatives** | **(a)** Stale arms stay Monitor (status quo): false constraint. **(b)** Exclude stale arms from the denominator: a pen of 5 recent plus 8 idle arms would look "thin". **(c)** The recommended rested-by-absence. **(d)** A new public label "Idle". This adds vocabulary; 02 limits labels |
| **Trade-offs** | (c) could label a silently injured but still-active arm as a clean option. The Constitution forbids medical inference, and the roster says he is active, so the descriptive statement ("no appearances in N days") is accurate. The qualifier is shown with it |
| **Recommendation** | **(c)** |
| **Impact on canonical standards** | 02: amend the availability rules and the On Watch definition (553-560); state "absence of workload is not workload". Methodology copy |
| **Proceed without a policy change?** | **Partly.** The current behaviour already violates 02:676 ("never silently degrades accuracy"), so correcting it is defensible under existing policy. Ledger it anyway because it changes published distributions |

## DEC-03 — Correct the October 2026 record

| | |
|---|---|
| **Decision** | Supersede, never delete or edit, every Team State share artifact and team-page publication whose read was produced by EOS-001/EOS-002, with a public correction note and a link to the corrected archive read. List the correction on Data & Trust |
| **Evidence** | EOS-003: 747 Vulnerable team-state artifacts since 09-29, among 1,436 in that period. The model supports `superseded_at`, `withdrawn_reason` (`models/share_artifact.py:240-242`) |
| **Alternatives** | **(a)** Leave them (history is history). Uncorrected false claims remain at permanent citation URLs. **(b)** Withdraw them (404). This breaks citations. **(c)** The recommended supersede with a banner |
| **Trade-offs** | (c) admits the error publicly. That is consistent with the trust model and the cheapest credibility repair |
| **Recommendation** | **(c)**, scoped exactly by the G-2.3 query |
| **Impact on canonical standards** | None. It implements the README rule "Corrections preserve history" |
| **Proceed without a policy change?** | **Yes** |

## DEC-04 — One pipeline: retire the parallel rewrites for 2027

| | |
|---|---|
| **Decision** | The legacy daily/postgame writer is the sole 2027 production writer. Archive the `feat/sync-pipeline` (SP-00…SP-14) program: tag it, write a summary doc, delete its Render service. Freeze the CU shadow lanes, disable their crons and the shadow-activation health job, and remove the fence triggers after an audit. Reuse a CU or SP component only if it measurably reduces runtime or fixes a defect |
| **Evidence** | EOS-016: the SP-14 verdict is NO-GO; AUDIT-R3 is BLOCKED; the branch is 304 files / ~45k lines divergent and idle since 09-19. CU-08S is PARTIAL; CU-08U's replay never ran. The fences caused the Sep 25 and Oct 1 incidents. EOS-007 (red workflow). The legacy writer delivered about 2 publications a day all October |
| **Alternatives** | **(a)** Finish SP-14 certification this offseason (probably most of the offseason). **(b)** Promote CU-08 to LIMITED_LIVE for faster in-game updates. **(c)** The recommended consolidation |
| **Trade-offs** | (c) gives up near-real-time in-game updates for 2027. That is acceptable: the product is a pre-game / post-game read, and no evidence shows users need minute-level freshness. It writes off sunk cost in the SP work |
| **Recommendation** | **(c)**. Revisit live updates only after a 2027 usage signal shows demand |
| **Impact on canonical standards** | 04: describe one writer and Render Cron; close O-008 as "not pursued for 2027". 05: ledger |
| **Proceed without a policy change?** | **Shutting down crons and jobs: yes** (operational). **Archiving the program and closing O-008: needs a ledger decision** |

## DEC-05 — Stop committing generated HTML to git

| | |
|---|---|
| **Decision** | Generate share artifacts only when a club's public read changes (`equivalence_key`). Serve `/share/{id}` and `/team/{ABBR}` metadata from the API or an edge function. Move the 10,042 existing pages to object storage under the same URLs. Stop bot commits to `main`, then fully protect `main` |
| **Evidence** | EOS-013: about 60 pages a day; 119 MB; per-publication duplicates; every commit redeploys; unprotected `main` is required for the bot to push |
| **Alternatives** | **(a)** Keep committing but generate only on change (halves growth; keeps the deploy coupling). **(b)** The recommended serve-dynamically. **(c)** A separate distribution repository |
| **Trade-offs** | (b) changes the D-053 mechanism and needs the crawler-visible metadata path re-verified (Twitterbot, Slack, iMessage unfurls). (a) is a cheap interim step |
| **Recommendation** | **(a) immediately** (Phase 0, trivial), **then (b)** in Phase 3b |
| **Impact on canonical standards** | 04 D-053 amended |
| **Proceed without a policy change?** | **(a) yes. (b) needs a D-053 amendment** |

## DEC-06 — The smallest correct offseason product

| | |
|---|---|
| **Decision** | From the World Series final to the first spring training game, BaseballOS presents: "2026 season complete" plus the champion; per-club 2026 bullpen season summaries; reliever season pages; the corrected Team State timeline; an offseason bullpen transactions feed; the next-season dates. **No current reads** |
| **Evidence** | `02` §12; EOS-M03. The data exists |
| **Alternatives** | **(a)** Go dark with a holding page. Loses archive value and SEO. **(b)** Keep the in-season UI with "no games". This is the status quo, and it shows wrong reads. **(c)** The recommended archive mode. **(d)** Build hot-stove analysis. Out of the bullpen-intelligence scope and speculative |
| **Trade-offs** | (c) costs about 15–20 d (WP-1.1–1.4) |
| **Recommendation** | **(c)** |
| **Impact on canonical standards** | 03: offseason states for Home, Team and Pitcher |
| **Proceed without a policy change?** | **Needs a 03 amendment** (new page states) |

## DEC-07 — Reconcile Tonight-as-home with the Product Experience and Frontend standards

| | |
|---|---|
| **Decision** | Ledger the TN-10/TN-11 cutover: Tonight is the home page in season. The home page carries phase-appropriate states (DEC-06). The daily-edition role described for "Today" in 03:124 is fulfilled by Tonight plus named-arm What Changed |
| **Evidence** | `02` §2.2 C1; `tonight-v1-root-cutover-tn-10.md:3-5`; 07:130 forbids it |
| **Alternatives** | **(a)** Restore Today at `/`. **(b)** The recommended ledgering of reality and amending 03/07 |
| **Trade-offs** | (b) legitimizes a change made without governance. It is better than leaving the standards false |
| **Recommendation** | **(b)** |
| **Impact on canonical standards** | 03 §Today; 07:130 |
| **Proceed without a policy change?** | **No.** This *is* the policy record |

## DEC-08 — Governance simplification

| | |
|---|---|
| **Decision** | Keep the six canonical authorities but limit routine maintenance to (1) the Decision Ledger and (2) a ≤3-page `docs/current/CURRENT_STATE.md` (what runs, where, what is active). Treat 07 explicitly as a subsystem specification. Move the `CU_*` proof reports to `docs/audits/`. Stop roadmap revision-history churn |
| **Evidence** | EOS-029, EOS-035: 420 docs, 123k lines, the Roadmap at 131 KB, no canonical update since Sep 4, prior audit findings not executed. Constitution 01:169 (founder sustainability) |
| **Alternatives** | **(a)** Status quo. **(b)** The recommended reduction. **(c)** Collapse the canonical documents into one |
| **Trade-offs** | (b) loses some ceremony. It gains docs that are true |
| **Recommendation** | **(b)** |
| **Impact on canonical standards** | README / documentation map; 05 process sections |
| **Proceed without a policy change?** | **Needs a ledger decision** (it changes the governance process) |

## DEC-09 — Demand gate and kill criteria before 2027 growth investment

| | |
|---|---|
| **Decision** | Record a 2026 usage baseline from first-party traffic. Adopt written kill/reduce criteria for 2027, for example the prior audit's K1–K8, adjusted. No new distribution automation or posting volume until the Opening Day creator trial shows citations or different-day returns |
| **Evidence** | EOS-M04: no usage number has ever been recorded. The prior audit proposed exactly this on 2026-09-24 and it was not executed |
| **Alternatives** | **(a)** Grow first, measure later. **(b)** The recommended measure-then-grow |
| **Trade-offs** | (b) may reveal low usage. That is the point |
| **Recommendation** | **(b)** |
| **Impact on canonical standards** | 05 Phase 6 (Growth & Validation) gets numeric criteria. 06 distribution plan |
| **Proceed without a policy change?** | **The baseline readout: yes.** Kill criteria need the founder |

## DEC-10 — Postseason as a first-class phase in 2027

| | |
|---|---|
| **Decision** | Within the POSTSEASON phase: role evidence uses postseason deployment, phase-scoped; Team State is published for active clubs only; the archive records postseason workload separately; the ERA/WHIP exclusion is retained |
| **Evidence** | EOS-006. 02:269 (performance excludes the postseason) is correct for performance but was applied to roles |
| **Alternatives** | **(a)** Regular season only; go quiet in October. **(b)** The recommended approach |
| **Trade-offs** | Slightly more phase logic. It covers the highest-attention month |
| **Recommendation** | **(b)** |
| **Impact on canonical standards** | 02: role evidence windows |
| **Proceed without a policy change?** | **Needs a 02 amendment** (role evidence scope) |

## DEC-11 — Security baseline for a public repository

| | |
|---|---|
| **Decision** | Protect `main`. Use a `production` GitHub environment, restricted to `main`, with required reviewers for write-mode workflows. Create a read-only DB role for diagnostics. Set a distinct `USER_AUTH_SECRET`. Rate-limit public write endpoints. Prove a restore path |
| **Evidence** | EOS-009, EOS-010, EOS-011 |
| **Alternatives** | **(a)** Make the repository private. Reduces exposure but does not fix credential sprawl. It can be combined with the recommendation |
| **Trade-offs** | Slight friction for incident workflows (a reviewer prompt) |
| **Recommendation** | Adopt. Consider making the repository private if open-source value is not a goal |
| **Impact on canonical standards** | 04: security and operations section |
| **Proceed without a policy change?** | **Yes**, operational |

## DEC-12 — Data retention policy

| | |
|---|---|
| **Decision** | Keep forever: canonical tables, every *published* snapshot, share artifacts, season closures. Prune after 30 days: unpublished, failed and candidate snapshots and proof scaffolding. Keep traffic for 13 months. Archive raw final-game payloads to object storage |
| **Evidence** | EOS-015; snapshot IDs about 60 a day; the Supabase egress P0 in September |
| **Alternatives** | Keep everything (cost and performance drift); aggressive pruning (risks historical integrity) |
| **Recommendation** | Adopt as stated |
| **Impact on canonical standards** | 04: data lifecycle |
| **Proceed without a policy change?** | **Needs a ledger entry**, because it touches historical integrity |

## DEC-13 — React Router acceptance

| | |
|---|---|
| **Decision** | Migrate to React Router v7 before 2026-11-10 rather than re-accept the risk |
| **Evidence** | EOS-012; expiry 2026-11-13; production advisories are 2 moderate |
| **Alternatives** | Re-review and extend the acceptance by 90 days |
| **Trade-offs** | Migration costs 2–3 d now. Extending postpones the work into Phase 1 |
| **Recommendation** | **Migrate.** Extend only if WP-0.1 is not yet shipped by 2026-11-08 |
| **Impact on canonical standards** | None (D-ID for #645 closeout) |
| **Proceed without a policy change?** | **Yes** |

## DEC-14 — AI attribution rule (D-013)

| | |
|---|---|
| **Decision** | Either reaffirm D-013 ("no AI attribution in commits") and enforce it in PR review, or retire it. Current practice (8 Claude-authored commits merged) contradicts it |
| **Evidence** | `02` §2.2 C9 |
| **Recommendation** | Founder's choice. Make the rule match practice |
| **Proceed without a policy change?** | **No** |

---

## Governing decisions this audit does **not** recommend changing

- The descriptive-only contract (no prediction, betting, fantasy, medical or manager-intent claims).
- The three-word Team State vocabulary and the arm-read and role vocabularies.
- Fail-closed publication and immutable artifacts.
- Backend ownership of baseball semantics. The audit recommends *enforcing* it (EOS-019).
- ERA/WHIP exclusion of the postseason.
