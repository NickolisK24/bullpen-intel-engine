# Foundation 3C Bootstrap Closeout

- **Status:** R6 complete in production; Stage E1 verification **pending**
- **Owner:** Nickolis Kacludis
- **Rollout window:** July 2026
- **Pull requests:** #569 through #579
- **Canonical homes:** `docs/current/GAME_DRIVEN_DAILY_INGESTION.md` (operating
  contract), `docs/current/SYNC_PIPELINE.md` (pipeline), and
  `docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md` (decisions)

This is a **historical record**, not an operating manual. It preserves what
Foundation 3C did, what it proved, and what it deliberately left open. The
canonical documents own the current rules; this file does not restate them.

---

## What Foundation 3C was for

BaseballOS needed a governed way to reconcile official completed pitching lines
into local `GameLog` evidence, one game at a time, with a durable checkpoint per
game and a fail-closed publication gate. Before this work, the daily lane
reconciled by pitcher-season sweep, which could neither prove that a specific
completed game had been fully ingested nor refuse publication when it had not.

The bootstrap problem was the 109 governed final games already sitting
unreconciled in the correction horizon. Foundation 3C built the mechanism and
then used it, under review, to clear exactly those 109 games.

---

## The rollout

| Stage | PR | What it did | Outcome |
|---|---|---|---|
| — | #569–#571 | Canonical innings semantics; exclusive game scope | merged |
| R1 | #572 | Shadow validation of five already-written games | **passed** (re-run after D-009) |
| R2 | #573 | Full-window shadow review of the governed window | **passed** (re-run after D-009) |
| D-009 | #574 | Completed-game pitcher-identity authority; complete mutation planning | merged |
| R3 | #575 | Controlled-sample shadow authorization over five games | **passed** under contract 4 |
| — | #576 | Repaired identity-by-value fingerprint coverage; parity contract → 4 | merged |
| R4 | #577 | Controlled write of five games + immediate replay | **passed in production** |
| R5 | #578 | Full remaining-window shadow authorization over 99 games | **passed in production** |
| R6 | #579 | Full remaining-window write of 99 games + replay | **passed in production** |
| E1 | this PR | Independent closeout verification; rollout workflow retirement | **verification pending** |

---

## The two permanent data rules this work established

### D-008 — integer recorded outs are the semantic innings authority

`innings_pitched_outs` is the authority. The decimal `innings_pitched` is a
derived companion for display. MLB innings notation does not sum, float
accumulation is not reproducible, and a decimal difference alone is never a
correction. The rollout ignored **323** decimal-only representation differences
across the bootstrap without writing one of them.

### D-009 — a completed game is not current-roster authority

A completed game establishes what happened in that game. It never establishes
who a pitcher is today, what team he is on, or whether he is active. Current
roster and team state belong to the official roster authorities.

This was found mid-rollout: R1 and R2 originally passed on GameLog
reconciliation while the same reports silently carried **942 pitcher-identity
actions** — 940 metadata updates and 2 reactivations across 423 pitchers —
attached to rows whose GameLog action was `unchanged`. None appeared in the
manifest or the fingerprint. D-009 made those refusals structural rather than a
matter of source precedence, and both gates were re-run and re-passed on the
complete mutation contract.

---

## Fingerprint contract version 4

The complete reconciliation fingerprint covers the GameLog decision, the pitcher
identity decision **by value**, appearance-team authority, and blocked
decisions. It excludes ignored decimal representation drift and suppressed
historical current-state evidence.

Contract 4 exists because contract 3 had a real hole: the identity half
collapsed to a constant on the reported row, so a reviewed fingerprint would
have authorized *any* identity creation rather than the reviewed one — creating
pitcher 111 and creating pitcher 222 fingerprinted identically. PR #576 repaired
it, and the repair immediately exposed a second defect: the writer patched only
the identity action onto the row, so the shadow and write fingerprints diverged.
Both were fixed together. The contract version is hashed into the fingerprint,
so every pre-repair value became unreproducible by construction.

---

## R6 production evidence

| | |
|---|---|
| repository SHA | `81271e0671b9391b4297f3b438e2a8b836bf94d7` |
| workflow run | `30664706174` |
| reference date | `2026-07-29` |
| parity contract | **4** |
| approved fingerprint | `40659a4051226df40ef7cedbca7a6bc2689d5c2bfbdd4ccdb717fc6fc0c79343` |
| 99-game scope digest | `43b9333ad228c60846f1cd24ae8518273dc1017aefc98e7b7930974c40bdfd22` |

```
games attempted / completed / failed        99 / 99 / 0
appearance rows                            865 — 0 inserted, 0 updated,
                                                 865 unchanged, 0 blocked
newly completed work items                  99
total work items                     10  ->  109
completed final games                10  ->  109
unresolved final games               99  ->    0
publication complete              false  ->  true
reconciled appearance rows                 946
partial completion                       false
baseball data changed                    false
replay database drift                    false
```

**R6 wrote 99 work items.** It is not accurate to say the run performed no
database writes. The accurate statement is that **only governed ingestion
control state changed, and no baseball-data row changed.**

### Baseball-data hashes, identical before the write, after the write, and after the replay

```
GameLog content
  a53f40addf8b818872b3a2d1c0ba88b9f2579046c54feaf49cfe7a659e33abf3
canonical outs
  a4329604b7fdcb138f02cbd5ae6d7cc34bd120e2b6fc9ea5d1de47587854508d
correction provenance
  dd49944590c854b557adf62824633665b8214239fdf7fd668684f8d503e3c84e
appearance-team authority
  6fe8523b0474f67de003b3bff46becda70720ff3f35f75e56c402f1a744c2046
Pitcher current state
  009b99b589d25ac49722166ed1a125a18144063063a850a16bd134c9d60cf626
```

These are **historical** values. Later verification does not require its own
hashes to equal them, because legitimate current-roster synchronization may
happen afterwards. Each verification requires its own before and after to equal
each other.

---

## Dead letters — stated precisely

**R6 created no new dead letters.** The pre-existing global count remained
**1,389** during R6.

That global figure belongs to unrelated workstreams and has nothing to do with
Foundation 3C. It would be wrong to write "dead letters: 0", "the system has no
dead letters", or "production is free of dead letters". The correct claims are:

- zero dead letters are associated with the governed 109-game bootstrap;
- R6 created no new dead letters;
- the global count was 1,389 at R6 closeout and remains an open, separate matter.

---

## Transaction boundary

The canonical writer commits **once per game**. Multi-game atomicity does not
exist and was never claimed. A failure partway through R6 would have left the
already-committed games durably checkpointed, and that state would have been
reported as FAILED with the exact completed and unresolved subsets — never
retried, never compensated, never deleted. R6 did not partially complete.

---

## What Foundation 3C did NOT resolve

This bootstrap closeout makes no claim about BaseballOS data quality in general.
The following remain open and are outside its scope:

- **14 false GameLog provenance events.** Rows carry correction provenance for
  changes that appear not to have happened. No before-images are reconstructible.
  `backend/scripts/inspect_first_write_pitcher_identity.py` is retained for that
  investigation and is deliberately **not** part of Stage E cleanup.
- **First-write Pitcher forensics.** Possible historic Pitcher changes during
  the first write remain unproven either way.
- **1,389 pre-existing global dead letters** at R6 closeout.
- **#561 / #562 deployment smokes** never ran.
- **Data & Trust `/api/bullpen/dashboard`** failure.

---

## Rollout state at closeout

- `GAME_DRIVEN_INGESTION_MODE` remains **off**. The bootstrap was performed by
  explicit manual dispatch; the automated lane was never enabled.
- **Authoritative mode remains unapproved.**
- Enabling either is a **separate decision** on its own merits. A completed
  bootstrap is a precondition, not an argument.

---

## Stage E verification status

**PENDING.**

Stage E1 (this pull request) retires the temporary rollout workflows, adds one
final read-only closeout workflow, and consolidates permanent regression
coverage. The production verification itself has **not been executed** at the
time of writing.

Stage E has two parts because a GitHub Actions workflow cannot verify production
after merge and also delete itself in the same already-merged commit.

### Section reserved for the E2 update

> **To be completed after the Stage E1 production closeout runs.**
>
> Record here: the Stage E workflow run ID, the repository SHA, the result, the
> verified 109/0 state, the 946 reconciled appearance rows, the full-bootstrap
> replay totals, the final contract-4 full-bootstrap fingerprint, the full-scope
> SHA-256, the observed global dead-letter count and its delta from 1,389, and
> confirmation that the replay caused no database drift.
>
> E2 then deletes the Stage E workflow and its temporary support files, removes
> the remaining rollout-only scope helpers, and proves no temporary Foundation 3C
> rollout workflow remains.
