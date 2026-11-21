# Sync 3.0 coverage registry

[Coverage registry](coverage.csv) is the NP-01 acquisition and derivation contract. Each row groups fields sharing identity and lifecycle. The source and authority describe who can establish a fact. The inputs, cadence, retention, historical coverage, correction and consumer columns describe how to carry it through replay. The pinned [historical field definitions](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/docs/sync-pipeline/SP-00_BULLPEN_DATA_CENSUS_AND_ACQUISITION_CONTRACT.md#12-master-fielddata-matrix) supply the original detailed taxonomy. The [current census](../audits/NP-00-existing-pipeline-census.md) identifies verified implementations and unresolved ownership.

## Qualification

- Every row requires source identity, represented date or game, acquisition time, completeness and version. Retrospective acquisition keeps its actual acquisition timestamp. Absence requires a complete applicable source. Missing numeric data stays null.
- MLB official lines govern final totals. Preserve differing live observations. The official club and roster class govern membership; affiliate activity cannot establish MLB eligibility. Keep active, forty-man and organizational membership separate.
- Savant and future enrichment rows specify coverage to acquire. Historical eras, taxonomy changes, actual sample coverage and retention need adapter-level verification. Undemonstrated coverage remains unsupported for delivery. Pitch movement and velocity provide descriptive evidence only.
- Derived rows require the contributing records, cohort, methodology version, numerator and denominator where applicable. Publication requires matching reference dates, generation and proof. A correction supersedes a cited result while the earlier published claim remains reproducible.
- During offline development all work uses isolated databases, local evidence and candidate artifacts. Unknown external production writers are an open gate on production access, cutover and retirement.

## Disposable rehearsal

From `backend`, run `python -m sync_v3.rehearse --pg-bin /path/to/postgres/bin` as an unprivileged OS user with psycopg2 installed. The launcher creates and removes a private UTF-8 PostgreSQL cluster, accepts connections through its private Unix socket, creates a restricted candidate writer and exercises a rejected update to a synthetic legacy selector. It takes no database URL. No scheduled task or Flask application is started.

## Official-source replay

From `backend/`, capture one historical day from the public MLB Stats API, then replay the local file. The capture records the date requested and a distinct retrieval timestamp for each parsed provider response. A retrospective response cannot certify what a contemporaneous sync saw.

```sh
python -m sync_v3.capture_day 2024-08-05 /tmp/baseballos-2024-08-05.json
python -m sync_v3.rehearse --pg-bin /path/to/postgres/bin --fixture /tmp/baseballos-2024-08-05.json
```

| Retrospective acquisition, November 21, 2026 UTC | Accepted final games | Official pitching lines compared | Roster and queue outcome |
|---|---:|---:|---|
| October 30, 2023, World Series Game 3, TEX/ARI and transaction subjects | 1 | 10 | 41 distinct requests completed |
| October 30, 2024, World Series Game 5, LAD/NYY and transaction subjects | 1 | 13 | 37 distinct requests completed |
| August 5, 2024, all 30 MLB clubs | 9 | 74 | 148 of 149 requests completed with accepted evidence; Boston forty-man reconciliation refused |

A final comparison checks game, club, player, outs, earned runs, runs, hits, walks, strikeouts, home runs, batters faced and pitches against the retained official boxscore. It does not establish complete pitch-event, roster or product parity. Boston's [August 5 roster](https://statsapi.mlb.com/api/v1/teams/111/roster?rosterType=40Man&date=2024-08-05), retrieved at 03:44:59 UTC, included Bryan Mata (667356) with parentTeamId 6052. Both the alternate roster path and the hydrated official response repeated that value. The [2024 team lookup](https://statsapi.mlb.com/api/v1/teams/6052?season=2024) identifies a college team. The SP-05 complete club-scope check therefore refuses this source. Its parsed-content SHA-256 was `1a5623cef74ca0b7859768912186de9b73d46d1ff2e39d096c51430c5c6d44b9`. A retry may acquire qualifying evidence; the previously accepted membership cannot silently fill this gap.

The engine preserves independent active and forty-man sources. Duplicate entries within one list preserve observed membership while conflicting individual status codes withhold a unique status. Transaction hints enqueue MLB-club confirmation, without giving an affiliate transaction membership authority. The regular-slate rehearsal originally made 193 fetches for 149 distinct requests. Reusing still-pending roster fetches reduced it to 149 with the same nine accepted finals and the same governed refusal.

Run the integration checks with `SYNC_V3_TEST_PG_BIN=/path/to/postgres/bin python -m pytest -q tests/test_sync_v3*.py`. Shard 4 of the backend CI suite provides the local server binaries. These clients and selectors operate only in the disposable rehearsal. Production shadow comparison, publication and retirement are separate gates.

### Workload replay

Add `--team 111 --through 2024-08-07` or `--pitcher MLB_ID --through YYYY-MM-DD` to the disposable rehearsal. Pass one `--fixture` per covered baseball date. Team totals count official relief for the club represented in the game. Per-arm rest includes supported openers and follows pitchers across clubs. The next baseball date is the rest reference. Team concentration identifies the dated MLB active-roster split separately from the published Board bullpen cohort. Missing coverage withholds the affected window.

A three-day retrospective replay for August 5–7, 2024 compared 338 pitching lines across 39 accepted finals. Boston recorded 12 official relief appearances, 185 pitches and 35 outs. An independent sum over the three retained official boxscores gave daily lines of 4/60/9, 5/59/13 and 3/66/13 (appearances/pitches/outs). Seven-day concentration lacked four days of coverage. The rehearsal exited with a withholding result for Boston forty-man sources and for transaction IDs 793270 and 793525, each of which included a player entry and a separate entry without a player under the same ID. Those receipts do not establish a unique transaction record. Accepted workload can be inspected even when another domain is withheld.

The August 1–7, 2024 replay on PostgreSQL 17.6 qualified three- and seven-day workload totals for all 30 clubs, including the seven-day contributor rankings. It compared 788 pitching lines from 89 finals. Boston's nine relief pitchers recorded 22 appearances, 327 pitches and 68 outs. The top three threw 169 pitches (51.68%). The team rehearsal now recounts each complete window directly from retained boxscores and fails on disagreement. A missing or blank official innings field withholds the final even when treating the missing value as zero would match team outs. Wider windows and the unqualified roster and transaction domains retain their separate coverage requirements.

The pitcher rehearsal also reports a descriptive comparison over 30 covered regular-season baseball dates. It compares the latest single outing's pitches with the maximum in earlier outings in the same window and reports the prior sample size and total. A missing date or count, ambiguous workload class, empty prior sample or unordered doubleheader at the latest date withholds the comparison. The candidate supplies the measured difference for research. A public pitch-spike label has no adopted calibration in the current Board contract.
