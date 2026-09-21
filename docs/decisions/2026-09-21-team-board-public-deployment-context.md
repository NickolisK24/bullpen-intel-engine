# Team Board public deployment context authority

**Scope:** TB-05 publication-time read model only. This decision does not unlock
the internal `appearance_entry_band` evidence family or change role authority.

## Population and clock

Only confirmed regular-season relief `GameLog` rows with resolved
`appearance_team_id` for the represented team qualify. The window is the 14
baseball dates `[data_through - 13, data_through]`. Current roster membership
does not reassign an old appearance. The projection is made while assembling
`trusted_dashboard_publication_v1` and is frozen with that snapshot. Final
source corrections may alter mutable rows before a later publication; they do
not alter an already published carrier.

## Entry and score context

For a game whose play-by-play processing marker is `fully_processed`, the
first contiguous event segment for the same game, fielding team, and pitcher
MLB ID establishes the factual entry inning. The public carrier counts exact
entry innings, eighth-or-later entries, and extra-inning entries (10th or
later). It does not call an inning preferred, expected, or assigned. A missing
event, invalid inning, incomplete game, or disjoint pitcher segment remains
unknown for that appearance. Mid-inning entry is not inferred from inning
alone and is not published by this contract.

Score context uses the last event *before* that pitcher's first segment.
The stored home and away scores are viewed from the appearance team's side
and counted as leading, tied, or trailing. Missing preceding scores, invalid
team side, or absent event evidence remain unknown; no pressure or mop-up label
is inferred. The first event in a game has no preceding stored score under
this rule and therefore remains unknown rather than receiving an assumed 0-0.
Runners on base at entry are not published: the stored play-by-play does not
certify that base state. Nullable boxscore inherited-runner totals are distinct
from entry base state and are not substituted.

## Recorded leverage index

The public leverage basis is **only** the finite, nonnegative recorded
`GameLog.leverage_index` from the completed-game boxscore line. Ingestion
normalizes the provider's `leverageIndex`, `avgLeverageIndex`, or `avgLI` into
that nullable field. This contract does not claim it is leverage *at entry*;
it is an appearance-level recorded index. It does not expose a source-key-
specific or cross-provider comparison. Its explicitly defined display bands
are low `<= 0.85`, middle `> 0.85 and < 1.5`, and high `>= 1.5`. These are
descriptive bins of the recorded measure, not a public role, quality grade,
or prediction. An absent, malformed, negative, or non-finite value is unknown.
Save, hold, score margin, and entry inning never fill a missing index. The
story-oriented `appearance_leverage_v1` save/hold fallback is not imported.

## Coverage and meaning

Each domain publishes its relief-appearance denominator, known count, and
independent status: `complete` when all are known, `partial` when some are
known, `unknown` when none are known despite appearances, and `unavailable`
when there are no qualifying appearances. Unknown is never zero, tied, low
leverage, or middle inning. Counts describe only known appearances when a
domain is partial. Missing context does not suppress the existing observed
saves, holds, games finished, or multi-inning facts.

The public role vocabulary remains Trusted Arm, Setup Arm, Coverage Arm,
Middle Relief Arm, and Role Unclear. Save/hold/finish and ninth-inning-entry
facts do not independently make a Closer role. No future usage, manager intent,
availability, or depth-chart claim is authorized. Named-arm role movement
remains `unavailable/not_published`: no public materiality rule exists.

The new context is additive to the established 14-day deployment profile.
Older trusted packages remain readable but cannot attach the new context from
mutable request-time rows. Exact trusted snapshot and represented-date
identity is required for attachment.
