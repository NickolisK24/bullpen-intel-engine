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

- **Purpose:** Observe how users consume BaseballOS intelligence — **presentation only**.
- **Definition:** A BaseballOS story was successfully presented to the user. It records the presentation fact and **nothing about engagement, understanding, or completion**.
- **Status (V3-1):** **No longer emitted on render.** Through V2 this fired when a story card mounted, whether or not it ever appeared on screen — i.e. it meant *rendered*, not *viewed*. From V3-1 the in-product surfaces emit `story_impression` (below) for the honest on-screen-presentation fact, and `story_viewed` is **reserved** for a future meaningful-consumption trigger (e.g. expand). The event name, endpoint (`POST /api/product/story-viewed`), payload, and all historical rows are unchanged; pre-V3-1 rows carry the *rendered* meaning, so segment any trend at the V3-1 cutover.
- **Trigger:** `POST /api/product/story-viewed` (owned, anonymous-safe). Retired from the render path in V3-1; the endpoint stays live for the legacy contract and the future consumption trigger.
- **Owner:** Product ingestion API (`api/product_events.py`).
- **Payload:** `{story_id, story_type}` — columns: `user_id` (if authenticated), `anon_id` (optional), `team_id`, `source = surface` (`home | stories | digest_web`, else null/unknown).
- **Frontend Activation:** D2A-4 originally sent this on render for canonical story cards/flagships. **Retired from render in V3-1** in favour of `story_impression`; see that event for the current on-screen beacon.
- **Introduced Phase:** D2A-3.
- **Related Metrics:** Story-presentation volume by type / team / surface (pre-V3-1; succeeded by `story_impression`). **No** engagement, dwell, or completion is inferred.
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

### story_interacted

- **Purpose:** Observe explicit interaction with a rendered story — **the fact only**.
- **Definition:** A user intentionally performed an explicit interaction with a rendered story (e.g. selecting / opening / expanding it). It records the interaction fact and **nothing about engagement, interest, completion, or understanding**.
- **Trigger:** `POST /api/product/story-interacted` (owned, anonymous-safe; client beacon on an existing story UI action).
- **Owner:** Product ingestion API (`api/product_events.py`).
- **Payload:** `{story_id, story_type, interaction_type}` — columns: `user_id` (if authenticated), `anon_id` (optional), `team_id`, `source = surface` (`home | stories | digest_web`, else null). `interaction_type` is an owned allowlist (`expand | open | select`); unrecognized values are recorded as null, never fabricated.
- **Frontend Activation:** D2A-7 fires this from the existing Stories feed card selection (the click-through link) with `interaction_type = select`, `surface = stories`. The client dedupes by `surface + team_id + story_id + story_type + interaction_type` during the browser session.
- **Introduced Phase:** D2A-7.
- **Related Metrics:** Story-interaction volume by type / team / surface; a future input to defining Product Understanding. **No** engagement, dwell, or completion is inferred.
- **Version:** 1.

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
