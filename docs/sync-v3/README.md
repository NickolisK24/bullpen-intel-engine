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

Editorial observations also use the existing concentration and optionality builders. Concentration resolves game-side club and player names from pinned final boxscores. Optionality requires dated arm reads and names for the entire represented active group. It uses the exact last workload date even when a pitcher worked for a different club. Individual source layers report their coverage. League concentration and role stability have their own evidence checks below. Injury context requires separate evidence.

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

A dated forty-man roster can identify a pitcher even when that edition has no active bullpen read or departure for him. Search, Pitcher Detail and the revision history use the MLB club list frozen into the selected depth snapshot. The observation cites its represented date, club, source digest and snapshot lineage. It supplies no active-roster status, current team projection or availability read. When a removal and continuing forty-man membership are both verified, the pitcher page preserves both.

On October 7, 2026, San Diego's retained forty-man response contained 23 distinct pitching identities. The offline PostgreSQL rehearsal reproduced all 23 names and matched 13 public IDs to snapshot 5843. Griffin Canning (MLB 656288, BaseballOS 415) had dated roster evidence without an active read. Wandy Peralta (MLB 593974, BaseballOS 431) had both a dated active-roster departure and continuing forty-man evidence. The MLB response digest was `e4effbe9bbd0626cbe338014d5c1d5c37a6c9c1b1e6251c217c3b5f0b703e331`.

An active pitcher outside the edition's verified bullpen can appear in Search, Pitcher Detail and dated History. His club and active status come from the generation's dated MLB roster. Pitcher Detail can cite his official appearances, including starts. A bullpen read requires separate evidence. The October 7 San Diego replay reproduced all 11 active pitching identities in the captured MLB response (SHA-256 `00c90bb5e080e8bcf25ed0388222a491c8c44482f89aa09220fee2836dc812b8`). Six had a verified route in the snapshot 5843 identity export.

The August 7, 2024 league replay compared the directory with the dated active responses for all 30 clubs. It reproduced 393 names, MLB IDs and club assignments. The archived public identity export supplied routes for 129 of those pitchers. No player appeared on multiple clubs' active pitching lists in that sample. This comparison covers roster identity only.

### Historical Share delivery

From `backend`, compare the static delivery tree with independently digest-pinned GitHub archives from run 44794472956:

```sh
python -m sync_v3.archived_share_pages "$PAGES_ZIP" \
  2b56cf9d2ded8f44287df301935d5c469cde5c95f96dd326711dd90f24e6e681 \
  "$DELIVERY_REPORT_ZIP" 8adf91796d085960aec9e8e69d6fd66ed4ef73347f84f8fab12e6e56dea7e918 \
  ../frontend/public/share --publication-proof "$PROOF_ZIP" \
  209f55a6904abf9602946e9b8f5ea5ce836ee398f662442fe199c7dbf169d449
```

Artifact 14657712979 contains the exported pages. Artifact 14659061276 records the page set and content digests. All 10,174 links and their HTML bytes matched, covering 9,358 Team State pages and 816 Since Yesterday pages with data through July 23–October 28, 2026. The separately delivered invalid-link fallback also matched. Snapshot 5843 identifies the export; each page retains its original historical identity. These archives preserve rendered output. Rebuilding an original page from its underlying frozen artifact still requires the original artifact record. Current candidate facts cannot establish its contents.

When the delivery archive contains `publication.json`, the checker verifies its snapshot, sync run and workload date against the Share export. The optional `--publication-proof` also requires that delivery record and verifies all three fields against a digest-pinned, postcommit-observed publisher proof. In run 44794472956, snapshot 5843, sync run 98300 and workload through October 28 agreed across the three records for all 10,174 delivered pages. The separate proof for snapshot 5751 was refused. The 1,557 historical source pairs carried by the pages retain their original identities. The observed proof retained its inconclusive cross-version assertion.

The archive check also repeats the existing public delivery verifier against the local copy, including canonical URLs, social previews and the invalid-link fallback. The export must identify a positive integer publication snapshot ID. Verifying the identity in an archive does not establish the lifecycle of its underlying database record.

The archive check counts the snapshot and sync-run pairs carried by the individual pages. All 10,174 pages carried both IDs across 1,557 distinct pairs. GitHub distribution run 44716734983, artifact 14620151702, recorded a successful handoff for snapshot 5843 and sync run 98300. Its prebuild and postbuild Share digests agreed for all 10,175 files including the fallback. Every digest matched the corresponding file in Git commit `ce0e3384b791744df5fb6a5c8e40b4877d3b1e7f`. The archives supplied no underlying artifact rows. In the offline Python comparison, pass `stored_artifacts` to `compare_share_pages` when original records are available in a disposable database. Each supplied record must have a unique public ID in the archive, pass the existing public lifecycle and integrity checks, and reproduce the independently pinned page digest with the existing renderer. The result reports record comparisons separately from delivered-page comparisons.

On PostgreSQL 17.6, synthetic Team State and Since Yesterday records reproduced their exported pages after reload from the database. Changing page bytes in both copies and their digest manifest passed the delivery-copy comparison but failed reproduction from the stored record.

Matchup's seven-day workload comparison uses each club's independently checked regular-season window. It includes every reliever who pitched for the club during those dates, including those who later left. The August 1–7, 2024 replay matched the MLB boxscores for San Francisco (18 relief appearances, nine relievers, 337 pitches, 20.2 innings) and Washington (22 relief appearances, eight relievers, 314 pitches, 21.1 innings). Innings use baseball thirds. A missing comparison withholds the domain. Unknown pitch and contributor counts remain unavailable.

Matchup also reads the two clubs' complete Team State blocks from the same League generation. The paired rest counts come from the League rest calculation and require each side's availability date to match the official game's baseball date. A prior day's counts cannot establish how many pitchers worked yesterday for a later game. Tonight's short-start context uses the rotating seven-day window through the workload date. The separate public Matchup rotation-pressure contract uses the availability reference date and its own starter-split evidence. The historical short-start card alone does not certify that comparison.

An independent comparison against the retained MLB pitcher game logs for the August 8, 2024 San Francisco–Washington game (744819) reproduced the dated rest counts. San Francisco had three rested options, four who worked yesterday and zero on back-to-back days. Washington had four rested options, four who worked yesterday and one on back-to-back days. The same evidence withheld the August 9 comparison.

For pregame Matchup rotation, the isolated read checks the six preceding dates plus the game date in the pinned slate. A completed, live, or unresolved game on that seventh date withholds the affected club comparison because its rotation snapshot ends the previous day. For ordinary starts the existing split calculator consumes the credited starter and both sides of the recorded outs split. It returns short starts, rotation-driven bullpen innings and sample limitations. A club with a complete game lacking relief split evidence or an unresolved game shape withholds the comparison. Tonight retains its own workload-date window.

With August 8, 2024 as the reference date, independent boxscore totals agreed for eight idle clubs across 48 starts. Boston had three short starts and 68 bullpen outs across six games. The public pressure calculation reports this as 22.7 decimal innings. The historical slate already showed games for 20 clubs, and this replay did not use those finals as pregame evidence. A separate selected synthetic pregame edition exercised both matchup sides and the limited-sample result.

Minnesota and the White Sox each had an opener/bulk game. For these shapes the Matchup read checks the complete game-side lines from the final revision cited by the rotation snapshot. It verifies the credited starter, individual relievers, recorded outs and game classification before excluding the game from rotation-driven pressure. Duplicate pinned revisions or conflicting lines withhold the comparison. The same rule covers verified bullpen games. A window containing only opener/bulk or bullpen games has no ordinary rotation-start sample.

In Minnesota game 746842, the starter recorded six outs and a bulk follower recorded nine. In White Sox game 745879, the starter recorded five outs and a bulk follower recorded ten. After accounting for those games, all ten idle clubs matched independent boxscore totals for the August 8 replay. Minnesota had one short start and 50 rotation-driven bullpen outs across its five ordinary starts. The White Sox had three short starts and 52 bullpen outs across five ordinary starts. A disposable PostgreSQL comparison also checked the legacy stored-split calculator on a window containing an ordinary start, an opener/bulk game and a bullpen game.

Historical Matchup availability uses the selected edition's active bullpen, availability date, verified appearances, and governed arm statuses. Each player must have a matching dated roster identity and a fresh workload observation inside the existing active window. A missing or disputed arm withholds the club count, and the paired comparison requires both clubs. The production comparison and the historical read share the same four count definitions, including the existing fold of Avoid and Unavailable. The historical field carries its own generation, dates and `current_serving_eligible=false`.

For the August 8, 2024 SF–WSH game, replaying the stored workload inputs through the independent arm-status verifier reproduced all 15 classifications. San Francisco had zero available, three on watch, four limited and zero unavailable. Washington had one available, five on watch, two limited and zero unavailable. A separate Dodgers control withheld the counts because the two-way role evidence was unresolved. This comparison establishes historical calculation agreement. An observed same-edition public response is still required for production delivery parity.

For a selected game, `read_game_cards` returns the seven historical comparison domains under `historical_comparison`. The comparison binds the away and home teams to the selected game, the workload date, the availability reference date and the selection revision. Qualified performance includes a displayable sample with the pitcher count, appearance count and date range. Partial and withheld domains carry the same limitation fields used by the public comparison. The historical response carries no publication authority.

The PostgreSQL rehearsal command `python -m sync_v3.rehearse --build-generation --exercise-selection` with dated fixtures follows every game on a selected slate through Search and Matchup before rolling back the selection. It checks official game identity, home and away clubs, both baseball dates, the selected revision and equality of the Tonight and Matchup cards. A 30-club fixture on PostgreSQL 17.6 selected game 10100 at revision 1 and recovered the empty selection at revision 2. Passing the historical response to the existing Matchup presenter at its normal entry point yielded no public comparison. Reading the domain fields separately in the isolated presenter check showed both sides' dated performance samples.

Team Board active arms retain their assessment for the represented date under `read`. Their `display_read` and `arm_context` apply the historical display rule. A Pitcher read for a represented active identity uses the same rule. This prevents an old assessment from appearing as a current availability claim and leaves its dated workload and History evidence accessible.

Offline captures of Boston's Board core and identity-bound details agreed on snapshot 5843, sync run 98300, workload through October 28, 2026 and availability reference October 30. Owen Murphy's saved Pitcher response carried the same snapshot in published deployment and the same dates. GitHub run 44794472956, artifact 14657943570, independently identified the twelve Boston pitcher IDs, Boston's Team State and Murphy's public/MLB identity (764/702566). All twelve Boston publisher inputs recorded Clean Option. All twelve served Board rows and Murphy's served Pitcher response matched the isolated historical display fields exactly, including Limited Read and null days of rest. This field-level replay exercises the display rule against saved responses. Full Board and Pitcher candidate parity still requires an eligible candidate with matching membership and availability dates.

The historical Team Board and Pitcher reads also expose postseason appearances in their 30-day workload window. Each line must belong to a game with a verified postseason decision in that generation's frozen readiness inputs and a matching confirmed game-side boxscore. The club view filters to relief appearances for the appearance team. The pitcher view includes starts and relief appearances by MLB player ID across clubs. An empty `verified_games_only` result cannot establish season-wide absence. The regular-season ledger and calculations keep their existing population.

For Boston through October 28, 2026, ten relief appearances matched the saved snapshot 5843 Board details. Five came from September 29 (849851) and five from September 30 (849848). Game, pitcher, team, date, outs, pitches, saves, holds and games finished all agreed. Murphy had no appearances among the verified playoff games in the window. The comparison used only retained MLB receipts and the saved Board response on disposable PostgreSQL 17.6. An earlier generation without the verified postseason decision continued to withhold the test game's lines after a later generation acquired the evidence.

Use `python -m sync_v3.rehearse --fixture DAY.json --through YYYY-MM-DD --availability-as-of YYYY-MM-DD` to reproduce the schedule-aware reference-date calculation. Repeat `--fixture` for the dates after workload coverage through the as-of date plus the production three-day lookahead. The read reports its daily receipts and acquisition timestamps. Missing schedules, unresolved listing removals and material ambiguity about a postponed game's date withhold the result. The as-of argument describes the scenario being tested. A historical publication's actual fatigue recalculation day and stored schedule inputs require independent evidence.

For workload through October 28, 2026 and an as-of date of November 20, twenty-six retained league schedules covering October 29 through November 23 contained zero games. The production resolver returned October 29. Snapshot 5843 recorded October 30. These November 21 retrievals cannot identify the rows retained by the original publisher. A separate replay for workload through July 16, 2024 advanced to July 18 using the subsequent league schedules. Game 747093 appeared on July 19 as postponed with an official date of July 20. Other fixtures independently established the later slate, so the reference date was identical with or without the disputed listing.

The historical Pitcher read projects the selected pitcher profile's monthly regular-season relief samples into `season_pitch_characteristics`, the contract used by the existing velocity and mix chart. The read verifies the profile's MLB ID and workload date. Missing season evidence withholds the chart. Each incomplete month retains its outing and verified-outing counts. Measurements and per-game evidence remain in the cited profile.

A PostgreSQL 17.6 replay for Owen Murphy (702566) through October 28, 2026 used 17 retained MLB responses. September matched the saved Pitcher response from snapshot 5843 on every chart field across two outings and 96 pitches. The replay verified 67 July relief pitches in games 824900 and 823030 and excluded the July 18 start. The saved July chart reported zero of two outings verified. Withholding July play-by-play in an isolated control reproduced the entire saved chart. This identifies a difference in verified coverage; the historical reason those two outings lacked verification remains unknown.

The historical Pitcher read supplies the 30-day chart and recent appearance list from the selected generation's regular-season and verified postseason lines. The chart retains one point per game, including doubleheaders, in chronological order. The appearance list shows the latest eight verified lines. Both preserve missing pitch counts. A gap in the regular-season or postseason ledger is disclosed in the chart caption, and an empty list reports only the absence of verified outings.

For Aroldis Chapman (547973) through October 28, 2026, the chart rendered 14 pitches against New York in game 849848 on September 30. That point matched Boston's saved snapshot 5843 Board. Seven dates in the replay had incomplete regular-season coverage. The chart displayed the gap notice alongside the verified point. The saved Murphy recent-work response retained its published empty-window wording when passed through the same React chart.

The isolated Pitcher read supplies the inning, score and recorded leverage distributions for regular-season relief appearances with the represented club in the 14 days through the workload date. It uses the official season log for the denominator and reads only final boxscores and ordered plays pinned by that pitcher profile. The separate movement chart uses the club snapshot's two comparable seven-day windows, including eligible postseason work, and the existing Board movement validator. Both charts can withhold evidence independently.

On PostgreSQL 17.6, Murphy's October 28 deployment context and absent movement matched the saved snapshot 5843 Pitcher fields. Through September 22, the replay found two sixth-inning entries while Atlanta trailed. Neither outing had a recorded leverage index. In the August 7, 2024 replay, Atlanta's A.J. Minter went from zero eighth-or-later entries out of three known outings to two out of three. The existing React chart displayed both dated samples. The isolated comparison does not assign a trusted production snapshot to the candidate.

The routed Pitcher Detail rehearsal served two isolated PostgreSQL 17.6 reads through the existing React router in Chromium. The represented Boston pitcher showed the dated identity, recorded throwing hand, four charts and the selected performance sample. A departed pitcher retained his dated name without a current team or performance table. Each built page requested only its pitcher endpoint once. React development remounts canceled and retried that endpoint successfully. Candidate editions omit the production history lookup and current Board link so a reader cannot combine generations through those controls.

The routed Team Board checks the requested club before rendering its answer and before requesting deferred sections. A disposable PostgreSQL 17.6 selection sent to the public Board in a loopback Chromium rehearsal withheld the answer and made zero detail requests. A saved Boston core for snapshot 5843 requested details once with all 19 identity fields. Two negative controls, a wrong-club receipt and a missing snapshot ID, each withheld the answer and made zero detail requests. This checks the public delivery boundary. Displaying an authorized replacement Board still requires a matching publication identity.

Add `--team 111` to the existing `--build-generation --exercise-selection` rehearsal to emit Boston's historical Team Board after a successful isolated selection. Its recent relief games combine the club's confirmed regular-season and postseason appearances on the five most recent verified appearance dates. Doubleheaders keep their separate game IDs. Missing pitches or outs withhold that game's affected total. The read includes the final revision, boxscore digests and coverage gaps. Empty game lists carry no claim that a team had no relief appearances.

Boston's saved snapshot 5843 and the PostgreSQL 17.6 replay agreed on the game, pitcher, club, date, pitches, outs, save, hold and game-finished values for ten appearances through October 28, 2026. At New York on September 29 (849851), five relievers recorded ten outs on 78 pitches. On September 30 (849848), five recorded ten outs on 77 pitches. The initial rehearsal lacked seven daily schedules. After supplementing the retained evidence, all 30 daily MLB slates and the retrospective season calendar agreed on Boston's two games. Independently totaling the verified lines reproduced the archived 30-day totals of ten appearances, 155 pitches and 20 outs, and all three zero totals for each of the 3-, 7- and 14-day windows. This comparison covers dated game-side workload only.

The selected historical Team Board returns `competitive_workload.windows` for 3, 7, 14 and 30 days. It checks the club's pinned daily slates against the selected season calendar, requires verified playoff finals, and passes regular-season and postseason relief lines through the publication's workload-window calculation. Boston's four returned windows matched the saved snapshot 5843 windows, including their dates, values, statuses and reason codes. Repeating the replay without seven daily slates withheld the 7-, 14- and 30-day totals. The independently covered three-day window still returned complete zeroes.

The selected Board's competitive workload includes seven-day concentration. It uses the public contributor ordering and the dated bullpen cohort for the active and off-active splits. Work remains attached to the club for which the reliever pitched. Missing contributor identity or unresolved membership withholds the breakdown while the independently qualified team windows remain available.

On PostgreSQL 17.6, the complete October 28, 2026 Boston concentration matched snapshot 5843, including zero contributors and an undefined top-three share. For August 1–7, 2024, the replay reproduced the official boxscore pitch count for each of nine San Francisco and eight Washington contributors. San Francisco's top three accounted for 166 of 337 pitches, led by Sean Hjelle with 61. Washington's accounted for 147 of 314, led by Derek Law with 59. The replay used synthetic public route IDs for the verified MLB identities. An isolated transfer case preserved the old club's 20 pitches, attributed them to its off-active contribution and kept missing outs unknown.

With a partial public identity export, a withheld concentration includes `unresolved_contributor_mlb_ids` in MLB ID order. A PostgreSQL 17.6 replay of August 1–7, 2024 with the observed snapshot 5843 export resolved seven of San Francisco's nine contributors and three of Washington's eight. The team windows retained 337 and 314 pitches respectively. Both named rankings were withheld. San Francisco lacked route evidence for Sean Hjelle (663546) and Randy Rodríguez (678495). Washington lacked it for Derek Law (571882), Jacob Barnes (606930), Tanner Rainey (663432), Joan Adon (672851) and Eduardo Salazar (674285).

The digest-verified GitHub proof artifacts for snapshots 5751, 5827 and 5843 (artifacts 12969263858, 14062833340 and 14657943570) contained 441 distinct public/MLB identity pairs in total. Overlapping pairs agreed in both directions. None of the three supplied the seven missing pairs. These later observations establish only the mappings they contain.

After a successful `--build-generation --exercise-selection`, the rehearsal follows each selected Board to Team History and every offered public pitcher ID to Pitcher Detail and Pitcher History. It checks all 30 clubs by default. Adding `--team` limits the check to that club. Each `board_history_verification` reports the selected revision, generation, matching team event count, verified pitcher routes and withheld MLB IDs. It checks dated club membership, evidence, workload and availability dates, observed roles and historical read display. The Board uses the same conflict-checked pitcher directory as its destinations.

The disposable PostgreSQL 17.6 league fixture checked 61 team events across 30 clubs and followed 29 synthetic pitcher routes. With the Yankees pitcher's mapping omitted, its Board withheld the link. Reversing the fixture ingestion order reproduced the same generation digest and all 30 verification records. Both rehearsals restored the empty selection. Regressions also reject a wrong MLB identity, a mismatched displayed read and a Board event list that disagrees with History. This is isolated product-contract evidence.

The same rehearsal resolves each Team History event through the editorial evidence reader at its exact selection revision. It checks the event payload and citation, including input and facts digests. Ambiguous identities withhold the evidence. For Stories it compares the rotation citation, represented dates and contributing game identities with the selected Board. Where both cite a relief game, they must share a retained boxscore digest. A withheld Story has no observation payload.

On the synthetic 30-club slate, all 61 event citations resolved and the Story builder produced 31 observations. All 15 Search and Matchup routes reproduced their Tonight cards, including home and away identity. Reversing ingestion order reproduced all 15 Matchup responses and all 30 Board verification records. These checks exercise historical read contracts using disposable PostgreSQL. An editorial observation has no published Story or Share identity.

A partial October 30, 2024 World Series fixture verified one official final and 13 pitching lines. With 24 discovery jobs still pending, the rehearsal returned `ReplayWithheld`. The selection gate reported `unresolved_club_readiness` and `incomplete_represented_schedule` and wrote zero selection records.

### Methodology and source coverage for a historical edition

The selection rehearsal emits `historical_trust` for either outcome. A selected edition has a selector revision. A withheld candidate can be inspected by digest with `sync_v3.editorial_reads.preview_trust`; its status is `candidate_preview` and its selection revision is null. Both reads verify the frozen inventory and report the two baseball dates, methods, source receipt counts, coverage for each of the 30 clubs, and game and roster comparison results. The separate selection result records the decision at the time of review. Only receipts with a retained response body can establish an acquisition timestamp. A failed fetch still contributes to the failure count.

For the partial October 30, 2024 fixture, the Trust preview matched World Series game 775296. It reported missing competitive schedule evidence for all 30 club readiness calculations and a missing complete October 31 slate. Nine pinned receipts contained responses. Another 18 pinned receipts represented failed lookups in the local fixture and had no acquisition dates. The counts cover the inputs cited by this candidate.

### Static Team Board delivery

From `backend`, compare a retained GitHub Actions delivery report with the matching generated tree. The optional publication proof independently binds each dated page’s Team State to its observed receipt.

```sh
python -m sync_v3.team_preview_comparison "$DELIVERY_REPORT_ZIP" "$REPORT_SHA256" "$CHECKOUT" \
  --publication-proof "$PROOF_ZIP" "$PROOF_SHA256"
```

The comparison runs the existing team delivery verifier, checks the exact 30 MLB clubs and fallback against the file digests, and follows both the visible link and the redirect to the club’s Team Board. A dated page must cite the publication snapshot, sync run and workload date. A withheld page retains its club route and reason. The isolated selection rehearsal passes each candidate Board through the existing preview renderer. It requires that the resulting page withhold public claims because the candidate has no trusted publication authority.

Two deliveries used snapshot 5843 and sync run 98300 with workload through October 28, 2026. Distribution run 44716734983 (artifact 14620151702, Git commit `ce0e3384`) produced 30 dated previews. Run 44794472956 (artifact 14659061276, Git commit `9ea5ac93`) produced 29. Pittsburgh alone changed, to `no_trusted_publication`. The job log identifies team 134 and the export’s withholding reason. It does not explain why the renderer lacked Pittsburgh’s snapshot receipt. All dated previews in both exports agreed with the observed Team State receipts in artifact 14657943570. All 30 clubs were season complete. A dated preview in these exports carried no current Team State label.

With the publication proof supplied, the comparison can also reproduce dated pages whose observed Team State withholds for competition reasons and whose export declares zero Story previews. In that case the existing renderer uses the frozen non-state message and omits the current baseball point. The replay takes the club identity from the MLB directory, the Team State from the observed publication receipt, and the dates and publication identifiers from the pinned delivery report. It compares the rendered UTF-8 bytes to the archived digest-verified page. A missing receipt, a withheld page or a need for additional Board or Story inputs is reported separately.

The renderer reproduced 30 of 30 dated pages in the earlier snapshot 5843 delivery, including Pittsburgh. It reproduced 29 of 29 dated pages in the later delivery. Pittsburgh’s later withheld page was verified as delivered. The published season-complete receipt does not establish why that export lacked a Board receipt for Pittsburgh.

To derive the season-complete state from MLB inputs, run the existing PostgreSQL rehearsal with one `--fixture` per retained day:

```sh
python -m sync_v3.rehearse --pg-bin "$PG_BIN" --competition --through 2026-10-30 \
  "${fixture_args[@]}" --identity-proof "$PROOF_ZIP" "$PROOF_SHA256" \
  --team-preview-export "$DELIVERY_REPORT_ZIP" "$REPORT_SHA256" "$CHECKOUT"
```

Here `fixture_args` is a shell array of `--fixture PATH` pairs. The 24-day fixture set supplied 553 retained MLB responses, 40 finals and 406 pitching lines. The rehearsal derived all 30 clubs’ competition states, compared them with the postcommit receipts, and used the derived Team State plus the archived publication identifiers and timestamps to reproduce the same 30 and 29 pages. Reversing the 24 fixture files produced identical per-club reproduction results for both exports. A replay containing only the October 30 fixture refused with `incomplete_competition_evidence` before reporting any reproduced pages.

The same replay compared all 30 season-complete projections with the independently observed receipts for snapshot 5827. Snapshot 5751 shared the workload and availability dates but omitted competition context for all 30 clubs. The comparator reports those missing club receipts and leaves their historical claims intact.

For a dated preview with an available Team State, the publication-proof comparison also replays the frozen readiness input through the public Team State projector. For status-only decisions it reconciles the recorded distribution to the counted population, lists the roster members without records, and checks the archived partition and decisive rule against the recorded thresholds. It separately reports whether the current partition rule gives the same label and decision. This reproduces the published state field. The Board’s supporting health sentence has its own population and inputs.

The October 28 export for snapshot 5656 has workload through October 27 and an availability reference of October 28. All 30 state fields matched the archived inputs and partition rules. Cleveland was Fresh, the Dodgers were Stretched, and 28 clubs were Vulnerable. There were 396 counted pitcher records and 32 membership entries without a counted record. Snapshot 5751 produced one Fresh and 29 Vulnerable labels from 399 counted records with 33 missing. The GitHub distribution/proof artifact IDs are 12806824657/12834450920 and 12968419887/12969263858, respectively.

Both historical proofs predate the competition-context receipts. When replayed MLB decisions establish season completion for a club that previously had a positive label, the competition comparison reports its archived label alongside the outcome and reason under the replayed rules. That comparison preserves the original publication and keeps the count of matched historical competition receipts at zero. On October 28 Tampa Bay and Milwaukee still had a scheduled game. For both clubs the independent readiness replay returned `regular_season_workload_scope_required` on October 28. Their postseason game falls outside the regular-season workload contract, so neither acquired an independent positive Team State.

For these two editions the export comparison also runs the Board health and static preview renderers using the Team State availability counts in place of the original Board card counts. All 60 HTML files matched byte for byte. The October 28 export described 28 On Watch groups and two Unavailable counts (Tampa Bay and Milwaukee). All 30 October 30 pages described On Watch groups. The separate per-page field `render_using_team_state_counts` reports this experiment. Matching bytes do not establish the identities or population of the original active bullpen cards, and do not increment `pages_reproduced`.

The GitHub workflow census for October 27–31, 2026 returned 21 bullpen sync runs, eight generated distribution runs and 12 CI runs. The sync artifacts covered the appearance audit, shadow diagnostic, generated-preview validation, Team State proof, and rendered Share and Team pages. The separate manual publication-truth certification workflow, which can inspect the Board population, ran successfully for snapshot 4496 on October 7 (run 37627372665). The run log identifies that snapshot and its artifact listing returned no entries. These records supply no independent Board card list for snapshots 5656 or 5751.

When a publication retains competition context for only some clubs, the offline comparator counts the clubs it can compare, keeps their field differences, and lists each club missing context. A mismatched club ID or reference date in any retained context refuses the comparison before attributing an outcome to a club. A partial comparison cannot establish league-wide agreement.

In a selected historical edition, pitcher Search results carry the same `historical_departure` event and source citation as Pitcher Detail and Team History. An observed destination club can supply its own active status. A departure alone leaves that status unknown. Search reads the pitcher directory only when the product query qualifies, and a database error in that optional lookup rolls back to a read-only transaction savepoint so the edition's team and matchup results can still be returned.

A departure with continuing forty-man membership retains the position from that edition's forty-man response. The August 7, 2024 Kansas City roster identified Hunter Harvey as a pitcher (position code 1). The isolated directory reported P, retained the removal and forty-man citations, and left his active club and public route unresolved. In a selected synthetic edition with an independently mapped public ID, Chromium displayed P alongside “Team unavailable” and UNKNOWN on the normal Search route. An injected pitcher-directory failure still yielded the Boston Board link and matchup 10101.

A historical read cites a selector revision only when that decision exists. An explicit request for an unknown revision yields `unknown_revision` and no selection identity. An empty selection yields `no_selected_generation`. If a rollback produced the empty selection, the reads retain that rollback revision and the history cursor can still reach the prior edition. The isolated off-day rehearsal verifies that the prior edition still returns its original empty slate. Replaying the retained August 6–7, 2024 Kansas City inputs left the incomplete edition unselected. Search, Pitcher Detail, Stories and event evidence all withheld revision 1.

Historical Stories require recorded relief pitch counts and official reliever names inside the ten-day concentration window before computing a workload share. An absent pitch count withholds the concentration layer with `missing_relief_pitch_count`. Other editorial layers retain their own coverage checks. Across retained regular-season boxscores for July 29–August 7, 2024, San Francisco recorded 406 relief pitches in eight games and Washington recorded 544 in nine. Their top-three shares were 44.8% and 49.4%. Dropping one relief count per club from copies of game 744822 previously yielded 46.9% and 50.6%. Both incomplete comparisons now withhold the share.

Historical concentration Stories include the ten-day league average and the number of contributing clubs. The comparison requires calendar coverage for all 30 clubs in the same generation. Both participating clubs must pin the same canonical final revision for each game, and relief pitch counts must be complete. The existing concentration calculation excludes planned bulk followers and clubs with zero qualifying workload from the average. A missing league input withholds the comparison while preserving any supported club share. The reader returns the dates and per-club rotation snapshot digests in `league_concentration_citation`.

For July 29–August 7, 2024, all 30 clubs contributed. Both the frozen PostgreSQL generation and a separate tally from retained MLB boxscores returned 46.7% as the mean club top-three share. San Francisco's 44.8% was 1.9 percentage points below the baseline and Washington's 49.4% was 2.7 points above it. This verifies the historical comparison without selecting the candidate for publication.

Reversing the daily fixture order reproduced generation `c7ad5d5f2f445d84b2bcadf6db67f204dfa85b9add7a9d5aeabef2e4e59235a6` and the same average. Freezing an earlier generation before Milwaukee's rotation snapshot existed returned `incomplete_league_clubs`. Reading that earlier generation after adding Milwaukee still withheld its comparison.

Historical Stories expose the dated MLB active/40-man comparison under `roster_depth_evidence`, with the same depth citation as the selected Team Board. The lists establish which pitcher IDs appeared on the 40-man response outside the active response and which status codes that source recorded. The production depth-pressure calculation also uses the club's assigned pitcher population, its active bullpen records and dated role evidence to account for starters. The historical reader reports missing coverage for that calculation and withholds the pressure band. Conflicting parent or active-roster evidence withholds the roster comparison itself.

For Kansas City on August 7, 2024, the retained active response listed 12 pitchers and the 40-man response listed 23. The replay matched all 11 additional IDs to the source and retained their codes (six RM, three D60 and two D15). These are counts of official roster listings. The number of unavailable relievers remains unverified. Boston’s August 5, 2024 40-man response failed the historical SP-05 authority check. Its replay returned the scope conflict with no player list or status codes.

Historical Pitcher Detail can show a verified outing after the pitcher leaves the active roster. For a departure or a forty-man-only identity, the ledger cites the club recorded in that evidence and filters each appearance by its game-side club. The route labels the club and leaves current team and availability unresolved. In the archived 30-day window ending August 7, 2024, the Kansas City ledger for Hunter Harvey matched six official outings and 124 pitches. The Washington ledger independently matched two outings and 36 pitches. The archive lacks a public pitcher ID for Harvey, so this comparison exercises the ledger. The selected-edition route test uses a mapped synthetic Boston starter.

The Pitcher ledger, recent rows and workload chart use the same verified outings. The response cites the regular-season workload and postseason readiness snapshots separately and reports gaps by source. Replaying Boston's retained 2026 postseason boxscores for Alec Gamboa (687941) exposed a discrepancy: the chart had both outings and the full ledger had zero. The corrected ledger and chart include games 849851 (15 pitches) and 849848 (7 pitches). The replay reported seven dates with missing regular-season coverage, so the combined result is partial.

Team History checks both clubs' pitching outs before reporting extra innings. Entering an inning requires each side to have completed the preceding innings. A replay of 269 retained July 2024 regular-season finals supported extra innings in 19. The other 250 lacked a final inning number and their outs alone could not settle the question. Game 745146 had 30 outs per side. Removing one starter's outs in a test copy caused the claim to be withheld.

Team History decisions carry the club's Team State, availability reference date and readiness citation from the exact selected generation. The Board-to-History rehearsal compares that state and date at the same revision. A rollback to an empty selection has no Team State. The existing History page recognizes this isolated response and displays dated decisions and game context as a historical rehearsal. In Chromium, the Boston fixture showed the original readiness evidence after rollback and requested only the local History payload. Public artifact history continues to use its existing contract.

Each displayed historical decision includes its cited What Changed events. A reader can expand a change to inspect its event ID and comparison input digest. Events must match the decision's club, represented date and comparison citation. The August 7, 2024 Kansas City preview rendered all 15 archived events, including Hunter Harvey's removal from the active roster. The retained August 6 roster listed him and the August 7 roster excluded him. This preview remained unselected. A separate selected Boston fixture exercised the normal History route and verified the displayed citations after rollback.

Pitcher Detail and Pitcher History project individual events from the same dated club comparisons as Team History. An active starter can have a cited short start even when he has no bullpen read. A player with a verified transfer can retain a departure from his former club. After rollback in the Boston rehearsal, the starter's short-start event still cited the original inputs and the recorded 12 starter outs and 15 bullpen outs. In the August 7, 2024 frozen Kansas City replay, Hunter Harvey had exactly one cited removal and lacked an independently mapped public pitcher ID.

The selection-and-recovery rehearsal includes a correction to the previous day's synthetic Boston active roster. Revision 1 cites a departure. Revision 2 withdraws it after the corrected roster removes the evidence for prior membership. Revision 3 restores revision 1's generation and exact citation. The forty-man observation remains available throughout. The test checks the event receipt, Pitcher Detail and Pitcher History at each revision. From `backend`, run `python -m pytest -q tests/test_sync_v3_corrections.py -k isolated_core_selection_and_recovery` with the disposable PostgreSQL test environment. After rollback, the corrected account remains independently readable at revision 2.

The historical Team History page can load the preceding selection decisions. Its continuation sends the numeric club and predecessor revision to the read-only rehearsal handler at `GET /api/sync-v3/history/teams/<team>/revisions/<revision>`. The handler uses the supplied disposable database connection factory and returns 14 decisions per page by default. An unknown revision returns HTTP 404. Before displaying a continuation, the page checks the historical scope, club, requested revision and every predecessor in the returned page. A failed request can be retried while the already displayed decisions stay visible. The Flask adapter is constructed separately from the production application.

To open an exact initial edition in a frontend pointed at the isolated rehearsal adapter, use `/history/team/BOS?rehearsalRevision=3` (substitute the club and an existing revision). The initial GET resolves the abbreviation against the MLB club directory. The page checks the returned club and revision before rendering. Earlier pages use that club's numeric ID. A Chromium rehearsal served both the initial Boston page and revision 1 from the same disposable PostgreSQL database. Duplicate revision parameters failed before any History request. Omitting the parameter uses the existing public season History route.

The same disposable Flask adapter exposes the existing product readers under `GET /api/sync-v3/revisions/<revision>/`. Use the following suffixes to inspect one edition across surfaces.

| Surface | Route suffix |
| --- | --- |
| League and Tonight | `league`, `tonight` |
| Matchup | `matchups/<game_pk>` |
| Team Board and What Changed | `teams/<mlb_team_id>/board`, `teams/<mlb_team_id>/changes` |
| Pitcher Detail and History | `pitchers/<public_pitcher_id>`, `pitchers/<public_pitcher_id>/history` |
| Search | `search?q=Boston` |
| Stories and event evidence | `teams/<mlb_team_id>/stories`, `teams/<mlb_team_id>/events/<event_id>` |
| Methodology and Trust | `trust` |

Event IDs include their original slash-separated components. Event evidence remains an input to editorial review. A missing event returns HTTP 404 and cannot supply a share artifact. With the disposable PostgreSQL test environment active, run `python -m pytest -q 'tests/test_sync_v3_corrections.py::test_isolated_core_selection_and_recovery[complete]'` from `backend` to exercise the routes after correction and rollback.

An individual change in a historical Team History decision offers a Pitcher Detail link when the selected generation resolves the player's BaseballOS ID and the pitcher read includes that club's event. The link carries both the selection revision and generation digest. The destination checks those values and the MLB and public pitcher identities before showing the read. The Boston rollback rehearsal follows the restored departure to pitcher 8999 at revision 3. The same pitcher at corrected revision 2 retains his forty-man observation without a departure.

Open `/search?rehearsalRevision=3` against the same adapter to search the selected edition. Search checks the returned revision, generation digest, historical eligibility, and echoed query. A mapped pitcher result opens Pitcher Detail with both the revision and digest. A mapped matchup opens its historical comparison at the same revision and generation. The destination checks the game, both clubs, represented dates and absence of publication authority before rendering. Team results open the club by MLB ID at the same revision and generation. The historical Board shows dated Team State, the represented active bullpen, club workload windows and cited changes. Mapped arms open Pitcher Detail at that same edition. A malformed or repeated revision displays an error before discovery runs.

Open `/dashboard?rehearsalRevision=3` against the adapter to inspect League for a selected revision. The page displays both dates and accounts for 30 distinct clubs, including withheld reads. Every Board link carries the returned generation and revision. An optional `rehearsalGeneration` binds the initial League request to a specific digest.

Open `/tonight?rehearsalRevision=3` against the adapter for the represented slate. Game cards, featured games, and changes carry that edition into Matchup and Team Board. A selected empty slate remains distinguishable from missing schedule evidence.

The historical Board links to `/trust?rehearsalRevision=<revision>&rehearsalGeneration=<digest>`. This reads the selected generation’s verified source inventory, acquisition spans, and calculation methods. The represented dates and acquisition times refer to different events. The underlying rehearsal has no trusted production snapshot ID.

The historical Board’s editorial observations link opens `/stories?team=<MLB team ID>&rehearsalRevision=<revision>&rehearsalGeneration=<digest>`. The evidence view preserves the observation engine’s inputs, rotation citation and official boxscore digests for that club and edition. Incomplete game evidence displays the qualification reason. Publication of a story and creation of a share artifact require separate authority.

### Reproduce the historical product journeys in Chromium

From the checkout root, install the existing test dependencies in your development environment. PostgreSQL server tools must be installed locally. Run as an unprivileged user.

```sh
python -m pip install -r backend/requirements-dev.txt
(cd frontend && npm ci && npx playwright install chromium)
cd backend
APP_ENV=test AUTO_SYNC=false SYNC_V3_TEST_BROWSER=1 SYNC_V3_TEST_PG_BIN="$(pg_config --bindir)" \
  python -m pytest -q -s 'tests/test_sync_v3_corrections.py::test_isolated_core_selection_and_recovery[complete]' \
  tests/test_sync_v3_corrections.py::test_selected_off_day_has_no_games_and_preserves_the_league
```

Backend CI shard 4 enables these browser assertions when it runs the two existing tests. The test creates a private PostgreSQL cluster and synthetic 30-club edition, corrects it, then rolls it back. Chromium reads the Flask rehearsal adapter over loopback and verifies the historical destinations against those records. A mismatched generation must withhold the Board. The off-day case opens the League listing from a selected empty slate and checks all 30 club destinations. The browser build lives in a temporary directory. To use an installed Chromium executable, set `SYNC_V3_TEST_CHROMIUM` to its absolute path.

### Historical pitch coordinate provenance

For Lucas Erceg (668674) on August 7, 2024, all 22 pitches in [game 746272](https://statsapi.mlb.com/api/v1/game/746272/playByPlay) matched [Baseball Savant's CSV](https://baseballsavant.mlb.com/statcast_search/csv?all=true&type=details&player_type=pitcher&game_date_gt=2024-08-07&game_date_lt=2024-08-07&pitchers_lookup%5B%5D=668674) by pitcher, game, one-based at-bat number and pitch number. All 22 pitch classifications and start speeds agreed. The retained Savant CSV SHA-256 was `582b4bcd8a3ae66042e09d8a9398964a01c445e78073dc3a8ddbaa5b90a868e1`. The game feed’s trajectory y0 ranged from 50.000 to 50.007 feet. Savant’s release_pos_y ranged from 53.90 to 54.11 feet. On pitch six of at-bat 66, the two values were 50.002 and 53.91 feet, respectively. All 22 pairs also differed on x and z at Savant’s displayed precision.

The historical Pitcher Detail response exposes the game feed’s three coordinates as trajectory_x0, trajectory_y0 and trajectory_z0 in the pitcher profile section. The section citation identifies its original v1 input facts. The game feed supplies extension independently. Release-position trends require an admitted source for the release measurements.

In the disposable PostgreSQL 17.6 replay, the retained official boxscore and game feed qualified Erceg’s 22 pitches. Aggregating the Savant rows separately reproduced the chart for that outing: eight changeups (91.2 mph, 36.4%), seven four-seamers (98.8 mph, 31.8%), three sinkers (99.2 mph, 13.6%) and four sliders (86.2 mph, 18.2%). This covers one outing. The replay retained the August 7 transaction contradiction and Boston forty-man scope refusal.

From `backend`, run `python -m pytest -q tests/test_sync_v3_pitch_measurements.py -k erceg` to repeat the pitch comparison offline. The fixture retains the joined pitch fields for this pitcher and game. It omits the rest of both responses.

### Trace a club’s withheld roster-role evidence

When selection refuses a candidate, the rehearsal’s existing `--build-generation --exercise-selection` output includes `historical_trust.withheld_role_evidence`. Each entry identifies the affected club, represented membership date, readiness facts digest, recorded pitcher-profile failure (if reached), and pinned source receipts. The acquisition time and payload SHA-256 identify the specific response used. A later corrected receipt belongs to a later generation.

A disposable PostgreSQL 17.6 replay traced these three August 7, 2024 decisions:

| Club | Official evidence | Effect on the candidate |
| --- | --- | --- |
| Cubs | Caleb Kilian (668873) was listed as a pitcher. His 2024 MLB pitching log had two entries, September 23 and 29, both after the represented date. | His season sample through August 7 could not establish his pitching role. |
| Dodgers | The dated active roster listed Shohei Ohtani (660271) at position Y. | The two-way population guard withheld the club before classifying individual pitcher profiles. |
| Mets | Edwin Díaz (621242) had a June 23 game-log entry for game 746862 with zero games pitched, pitches, batters faced and outs. The official boxscore also listed him with those zeroes. | The season-profile validator requires one credited game per included log row. It withheld the profile. An accepted rule for zero-game entries would need consistent handling in canonical finals, appearance counts, role populations and comparisons. |

The three decisions cited seven distinct receipts. The June 23 boxscore was inspected separately as corroboration. It was outside the inputs to this focused candidate. The selector retained its authority to withhold the edition.

[MLB June 23 boxscore](https://statsapi.mlb.com/api/v1/game/746862/boxscore) · [Dodgers August 7 active roster](https://statsapi.mlb.com/api/v1/teams/119/roster?date=2024-08-07&rosterType=active)

A second historical check evaluated the September 25, 2023 active lists for all 30 clubs. All 832 roster rows passed the position/status screen and club-scope check. Of 412 pitcher profiles, the standalone game-log and date-range validators found a refusal in seven clubs. Four pitchers had no MLB season sample through that date, one had missing scoped pitching statistics, and three had an explicitly uncredited game-log row. The June 13 Mets boxscore (717779, Drew Smith), August 23 Padres boxscore (716883, Robert Suarez), and September 24 Twins boxscore (716445, Chris Paddack) independently list each pitcher with zero games pitched, pitches, batters faced and outs. This establishes a recurring source shape across two seasons. The 23 clubs that passed the profile screen still require canonical finals, workload and publication checks.

### Explicit zero-game pitching listings

MLB can include a pitcher in both the boxscore pitcher list and the pitching game log while assigning zero games pitched. The candidate retains the original responses. Its final reconciliation excludes the listing from appearances only after the original lineup, starter and club-out checks pass, the source explicitly records zero games played, starts, pitches, batters faced, outs and innings, and any supplied pitching event counts agree. A credited zero-out appearance remains an appearance. Missing or contradictory evidence on an explicit zero-credit row withholds the final.

For an explicit zero-game log row, a historical season profile also requires the represented regular-season schedule and a compatible, confirmed final for the same game. The boxscore must list that pitcher for that club with agreeing evidence, and the canonical final must exclude the appearance. Without that proof the profile reports `uncredited_game_requires_official_final`. A credited boxscore conflicting with the log reports `uncredited_game_and_boxscore_disagree`. Confirmed exclusions are identified by MLB game ID in the season facts. The active bullpen population, workload and role calculations use credited appearances.

Four official PostgreSQL 17.6 replays compared 36 canonical appearances against their boxscores. Through August 7, 2024, Edwin Díaz had 33 credited relief appearances after excluding game 746862. Through September 25, 2023, Drew Smith had 60 after excluding game 717779, and Robert Suarez had 24 after excluding game 716883. Chris Paddack’s game 716445 supplied no season pitching sample through that date. With the full fourteen-day schedule and final evidence, the August 7 Mets calculation resolved eight relievers and returned historical **Fresh** for the August 8 reference date. This club calculation has no production selection authority.

From `backend`, run `SYNC_V3_TEST_PG_BIN="$(pg_config --bindir)" python -m pytest -q tests/test_sync_v3_deployment.py` for the correction and conflicting-final regression.

An additional 2017 control, Jorge De La Rosa in game 490559 on May 7, reproduced the same source shape. His verified season sample through August 10 remained 48 relief appearances. Across the five finals the independent boxscore comparison accounted for 43 credited appearances.

Three additional 30-club roster screens in 2017 retained their independent limitations. On August 10 the 365 listed pitchers included Ricardo Rodríguez without a qualifying MLB season sample. On August 15 the 367 included Kevin McGowan without one. On August 23 the 369 included Angel Sánchez, Ryan Sherriff and John Curtiss without one. These are retrospective roster and player-profile checks. None establishes a selected 30-club edition.

When an uncredited pitching row blocks a profile, the historical Trust rehearsal now returns the game ID, official game date, club ID, and failed check under `withheld_role_evidence[].failed_profiles[].game_evidence`. For example, the August 7, 2024 Díaz profile points to **game 746862, June 23, team 121**. With no qualifying June 23 schedule the stage is `qualified_schedule_required`. With that schedule present and no compatible final it is `missing_compatible_final`. A credited final that disagrees with the game log produces `boxscore_disagreement`. The receipt list cites the pinned schedule and boxscore when available. Earlier frozen generations retain the evidence detail originally recorded for them.

### Historical single-game Wild Cards

The 2017 official season calendar records games 526475 (Minnesota at New York) and 526476 (Colorado at Arizona) as round F with one game in each series. The historical calendar validates the declared single-game format for 2012–2019 and 2021, the game identities and the participating clubs. A club appearing in two different Wild Card games, or more than four participating clubs, invalidates the calendar. The rehearsal passes the verified game IDs to the competition classifier. The default production classifier continues to use its existing series lengths. MLB’s round-F schedules independently returned two one-game contests in each of the nine admitted seasons. The 2020, 2022 and 2023 responses specified three-game series.

A PostgreSQL 17.6 replay retained each schedule before its corresponding final. The missing pitching decision kept the outcome unresolved. After the finals, the October 5, 2017 read classified Minnesota and Colorado as eliminated and New York and Arizona as active. The isolated classifier used the official winning pitcher, game-side score and winner flags. The August 28 roster-profile screen covered all 30 clubs, with one separately corroborated uncredited listing for Jorge De La Rosa.

Across those nine seasons, a second PostgreSQL replay verified the prior-day decisions for all 18 single-game Wild Cards against their daily schedules and canonical finals. In each case the losing club qualified as season complete after the game. The season-schedule game IDs and the daily boxscore decisions were checked independently.

### Selected historical edition, August 28, 2017

On an isolated PostgreSQL 17.6 server, the August 28 workload and August 29 availability slate produced generation `8b839ac447baf13850d5e53113b052056c9ac48cc8635dfff7d170ad2f62eeff`. The reviewer selected it as local revision 1. All 1,854 calculation scopes settled. The core comparison reported ten matched finals and historical Team States for 30 clubs (six Fresh, 16 Stretched, eight Vulnerable). The 371 listed pitchers supplied 742 game-log and date-range responses. Five daily transaction inputs retained refusals (August 15, 16, 19, 23 and 26). Core selection certifies only the domains covered by its contract.

The product rehearsal checked all 15 August 29 games across Tonight, Search and Matchup. It checked Board and History for all 30 clubs, including 88 team events. The archived identity export supported 18 pitcher routes. Another 214 MLB identities withheld a public pitcher route. Static previews withheld trusted publication. The Chromium journey followed League → Boston → Trust and Tonight → Matchup using five local GETs pinned to revision 1. Trust took longer than the browser assertion’s original five-second wait in one run. The assertion allows 30 seconds for this evidence page; this is a functional check, not a latency certification.

A backup taken with 174 calculation scopes outstanding restored into a fresh disposable cluster. Batches of 75, 75 and 24 reconstructed the same digest. Repeating selection returned revision 1; rollback cleared the private selection at revision 2. Revision 1 continued to serve the original 30-club edition.

From `backend`, with frontend dependencies and Chromium installed, run the checked-in selected-slate and rollback fixtures with:

```sh
APP_ENV=test AUTO_SYNC=false SYNC_V3_TEST_BROWSER=1 \
  SYNC_V3_TEST_CHROMIUM="$(command -v chromium)" SYNC_V3_TEST_PG_BIN="$(pg_config --bindir)" \
  python -m pytest -q 'tests/test_sync_v3_corrections.py::test_isolated_core_selection_and_recovery[complete]'
```

The fixture exercises the same revision-bound browser assertions using synthetic data. The 2017 replay used separately acquired retrospective MLB evidence. Neither run measures production parity or transfers publication authority.

### Recovering historical pitcher routes from publication proofs

The optional, repeatable `--earlier-identity-proof ZIP SHA256` argument supplements `--identity-proof` with earlier, independently verified BaseballOS publications. The frozen edition pins each export digest. A pitcher route requires an explicit MLB/public ID pair in a pinned export and the existing dated baseball evidence for the player. Each Pitcher Detail response cites only the exports containing its pair. Their observation dates are independent of the roster date. Conflicting assignments fail the database identity constraint. The primary proof continues to supply the reference dates and club receipts for publication comparisons.

For the August 28, 2017 edition, snapshots 5656 and 5751 independently identified Albert Suárez (MLB 544150, BaseballOS 51). Snapshot 5843 omitted him. With both earlier archives loaded, private revision 2 retained the same 30 Team States and recovered the Giants route. Search for `Albert Suarez` returned one pitcher, and his detail and dated history resolved. Represented bullpen routes increased from 18 to 19 of 232. The other 213 remained withheld. Revision 1 retained its original Board and withheld route. The new generation digest was `473a4f7fe512bbf81aabde3f0c23e733c54ae6c0a231a42a9e9dd367e0572095`.

Use these additional arguments with the historical day fixtures, `--through 2017-08-28 --build-generation --exercise-selection`, and the separately retained May 7 game evidence described above. The three archive digests were checked against GitHub Actions artifact metadata.

```sh
--identity-proof "$PROOF_5843" 209f55a6904abf9602946e9b8f5ea5ce836ee398f662442fe199c7dbf169d449 \
--earlier-identity-proof "$PROOF_5751" 55490a0af6b058a1c2b9263c07d45e7a25b83e7ef8738f927e67b46386aed4fc \
--earlier-identity-proof "$PROOF_5656" 156e3d33a02c9724540990f448f47de8050d88d140dcdcc3dde1eabcbcdfa945
```

[Snapshot 5843, artifact 14657943570](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/44794472956) · [Snapshot 5751, artifact 12969263858](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/41040263609) · [Snapshot 5656, artifact 12834450920](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/40727951878)

Three further proofs produced the same result for the original 214 withheld routes. Snapshots 5338 and 5369 contained 380 pitcher identities each, and snapshot 5433 contained 379. All three supported only the Suárez pair among the withheld routes. They were inspected independently of the archives pinned by revision 2. [October 22 proof](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/39803505675) · [October 23 proof](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/39975286406) · [GitHub Actions run 40100640174, artifact 12562352789](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/40100640174)

### Cost of verifying a complete historical edition

The Trust reader verifies each snapshot’s source and request associations, input digest and facts digest on every read. It processes eight snapshots at a time. When snapshots in the batch share a source receipt or request, PostgreSQL returns its contents once together with the IDs of the snapshots that cite it. Each snapshot still gets a separate digest computed only from its own associations.

For the selected August 28, 2017 edition (1,854 calculation records), evidence lookup required 464 queries across 232 batches, down from 3,708 individual queries. On a restored, disposable PostgreSQL 17.6 server, six interleaved reads of revision 1 compared the implementation at `a9d5d18b` with the batched verifier. Elapsed times in seconds were 5.585, 6.009 and 6.209 for the original and 2.133, 2.278 and 2.624 for the batched verifier. Other local tests were running. These timings measure backend Trust reads in that rehearsal. All six returned identical canonical JSON (SHA-256 `b0adaa9a1db17febcdb7a365ceced45e9697bbdbee1bfcf498390b862eb49713`).

Removing one snapshot’s link to a shared receipt made the read fail. Removing one link to a shared request also made it fail. Rolling back each injected change restored the original response. The PostgreSQL regression is `tests/test_sync_v3_corrections.py::test_isolated_core_selection_and_recovery[complete]`.

### Historical Pitcher Detail seven-day workload

The historical Pitcher header reads `sections.workload.value.windows["7"]` from the selected edition. The two counts describe regular-season bullpen appearances and pitches, including qualifying openers. Missing pitches leave the appearance count available. An unresolved calendar or unobserved player withholds both counts. Current availability remains withheld. A pitcher with an identified active club can return to its Board at the same revision and generation.

In the August 28, 2017 private edition, Chromium checked all 19 mapped pitchers against the official August 22–28 boxscores. The seven dated schedules accounted for 99 completed regular-season games. These pitchers contributed 49 bullpen appearances and 824 pitches. Albert Suárez had two appearances and 32 pitches for San Francisco. Two pitchers had zero bullpen appearances despite making three rotation starts between them. Each route reproduced its own counts, including those zeroes. The 213 bullpen members without verified public routes were outside this browser comparison.

Suárez threw 15 pitches on August 22 and 17 on August 25. His historical pitcher route returned to San Francisco’s revision 2 Board with the same generation digest. [August 22 boxscore](https://statsapi.mlb.com/api/v1/game/491972/boxscore) · [August 25 boxscore](https://statsapi.mlb.com/api/v1/game/492019/boxscore)

The same 19 Pitcher pages also showed the last regular-season bullpen outing and elapsed calendar days as of August 29. A second comparison used all 193 official finals from August 15–28. Suárez’s last outing was August 25 (17 pitches), four calendar days before the availability reference date. For two pitchers, the verified date was August 17 and the seven-day last-outing pitch check supplied no pitch count. The header showed the dated result and withheld the count. A missing rest fact or a mismatch in pitcher, workload date or reference date withholds the historical timing.

### Observed deployment on a historical Pitcher page

The 14-day panel covers regular-season relief appearances across all clubs the pitcher represented. The selected profile supplies saves, holds and games finished from official game logs reconciled with dated totals. A retained final with recorded outs supplies the multi-inning count for that appearance. The panel gives its denominator and withholds the last multi-inning date when any qualifying outing lacks outs. A withheld season profile leaves deployment unavailable.

In Chromium, all 19 mapped routes in revision 2 of the August 28, 2017 edition matched an independent count from the 193 official August 15–28 boxscores. Together the pitchers made 99 relief appearances, recorded 19 saves and 18 holds, finished 44 games and worked at least four outs 27 times. Albert Suárez appeared four times, finished one game, and recorded three multi-inning outings. The same historical edition and identity limits apply.

Owen Murphy's qualified MLB game logs through October 28, 2026 recorded zero relief appearances in the final 14 days. The resulting quiet panel agreed with the saved snapshot 5843 Pitcher response on profile, status, workload date and window length. The saved response used his club's official relief appearances. Agreement on Murphy's empty window leaves cross-club and postseason parity unverified.

### Verified games on a historical Team Board

The Board displays the game, opponent, relief appearances, baseball innings and pitches for its five most recent verified appearance dates. Each date links to the specific MLB game. Doubleheaders retain both games, and missing pitches or innings remain unavailable. An empty window or a gap is identified on the Board.

On the August 28, 2017 edition, Chromium compared all 30 Boards with a separate count from MLB's dated schedules and boxscores. The 152 club-game rows covered 477 relief appearances and 8,255 pitches. Washington and the Mets each had six rows across five dates, including both games of their August 27 doubleheader. Opening the 30 Boards used 30 local revision-bound requests.

### Postponement and makeup coverage

The workload reader validates the full season schedule, then compares its listing for each date with that date's retained slate. The final-game index still identifies a makeup by its official completion. MLB game 491893 appeared on August 16, 2017 as postponed and on August 17 as final. Comparing only the final-game index lost the first listing and withheld both clubs' 14-day totals.

Through August 28, Cleveland's 41 relief appearances, 121 outs and 632 pitches and Minnesota's 40 appearances, 126 outs and 635 pitches agreed with an independent boxscore count. The other 28 clubs' 14-day fields already agreed. The PostgreSQL regression also requires a verified playoff final before counting a rescheduled postseason game. [August 16 schedule](https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2017-08-16) · [Makeup boxscore](https://statsapi.mlb.com/api/v1/game/491893/boxscore)

### Thirty-day historical Board workload and active-group performance

The historical Board shows separately qualified recent-30-day and season-to-date metrics for the active bullpen represented on that date. Only relief work for that club enters the active-group sample. Matchup uses the same season projection. Each sample has its own start date, active pitcher count and relief appearance count. The Board can retain a sample size when the underlying evidence withholds every metric.

Sixteen additional dated fixtures extended the August 28, 2017 rehearsal to July 30. The previous selection withheld the 30-day workload for every club. With the additional fixtures, the rebuilt private generation was `a6156e8303d971c96ce966895e3743b62836f46759b0f1b85e6a5d737aa93290`. All 30 clubs' workload totals matched a separate count of the 410 MLB boxscores. The league recorded 2,538 relief appearances, 8,028 outs and 44,842 pitches. Eleven of the added daily transaction responses had contradictory same-instant evidence. Those requests retained their refusals and pending jobs.

Chromium followed all 30 Boards in the restored PostgreSQL 17.6 edition. An independent recount of the 2,148 relief appearances credited to those clubs' dated active groups matched all 148 qualified recent metrics. Boston's three represented relievers made 32 appearances, recorded 93 outs, struck out 44 and walked 11 of 131 batters. The Board showed 25.2% K−BB, six HR allowed and four of 14 inherited runners scored. The 108-out minimum withheld ERA and WHIP. For team workload, all Boston relief arms contributed 83 appearances and 1,335 pitches.

The historical Board also renders the seven-day pitch contributors from its selected workload. It shares the contributor display and validation with the public Board. The dated view identifies membership on the represented baseball date. An unavailable ranking preserves the separate workload totals. In the disposable rollback browser test, Boston's one ranked pitcher contributed 15 pitches and belonged to the dated active bullpen on July 29, 2026. The test follows the same edition back from Pitcher Detail.

### Rotation workload on historical Team Boards

The Board reads the selected club's seven- and fourteen-day regular-season rotation windows. It shows short starts, starter outs and relief outs after rotation starts, together with the number of games analyzed. Opener/bulk-follower games, bullpen games and excluded games are counted separately. Missing dates withhold the affected window.

In the August 28, 2017 private edition, a separate count from 193 official MLB boxscores matched both windows on all 30 Boards in Chromium. Across the 386 club-game lines in the fourteen-day window, 381 were rotation starts and five were opener/bulk-follower games. The 381 starts included 78 short starts, 6,397 starter outs and 3,713 subsequent relief outs. In the seven-day window, Boston recorded two short starts in seven rotation starts, 125 starter outs and 61 relief outs.

### Dated MLB roster lists on the Team Board

The Board and Stories use the same club, date, depth citation and governed comparison of the active and 40-man pitcher lists. The Board shows the two list sizes and the number of pitchers listed only in the 40-man response. Conflicting parent or active-roster evidence withholds the comparison. These counts describe official list membership. Bullpen role and availability require separate evidence.

For August 28, 2017, all 30 Boards in Chromium matched a comparison of the 60 retrospective MLB roster responses, including every MLB ID in the 40-man-only set. Those responses contained 371 active pitcher listings and 699 40-man pitcher listings, with 328 listed outside the active list. Boston had eight active listings, 26 on the 40-man list and 18 listed only on the latter.

### Reobserved finality and season performance across products

A pitcher profile checks each retained official final against its game log. It pins the schedule that authorized that boxscore and the latest receipt for the same dated schedule. The latest receipt must confirm the same canonical revision of the game. A changed score or a removed game withholds the overlapping final. The original boxscore and schedule remain traceable.

The July 16, 2017 replay received the same MLB schedule digest at 15:09:31 and 15:09:55 UTC on November 21, 2026. Game 490398's boxscore referenced the first receipt. Before the repair, rebuilding its pitcher profile repeatedly omitted the second receipt and the selection gate continued to mark the calculation stale. The isolated regression reproduces the omitted receipt and separately rejects a changed score and a missing listing. [Game 490398 boxscore](https://statsapi.mlb.com/api/v1/game/490398/boxscore)

The August 28, 2017 rehearsal added 304 dated public MLB requests covering the earlier season samples needed by Boston and Toronto. From a saved PostgreSQL 17.6 checkpoint the corrected builder processed batches of 75, 75 and 28 outstanding calculations, then reported zero. All 30 clubs passed the core comparison. The reviewer selected private revision 3, generation `6aacf3baaf84c1e7e8554f5fe68d802de43f1ab2a51c25f272a773796d128ff3`. Both teams' revision 2 reads still reproduced their prior output.

| Dated active group | Relief appearances for the club | ERA | WHIP | K−BB% | HR allowed | Inherited runners scored |
|---|---:|---:|---:|---:|---:|---:|
| Boston, 3 pitchers | 108 | 2.35 | 0.93 | 26.8% | 10 | 12 of 43 |
| Toronto, 10 pitchers | 331 | 3.63 | 1.17 | 17.6% | 36 | 42 of 191 |

Independent sums from the official game lines matched all ten season values on the two Team Boards and in the August 29 Matchup. The rehearsal compares each available or partial Matchup performance side with that club's exact season window, including its declared sample, at the same selection revision. An injected disagreement fails verification. [August 29 game](https://www.mlb.com/gameday/492064)

The selected-slate verifier followed all 15 games through Search and Matchup. Chromium rendered the two Boards and game 492064 with three local, revision-bound GETs and reproduced all ten values.

### Named workloads and deployment on historical Team Boards

Each active arm shows its represented seven-day regular-season bullpen workload across clubs, including qualifying openers. The Board reads the pitcher snapshots in one database query and uses the same covered window as Pitcher Detail. Missing game coverage withholds the window. A missing pitch count can leave the appearance count available. A dated MLB identity supports workload on the Board independently of whether a public Pitcher route can be established.

Through August 28, 2017, the 232 represented arms made 564 qualifying appearances and threw 9,786 pitches across the 99 games in the seven-day window. Thirteen arms recorded zero appearances. Blake Wood made one appearance for Cincinnati and one for the Angels, totaling 41 pitches. Chromium reproduced all 232 players' counts across 30 local Board requests.

The Board also attaches a supported deployment change to its named active pitcher. It uses the existing role-movement contract and displays the backend sentence and both seven-day samples. In the fourteen-day replay, 15 profiles were stable, 277 had insufficient evidence, and four supported a directional change. Chromium verified Chasen Bradford and Ryan Tepera moving toward earlier innings, and Danny Coulombe and Sam Tuivailala toward later innings. Counts were checked against the 193 official boxscores and accepted play sequences. Coulombe's August 23 appearance counted in his sample while the play-by-play batter counts disagreed with the official lines, so that game's entry inning stayed unknown. [August 23 boxscore](https://statsapi.mlb.com/api/v1/game/491990/boxscore)

Restoring the season-performance checkpoint again and changing the batch size from 75 to 37 produced the same revision 3 generation. A private rollback restored revision 2's withheld Matchup performance at revision 4. Revision 3 could still serve the complete Boston and Toronto comparison. With snapshot 5843 as its sole identity export, that generation's whole-edition rehearsal checked 30 Boards, 15 Matchups, 114 Board/History event citations, 41 editorial observations and 18 verified pitcher routes. It withheld 214 pitcher routes and all 30 public static previews.

In a separate restore, adding the two earlier corroborating identity archives to revision 3 produced generation `cdc1d33dbe5519b606b50859285d95fd2c6162170968fb0e024392a502957504`. All 30 Boards retained their baseball facts and all 114 event citations. The archives restored Albert Suárez's public route 51, bringing verified pitcher routes to 19 and withheld routes to 213. The Boston–Toronto season comparison retained its ten values.

### Conflicts in the league-wide season comparison

The August 28, 2017 rehearsal compared 1,959 official regular-season finals with the season logs of the dated bullpen members. A separate boxscore count found 7,558 relief appearances for their represented clubs. Of 150 potential club metrics, 143 matched the independent count and qualified in the candidate calculation. Seven were withheld.

| Club | Independently checked disagreement | Effect |
| --- | --- | --- |
| Cubs | Wade Davis faced four batters according to his April 4 game log and three according to the boxscore. | Season K−BB% had 366 of 367 verified appearances. [Game 490136](https://statsapi.mlb.com/api/v1/game/490136/boxscore) |
| Rockies | Greg Holland faced three batters according to his April 3 game log and two according to the boxscore. | Season K−BB% had 336 of 337 verified appearances. [Game 490101](https://statsapi.mlb.com/api/v1/game/490101/boxscore) |
| Yankees | Aroldis Chapman's April 30 pitching log records zero games finished. The boxscore records one. | The contradictory season profile withheld the dated population and all five season metrics. [Game 490461](https://statsapi.mlb.com/api/v1/game/490461/boxscore) |

The Trust preview of the rebuilt Yankees readiness record identifies game 490461, the field and the two values. Its pinned sources include the boxscore acquired November 21, 2026 at 15:51:27 UTC (SHA-256 `743205eab8937fb0627dcf0ce8011e7f900ec84489d6d0f7196cb6b4673688d1`) and the pitcher log acquired at 13:20:46 UTC (SHA-256 `452c25c53eaffa1936e50194bca2f27f92fee07e4f7c2dbea405b4040c7be3c7`). The earlier private selection remained readable.

The supplementary collection harness mistakenly requested game 490124 against May 26 because MLB's postponed listing had abstract state Final. Candidate reconciliation refused that receipt. The May 27 schedule authorized a separate receipt with identical boxscore bytes. The pipeline's discovery classifier already recognizes the detailed Postponed status. [May 26 schedule](https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2017-05-26) · [May 27 schedule](https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2017-05-27)

After processing 796 outstanding calculations, the full-season build reported zero remaining. The core reviewer withheld generation `9ba58de18def7e7973e1586dcb139bbd5318c67d7da83fdfa41602d1cd93fc09` for unresolved Yankees readiness. Restoring the reviewed database independently reproduced all 143 qualified values from frozen snapshots covering 7,352 cohort appearances on 29 clubs. The selector still returned revision 4 and had no revision 5. All 15 revision 4 Matchups passed their Board comparisons. Chromium followed League, Boston Board, Trust, Tonight and Matchup using five local revision 4 GETs.

### Official pitcher profile observation dates

Historical Board and Pitcher pages identify the date MLB's person profile was observed alongside a supported throwing hand. The date comes from the pinned hydrated active-roster response. A conflicted, uncited or missing hand stays undisplayed. The roster's represented baseball date is retained independently.

In a separate PostgreSQL 17.6 restore of the withheld candidate, the pipeline ingested official affiliate directories and hydrated parent active rosters for 30 clubs. The 371 pitcher listings on the August 28, 2017 rosters had 273 right-handed and 98 left-handed profiles at retrieval on November 21, 2026. Each reported hand and its observation time matched the separate raw-response recount. The private selector remained at revision 4. [Boston dated roster with person profiles](https://statsapi.mlb.com/api/v1/teams/111/roster?rosterType=active&date=2017-08-28&hydrate=person)
