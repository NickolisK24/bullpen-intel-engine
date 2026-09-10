# Foundation 3C Bootstrap Closeout

- **Status:** **CLOSED.** Bootstrap complete; Stage E1 verified in production; all rollout workflows retired
- **Owner:** Nickolis Kacludis
- **Rollout window:** July 2026
- **Pull requests:** #569 through #580, plus the Stage E2 closure
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
| E1 | #580 | Independent closeout verification; R1–R6 workflow retirement | **passed in production** |
| E2 | this PR | Stage E workflow and temporary support retired; rollout closed | repository closure only |

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

## Stage E verification — PASS

Stage E1 executed in production and independently verified the completed
bootstrap. It wrote nothing.

| | |
|---|---|
| result | **PASS** |
| repository SHA | `bd7e610a368c2229943a459cef887a1fe94194ff` |
| workflow run | `30673146173` (run 1, attempt 1, `workflow_dispatch`) |
| dispatched | 2026-07-31T23:32:02Z |
| completed | 2026-07-31T23:35:36Z |
| artifact | `foundation-3c-stage-e-bootstrap-closeout` |

### Verified bootstrap state

```
expected final games        109
completed final games       109
unresolved final games        0
terminal failures             0
correction-pending games      0
publication complete       true
reconciled appearance rows  946
```

### Full 109-game replay

```
requested / planned / completed in shadow    109 / 109 / 109
failed games                                   0
rows expected                                946
rows unchanged                               946
rows inserted / updated / blocked          0 / 0 / 0
decimal-only differences ignored             323
```

### Mutations and integrity

```
GameLog / pitcher identity / appearance team / complete plan    0 / 0 / 0 / 0
database drift                                               none
work items changed                                             no
checkpoints changed                                            no
governed-game dead letters                                      0
```

**No baseball-data mutation occurred during Stage E1.**

### Dead-letter accounting

| | |
|---|---:|
| global count at R6 closeout | 1,389 |
| global count observed at Stage E1 | 1,389 |
| delta | 0 |
| governed-bootstrap dead letters | **0** |

The global figure belongs to unrelated workstreams. It is recorded, not
resolved, and Stage E made no claim that the system is free of dead letters.

### Final historical identities

```
parity contract version   4

full-bootstrap fingerprint
  9f0fe9839e5aef4149dd6f2761d038e600ca1ea9562830832f5f952324d3e2c6

full-scope SHA-256
  e8cde57b9fe1033077533f7bee0cc64fc5969aa7fa3fc64efdc672c26d08a804

write approved            false
future write authorized   false
```

**These are historical closeout identities and nothing more.** They record what
the completed bootstrap looked like on 2026-07-31. They are not authorization,
they cannot be supplied to authorize a future write, and no future write
inherits approval from them. Any later write requires its own reviewed
fingerprint produced by its own reviewed shadow.

---

## Rollout closure

| | |
|---|---|
| R1–R6 workflows | retired during Stage E1 (PR #580) |
| Stage E workflow | retired during Stage E2 |
| Foundation 3C rollout workflows remaining | **none** |
| temporary Stage E scripts and tests | removed during Stage E2 |
| permanent runtime and regression coverage | intact |
| `GAME_DRIVEN_INGESTION_MODE` | **off** |
| authoritative mode | **unapproved** |

**The Foundation 3C bootstrap rollout is closed.**

The permanent architecture it built remains in production service: the planner,
the reconciliation and identity authorities, canonical integer-outs semantics,
contract-4 fingerprinting, exclusive scope, per-game transactional checkpoints,
and fail-closed publication completeness. What was retired is the temporary
machinery that performed a one-time backfill, not the machinery that runs.

### What was deliberately kept

- **`backend/scripts/profile_daily_ingestion_readonly.py`** and its test, as
  `activation_operations_support`. The next controlled stage is automated
  shadow activation, and this read-only profile is how that gets observed.
- **`backend/scripts/inspect_first_write_pitcher_identity.py`**, as
  `unresolved_forensic_support` for the open first-write provenance question.

### Next stage

**Automated game-driven ingestion shadow activation**, as a separately reviewed
change with its own evidence and its own production observation. A completed
bootstrap is a precondition for considering it, not an argument for it. No
activation decision has been made.

---

## Still unresolved — outside this closeout

This record closes the Foundation 3C bootstrap. It closes nothing else. The
following remain open and separate:

- **14 false GameLog provenance events** — rows carrying correction provenance
  for changes that appear not to have happened, with no reconstructible
  before-images.
- **First-write Pitcher forensics** — possible historic Pitcher changes during
  the first write, unproven either way.
- **1,389 pre-existing global dead letters**, unchanged through R6 and Stage E1.
- **Data & Trust `/api/bullpen/dashboard`** failure.
- **#561 / #562 deployment smokes**, never run.
