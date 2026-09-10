# Share Cards — Canonical Baseball Voice + Public Page Production Polish (SC-04B)

One deterministic, backend-owned, baseball-native copy system for Team State
Share Artifacts, and a finished, responsive BaseballOS citation page at
`/share/{public_id}`. The immutable artifact — not the page and not the renderer —
owns every public claim and word. The page only formats and arranges them.

Canonical flow: **State → Why → Evidence → Freshness → Limitations → Destination.**

## Public vocabulary (Workstream A)

Single owner: `backend/services/team_state_public_vocabulary.py`.

- Public Team State dictionary (Product Vision §2): **Fresh / Stretched / Vulnerable**.
- Canonical internal→public map (founder decision — see the decision record):
  `operationally_stable → Fresh`, `operationally_constrained → Stretched`,
  `operationally_stressed → Vulnerable`.
- `data_limited` / `refused` map to **no** public state and are never published
  (SC-02 eligibility already refuses them; `public_state_for()` fails closed).
- Internal Team Operations status codes are unchanged and stay internal. Public
  labels come from the explicit map — never by title-casing an enum, and no
  snake_case ever reaches a public field.

## Deterministic copy authority (Workstreams B/C/D)

Single owner: `backend/services/team_state_public_copy.py::build_public_copy`.

Consumes governed immutable facts only (team identity, internal status, governed
constraints + counts, confidence, active-bullpen coverage, limitations, product
date) and produces: `headline`, `why`, reader-facing `evidence` receipts,
`freshness_line`, `trust_line`, `limitations`, `alt_text`, `description`, and the
public `state`.

Properties: deterministic and byte-stable (identical governed input → identical
copy), no AI, no external language service, no randomness, no prediction, no
manager-intent/injury/betting/fantasy framing, no embellishment beyond the
evidence. It describes only evidence already selected into the artifact — it is
not a second evidence selector, state calculator, or trust engine.

- **Headline**: `"{Team} bullpen — {Public State}"`.
- **Why**: one concise, state-specific, evidence-aware sentence naming a baseball
  cause (recent workload, clean options, arms down); never repeats the state
  label; never predicts.
- **Trust line**: high → "Verified from the current active bullpen and completed
  recent appearances."; medium → a plain confidence statement, with the bounded
  partial-coverage caveat carried in **Limitations**.
- **Alt text**: `State → Why → Evidence → Freshness` (deterministic; date-only, no
  build-time timestamp).

## Evidence display contract (Workstream E)

Reader-facing labels are owned by the vocabulary module and shared by the copy
authority (new artifacts) and the public read service (version-aware legacy
presentation) via `build_evidence_receipts`:

| Internal `affected_area` | Reader-facing label |
| --- | --- |
| `availability_distribution` | Available bullpen options |
| `coverage_inventory` | Active bullpen coverage |
| `handedness_coverage` | Bullpen handedness |
| `workload_pressure` | Recent bullpen workload |
| `readiness` (freshness) | Data freshness |
| `trust_metadata` | Read confidence |

Details are composed reader-facing from the governed `count` (never the engine
`message`); an unrecognized family uses one reviewed generic label
(`Bullpen evidence`) and never leaks the enum.

## Public copy guard (Workstream F)

`guard_public_copy` fails closed **before publication** (typed
`PublicCopyGuardError`), so bad canonical copy produces no artifact — it is not
merely sanitized at render time. It rejects banned internal phrases
(`team-level bullpen readiness`, `constrained inventory`, `coverage inventory`,
`model output`, `engine says`, …), banned words (`payload`, `algorithm`,
`actionable`, `optimization`, …), and any snake_case token, across the public
fields (state label, headline, why, evidence label/detail, freshness, trust,
limitation copy, alt text, description). Ordinary baseball words (`leverage`,
`edge`) are not over-banned. Internal codes and logs keep technical vocabulary.

## Versioning + immutability (Workstream G)

- New contract `team-state-1.1.0` (registered beside `1.0.0`); the generation path
  publishes `TEAM_STATE_LATEST`. Artifact type unchanged — **not** "Share Cards V2".
- `public_copy` lives in the immutable payload, so it automatically participates in
  the equivalence key and integrity hash. Revised artifacts have a distinct
  `render_version`, so a revised request never reuses a legacy artifact whose
  public claim differs, and equivalent revised requests reuse correctly.
- `schema_version` is unchanged (the table + JSON column shape are unchanged).
- Legacy `1.0.0` artifacts remain immutable, integrity-valid, and publicly
  readable. The public read service maps their coded state label and coded evidence
  families to reader-facing presentation (permitted version-aware display of coded
  metadata) but preserves the original stored why sentence verbatim (historical
  fidelity wins over presentation). Legacy artifacts are never re-generated to hide
  old wording and are never represented as using the revised contract.

## Public page (Workstreams J/K/L/M/O)

`frontend/src/components/share/PublicShareArtifactPage.jsx`, styled with the
existing BaseballOS design system (tokens `field/dugout/chalk/dirt`, accents
`pine/warning/danger`, `.card`, `font-display`/`font-mono`, `section-title`).
Layout: historical context bar → designed hero (team · bullpen state · why) →
evidence receipt rows → trust & freshness → limitations (omitted when empty) →
"where to go next" (methodology, Data & Trust, and the clearly-labeled live
bullpen surface). It renders solely from the public Share Artifact API — no
live/current-state lookup, no internal/admin call, no generation, no deprecated
client-side generator import.

- **Dates (Workstream L)**: the one shared formatter `utils/dateDisplay.js`
  (`formatUtcDateTimeEt`, `formatDateOnly`) renders human-readable Eastern Time;
  `<time datetime="…">` retains the exact machine value; no raw ISO text.
- **Responsive (Workstream M)**: mobile-first, `max-w-3xl`, intentional padding,
  no horizontal overflow, long team names wrap; readable at 320/375/390/430px,
  tablet, and desktop.
- **Historical vs live (Workstream O)**: the wrapper establishes the snapshot date;
  the original read is preserved; the current bullpen surface is separately labeled
  live. No current-state fetch, no comparison (SC-05 owns current-versus-shared).

## Presentation boundary (Workstream K)

The immutable artifact owns all baseball meaning. The page performs styling,
layout, responsive wrappers, deterministic view-model formatting, and version-aware
label formatting only. It does not select evidence, calculate state/trust, generate
copy, look up current state, or fall back to client-side intelligence. The
compatibility projection and current browser renderer are untouched; SC-06 still
owns canonical renderer replacement.

## Fixtures

- **Arizona production-shaped (Workstream H)**: `operationally_stressed` / high /
  fresh with four governed evidence families and no material limitation →
  **Vulnerable**, baseball-native why, reader-facing evidence, empty-limitations
  omitted. Proves the generalized contract (no Arizona-specific logic).
- **Medium (Workstream I)**: `operationally_constrained` / medium with
  `8/6/2` bounded partial active-bullpen coverage → **Stretched**, exact
  disclosure "This read covers 6 of 8 active bullpen pitchers. Two current
  workload records remain incomplete."; immutable limitation preserved; no
  unresolved pitcher described as available.

Tests: `backend/tests/test_team_state_public_copy.py`,
`frontend/tests/publicShareArtifact.test.mjs`, plus the updated generation-path
and active-bullpen publication tests.

## Production smoke (post-deploy)

1. Let the next trusted snapshot generate revised (`team-state-1.1.0`) artifacts.
2. `GET /api/share-artifacts/{public_id}`: public state is Fresh/Stretched/
   Vulnerable, baseball-native headline + why, reader-facing evidence labels, no
   snake_case, approved versions, integrity valid, no sensitive fields.
3. Open `/share/{public_id}` on mobile + desktop: designed hero, clear hierarchy,
   ET dates (no raw ISO), empty limitations omitted, historical context clear,
   live destination distinct.
4. Open the legacy Arizona artifact `/share/460802966aff4edfb0956cd3f18dacdc`:
   still readable, stored claim unchanged, integrity valid, improved presentation,
   clearly historical, not represented as the revised contract.

## Deferred

SC-05 current-versus-shared; SC-06 renderer replacement; SC-07 PNG/Open Graph;
share/download/native-share controls; `data_limited`/`refused` publication; any
fourth public Team State. SC-05–SC-10 remain deferred.
