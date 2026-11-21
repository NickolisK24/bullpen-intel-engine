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

Use `--league --through YYYY-MM-DD` with the dated fixtures to compare all 30 clubs in one disposable database. The report lists the windows independently recounted and the dates with missing evidence for each club. For the August 1–7 sample, loading all club calendars together took 0.054–0.069 seconds over three local PostgreSQL 17.6 repetitions. Loading each club separately took 0.332–0.446 seconds. The calendar contents were identical in each comparison. These timings cover calendar assembly only.

The July 16, 2024 All-Star replay retained 20 official pitching lines across the two league representative teams. It established a covered regular-season off-day for all 30 franchises. The special team identities 159 and 160 qualify as a pair solely for the official All-Star game type. An unknown game type withholds the schedule. The Boston–Toronto suspended game 746942 appears on both June 26 and August 26. Its combined final boxscore remains available, while the two club workload calendars withhold dates requiring session-level attribution. Replaying both slates verified 27 distinct finals and 224 pitching lines. [MLB game types](https://statsapi.mlb.com/api/v1/gameTypes) · [June 26 Boston schedule](https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=111&date=2024-06-26) · [August 26 Boston schedule](https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=111&date=2024-08-26)

An accepted dated active roster can establish pitcher identity for a covered zero-outing window. The rehearsal cites that roster receipt separately from the schedule and finals. A pitcher with no dated appearance has an unknown last appearance even when a complete workload window contains zero outings.

The July 9–August 7, 2024 replay retained 3,601 official responses across 30 baseball dates. The candidate verified 359 finals and 3,107 pitching lines. All 30 clubs matched all five inclusive windows (3, 5, 7, 14 and 30 days) for official relief appearances, pitches, outs and batters faced. The comparator checks the scheduled games independently of the candidate's cited boxscores. Missing batters faced withholds that measure. The existing public Board window contract keeps its original fields and windows.

Lucas Erceg (668674) pitched for Oakland and Kansas City during the same month. All five candidate windows matched his separately retrieved official game log. The 30-day window included ten outings, 132 pitches, 34 batters faced and 26 outs. His August 7 outing had 22 pitches versus a prior maximum of 21 over nine outings. These are descriptive regular-season workload facts. The batch ended with 26 source refusals across 18 dates (13 transaction conflicts and 13 roster scope conflicts). [Official pitcher game log](https://statsapi.mlb.com/api/v1/people/668674/stats?stats=gameLog&group=pitching&season=2024&sportIds=1&gameType=R&limit=200)

### Observed deployment

With the dated fixtures loaded, use `--game GAME_PK --through YYYY-MM-DD` to inspect one competitive final. The candidate reports each official relief line's credited save, hold, finish and outs. Qualified play-by-play supplies entry inning and score margin under the existing Board convention. The source checks require ordered completed plays, matching fielding-team and pitcher batter counts, a compatible final score and play evidence acquired at or after the verified boxscore. Ambiguous entries preserve the official line and carry a withholding reason.

Across the August 7, 2024 slate and the two October 30 World Series fixtures, 150 official relief appearances were represented. Entry evidence qualified for 114 appearances in 15 games. Three games had divergent play and official batter counts, and one included a pitching change within a plate appearance. On August 7, Erceg entered game 746272 in the seventh with Kansas City leading by four, recorded five outs and earned a hold. This establishes observed usage in that game. [Official boxscore](https://statsapi.mlb.com/api/v1/game/746272/boxscore) · [Official plays](https://statsapi.mlb.com/api/v1/game/746272/playByPlay)

Add `--deployment-team TEAM_ID --through YYYY-MM-DD` to the rehearsal to compare two adjacent seven-day windows of game-side relief appearances. Each day requires an accepted slate, including off-days, and a compatible final for every applicable game. The candidate uses the Board's role-movement classifier and recorded leverage thresholds. In the 14 days through August 7, 2024, 30 clubs had complete game coverage. Of 345 pitcher-club profiles, 16 were stable and two shifted toward later innings. Austin Voth and A.J. Minter each moved from zero late entries in three known outings to two in three. The remaining 327 profiles lacked the governed appearance or signal sample.

For pitcher season context, include the player in the acquisition, then inspect the saved fixture.

```sh
python -m sync_v3.capture_day 2024-08-07 /tmp/kc-aug7.json --team 118 --pitcher 668674
python -m sync_v3.rehearse --pg-bin /path/to/postgres/bin --fixture /tmp/kc-aug7.json --pitcher 668674 --through 2024-08-07
```

The season and 14-day samples use credited regular-season game dates, separate starts from relief, cite the game identities and retain per-club splits across trades. The player game log must agree with the dated MLB pitching totals for every represented franchise and with overlapping confirmed final lines. MLB may return a separate all-sports row with the same club identity. Only sport ID 1 supplies MLB comparison authority. The 45-day role classification uses the existing descriptive classifier and discloses its recorded leverage sample. Through August 7, Erceg had 38 relief outings for Oakland and four for Kansas City. Nick Martinez's completed 2024 regular season contained 26 relief outings with 160 outs and seven holds, plus 16 separately accounted starts.

### Pitch measurements

The game rehearsal reports pitch mix for each qualifying relief outing when tracked pitch identities resolve, every pitch has a type and the count matches the official final. Each physical measurement carries its own measured sample. An incomplete speed, spin, extension, release or movement sample withholds that type's mean. The pitcher rehearsal groups expected relief outings by calendar month and combines only fully covered monthly pitch samples. Include every dated fixture needed for the requested sample.

Across the August 7 slate and two October 30 World Series fixtures, 114 of 150 relief lines qualified, covering 1,907 pitches. The 36 remaining outings retained their withholding reasons. In the August 1–7 replay, all three Erceg outings qualified. An independent count from MLB plays in games 746272, 746440 and 746443 matched all 36 pitches and all four mean velocities. His 13 four-seamers averaged 98.7 mph, 11 changeups 90.9 mph, eight sinkers 98.8 mph and four sliders 86.2 mph. The same seven-day fixture withheld his earlier months due to missing finals and plays. These are retrospective measurements through August 7.

The pitcher rehearsal also reports individual season and recent 30-day performance. Each expected relief outing carries its credited club and game identity. Each metric reports covered outings and its denominator. Missing finals stay in the sample. Conflicting counts withhold affected metrics. Rate calculations use the existing individual pitcher contract.

Across the 30 days through August 7, 2024, Erceg had 10 outings with a 4.15 ERA, 0.81 WHIP, 0.00 HR/9, 20.59 K-BB% and one of seven inherited runners scoring. Jansen had seven outings with a 6.48 ERA, 1.68 WHIP, 2.16 HR/9, 23.68 K-BB% and zero of one inherited runner scoring. Independent sums from the official game logs matched all four rates for each pitcher. The same fixtures covered only 10 of 42 and seven of 38 season outings, respectively, and withheld all five season measures.

For a fully covered season-to-date example, capture March 20, 2024 with team 119 and pitcher 623465. In Seoul game 745444, Evan Phillips retired three batters with one strikeout. Both the season and recent samples yielded 33.33 K-BB% over three batters faced and zero earned runs, walks, hits and home runs over three outs. A separate transaction-source conflict withheld the overall replay. [MLB boxscore](https://statsapi.mlb.com/api/v1/game/745444/boxscore)

### Active bullpen performance

Use `--performance-team TEAM_ID --through YYYY-MM-DD` with the dated active roster, both scoped MLB stats responses for each roster pitcher, and dated regular-season game fixtures. The candidate uses the existing role-authority classifier with the regular-season log window. Unresolved pitching positions, ambiguous two-way evidence, or missing player profiles withhold the group. The role sample includes prior-club work. The performance sample counts only relief appearances credited to the represented club, and checks each expected pitcher/game identity against the confirmed finals. Each window reports its covered and expected sample. ERA and WHIP use the governed minimum of 108 outs and K-BB% uses 100 batters faced. HR/9 is an additional retrospective measurement.

For the August 7, 2024 Kansas City fixture, capture the represented date with team 118 and repeat `--pitcher` for each of the 12 dated roster pitchers. Replay those profiles together with the daily fixtures, using the existing rehearsal command from the backend directory.

```sh
python -m sync_v3.capture_day 2024-08-07 /tmp/kc-aug7-with-profiles.json --team 118 \
  --pitcher 519293 --pitcher 547179 --pitcher 607625 --pitcher 608379 --pitcher 608717 --pitcher 663460 \
  --pitcher 663704 --pitcher 663903 --pitcher 666142 --pitcher 668674 --pitcher 669674 --pitcher 672582
python -m sync_v3.rehearse --pg-bin /path/to/postgres/bin \
  --fixture /tmp/kc-aug7-with-profiles.json --performance-team 118 --through 2024-08-07
```

A single-day fixture exposes the season obligations and the missing-final reasons. Add dated fixtures with repeated `--fixture` arguments to close the coverage. For Kansas City, seven of the 12 arms met the role rule. The 30-day replay covered 56 of 213 season appearances. Adding official schedules and club boxscores for 84 earlier appearance dates covered all 213. An independent recount from the boxscores reproduced the five existing measures in both windows.

| Through August 7 | Relief outings | Outs | BF | ERA | WHIP | K-BB% | HR | Inherited scored |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Recent 30 days | 56 | 179 | 240 | 3.62 | 1.12 | 15.0% | 7 | 7 of 25 |
| Season | 213 | 631 | 888 | 3.94 | 1.28 | 12.2% | 21 | 28 of 108 |

These historical results describe the represented roster. Production promotion still requires independent parity and publication certification. The August 7 transaction refusal remains visible in the replay status.

### Rotation burden

The `--team` rehearsal includes a 14-day ledger of confirmed regular-season games and seven- and fourteen-day rotation pressure. Each team-game cites its date's schedule and final evidence, identifies the credited starter, and reports pitches, outs and batters faced for the starter and relief group. A missing pitch count withholds the affected pitch total. A missing slate or unresolved club final withholds pressure for the affected window. The existing rotation classifier counts opener/bulk games separately, and discloses exclusions such as abbreviated games.

For July 25–August 7, 2024, a PostgreSQL 17.6 replay covered 184 regular-season games. Independent boxscore counts matched the starter identity and all six workload totals for both sides of every game. The governed rotation classifier counted 254 normal starts, 101 short starts and 13 opener/bulk games. Kansas City's seven-day window contained seven rotation starts, 128 starter outs and 66 relief outs with zero short starts. Its fourteen-day window contained 13 rotation starts, 241 starter outs, 115 relief outs and one short start. Game 746602 had abstract status Final on August 6 but detailed status Postponed. Its August 7 final counted once.

Use `--schedule-team TEAM_ID --through YYYY-MM-DD` to inspect the official calendar around a represented date. The rehearsal uses the existing ten-day lookback, fourteen-day lookahead and schedule-context rules. It retains each date's schedule receipt, game identities, series positions and venue IDs. Venue changes describe scheduled locations. Retrospective observations cannot establish the calendar a reader would have seen before first pitch.

The schedule context requires all 25 dated responses. Missing days, unresolved resumptions and unexplained disappearing games withhold the aggregate. A postponed listing can carry the makeup game's official date. The ledger preserves both that date and the date of the postponed listing. For July 24, 2024 Kansas City had one listed game, five played games over the preceding five days and a next off-day of July 25. In the August 7 replay the fourteen later dates were absent, so the forward-looking context was withheld.

### Organizational depth and pitcher hand

Add `--depth-team CLUB_ID` to a historical capture to retain the official season affiliate directory and dated active roster with person attributes for the parent and its affiliated minor-league levels. Inspect the resulting `depth` section through the team rehearsal. The active and 40-man membership reads retain their original source authority. Each affiliate is reported by its own club ID, level and source receipt. A player listed by multiple affiliates or by both an affiliate and the MLB active roster has an ambiguous assignment. Person-profile hand has the retrieval timestamp. Matchup hand has a separate, game-specific source.

```sh
python -m sync_v3.capture_day 2024-08-05 /tmp/boston-kc-depth.json --team 111 --team 118 --depth-team 111 --depth-team 118
python -m sync_v3.rehearse --pg-bin /path/to/postgres/bin --fixture /tmp/boston-kc-depth.json --team 118 --through 2024-08-05
```

The August 5, 2024 capture retained 99 responses. Each club had seven affiliated minor-league roster views. Independent counts matched 105 distinct Boston affiliate pitchers and 119 Kansas City affiliate pitchers. Each MLB active view listed 13 pitchers. At retrieval the Boston profiles recorded ten right-handed and three left-handed pitchers, and Kansas City recorded eight right-handed and five left-handed. Kansas City had ten pitchers listed on its 40-man view outside its active roster. Boston's 40-man and full organizational views contained conflicting parent evidence. The comparison remained unavailable and the overall rehearsal reported the source refusal. The affiliate reads produced zero MLB membership revisions for affiliate club IDs.

The game rehearsal also reports the score after the starter's last completed plate appearance and immediately before the first reliever's plate appearance. Those scores can differ between innings. It checks outs against the starter's official total, reports observed pitcher hand and batter side by plate appearance, and retains unknown entry base occupancy under the existing evidence rule. Across the August 7 slate and two World Series fixtures, 15 games qualified. All 30 game sides matched the independent exit, entry and out counts, and all 1,153 observed handedness pairs matched the official plays. Four games retained their prior play-sequence refusals.

The rotation rehearsal pools relief burden across complete regular-season series inside the fourteen-day window. It requires consecutive official series positions, matching participants and home/away identities, a consistent series length, and unambiguous same-day order. The July 25–August 7 replay yielded 104 club-series samples covering 316 team-games. Independent final lines matched relief outs, pitches and batters faced for every sample. The other 52 team-games remained visible in the daily ledger outside a complete series sample.

### Retrospective Team State and arm reads

Pass `--competition` to `python -m sync_v3.capture_day` on one date to retain the official league season calendar. Supply that fixture and the dated schedule and boxscore fixtures to `python -m sync_v3.rehearse --competition --through YYYY-MM-DD` using repeated `--fixture` arguments. The date is the pregame reference. The season calendar has no authority to write daily schedules or create final-game jobs. Each credited postseason decision needs a compatible retained daily final and a single winning pitcher whose club agrees with both score and winner flags. Future postseason results cannot decide an earlier read. A game on the reference date needs its dated slate to establish participation.

The 2024 PostgreSQL 17.6 replay resolved all 43 postseason decisions. On October 30, 28 clubs had completed their season and the Dodgers and Yankees were active. On October 31 and November 30 all 30 clubs had completed their season. Removing the earlier playoff boxes withheld unresolved classifications. Boston's October 25 forty-man source conflict remained recorded.

Use `--readiness-team TEAM_ID --through YYYY-MM-DD` to calculate a regular-season research candidate. Supply the same season calendar, a dated active roster, both official pitcher profiles for each roster pitcher, and the prior 14 league slates and finals ending on the represented date. Membership uses that date and the availability calculation uses the following date. The calculation compares per-player game identity, club, outs and pitches across boxscores and individual logs, including work for another club. It reuses BaseballOS fatigue, availability, active-bullpen coverage and Team State rules. Missing coverage and disagreements are reported. Every result carries `current_serving_eligible=false`.

Kansas City's August 7, 2024 roster produced seven qualifying relievers for the August 8 read. All 35 recent pitcher-game lines matched. Three arms had Clean Option, two Watch Arm and two Limited Rest. Contract A classified the group Stretched. The overall fixture replay retained its roster and transaction refusals. The historical read establishes calculation behavior independently of production publication and contemporaneous pregame availability.

The readiness rehearsal independently recounts the partition and checks arm classifications and the decisive team rule with the existing production accuracy and publication truth comparators. The August 8 comparison matched 23 arm decisions and three club decisions. Boston was Stretched with three clean, four moderate and one severe arm. Kansas City was Stretched with three clean and four moderate arms. The Yankees were Vulnerable with one clean and seven moderate arms. A withheld arm is reported separately from a compared decision.

### Historical workload snapshots

The isolated rehearsal accepts `--snapshot --team 118 --through 2024-08-07` or `--snapshot --pitcher 668674 --through 2024-08-07` with repeated offline `--fixture` arguments. It stores the five workload windows under an explicit methodology version and repeats the calculation to verify idempotency. Each revision retains the observed facts, coverage gaps, source receipt references, input digest and predecessor. The worker has SELECT and INSERT privileges on this history.

Two disposable PostgreSQL 17.6 clusters ingested the same 30 MLB dates from July 9 through August 7, 2024 in opposite orders. Kansas City and Lucas Erceg each produced matching input and semantic digests across clusters. The team semantic digest was `68110544630c21e9e0fbc52bc48f8095caac55a78e592587c50b1a30f9747368`. The pitcher semantic digest was `25e4bd0ae9570117f2f2ce0c51cbff26ab8f1d4063550ce1a82bd5df2312e38d`. Eighteen fixture days still reported refusals in other evidence scopes.

For an accepted final revision, `sync_v3.history.rebuild_for_final` refreshes the stored subject/date windows affected by its pitching lines. A changed bulk follower can affect the starter's opener classification. A newly covered game can also resolve a league coverage gap for another pitcher. The rebuild commits its affected revisions together. A PostgreSQL regression changed a 15-pitch outing to 24, retained the original snapshot, rolled back an interrupted rebuild, and repeated the successful rebuild without duplicating history. This path currently covers regular-season workload and accepted final revisions. For a changed daily schedule, dated active roster or boxscore, `sync_v3.history.rebuild_for_observation` uses the retained receipt to select the dependent scopes. A league slate can change the coverage of a 30-day workload window for every subject. A roster observation affects its club and pitchers with recorded membership on that date. An unexplained disappearing game withholds the league and affected clubs' workload and cites both dated schedules. Other intelligence domains require separate dependency coverage.

Use `--snapshot --readiness-team TEAM_ID --through YYYY-MM-DD` to freeze a club's represented Team State, individual arm reads, coverage and independent comparison. Accepted and refused evidence receipts are retained alongside the exact request scopes consulted, including requests with no receipt. A later observation can therefore recover a previously missing input. `sync_v3.readiness_history.rebuild_readiness` selects only latest snapshots that depended on the observed request. Snapshot construction and dependency recording share one serializable transaction.

Two PostgreSQL 17.6 clusters replayed the August 7, 2024 evidence in opposite fixture orders. Both produced identical input and semantic digests for Boston, Kansas City and New York, covering 23 arm decisions. Injecting a malformed Lucas Erceg game-log response superseded Kansas City's snapshot with `incomplete_roster_role_evidence` and retained its prior Stretched read. Repeating the rebuild reused the same revision. All of these snapshots carry `current_serving_eligible=false`.

### Replaying daily intelligence history

`--snapshot-domain` freezes one of nine calculations under its own methodology and records each dependency in the same transaction. Use `--team` for readiness, rotation, schedule, depth, roles or group_performance. Use `--pitcher` for pitcher_profile or pitcher_rest, and `--game` for game_deployment. Each replay reports both the semantic digest and the digest of its input evidence. Add `--since YYYY-MM-DD` to rebuild every represented day through the inclusive `--through` date. The existing workload snapshot commands remain available.

From the backend directory, this command exercises the game snapshot on the checked-in synthetic fixture:

```sh
python -m sync_v3.rehearse --pg-bin "$(pg_config --bindir)" \
  --fixture tests/fixtures/sync_v3/played.json --game 12345 \
  --snapshot-domain game_deployment --through 2026-07-29
```

`sync_v3.intelligence_history.rebuild_intelligence` refreshes latest snapshots that consulted a changed request. A PostgreSQL test supplied one previously missing daily slate. Five dependent snapshots acquired successors, the other four kept their original revisions, and repeating the rebuild produced no duplicates.

The historical MLB rehearsal used 27 captures in two fresh PostgreSQL 17.6 clusters. All 3,161 supplied parsed responses were archived in each cluster. There were 920 responses preserved solely as acquisition evidence in each order. The archive keeps the endpoint, parameters, retrieval time and payload digest even when transaction validation withholds downstream roster processing. Raw HTTP wire bytes are outside this archive's contract.

Loading those captures in reverse reproduced the same facts and input digests for all nine sampled calculations. The comparison included Kansas City's rotation, schedule, affiliate depth, active-group performance and observed roles, Lucas Erceg's workload and pitch profile, and game 746604. Rehearsal jobs use the capture's content identity so two actual observations taken during the same polling interval both survive replay. Ordinary acquisition retains its polling policy.

MLB listed games 746602 and 745713 as postponed on August 6, 2024 and final on August 7. Final reconciliation now matches the boxscore to the daily schedule request that authorized it. The two dates retain independent schedule observations and each game has one canonical final. Two disposable PostgreSQL 17.6 replays loaded the evidence in opposite orders. Kansas City's August 6 workload produced a Vulnerable read with eight verified arms for August 7. Its August 7 workload produced a Stretched read with seven verified arms for August 8. Both semantic digests matched across replay orders.

### Historical readiness changes

Running the readiness snapshot rehearsal over two or more adjacent dates also emits the candidate changes for each represented pair. Each result includes both revisions, both semantic and input digests, the methodology and the affected MLB identities. The snapshot date is the membership/workload date. The arm read applies to the following reference date. To reproduce a superseded comparison from the immutable inputs, call `sync_v3.change_history.readiness_changes(cur, team, through, revisions=(previous_revision, current_revision))`. Missing snapshots and withheld Team States are recorded as gaps. Unknown arm reads suppress the clean-option count comparison.

In the August 6–7, 2024 Kansas City replay, the candidate for the following day's slate moved from Vulnerable to Stretched. Five individual arm labels changed, including Lucas Erceg from Clean Option to Watch Arm. The clean-option count increased from two to three. Reversing the capture order yielded identical events and lineage digests. These comparisons cover readiness only and have no production publication identity.

The depth snapshot rehearsal also compares dated MLB active lists. It qualifies pitchers from each represented date and checks absence against the other day's full club list. A position change within the club does not generate a roster addition or removal. A missing, empty or unconfirmed list, or a disagreement between the hydrated and unhydrated active populations, withholds the comparison. The Kansas City August 6–7, 2024 replay found Hunter Harvey (640451) listed on August 6 and absent on August 7. Both capture orders yielded the same event and lineage. This evidence establishes the list change only. A transaction reason or a change in forty-man membership needs separate evidence.

The event archive covers six inputs. Readiness, depth, rotation, roles and pitcher_rest use their corresponding snapshot domains. Team burden uses `--snapshot --team`. The rehearsal freezes the event set for each ending date, including a missing-prior result. Each revision links its immutable inputs through `candidate.change_inputs`, retains their source receipts, and identifies the exact represented dates. Rebuilding a source snapshot automatically updates existing event sets ending that day and the next day in the same transaction. The predecessor stays readable. The SQL objects are in the isolated candidate schema.

Two PostgreSQL 17.6 replays of the Kansas City August 6–7, 2024 evidence produced identical facts and input digests for all six event sets. They contained 13 events, including the two official relief appearances in game 746272, the start of Lucas Erceg's recent multi-inning pattern, and both rolling burden changes. Seven-day relief pitches rose from 291 to 297 while fourteen-day pitches fell from 599 to 557. Deployment coverage was partial. The archive recorded that limitation and emitted zero deployment changes. Tests cover supported movement with comparable signals, an appearance in each half of a doubleheader, uncertain rotation shape and a roster correction that supersedes the following day's event set. Trusted publication identity and product delivery remain separate gates.

### Candidate generation rehearsal

From `backend`, build the represented inventory in a disposable PostgreSQL cluster. Supply one `--fixture` per captured MLB date or acquisition. For a small repeatable example:

```sh
python -m sync_v3.rehearse --pg-bin "$(pg_config --bindir)" \
  --fixture tests/fixtures/sync_v3/played.json --through 2026-07-29 --build-generation
```

The builder enumerates all 30 clubs, dated active pitching populations when available, and competitive finals from the represented MLB slate. It records the following slate separately. Each batch commits individual calculations and resumes from missing or superseded inputs. The manifest identifies unknown populations, withheld readiness, missing scopes, stale source dependencies and comparisons still referencing a superseded revision. A completed batch can contain withheld facts. Source refusals remain visible in the command's exit status.

The generation digest binds exact revisions, facts digests, input digests, calendar observations and their retrieval times. PostgreSQL seals the membership when the creation transaction ends. Reverification streams the pinned snapshot facts, recomputes their hashes, checks the club inventory and verifies the retained calendar payloads. This candidate inventory has no trusted publication pointer.

Two opposite-order PostgreSQL 17.6 replays built 425 August 7, 2024 snapshots with digest `6665cb542eca6e91573887f7f7f9c129d3b81b1f56dd293971256c25baa0e34c`. The batch queue settled, and independent verification recounted 425 pinned snapshots. In that capture set only Kansas City had supported readiness. The other 29 clubs were withheld for missing dated active-roster evidence. An October 30 World Series replay accounted for all 30 clubs as season complete for October 31. Product contract certification, production parity and promotion remain separate gates.

For a league-wide historical capture, `python -m sync_v3.capture_day 2024-08-07 /tmp/bos-2024-08-07.json --active-profiles` requests both official pitching profiles for the pitchers listed on the dated active MLB rosters. The destination must be new. Replay drains large offline captures using successive 256-job batches and the original fixture clock. No retry clock or current acquisition budget is advanced.

The expanded August 7 comparison used 30 official active club lists and 393 pitcher listings. Opposite capture orders reproduced 226 verified arm decisions and 27 club decisions. The Pirates' and Cardinals' lists included MLB generic outfield and infield position codes. The pitcher population now handles these fielders consistently with the depth calculation. Three clubs remained withheld:

- Chicago Cubs pitcher Caleb Kilian (668873) had no supported season sample through August 7. The retained MLB game log begins September 23, and the dated totals contained no split.
- Los Angeles listed Shohei Ohtani (660271) in the two-way position. His two pitching-profile responses provided no scoped pitching groups on which to qualify his bullpen role.
- New York Mets pitcher Edwin Díaz (621242) had an official game-log entry for June 23, game 746862, with zero games pitched, batters faced, outs and pitches. The existing single-appearance validator withheld the sample.

An older copy of an identical, unrevised daily schedule may corroborate the boxscore fetched after that copy. An older conflicting schedule still cannot authorize a final. The frozen generation verifier now checks each snapshot's input digest against its exact source receipts and request scopes. PostgreSQL seals those provenance links at commit.

Generation verification runs in a read-only transaction. It checks each represented final's game-side teams, relief pitcher identities and official outs against the pinned boxscore. For each club with supported readiness, it compares the readiness arms to the performance cohort and checks both against the dated active roster used by depth. The three snapshots must cite the same accepted club roster receipt. It also verifies that each change set cites the correct subject, dates, methodology, revisions and digests; event identities must be unique within the generation.

A direct August 7, 2024 league capture contained 959 official responses. In a 107-snapshot rehearsal, all 17 finals matched their official games and all 27 qualified club populations matched across the three calculations. The remaining three clubs retained their reasons for withholding. Another 425-snapshot verification checked 162 event sets containing 213 distinct events, including 88 sets with partial or withheld comparisons. An injected failure while inserting generation membership rolled back the new manifest and preserved the prior one.

Workload snapshots also retain the exact requested scopes that had no receipt at build time. When a missing roster, schedule or boxscore arrives, the candidate inventory can identify the superseded workload before recomputation. Older workload snapshots without this coverage remain readable and require a rebuild for a new candidate. A change set reuses its exact source snapshots when their evidence is still current. When a source has changed, both sides of the comparison are checked and its revisions commit together.

The verifier derives expected team, pitcher and game scopes from pinned club facts and checks the represented and following slates against their retained MLB responses. An omitted scope, incorrect availability date or unsupported empty slate invalidates the manifest even if its content hash is correct. When the same source body is acquired again, a rebuilt snapshot can retain the new receipt while preserving the earlier revision. Repeating the build against the same receipts reuses the existing revision.

The full August 7, 2024 league build settled 1,949 scopes in each of two opposite capture orders. Separate read-only PostgreSQL 17.6 verifications returned the same generation digest, `10fe536e1a845d1a0bd7c59e5fdced0b15f90fb6fee01b34d585b4bd9643c4a2`. All 17 finals matched the official relief lines. The 543 historical comparisons contained 317 distinct events and 222 partial or withheld comparisons. No required scope was missing or stale. Chicago (NL), Los Angeles (NL) and New York (NL) still lacked sufficient roster-role evidence for league-wide readiness. The two runs spent 774 and 782 seconds in materialization batches on the disposable Cloud host, excluding source capture, initial ingestion and independent verification.

### Isolated historical selection and recovery

Add `--exercise-selection` to the generation build command. The rehearsal creates a separate local reviewer and an empty selection history. It independently verifies the frozen candidate, reconstructs the latest inventory for the same baseball date, and requires a completed 30-club core comparison. A partial candidate or season-complete no-op preserves the prior selection. The ingestion worker cannot append a selection. The reviewer can inspect candidate inputs and record a decision through a restricted PostgreSQL function. Public product contracts and production publication authority are outside this selector's scope.

Each committed selection identifies its predecessor revision and exact generation. Repeating an acknowledged operation returns the same revision. Recovery appends a decision that selects the exact preceding immutable generation, including its original roster receipts, manifests and historical changes. Readers can use that prior generation even after a later correction. An initial selection can be rolled back to the empty state. The rehearsal has no cache handoff or public serving route.

The synthetic 30-club PostgreSQL test is `SYNC_V3_TEST_PG_BIN="$(pg_config --bindir)" python -m pytest -q tests/test_sync_v3_corrections.py -k isolated_core_selection` from `backend`. It builds the roster, game, workload and calendar inputs, selects successive qualified generations and restores the first. It covers concurrent reviews, retry, transaction rollback and visibility from another connection.

### Product reads from a historical generation

The disposable rehearsal exposes `read_league`, `read_team_board`, `read_pitcher`, `read_game_cards`, `read_search` and `read_team_events` in `sync_v3.product_reads`. Each runs a read-only transaction. The default follows the latest isolated selection. Passing its exact `revision` reproduces that selection after a later correction or rollback. `preview_league(connection, digest)` independently verifies an unselected historical candidate and shows each club's corresponding evidence or reason for withholding. The result carries the generation, represented date and historical scope.

League uses the existing public row, State vocabulary and rest-count builders. Search and the slate share official game identities. Asking for one game returns the same card as the slate. The shared event reader returns the same identity, dates and citations on the Team Board and in dated History. Pitcher patterns require membership in the club's bullpen on both dates. A missing comparison remains visible. These are isolated research reads. They carry no public publication or cache authority.

The official MLB player ID and BaseballOS's public `pitchers.id` have distinct meanings. A rehearsal can supply `--identity-fixture` with a sanitized local export containing `source` equal to `BaseballOS.pitchers`, a timezone-qualified `observed_at`, and `rows` containing only integer `id` and `mlb_id` pairs. The disposable installer validates both directions, pins the export digest to the candidate and gives both runtime roles read access. A verified pair supports that individual Board link, Pitcher page and dated history. Within the represented active bullpen, Search withholds its pitcher results if any matching name lacks a verified route. A club needs a complete mapping to rank its named key arms. The Board can still retain confirmed roster names without links. A missing route in a partial export has unknown coverage. The checked-in synthetic test exercises complete, incomplete and absent maps with different MLB and BaseballOS IDs. An archived production proof supplies the observed subset described below. Full pitcher-directory coverage and parity with the deployed product remain unverified.

The August 7, 2024 candidate League preview returned all 30 clubs. Boston's historical row was Stretched with five rested arms, three who worked August 7 and one back-to-back. Kansas City was Stretched after Vulnerable on August 6. Its archive yielded 15 distinct events, including Hunter Harvey's active-roster removal and Lucas Erceg's relief appearance and multi-inning pattern. The Mets' row withheld state and rest counts. The independent selector rejected this generation for unresolved club readiness and retained its empty state.

The synthetic played-slate rehearsal verifies the same 15 game identities in Search and the slate, the exact same card for a game detail request, and the same pitcher changes in the Board and the History slice. `sync_v3.editorial_reads.read_story_observations` runs the existing rotation-context and story-observation builders on official pitching lines pinned by the rotation snapshot. Missing calendar dates and conflicting pinned finals withhold the story input. `read_event_evidence` reads an immutable event for editorial or share review. `read_trust` verifies a selected generation and reports methodology versions, counted receipt outcomes and acquisition timestamps. These inputs have no trusted artifact identity. Published Stories, asset rendering and production artifact handoff still require their existing publication contracts.

Both the slate and single-game reader carry the same aligned performance and named-rest comparison. The performance projection repeats qualified season metrics from the generation's active-group snapshot, carries each club's appearance sample, and withholds comparisons with no common qualified metric. Observed save work requires a pinned, club-owned final relief line in the existing fourteen-day deployment window. Named rest also requires complete days-since-appearance evidence and a mapped BaseballOS identity. A save at a former club cannot qualify a pitcher for the represented club.

Editorial observations also use the existing concentration and optionality builders. Concentration resolves game-side club and player names from pinned final boxscores. Optionality requires dated arm reads and names for the entire represented active group. It uses the exact last workload date even when a pitcher worked for a different club. Individual source layers report their coverage. League-relative editorial baselines, stability and injury layers still need separate evidence.

Tonight reuses the edition's feature, lead and summary rules across its full slate before restricting a game detail request. The isolated league change feed includes comparable Team State transitions and official short starts from complete game comparisons. Both retain the exact Board event identity. Each short start also links its original game and cites its rotation revision. Per-team and league display limits follow Tonight ordering. Editorial observations cite the retained boxscore content digests. On the synthetic pregame slate Boston's one four-inning start qualifies for partial short-start context, while the existing minimum-sample rule withholds a rotation lead. On a verified off-day all 30 clubs remain accessible and Search offers no game for that edition.

Dated identity exports are immutable inputs to a generation. Import order cannot replace a newer observed mapping with an older export. An identical export can be replayed. Reusing a public route for a different MLB player, assigning another route to an already mapped player, or exporting different contents for the same observation instant fails within the transaction. Earlier generations retain the original identity set. The isolated Pitcher History lookup pages through selection revisions and reproduces each represented club, dated arm read, deployment profile and linked changes, including rollback.

The historical August 8, 2024 San Francisco at Washington matchup (MLB game 744819) supplied a two-club season benchmark through August 7. In disposable PostgreSQL 17.6, 406 official request receipts covered the represented active rosters, pitcher profiles, club schedules and final boxscores. A separate sum of the original boxscore fields for every relief game enumerated by the frozen cohort's official game logs matched all five displayed metrics. This compares the measurements for the declared cohort. It does not certify the production roster or a live publication.

| Club | Arms | Relief appearances | Outs | ER | H | BB | K | BF | ERA | WHIP | K−BB% | HR | Inherited scored |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| San Francisco | 7 | 316 | 1,014 | 128 | 302 | 98 | 360 | 1,403 | 3.41 | 1.18 | 18.7% | 35 | 36 of 112 |
| Washington | 8 | 247 | 764 | 121 | 246 | 88 | 234 | 1,086 | 4.28 | 1.31 | 13.4% | 33 | 37 of 88 |

The range of acquisition times was November 21, 2026, 06:21:10–07:39:50 UTC. San Francisco's facts digest was `d40a1ab8cc7df8ea7a075ff65f0063b8f0c7e4ad961f293178c4d5b2a9122cad`; Washington's was `1e205684a5faf44432c0439ed526f13c0a6a3eec7dd4d15d99f2b6111ef2c0f3`. The rehearsal recorded a refusal for a final boxscore paired with the May 13 postponed listing of game 746799. Its MLB official date was May 14. The independent appearance sum used the official game date and counted each player/game once.

The Board and Pitcher views also read dated appearance lines from their exact workload snapshot. Each line identifies its MLB game, pitcher, game-side club, opponent, final revision and source body digest. The club ledger includes every official reliever for that club, including players who later left. The pitcher ledger follows the player across clubs and includes starts. Incomplete calendar dates remain explicit gaps. Missing counts remain unknown. A 30-day retrospective boxscore recount through August 7 matched all 79 Giants relief appearances and all 88 Nationals relief appearances by game, player, date, pitches and strikeouts. The Giants' July 27 doubleheader retained distinct games 745307 and 745310. Five additional complete calendar receipts covered dates neither club played.

Board and Pitcher also share the pinned, dated MLB active-roster profile for throwing hand. It states when the person attribute was retrieved. An absent, incompatible or contradictory profile leaves the hand unknown.

The isolated rehearsal can use pitcher IDs retained in an observed BaseballOS publication. Supply the original proof ZIP and the SHA-256 reported independently by GitHub. From backend, run:

```sh
python -m sync_v3.rehearse --fixture tests/fixtures/sync_v3/quiet.json \
  --identity-proof /path/to/production-proof.zip 209f55a6904abf9602946e9b8f5ea5ce836ee398f662442fe199c7dbf169d449
```

GitHub Actions run [44794472956](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/44794472956), artifact 14657943570, supplied 440 unique pitcher identity pairs across 30 clubs for snapshot 5843 (sync run 98300). Its membership date was October 28, 2026, and its availability date was October 30. The importer verifies the archive, publication status, postcommit observation, club dates, original receipt digest and player identity uniqueness. It preserves the original inconclusive cross-version assertion. Identities outside the observed population still require a separate reference. The same run's delivery artifact 14659061276 independently matched the repository's generated digest manifests for 30 team pages and 10,174 share pages. This verifies retained legacy artifacts. Replacement delivery parity requires comparing candidate outputs against corresponding dated references.

Stories also compares the workload core across two consecutive ten-day windows using the existing role-stability calculation. Every included reliever has a game-side identity, a recorded pitch count and a name from the pinned official boxscore. Missing calendar days, ambiguous boxes and unknown pitch counts withhold this observation. Through August 7, 2024, the Giants retained one of three core relievers (33%) and the Nationals retained two of three (67%). Independent sums of the raw pitching lines matched both ten-day pitch totals for each club: 406 and 676 for San Francisco, 544 and 591 for Washington (recent window first).

Replaying the August 7, 2024 league readiness scopes against the archived snapshot 5843 identity evidence resolved 96 of 226 represented bullpen arms. All 96 agreed with the original archived pairs. The other 130 had no route in that export. For example, the dated Atlanta roster establishes A.J. Minter as MLB 621345 and the archive supplies BaseballOS pitcher 337. His club and baseball facts come from the represented date. This replay inspected a candidate and did not select it.

Team History also reads game and calendar context from each selected revision's pinned rotation and schedule receipts. A verified rest day requires an empty club schedule between two final dates. The seven-day relief total includes doubleheaders and withholds its total for missing dates or unusable splits. Extra innings require a final-game schedule with a declared regulation length and qualifying inning or outs evidence. Without enough evidence the field remains unknown.

The July 2024 PostgreSQL replay identified Washington's July 22 off-day between games 744831 and 744828 and extra innings in game 745146 on July 26. The July 27 San Francisco history preserved two games, 745307 and 745310. Its seven-day burden was 77 relief outs over eight games, independently recounted from the official boxscores. These observations describe historical game context; they do not establish a public Team State.

Supplying an observed identity proof during a generation rehearsal also compares the candidate League Team State blocks with the publication's retained receipts. The comparison requires matching coverage, membership and availability dates and the same 30 unique clubs. It reports differences by team and field, including a field missing on only one side. An exact match covers those Team State fields only.

For snapshot 5843, a PostgreSQL 17.6 replay of October 28, 2026 retained the official final (game 849799) and compared 11 pitching lines. The candidate and archive both used October 28 for workload and membership. The candidate availability date was October 29 and the archived availability date was October 30. The comparison returned `edition_dates_differ` with zero clubs compared. The retrospective MLB schedules retrieved November 21 between 08:10 and 08:14 UTC contained no games October 29 through November 2. Given those rows, an October 30 as-of date and the existing three-day lookahead, BaseballOS's schedule-aware resolver also returned October 29. This evidence cannot reconstruct which future schedule listings were available to the original publisher.

A separate four-day replay preserved 207 acquisition observations. The October 29 transaction response triggered the existing same-instant contradiction refusal. The overall replay reported withholding. Neither the date comparison nor the transaction refusal advanced a selector.

For a competition-only comparison, pass the same proof ZIP and SHA to the rehearsal with `--competition --through 2026-10-30` and the retained season calendar, playoff-day schedule and final-game fixtures. In this mode the date is the competition reference date. Each playoff decision must reconcile across the season calendar, daily slate and official boxscore. Missing evidence withholds the comparison. For a season-complete club the rehearsal also projects the public withholding block using the archive's workload coverage date. This tests the withholding contract independently of generation date selection.

The October 30 competition replay used 64 retrospective MLB responses acquired November 21, 2026 between 08:17:13 and 08:17:29 UTC. It reconciled all 40 postseason decisions. All 30 club contexts and all 30 Season Complete public blocks matched snapshot 5843, including the clubs' final recorded dates and withholding reasons. Running the comparator with only the October 28 day fixture returned `incomplete_competition_evidence` with zero clubs compared. The independent edition-date discrepancy still applies to a full League comparison.

The normal capture and rehearsal entry points reproduced that result with 24 complete daily fixtures. The second collection retained 553 responses (November 21, 2026, 08:19:54–08:21:19 UTC). The isolated cycle accepted all 553, compared 406 pitching lines across 40 finals, and reported `competition_fields_match` for 30 clubs with zero differences. These fixtures cover the playoff dates and the comparison date. Their transaction requests and resulting roster requests went through the normal acquisition path.

To repeat from `backend`, supply the original proof ZIP via `PROOF_ZIP`, an installed PostgreSQL 17 bin directory via `PG_BIN`, and a new scratch directory via `CAPTURE_DIR`. This example obtains public MLB evidence and replays it into a disposable local database. Later source revisions can change the result.

```bash
python - <<'PY'
import json
import os
from datetime import date
from pathlib import Path
from sync_v3.capture_day import capture
from sync_v3.competition_calendar import calendar_games, POSTSEASON_GAME_TYPES
from sync_v3.discovery import competition_calendar_request

target = Path(os.environ['CAPTURE_DIR'])
target.mkdir(exist_ok=False)
reference = date(2026, 10, 30)
edition = target / f'{reference}.json'
capture(reference, edition, teams=[], competition=True)
request = competition_calendar_request(reference.year)
source, = [r for r in json.loads(edition.read_text())['responses']
           if r['endpoint'] == request.endpoint and r['params'] == request.params()]
games = calendar_games(request.params(), source['body'])
days = {d for d, row, _ in games.values()
        if d < reference and row['game_type'] in POSTSEASON_GAME_TYPES and row['status_state'] == 'final'}
for d in sorted(days):
    capture(d, target / f'{d}.json', teams=[])
PY
fixtures=()
for day in "$CAPTURE_DIR"/*.json; do fixtures+=(--fixture "$day"); done
python -m sync_v3.rehearse --pg-bin "$PG_BIN" "${fixtures[@]}" \
  --competition --through 2026-10-30 --identity-proof "$PROOF_ZIP" \
  209f55a6904abf9602946e9b8f5ea5ce836ee398f662442fe199c7dbf169d449
```

Search and Pitcher Detail can also cite a pitcher who left a club's active roster on the represented date. This requires a named departure in a complete, generation-pinned comparison of consecutive official rosters and a verified public pitcher ID. A departure-only result carries the originating club, date and exact Board/History event. Its current team and roster status remain unknown. Where the new club independently has an active bullpen read, the route retains both the new club's read and the former club's departure citation.

The October 2026 isolated replay matched San Diego departures to archive-backed public IDs for Mason Miller (MLB 695243, BaseballOS 423) on October 6 and Wandy Peralta (MLB 593974, BaseballOS 431) on October 7. These dates represent changes between official roster lists. They do not establish the reason for removal or a receiving club. The selected synthetic league also exercised separate source and receiving clubs, missing ID maps and rollback.

Kansas City's August 7, 2024 roster comparison retained Hunter Harvey's named departure (MLB 640451). Snapshot 5843 supplied no public ID for him. The offline read kept the historical event and withheld its pitcher destination. The separate transaction contradiction on August 6 remained recorded.
