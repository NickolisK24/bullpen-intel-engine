# CR-04 Integration Deployment and Atomic Publication Cutover

## 1. Objective and verdict

CR-04 remains **BLOCKED**. The recurring Render and queue-fairness gates are
closed, and the first governed production SP-11 publication now exists. The
public-reader cutover is correctly withheld because publication 1 does not
contain the public Team Board v2, What Changed, or public pitcher-current
artifacts required for a complete generation.

This is a fail-closed result. Atomic reads remain disabled and the legacy
publication/read path remains public authority. CR-05 has not started.

## 2. Starting integration SHA and branch

The remediation branch `feat/cr04-publication-reader-proof` was created from
`feat/sync-pipeline` at
`fe24ad26c41552c9bbee06f0381087d7a566152a`. Main was neither checked out nor
modified.

## 3. Recurring production execution

The production evidence supplied for this remediation closes the recurrence,
roster, observation-stability, finality-recovery, and queue-fairness gates:

* Render cron: `crn-da98kclg1s2s739k0870`
* branch: `feat/sync-pipeline`
* schedule: `*/3 * * * *`
* command: `python backend/scripts/run_sync_pipeline_shadow.py --max-jobs 24 --include-morning --include-continuous-observation`
* active-roster authority: 30/30
* 40-man authority: 30/30
* SP-10 pending: 115 to 15
* SP-10 succeeded: 224 to 327

CR-02 observation semantics remain healthy. Required historical-finality
retry/dead work has governed recovery. SP-09 remains bounded. These facts are
not re-proved by this branch.

## 4. Candidate reselection

Production workflow run `34525980130` selected cohort `330`, rather than stale
candidate `205`.

| Field | Value |
| --- | --- |
| Cohort | `330` |
| Impact plan | `337` |
| Authority | `corrected_final` |
| Baseball date | `2026-09-10` |
| gamePk | `823413` |
| Teams | `117`, `143` |
| Pitchers | `232`, `615` |
| Source observations | `831`, `838` |
| Cohort fingerprint | `368747854397d2b0e1272c1b3e5bfdb1039499dd5adcda82b604602e92c8fa2e` |
| Input-manifest fingerprint | `cf18a04f5b24686723b7e02f3a504633d375c07a0dcc9f351bb12374da0e2188` |

The cohort was complete, current, non-live, had no withheld domains, and had
five direct candidate snapshots. Its affected scope had no unresolved required
queue blocker.

## 5. Baseline bootstrap

SP-11 originally could not create a safe first generation because predecessor
inheritance was unavailable. The baseline builder now materializes only
existing, complete SP-10 candidate snapshots:

* one team artifact for every MLB team;
* one pitcher artifact for every available current pitcher snapshot;
* one game artifact for every available current matchup snapshot.

It records each source snapshot/cohort identity, is deterministic and
idempotent, does not recompute baseball intelligence, and rejects incomplete
30-team coverage. It does not fabricate source history or mutate canonical
facts.

## 6. Pre-publication health

Run `34526238360`, evaluated at `2026-09-10T20:26:52.813992`, passed every
publication precondition:

| Check | Result |
| --- | --- |
| Active roster | 30/30 |
| 40-man roster | 30/30 |
| Unreconciled Finals | 0 |
| Blocking dead work | 0 |
| Required retry-wait work | 0 |
| Stale leases | 0 |
| Pending SP-09 work | 0 |
| Pending SP-10 work | 0 |
| Candidate current/complete | PASS |
| Atomic pointer | null and consistent |
| Atomic pointer owner | `services.atomic_publication.publish_derived_cohort` only |

## 7. First atomic publication

After explicit confirmation, controlled workflow run `34526501184` published
cohort `330` through SP-11.

| Field | Value |
| --- | --- |
| Publication job | `2030` (succeeded) |
| Publication SyncRun | `8657` |
| Publication | `1` |
| Fingerprint | `45c5d0957c8296e9e5b1cd045fd6eb930a74f711ba3670cea67644a0482f27c2` |
| Predecessor | null |
| Pointer | null to `1` |
| Artifact IDs | `1` through `1013` |
| Newly materialized | 1,013 |
| Inherited | 0 |
| Team artifacts | 30 |
| Pitcher artifacts | 790 |
| Game artifacts | 193 |
| Published at | `2026-09-10T20:28:47.981085` |
| Source data-through | `2026-09-10T19:54:17.054683` |

The pointer moved only after validation and artifact persistence. The legacy
public API remained authoritative because atomic reads were false. The
publication flag was enabled only for the explicitly confirmed controlled
workflow.

## 8. Natural lineage

Publication `1` is linked to a natural official correction for game `823413`:

* source observation `838`, authoritative and complete, version `2`, outcome
  `corrected`, observed at `2026-09-10T19:54:17.054683`;
* source job `1974`, source SyncRun `8536`, source subject `655`;
* current final-game version `196`, version number `2`, with boxscore
  observation `831`, finality observation `837`, and play-by-play observation
  `838`;
* final mutation `1881`, subtype `final_play_by_play_corrected`;
* impact plan `337`;
* derived cohort `330`;
* publication job `2030` and publication SyncRun `8657`;
* publication `1`, now referenced by `atomic_publication_current`.

The production lineage inspector reports final-version and mutation
associations directly from the impact-plan references. IDs are not inferred
from timestamps.

## 9. Live-to-final evidence

The same natural game has provisional appearance states `37`, `38`, `44`,
`45`, `46`, `47`, and `48`. They are no longer current and were superseded at
`2026-09-10T19:41:40.516606` by initial final-game version `195`; official
correction processing then produced current final-game version `196`. Natural live mutation
evidence includes starter-exit/reliever-entry pairs `151`/`152`, `154`/`155`,
`158`, and `162` from observations `810`, `812`, `818`, and `822`.

This proves authority supersession. A full production numerical comparison of
live-derived versus final workload remains an evidence limitation; no production
state was manufactured to close it.

## 10. Atomic reader boundary

`SYNC_PIPELINE_ATOMIC_READS_ENABLED` defaults false and is frozen into Flask
configuration at process startup. When enabled, the request boundary:

1. resolves `atomic_publication_current` once;
2. validates generation-wide reader coverage once;
3. freezes the publication context in request-local state;
4. loads only artifacts associated with that publication;
5. rejects an artifact whose publication identity differs.

The production trusted Team Board override respects this boundary rather than
silently replacing an atomic response with a legacy snapshot response.

## 11. Reader coverage gate and blocker

Production reader proof run `34528840066` inspected publication `1`:

| Requirement | Available |
| --- | --- |
| Team baseline artifacts | 30/30 |
| League rows | 30/30 |
| Game matchup artifacts | 193 |
| Team Board v2 payloads | 0/30 |
| What Changed payloads | 0/30 |
| Public pitcher-current payloads | 0/790 |

The SP-10 snapshots contain internal workload/rest and arm-read evidence, but
not the governed public pitcher response. Likewise, `read_models.team_board`
is the older team-board shape, not the public `board-v2` core/details contract,
and `what_changed` contains summary identity rather than a public payload.

Consequently every atomic reader request fails closed with HTTP 503 and
`atomic_publication_reader_coverage_incomplete`. Coverage is cached only by
database identity and immutable publication fingerprint, so it is not
recomputed per artifact request and cannot become stale across a pointer
transition.

## 12. One-lookup and race proof

PostgreSQL tests prove that a request bound to publication N continues reading
N after another transaction advances the singleton pointer to N+1. Artifact
lookups use the frozen publication ID, never another latest/current query.

Those same tests prove 30-team league inheritance under one publication and
reject mixed-publication artifacts. The production generation cannot yet pass
the public Team Board v2, pitcher, or What Changed coverage gate, so an API
cutover was not attempted.

## 13. Legacy versus atomic comparison

Read-only production dual-read runs compared three teams, five pitchers, two
games, the league listing, dashboard, and What Changed. Earlier diagnostic
results showed structural-only game-matchup differences with additive atomic
metadata and lower observed request time. They also exposed incompatible
internal pitcher and league payload shapes. The final fail-closed run classifies
all atomic cases as blockers instead of allowing a partial generation.

No semantic parity claim is made for the missing reader families. That is the
precise remaining CR-04 blocker.

## 14. Request-time write audit

The proof script snapshots publication, artifact, pointer, source-observation,
and derived-snapshot counts before and after reads. It reports no publication,
artifact, or pointer writes. The atomic handlers do not create canonical facts,
repair state, build snapshots, or publish on GET.

The proof calls the actual Team Board v2 and dashboard routes in addition to
the v1 compatibility routes, preventing a false pass based only on unused
surfaces.

## 15. Public API and deployment decision

No public API service was moved to this branch and atomic reads were not enabled
publicly. Deploying the reader flag now would make core product routes return
503 because the generation lacks required public artifacts. Legacy reads remain
available and authoritative.

## 16. Publication safety and duplicate writers

SP-11 is the sole owner of `atomic_publication_current`. Legacy publication may
continue writing its existing snapshot system but cannot move the SP-11 pointer.
With atomic reads false, a request uses legacy authority only; when atomic reads
are eventually enabled, the resolver will not mix in legacy semantic fallbacks.

## 17. Second publication and inheritance

No second natural publication was attempted. A second publication cannot fix
the missing artifact families because the current SP-10 candidate schema does
not produce them. PostgreSQL inheritance and N-to-N+1 race behavior remain
covered by integration tests. Publication `1` remains immutable.

## 18. Performance

An early production diagnostic measured game/matchup atomic reads at roughly
127-128 ms versus 430-434 ms for legacy reads. The incomplete league-shaped
atomic response was roughly 1,753 ms versus 446 ms and is not an acceptable
comparison because its schema was invalid. Team Board and pitcher performance
cannot be certified until complete public artifacts exist. No misleading final
median/p95 claim is made from these sparse samples.

## 19. Rollback

Set:

```text
SYNC_PIPELINE_ATOMIC_READS_ENABLED=false
SYNC_PIPELINE_PUBLICATION_ENABLED=false
```

Restart only the affected services. Reads remain on legacy authority and new
SP-11 publication stops. Publication `1`, its 1,013 artifacts, the pointer
history, observations, cohorts, and canonical evidence remain intact. No data
deletion, migration downgrade, or direct pointer edit is required.

## 20. Validation

Focused local validation at the reader-coverage checkpoint:

* atomic publication/reader/trusted-board suite: 59 passed, 3 skipped;
* atomic route and reader suite: 26 passed, 3 skipped;
* bounded coverage tests: 10 passed;
* proof scripts compile successfully.

Final branch CI must be recorded in the PR before this evidence is treated as a
merge-ready remediation.

## 21. Remaining blocker

The blocker remains inside CR-04, not CR-05: SP-10/SP-11 must supply immutable,
publication-bound public artifacts for Team Board v2, What Changed, and pitcher
current-state responses. Until a first generation has complete public-reader
coverage, parity and public API cutover cannot be proven safely.

Scheduler retirement, legacy authority retirement, and final production
authority cutover remain out of scope and belong to CR-05 only after CR-04
passes.

## 22. CR-04 verdict

**BLOCKED**. Natural production SP-11 publication and atomic pointer transition
are proven. Atomic request identity, N-to-N+1 freezing, rollback, and
request-time write safety are implemented. Complete public-reader artifact
coverage, production parity, and safe public API deployment are not yet proven,
so atomic reads remain disabled and legacy remains public authority.

## 23. Final artifact-coverage remediation

The final CR-04 implementation moves the three missing public read families
into SP-10 without changing their baseball semantics:

* `team_board_v2_publication` freezes the existing Team Board v2 full, core,
  and details payloads under one candidate identity;
* `pitcher_current_publication` freezes the existing pitcher detail workload,
  rest, availability, roster, role, recent-work, and deployment response;
* `what_changed_publication` freezes the governed team comparison and records
  whether it has a comparable predecessor cohort or is a no-predecessor
  baseline.

The generic `team_intelligence`, `pitcher_intelligence`, and
`game_intelligence` candidates remain separate. SP-11 packages the specialized
snapshots by their explicit artifact types and may inherit each independently.
It does not query current baseball tables or derive these payloads.

Because publication `1` is immutable and incomplete for atomic public reads,
SP-10 detects that the current generation lacks reader coverage and performs
one explicit baseline materialization from the current immutable Dashboard
snapshot plus its governed candidate-time authorities. This baseline covers all
30 team and Team Board artifacts and the pitcher set named by those frozen Team
Boards. Once a complete publication becomes current, ordinary impact scope and
artifact inheritance resume; a one-pitcher or one-team mutation does not repeat
the league baseline.

Before moving the pointer, SP-11 now requires all 30 generic team artifacts,
all 30 Team Board v2 artifacts, all 30 What Changed artifacts, one league row
per MLB club, a pitcher-current artifact for every pitcher in the frozen
active-bullpen denominator, and at least one governed game/matchup artifact.
An incomplete generation raises a validation error before the pointer
transaction. Old incomplete artifacts are not inherited into a reader-ready
generation. Published history is never edited.

The real Team Board v2 full/core/details routes now use the same request-local
atomic context as the team, pitcher, matchup, league, and What Changed routes.
Each artifact lookup names its exact artifact type. The league reader batches
30 direct team artifacts into one artifact query and one snapshot query,
removing the earlier per-team lookup pattern. PostgreSQL coverage includes a
pointer N to N+1 race for Team Board v2, pitcher-current, and What Changed; the
frozen request remains on N for all three.

Production activation remains fail closed. The code is deployed with
`SYNC_PIPELINE_ATOMIC_READS_ENABLED=false`; no public API switch is authorized
until a new natural cohort creates a complete publication, the read-only
coverage report passes, dual-read semantic parity passes, and rollback is
rechecked. Publication `1` remains historical evidence and is not modified.

## 24. Cohort 484 watermark remediation

Production cohort `484` (impact plan `491`, `roster_authoritative`, baseball
date `2026-09-11`, Team `134`, pitchers `388` and `390`) started at
`2026-09-11T04:03:27.216947`, was created at
`2026-09-11T04:03:27.216957`, and completed at
`2026-09-11T04:05:16.488412`. Its 38-row captured and completion manifests
both fingerprinted to
`c8a1083caf8fa602bbe9a26ab09cd65b952d555420b1c4e767874cac171fc3d3`.
The current manifest retained the same 38 identities but fingerprinted to
`d82f4dddf68db0b4625ff859e077c13a915bf3fdec2609d999afeb4eb923b9d5`.
The schema has no `stale_at` field: the immutable cohort row remains complete,
while SP-11 rejects it as `cohort_input_watermark_drifted`.

Exactly four Team `134` forty-man membership versions changed:

| Interval | Pitcher | MLB ID | Captured version | Current version | Close mutation |
| --- | ---: | ---: | --- | --- | ---: |
| `633` | `1017` | `668716` | `633:2026-09-10:open` | `633:2026-09-10:2026-09-11` | `1302` |
| `622` | `396` | `681895` | `622:2026-09-10:open` | `622:2026-09-10:2026-09-11` | `1295` |
| `624` | `398` | `682995` | `624:2026-09-10:open` | `624:2026-09-10:2026-09-11` | `1297` |
| `635` | `405` | `802419` | `635:2026-09-10:open` | `635:2026-09-10:2026-09-11` | `1304` |

All four intervals were closed at `2026-09-11T04:06:27.964806` by complete,
authoritative roster observation `1112` (source subject `738`, SyncRun `10752`,
SyncJob `3922`, observed `2026-09-11T04:06:29.449575`). This was legitimate
new roster authority about 71 seconds after cohort completion, not a cohort
self-write, live/final race, pregame drift, or global unrelated watermark.
The roster-authoritative plan semantically depends on these exact Team `134`
membership intervals, so retaining them in the manifest is required.

The owner pipeline did not strand the advance. Close mutations `1295`, `1297`,
`1302`, and `1304` produced replacement impact plan `496` and cohort `489`.
Cohort `489` ran from `2026-09-11T04:18:02.655008` through
`2026-09-11T04:20:00.042057`; its captured and current input fingerprints both
equal `38129a6a1607c6abaa1b6754f664a1fe44dbd2b01067b3f25e24740680e84937`.
It is therefore fresh, but it cannot be published: it contains 30 generic team
snapshots, 30 What Changed artifacts, and four generic pitcher snapshots, while
Team Board v2, pitcher-current, and a governed game artifact are absent.

The missing specialized artifacts exposed a separate baseline packaging defect.
The SP-10 read rebuild correctly computed the full reader baseline while the
current publication is incomplete, but a roster plan without an explicit
`read_models` domain discarded its already-computed Team Board v2 and
pitcher-current results. SP-10 now retains Team Board v2, pitcher-current, and
What Changed candidates whenever the one-time publication baseline is required,
whether the plan reaches the rebuild through `team_snapshot` or `read_models`.
After a reader-complete publication exists, this behavior switches off and
ordinary bounded impact scope resumes.

No watermark input was removed and completion-time revalidation is unchanged.
Tests prove relevant final-authority advancement still makes a cohort stale,
the new authority can produce a fresh replacement cohort, unrelated source or
derived compatibility changes do not invalidate a bounded manifest, and
post-baseline team snapshot work remains scoped. A new naturally triggered
cohort under the deployed fix is still required before artifact coverage or
publication can be certified; cohorts `484` and `489` must not be published.
