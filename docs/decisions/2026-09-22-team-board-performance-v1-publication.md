# Decision: Team Board Performance v1 Publication

TB-06 v1 preserves the existing Current Active-Pen Performance family. The
population is the represented, default-visible active bullpen frozen in the
trusted Team Board package. Only official, completed regular-season relief
appearances for the represented team, through the represented baseball date,
qualify. `game_logs.appearance_team_id`, not the pitcher's current team, owns
each appearance. An acquired arm's prior-club work and a now-off-active arm's
work are excluded from this active-group read. This is not historical team
bullpen performance.

M-001 Active Bullpen ERA and M-002 Active Bullpen WHIP retain their existing
formula, 108-recorded-out minimum sample, exact rounding, evidence, and
fail-closed gates. Their independent values, qualification, sample, and
evidence states are now authored during trusted Dashboard publication and
frozen under `trusted_team_boards.performance` with contract
`team_board_performance_v1`. The read includes the current regular-season
start, represented through-date, relief appearances, recorded outs and
innings, active-arm count, and contributing-arm count. A below-minimum read
retains its sample and wording without exposing the internal rate. Missing
required rows withhold only the affected metric. A proven zero is the string
`0.00`; absence never becomes zero.

The existing appearance selection is shared once per represented team across
ERA/WHIP and bounded optional-input coverage checks. K-BB% is **not
published** in v1. The official line carries strikeouts, walks, and batters
faced, but batters faced is optional in reconciliation and is not certified
against the official line as a publication-critical denominator. Coverage
counts are recorded without calculating or releasing a percentage. Any
future public K-BB% contract must explicitly approve `(strikeouts - walks) /
batters_faced * 100`, the treatment of official walks including intentional
walks, a BF sample rule, a precision rule, and complete BF proof on every
qualifying line. No such metric is registered by this decision.

Factual home runs allowed are likewise **not published** in v1. The official
pitching-line comparison includes home runs, but that comparison is not bound
to every candidate Team Board publication. In addition, historical
`GameLog.home_runs_allowed` rows may carry a storage default of zero, so
non-null alone cannot certify a group zero. The carrier records bounded
field-coverage counts, not a public HR value. HR/9 is not introduced.

Inherited-runner context is `unavailable` with reason
`source_completeness_not_certified`. Its source fields exist but source
completeness remains Partial; neither an inherited-runner count nor a scored
count is synthesized from nulls. No inherited-runner ingestion,
reconciliation, correction, or backfill is part of TB-06 v1.

Each approved metric has independent qualification and evidence state.
Unavailable optional capabilities carry `value: null`, reason codes, and no
client-side fallback. Performance is descriptive support only: it cannot
change Team State, rank a bullpen, grade an arm, or predict future results.

New trusted packages serve performance solely by value from the exact
team/date/package carrier. Older packages without this carrier serve no new
TB-06 read and never recompute it from mutable GameLog rows. Core/details
identity remains the publication fence; a mismatched carrier is withheld
without withholding earlier Team Board sections. No new selector, migration,
sync authority, or atomic publication authority is created.

## Publication-bound official comparisons

A candidate can now freeze factual HR allowed and inherited/scored counts.
The daily writer uses the MLB pitching game logs it already fetched in the same
sync. The completed-game writer retains the explicit boxscore fields in its
existing reconciliation checkpoint. A build outside daily acquisition can
use those checkpoints only while their status, game identity, revision, and
reconciled count agree. Historical packages keep their original contract.

Each qualifying appearance must match its MLB player, club, game, represented
date, and relief role. HR requires agreement with an explicitly recorded
local count. For BF and inherited runners the official line can supply a
missing local component. A conflicting stored count withholds the affected
domain. An absent official field never contributes zero. Strikeouts plus all
official walks cannot exceed BF, and inherited runners scored cannot exceed
inherited runners. The package retains the compared lines, their content
digest, and the verified population and totals. A GET reads the package by
value.

Proving all strikeout, walk, and BF inputs changes the K-BB% withholding
reason to `metric_publication_rule_unapproved`. Evidence qualification and
approval of a public rate remain separate under the metric-family contract.
