# Foundation 3A production bootstrap workflow fix

## Decision

The read-only Canonical Season Bullpen Aggregation Audit runs with `APP_ENV=production`, so it must provide every production bootstrap secret required by `ProductionConfig`, including `ADMIN_API_TOKEN`.

The workflow now maps `ADMIN_API_TOKEN` from the existing `BASEBALLOS_ADMIN_API_TOKEN` repository secret and validates that `DATABASE_URL`, `SECRET_KEY`, and `ADMIN_API_TOKEN` are all present before importing the application.

The validation error remains generic and never prints secret names or values. This correction changes workflow bootstrap only; it does not change aggregation logic, official validation logic, database behavior, public surfaces, Team State, Share Cards, rankings, or Foundation 3B.
