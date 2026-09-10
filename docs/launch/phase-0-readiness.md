# Phase 0 Launch Readiness

## Usage measurement

- The application does not include usage-tracking instrumentation.
- Do not add client or server usage tracking without a separately approved product and privacy plan.

## Search Console

- No real Google Search Console verification token is present in repo config, so Phase 0 does not add verification metadata.
- After `https://baseballos.app` is deployed, add the site in Google Search Console as either a Domain property or URL-prefix property.
- Preferred verification path: use DNS verification for the domain through the domain host. If HTML tag verification is chosen instead, add the real token only after it is issued by Search Console.
- `frontend/public/robots.txt` exists. A sitemap is not currently generated in `frontend/public`; submit a sitemap only after a real sitemap file or generated sitemap route exists.
- Do not commit placeholder verification tokens or example ownership tags.

## UTM Rules

Use UTM parameters on public launch, social, newsletter, and creator-outreach links to keep distributed links consistently labeled if campaign measurement is introduced later.

Standard fields:

- `utm_source`: the channel, such as `x`, `linkedin`, `instagram`, `reddit`, `newsletter`, or `outreach`.
- `utm_medium`: the distribution type, such as `social`, `email`, `community`, or `dm`.
- `utm_campaign`: use `phase0_launch` for public launch links and `weekly_bullpen_notes` for recurring weekly notes.
- `utm_content`: a short descriptor for the specific post or link placement, such as `pinned_intro`, `weekend_watch`, `team_card`, or `methodology`.

Examples:

| Channel | Example URL |
| --- | --- |
| X/Twitter | `https://baseballos.app/?utm_source=x&utm_medium=social&utm_campaign=phase0_launch&utm_content=pinned_intro` |
| LinkedIn | `https://baseballos.app/methodology?utm_source=linkedin&utm_medium=social&utm_campaign=phase0_launch&utm_content=methodology` |
| Instagram | `https://baseballos.app/?utm_source=instagram&utm_medium=social&utm_campaign=phase0_launch&utm_content=profile_link` |
| Reddit | `https://baseballos.app/trust?utm_source=reddit&utm_medium=community&utm_campaign=phase0_launch&utm_content=data_trust` |
| Newsletter | `https://baseballos.app/?utm_source=newsletter&utm_medium=email&utm_campaign=weekly_bullpen_notes&utm_content=weekend_watch` |
| Direct creator outreach | `https://baseballos.app/team/TOR?utm_source=outreach&utm_medium=dm&utm_campaign=phase0_launch&utm_content=team_card` |

Rules:

- Keep canonical URLs clean in metadata; add UTM parameters only to distributed links.
- Use lowercase values with underscores.
- Use one `utm_content` value per distinct post, card, or placement.
- Do not use UTM parameters to imply a paid campaign, newsletter provider, user account, or follow feature.
- If a shared link already has query parameters, append UTM parameters with `&` instead of starting a second query string.

## Weekly Notes Interest

- The homepage uses a mailto-based interest CTA for weekly bullpen notes.
- The CTA asks interested users to include a favorite team, but it does not claim that a full newsletter system exists.
- A future provider integration should define consent copy, unsubscribe behavior, storage ownership, and team preference fields before replacing the placeholder.

## Public Boundaries

- BaseballOS is positioned as descriptive MLB bullpen intelligence from public data.
- Public copy should not claim manager intent, private medical availability, final game-day decisions, unsupported action guidance, or future outcomes.
- Injury and injured-list context should be described only as public roster/injury signals unless the page shows a more specific modeled source.
