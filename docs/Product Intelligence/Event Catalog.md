# BaseballOS — Product Intelligence Event Catalog

This is the **canonical reference** for every Product Intelligence event BaseballOS
records. It is the source of truth for what each event means, when it fires, who
emits it, and what it carries.

Product Intelligence answers one question: **is BaseballOS creating a repeat user
habit?** The primary KPI is **Return Rate**. Email exists to bring users back;
BaseballOS exists to create understanding. Every event below must ladder up to
that — nothing is collected for vanity.

## Principles (apply to every event)

- **Immutable facts.** A row records a thing that happened, stamped with when it
  happened. Rows are only ever inserted — never updated or deleted.
- **Append-only.** Corrections are new compensating events, never edits. History
  is never rewritten.
- **State stays derived.** Current state (open counts, return timestamps, opt-in
  status, followed teams) lives in its own tables; this log never stores derived
  status.
- **Owned telemetry.** First-party only — no third-party behavioral analytics.
- **Fault-isolated.** Emission is best-effort; a telemetry failure can never raise
  into, or roll back, a production write.
- **Trust-first.** Smallest useful payload. No PII. No browser-analytics payloads
  (no mouse / scroll / cursor / heatmaps / dwell, and no stored viewport geometry).
  Viewport visibility may be used **only** as a local client-side trigger (e.g.
  `story_impression`), never recorded. Every field has a clear Product Intelligence
  purpose.

## Storage & envelope

All events live in one append-only PostgreSQL table, `product_events`
(introduced D2A-1). It is deliberately **foreign-key-free** so the log survives
deletion of the rows it references and never cascades a delete into history.

Every event shares this envelope; per-event rows below list only the meaningful
fields.

| Field | Meaning |
| --- | --- |
| `id` | Surrogate primary key (append order). |
| `event_name` | Canonical event name (see catalog). |
| `occurred_at` | UTC timestamp the fact occurred. |
| `schema_version` | Payload schema version (currently `1`). |
| `user_id` | Actor user id, when known (nullable; not a FK). |
| `anon_id` | Pseudonymous client id, when supplied (nullable; never PII). |
| `team_id` | Team the fact concerns, when applicable (nullable; not a FK). |
| `run_id` | Digest run id, for digest-job events (nullable). |
| `delivery_id` | Digest delivery id, for per-send events (nullable). |
| `source` | Where the fact originated / its surface. |
| `payload` | Event-specific JSON (JSON-safe primitives only). |
| `created_at` | Row write time (audit; equals `occurred_at` for live events). |

Vocabulary, sources, normalizers, and emitters live in
`backend/services/product_events.py`. Ingestion endpoints live in
`backend/api/product_events.py`; digest-lifecycle emission lives at the existing
digest seams.

## Operator inspection

D2A-5 adds a minimal internal verification surface for recent rows; D2A-7 adds a
flow heartbeat:

- **Backend:** `GET /api/system/product-events` — recent rows; and
  `GET /api/system/product-event-heartbeat` (D2A-7) — per-event Name / Count /
  Most-Recent across every canonical event. Both admin-gated with the existing
  `X-Admin-Token` pattern.
- **Frontend:** `/admin/product-intelligence`, a hidden read-only console for the
  operator to enter the admin token at runtime, inspect recent events, and (D2A-7)
  see at a glance that every event type is still flowing.

This surface is not Product Health, a public dashboard, a read model, a rollup,
or retention analytics. It returns only recent event rows with `anon_id_present`
instead of raw anonymous identifiers and sanitized payload summaries instead of
full payloads. The heartbeat returns counts and a latest-timestamp per event so a
stopped beacon (count 0 or a stale timestamp) is obvious — operational
verification only, no rates or time series.

---

## Catalog

### digest_generated

- **Purpose:** Measure content supply — whether there was something worth saying.
- **Definition:** The composer produced a digest payload for an eligible user during a run.
- **Trigger:** `DbDigestRecorder.on_decision`, once per eligible decision in `run_digest_job`.
- **Owner:** Digest delivery recorder (`services/digest_metrics.py`, via `services/digest_delivery.py`).
- **Payload:** `{reference_date, digest_type, has_meaningful_change}` — columns: `user_id`, `team_id`, `run_id`, `source=digest_job`.
- **Introduced Phase:** D2A-1.
- **Related Metrics:** Generation volume, suppression rate, content-supply health.
- **Version:** 1.

### digest_suppressed

- **Purpose:** Measure how often a generated digest is held back.
- **Definition:** The engine suppressed a generated digest (`send=False`).
- **Trigger:** `on_decision` with status suppressed.
- **Owner:** Digest delivery recorder (`services/digest_metrics.py`).
- **Payload:** `{reason, digest_type}` — columns: `user_id`, `team_id`, `run_id`, `source=digest_job`.
- **Introduced Phase:** D2A-1.
- **Related Metrics:** Suppression rate, suppressed-by-reason.
- **Version:** 1.

### digest_sent

- **Purpose:** The digest was sent — the denominator for open/click/return rates.
- **Definition:** A digest email was accepted for delivery to the user.
- **Trigger:** `on_decision` with status sent (recorded with the delivery row).
- **Owner:** Digest delivery recorder (`services/digest_metrics.py`).
- **Payload:** `{digest_type}` — columns: `user_id`, `team_id`, `run_id`, `delivery_id`, `source=digest_job`.
- **Introduced Phase:** D2A-1.
- **Related Metrics:** Sent volume; denominator for Return Rate, open/click rate.
- **Version:** 1.

### digest_opened

- **Purpose:** Soft attention signal (treat as soft — Apple MPP inflates opens).
- **Definition:** The tracking pixel of a sent digest was loaded. Every open is a fact.
- **Trigger:** `GET /api/digest/open` → `record_open`.
- **Owner:** Digest tracking endpoint (`api/digest.py` → `services/digest_metrics.py`).
- **Payload:** none — columns: `delivery_id`, `user_id`, `team_id`, `source=tracking_pixel`.
- **Introduced Phase:** D2A-1.
- **Related Metrics:** Open rate (supporting, soft).
- **Version:** 1.

### digest_clicked

- **Purpose:** Intent signal — the content created enough curiosity to act.
- **Definition:** A tracked CTA link in a sent digest was clicked. Every click is a fact.
- **Trigger:** `GET /api/digest/click` → `record_click`.
- **Owner:** Digest tracking endpoint (`api/digest.py` → `services/digest_metrics.py`).
- **Payload:** none — columns: `delivery_id`, `user_id`, `team_id`, `source=click_redirect`.
- **Introduced Phase:** D2A-1.
- **Related Metrics:** Click rate, click-to-open.
- **Version:** 1.

### digest_returned

- **Purpose:** **Primary KPI** — the user came back into the product via the digest.
- **Definition:** The first attributed return after a sent digest, within the attribution window. Idempotent (first return only).
- **Trigger:** `record_click` (a click implies a return) or `attribute_return` (sign-in within the window).
- **Owner:** Digest tracking endpoint + auth verify (`services/digest_metrics.py`).
- **Payload:** `{attribution_source: click | sign_in}` — columns: `user_id`, `delivery_id`, `team_id`, `source=click_redirect | sign_in`.
- **Introduced Phase:** D2A-1.
- **Related Metrics:** **Return Rate (primary KPI).**
- **Version:** 1.

### digest_unsubscribed

- **Purpose:** Trust / list health.
- **Definition:** The user turned the digest off (effective opt-in → opt-out).
- **Trigger:** One-click unsubscribe (`/api/digest/unsubscribe`) or `PUT /api/digest/preferences` disabling.
- **Owner:** Digest API (`api/digest.py` via `record_digest_optin_change`).
- **Payload:** none — columns: `user_id`, `source=one_click | settings`.
- **Introduced Phase:** D2A-1.
- **Related Metrics:** Unsubscribe rate.
- **Version:** 1.

### digest_reenabled

- **Purpose:** Channel reactivation.
- **Definition:** The user turned the digest back on (effective opt-out → opt-in).
- **Trigger:** `PUT /api/digest/preferences` enabling.
- **Owner:** Digest API (`api/digest.py` via `record_digest_optin_change`).
- **Payload:** none — columns: `user_id`, `source=settings`.
- **Introduced Phase:** D2A-1.
- **Related Metrics:** Re-enable / reactivation rate.
- **Version:** 1.

### today_loaded

- **Purpose:** Measure arrival inside BaseballOS — the bridge from email to product.
- **Definition:** A user successfully arrived at the Today view.
- **Trigger:** `POST /api/product/today-loaded` (owned, anonymous-safe; client beacon on Today-view mount).
- **Owner:** Product ingestion API (`api/product_events.py`).
- **Payload:** none — columns: `user_id` (if authenticated), `anon_id` (optional), `team_id`, `source = digest | direct | organic`.
- **Frontend Activation:** D2A-4 sends this from Today after the dashboard has loaded and team/auth resolution is no longer pending. The client dedupes by `source + team_id` during the browser session and includes the stable pseudonymous `anon_id`.
- **Introduced Phase:** D2A-2.
- **Related Metrics:** Arrival / return-to-product rate; an input to a future Understanding definition.
- **Version:** 1.

### signed_in

- **Purpose:** Bridge anonymous usage to authenticated usage.
- **Definition:** A user authenticated via the magic-link verify flow.
- **Trigger:** `POST /api/auth/verify` success.
- **Owner:** Auth API (`api/auth.py`).
- **Payload:** `{new_user}` — columns: `user_id`, `anon_id` (optional; the pre-auth → user bridge), `source=sign_in`.
- **Frontend Activation:** D2A-4 includes the same stable pseudonymous `anon_id` in the magic-link verify request so pre-auth Today/story observations can be bridged after authentication. The id is generated client-side and contains no PII.
- **Introduced Phase:** D2A-2.
- **Related Metrics:** Sign-in volume, new vs returning, anon→auth bridge coverage.
- **Version:** 1.

### followed_team_changed

- **Purpose:** Observe product preference changes (input to future Team Intelligence).
- **Definition:** A user's followed-team set or primary team actually changed.
- **Trigger:** `POST /api/me/teams`, `DELETE /api/me/teams/<id>`, or `PUT /api/me/primary-team` — only when state changes.
- **Owner:** Authenticated user API (`api/me.py`).
- **Payload:** `{action: follow | unfollow | set_primary, prior_primary_team_id, primary_team_id}` — columns: `user_id`, `team_id`, `source=app`.
- **Introduced Phase:** D2A-2.
- **Related Metrics:** Net follows, primary-team churn, per-team subscriber growth.
- **Version:** 1.

### story_viewed

- **Purpose:** Observe meaningful story consumption — the reader chose to read the full story.
- **Definition (V3-2):** The user intentionally consumed a story by **expanding it** ("Read the full read"). It records the meaningful-consumption fact and **nothing about dwell, scroll, completion, or understanding**.
- **Status / cutover:** The meaning of this event changed across V3 — segment any trend at the cutovers. **≤ V2:** emitted on *render* (a card mounted, seen or not) — it meant *rendered*. **V3-1:** retired from render; on-screen presentation moved to `story_impression`, and `story_viewed` was reserved. **V3-2:** now emitted on the **first expand** of a collapsible story card — it means *read*. The event name, endpoint, payload, and historical rows are unchanged.
- **Trigger:** `POST /api/product/story-viewed` (owned, anonymous-safe), fired on the first expand of a story card.
- **Owner:** Product ingestion API (`api/product_events.py`).
- **Payload:** `{story_id, story_type}` — columns: `user_id` (if authenticated), `anon_id` (optional), `team_id`, `source = surface` (`home | stories | digest_web`, else null/unknown).
- **Frontend Activation:** V3-2. The Stories feed card renders collapsed (headline + team + what everyone saw + what BaseballOS noticed); the blueprint's "Read the full read" control expands it and fires `story_viewed` once per story per surface per browser session (never on collapse, render, or impression). The always-expanded Home flagship and the compact Home watch cards have no expand control, so they emit `story_impression` (and, on the CTA, `story_team_board_opened`) but not `story_viewed`.
- **Introduced Phase:** D2A-3 (reinterpreted V3-1 → V3-2).
- **Related Metrics:** Meaningful story-consumption (expand) volume by type / team / surface. **No** dwell, scroll, or completion is inferred.
- **Version:** 1.

### story_impression

- **Purpose:** Observe how users actually consume BaseballOS intelligence — **on-screen presentation only**. The honest successor to the old render-fired `story_viewed` volume.
- **Definition:** A story card appeared on screen (viewport ≈ 50%+ visible), as opposed to merely rendering into the DOM. It records the presentation fact and **nothing about engagement, dwell, reading, or understanding**.
- **Trigger:** `POST /api/product/story-event` with `event_name=story_impression` (owned, anonymous-safe; client beacon fired from an `IntersectionObserver` when a card crosses ~50% visibility). The endpoint accepts only an allowlisted `event_name` (V3-1: `story_impression` only); an unrecognized or missing name records nothing and still returns 200.
- **Trust-first note:** viewport visibility is used **only** as a client-side trigger. No viewport, scroll, coordinate, dwell, or heatmap data is ever sent or stored — the payload is the same minimal presentation fact as every other story event.
- **Owner:** Product ingestion API (`api/product_events.py`).
- **Payload:** `{story_id, story_type}` — columns: `user_id` (if authenticated), `anon_id` (optional), `team_id`, `source = surface` (`home | stories | digest_web`, else null/unknown).
- **Frontend Activation:** V3-1. `useStoryImpressionObservations` observes each rendered story card and fires once per story per surface per browser session when it reaches the threshold. `IntersectionObserver` is feature-detected; where it is unavailable the tracker no-ops (it never fires a false impression). Cards without a canonical story identity (e.g. the league context card) are never observed. Dedupes by `surface + team_id + story_id + story_type`.
- **Introduced Phase:** V3-1.
- **Related Metrics:** On-screen story-presentation volume by type / team / surface; the like-for-like successor to pre-V3 `story_viewed` volume. **No** engagement, dwell, or completion is inferred.
- **Version:** 1.

### story_team_board_opened

- **Purpose:** Observe the high-intent story → Team Board conversion — the reader acted on a story.
- **Definition:** The user clicked a story's primary CTA to open the Team Board. It records the navigation-intent fact only.
- **Trigger:** `POST /api/product/story-event` with `event_name=story_team_board_opened` (owned, anonymous-safe), fired on the CTA click. Allowlisted on the same generic seam as `story_impression`.
- **Owner:** Product ingestion API (`api/product_events.py`).
- **Payload:** `{story_id, story_type}` — columns: `user_id` (if authenticated), `anon_id` (optional), `team_id`, `source = surface` (`home | stories | digest_web`, else null/unknown).
- **Frontend Activation:** V3-2. Fired from the Stories feed card's "Open the team board" CTA, the Home flagship's "Step inside the … pen" CTA, and the Home watch-card link — each replacing the generic `story_interacted(select)` for Team Board opens. Fires **once per physical click** (NOT deduped per session): each open is a distinct intent signal.
- **Introduced Phase:** V3-2.
- **Related Metrics:** Story → Team Board conversion by type / team / surface. **No** engagement or completion is inferred.
- **Version:** 1.

### story_share_clicked

- **Purpose:** Observe share intent from a story context — the reader chose to share.
- **Definition:** The user activated the Share control on a story surface. It records the share-**intent** fact only — it does **not** assert that a native share or clipboard copy actually completed (that cannot be reliably interpreted).
- **Trigger:** `POST /api/product/story-event` with `event_name=story_share_clicked` (owned, anonymous-safe), fired on the Share button click/tap, before (and independent of) `navigator.share` / clipboard. Allowlisted on the same generic seam as `story_impression`.
- **Share scope:** Today's Share shares the **team page** (`/team/<abbr>`), not a unique story URL. The payload therefore carries `share_target: "team"` so the event is honest about what was shared. (No story-specific permalink system exists; none is introduced here.)
- **Owner:** Product ingestion API (`api/product_events.py`).
- **Payload:** `{story_id, story_type, share_target}` (`share_target` is an owned allowlist — currently only `team`; anything else records as null, never fabricated) — columns: `user_id` (if authenticated), `anon_id` (optional), `team_id`, `source = surface` (`home | stories | digest_web`, else null/unknown).
- **Frontend Activation:** V3-3. Fired from `TeamShareButton`'s click on the Stories feed card and the Home flagship (the only story surfaces that render Share). Fires **once per physical click** (NOT deduped per session): each share click is a distinct intent signal. A Share with no canonical story identity emits nothing (no malformed event).
- **Introduced Phase:** V3-3.
- **Related Metrics:** Story share-intent volume by type / team / surface. **No** share completion or engagement is inferred.
- **Version:** 1.

### story_interacted

- **Purpose:** Observe explicit interaction with a rendered story — **the fact only**.
- **Status (V3-2): legacy / deprecated for Team Board opens.** The Stories feed card selection that emitted `story_interacted(select)` was a Team Board open; V3-2 replaces it with the explicit `story_team_board_opened`, and the frontend no longer emits `story_interacted`. The event name, endpoint (`POST /api/product/story-interacted`), payload, and historical rows are preserved unchanged; the endpoint stays live and anonymous-safe.
- **Definition:** A user intentionally performed an explicit interaction with a rendered story (e.g. selecting / opening / expanding it). It records the interaction fact and **nothing about engagement, interest, completion, or understanding**.
- **Trigger:** `POST /api/product/story-interacted` (owned, anonymous-safe). No longer fired by the client as of V3-2.
- **Owner:** Product ingestion API (`api/product_events.py`).
- **Payload:** `{story_id, story_type, interaction_type}` — columns: `user_id` (if authenticated), `anon_id` (optional), `team_id`, `source = surface` (`home | stories | digest_web`, else null). `interaction_type` is an owned allowlist (`expand | open | select`); unrecognized values are recorded as null, never fabricated.
- **Frontend Activation:** D2A-7 fired this from the Stories feed card selection with `interaction_type = select`, `surface = stories`. **Retired in V3-2** in favour of `story_team_board_opened`.
- **Introduced Phase:** D2A-7.
- **Related Metrics:** Story-interaction volume (legacy). Superseded by `story_team_board_opened`. **No** engagement, dwell, or completion is inferred.
- **Version:** 1.

### V4.0 product-loop analytics events

- **Purpose:** Measure whether users open BaseballOS, inspect bullpen context, use
  trust surfaces, and act on existing share/newsletter/social/team paths.
- **Definition:** Current-surface product-loop observations emitted through the
  owned first-party event log. They are measurement facts only.
- **Trigger:** `POST /api/product/event` with an allowlisted `event_name`.
- **Owner:** Product ingestion API (`api/product_events.py`) and frontend helper
  (`frontend/src/utils/analytics.js`).
- **Payload:** Safe optional properties only: `surface`, `route`, `team_abbrev`,
  `player_id`, `freshness_state`; `source` is stored in the event's source
  column; `team_id` is stored in the existing team column when already available.
- **Privacy note:** The client strips query strings, fragments, email-like text,
  free-form player names, and unknown/future events. Tracking is best-effort and
  fault-isolated; it cannot change a baseball read or user-facing claim.
- **Introduced Phase:** V4.0.
- **Version:** 1.

| Event | Purpose | Trigger location | Properties | Privacy notes |
| --- | --- | --- | --- | --- |
| `app_viewed` | Count route-level app views across the existing shell. | `App.jsx` route observer on route changes. | `surface=app`, `route`, `source=app`. | Path only; no query string or browser payload. |
| `homepage_viewed` | Count Today/home arrivals as the daily read entry point. | `IntelligenceSurfaceView` mount. | `surface=home`, `route=/`, `source=page`. | Anonymous-safe; no slate or user data attached. |
| `bullpen_board_viewed` | Count Bullpen Team Board surface views. | `Bullpen.jsx` when the Team Board tab is active. | `surface=bullpen`, `route=/bullpen`, `source=page`. | Measures product navigation only. |
| `team_surface_viewed` | Count existing team board inspections. | `TonightsBullpenBoard.jsx` when a team is selected. | `surface=bullpen`, `route=/bullpen`, `source=team_board`, `team_abbrev`, `team_id`. | Team context is already visible in the UI. |
| `pitcher_surface_viewed` | Count existing pitcher-detail inspections. | `Bullpen.jsx` and `TonightsBullpenBoard.jsx` when pitcher detail opens. | `surface=bullpen`, `route=/bullpen`, `source`, `team_abbrev`, `team_id`, `player_id`. | Player id only; no names or health claims. |
| `methodology_viewed` | Count visits to explanation/methodology context. | `Methodology.jsx` mount. | `surface=methodology`, `route=/methodology`, `source=page`. | Measures page view only. |
| `trust_surface_viewed` | Count visits to Data & Trust. | `DataTrust.jsx` mount. | `surface=trust`, `route=/trust`, `source=page`. | Measures page view only. |
| `freshness_surface_viewed` | Count visits to the freshness/sync trust section. | `DataTrust.jsx` mount for the existing Freshness & Sync section. | `surface=freshness`, `route=/trust`, `source=trust_page`. | No raw sync payload is sent. |
| `social_outbound_clicked` | Count current footer connect-link intent. | `Footer.jsx` connect icon click. | `surface=footer`, current `route`, `source=footer_x \| footer_instagram \| footer_email`. | No handle, email address, or URL is stored in payload. |
| `newsletter_interest_clicked` | Count existing weekly Bullpen Report mailto interest. | `IntelligenceSurface.jsx` hero secondary CTA click. | `surface=home`, `route=/`, `source=hero_cta`. | Click intent only; no email address or submitted form exists. |
| `team_interest_clicked` | Count existing team-board intent links. | Today Bullpen Picture, Today watch cards, Dashboard landscape rows, Stories cards. | `surface`, `route`, `source`, `team_abbrev`, `team_id`. | Team context is already visible; no advisory claim. |
| `share_intent_clicked` | Count existing team-share intent. | `TeamShareButton.jsx` click, before native share or clipboard. | `surface=share`, current `route`, `source=team_share_button`, `team_abbrev`, `team_id`. | Records intent only; does not claim share completion. |

### digest_delivered

- **Purpose:** Confirm a sent digest reached the recipient — cleans the Return Rate denominator.
- **Definition:** The email provider confirmed a sent digest was delivered to the recipient's mailbox.
- **Trigger:** `POST /api/digest/email-events` (Svix-signature-gated provider webhook; `email.delivered`), correlated to a recent sent delivery for the recipient. Digest-scoped: a provider event with no correlated recent send is ignored.
- **Owner:** Digest API webhook (`api/digest.py`).
- **Payload:** `{provider_message_id}` — columns: `user_id` (resolved by recipient email; the email is **never stored**), `delivery_id` (best-effort: the most recent sent delivery), `team_id`, `source=email_provider`.
- **Introduced Phase:** D2A-7.
- **Related Metrics:** Delivery rate; Return Rate denominator hygiene.
- **Version:** 1.

### digest_bounced

- **Purpose:** Surface undeliverable digests (list health, sender reputation).
- **Definition:** The provider reported a sent digest bounced (undeliverable).
- **Trigger:** `POST /api/digest/email-events` (`email.bounced`), correlated as above.
- **Owner:** Digest API webhook (`api/digest.py`).
- **Payload:** `{provider_message_id, bounce_type}` — columns: `user_id`, `delivery_id`, `team_id`, `source=email_provider`.
- **Introduced Phase:** D2A-7.
- **Related Metrics:** Bounce rate; list health.
- **Version:** 1.

### digest_complaint

- **Purpose:** Surface spam complaints (trust, sender reputation).
- **Definition:** The provider reported a spam complaint against a sent digest.
- **Trigger:** `POST /api/digest/email-events` (`email.complained`), correlated as above.
- **Owner:** Digest API webhook (`api/digest.py`).
- **Payload:** `{provider_message_id}` — columns: `user_id`, `delivery_id`, `team_id`, `source=email_provider`.
- **Introduced Phase:** D2A-7.
- **Related Metrics:** Complaint rate; trust / deliverability.
- **Version:** 1.

> The three deliverability events are provider-backed digest-lifecycle facts. They
> are signature-gated, digest-scoped by correlation to a recent sent delivery, and
> resolve the recipient to a `user_id` without ever storing the email. They never
> change digest behavior or existing metrics.

---

## Reserved (architecture only — intentionally NOT yet defined)

These are reserved so future phases can define them **from observed reality**, not
from invented thresholds. None is implemented:

- **`story_engaged`** — engagement beyond presentation.
- **`feedback_intent_clicked`** — reserved until a public feedback action exists again.
- **`team_follow_started` / `team_follow_completed`** — reserved for Follow My Team.
- **`daily_home_viewed`** — reserved for the future Daily Bullpen Home surface.
- **`what_changed_viewed`** — reserved for the future What Changed Since Yesterday surface.
- **`team_page_viewed`** — reserved for future team pages.
- **`share_card_clicked` / `share_card_downloaded`** — reserved for shareable team cards.
- **`digest_signup_started` / `digest_signup_completed`** — reserved for a real digest signup flow.
- **`correction_submitted`** — reserved for a feedback/correction loop.
- **`pro_waitlist_started` / `pro_waitlist_completed`** — reserved for a pro beta waitlist.
- **Understanding Session** — a derived session concept.
- **Understanding Rate** — a derived KPI.
- **Story taxonomy / `story_category`** — classification beyond the existing `story_type`.
- **Retention engine; User / Team / Story / Trust / Release Intelligence; dashboards.**

Measure first. Define later.

## Change policy

- Adding an event: append a new section here in the same phase as the code change.
- Changing a payload incompatibly: bump that event's `Version` and the row's
  `schema_version`; never rewrite historical rows.
- This catalog and the vocabulary in `backend/services/product_events.py` must
  stay in lockstep.
