# Operational Review 1 - Deployment Configuration and Environment Classification Investigation

Review date: June 3, 2026

## Investigation Conclusion

```text
DEPLOYMENT_CONFIGURATION_INCORRECT
```

Rollout impact decision:

```text
Should Team Operations Bullpen Readiness rollout remain blocked?
YES
```

The deployed backend health endpoint currently reports `environment =
development` and `debug = true`. Repository evidence shows the health endpoint
reports the Flask application configuration selected by `APP_ENV`, and
`DevelopmentConfig` sets `DEBUG = True`. The deployed service is therefore not
providing acceptable production-classification evidence for controlled rollout.

This review does not modify runtime behavior.

## 1. Investigation Purpose

Operational Review 1 investigates the deployment-environment finding retained
during V3 Phase 17:

```text
environment: development
debug: true
```

The purpose is to determine whether this indicates a real deployment
configuration issue, a health endpoint reporting defect, an environment
classification logic defect, or insufficient evidence.

## 2. Scope

In scope:

- backend configuration selection
- backend health endpoint behavior
- debug flag handling
- production/development classification logic
- deployment documentation and assumptions
- deployed endpoint observation
- V2 Recommendation Engine impact
- V3 Team Operations Bullpen Readiness impact
- rollout readiness impact
- remediation planning

Out of scope:

- runtime fixes
- Render service configuration changes
- API behavior changes
- Recommendation Engine V2 contract changes
- Team Operations readiness route changes
- frontend behavior changes
- fatigue formula changes
- ranking behavior
- selection behavior
- prediction behavior

## 3. Discovery Summary

V3 Phase 17 retained deployed backend health evidence:

```text
GET https://baseballos-api.onrender.com/api/health
HTTP status: 200
status: ok
environment: development
debug: true
```

Operational Review 1 refreshed the deployed health observation and reproduced
the same finding:

```text
debug: true
environment: development
status: ok
```

The deployed V2 and V3 routes remain reachable, but reachability does not prove
production-safe environment classification.

## 4. Deployment Architecture Review

The documented hosted architecture is:

| Layer | Expected host |
| --- | --- |
| Frontend | Vercel static React build |
| Backend | Render Flask service with gunicorn |
| Database | Managed PostgreSQL |
| Scheduled sync | GitHub Actions |
| Data source | MLB Stats API |

Repository evidence:

- `README.md` documents the frontend as Vercel and backend as Render.
- `docs/SETUP.md` documents hosted backend expectations for `APP_ENV`,
  `SECRET_KEY`, `DATABASE_URL`, and `ADMIN_API_TOKEN`.
- `.github/workflows/baseballos-sync.yml` documents the external daily sync
  model and expects `BASEBALLOS_SYNC_URL` to point at the hosted backend.
- No committed `render.yaml`, `Procfile`, Dockerfile, or equivalent backend
  deployment manifest was found in the repository.

Because Render service environment variables are not committed in this
repository, this review can prove the expected application behavior and the
observed deployed behavior, but it cannot directly inspect the Render dashboard
configuration.

## 5. Environment Classification Review

Repository source:

```text
backend/app.py
```

The app chooses configuration with:

```text
config_name = os.environ.get('APP_ENV', 'development')
```

If the value is not one of the configured keys, the app falls back to:

```text
development
```

Repository source:

```text
backend/config.py
```

Configured environments:

```text
development -> DevelopmentConfig
production -> ProductionConfig
default -> DevelopmentConfig
```

Review result:

- If `APP_ENV=production`, the app should select `ProductionConfig`.
- If `APP_ENV` is unset, empty, or invalid, the app selects development.
- The deployed health endpoint reports `environment: development`, which means
  the deployed Flask app selected the development configuration.

## 6. Debug Flag Review

Repository source:

```text
backend/config.py
```

Debug configuration:

```text
DevelopmentConfig.DEBUG = True
ProductionConfig.DEBUG = False
```

Repository source:

```text
backend/app.py
```

The health endpoint returns:

```text
debug: bool(app.config.get('DEBUG', False))
```

Review result:

- `debug: true` is consistent with `DevelopmentConfig`.
- The health endpoint is not inventing the debug value; it reflects Flask
  application config.
- This supports a configuration issue more strongly than a health reporting
  issue.

## 7. Health Endpoint Review

Repository source:

```text
backend/app.py
```

Health endpoint response:

```text
{
  "status": "ok",
  "environment": app.config.get("APP_ENV", "development"),
  "debug": bool(app.config.get("DEBUG", False)),
  "message": "BaseballOS API is live"
}
```

Review result:

- The health endpoint is intentionally designed to expose environment and debug
  state.
- `docs/SETUP.md` explicitly says `/api/health` should confirm production by
  returning `production` with debug `false`.
- Current deployed output does not satisfy that expectation.

## 8. Configuration Source Review

Repository source:

```text
backend/config.py
```

The app loads environment variables through `python-dotenv`, then reads:

- `APP_ENV`
- `SECRET_KEY`
- `DATABASE_URL`
- `ADMIN_API_TOKEN`
- `MLB_API_BASE`
- `AUTO_SYNC`
- `CORS_ORIGINS`

Production initialization in `ProductionConfig.init_app` fails fast unless:

- `SECRET_KEY` is non-default.
- `DATABASE_URL` is set.
- `ADMIN_API_TOKEN` is set.

Review result:

- Production mode has explicit safety checks.
- Development mode does not run those production checks.
- A deployed service running development mode bypasses production-startup
  validation.

## 9. Environment Variable Review

Committed expected production variables:

| Variable | Production expectation |
| --- | --- |
| `APP_ENV` | `production` |
| `SECRET_KEY` | strong non-default value |
| `DATABASE_URL` | hosted PostgreSQL URL |
| `ADMIN_API_TOKEN` | required for protected write/admin endpoints |
| `CORS_ORIGINS` | optional additional frontend origins |
| `AUTO_SYNC` | optional; external scheduler preferred |

Evidence available:

- `backend/.env.example` defaults `APP_ENV=development` for local setup.
- `docs/SETUP.md` says hosted backend environments should set
  `APP_ENV=production`.
- The deployed health endpoint reports development mode.

Evidence unavailable:

- Render dashboard environment-variable values.
- Render service start command.
- Render runtime logs.

Review result:

The exact Render setting that caused development mode cannot be proven from the
repository alone. The deployed application state is still incorrect relative to
documented production expectations.

## 10. Production vs Development Behavior Review

Production behavior expected by repository code:

- `APP_ENV=production`
- `DEBUG=False`
- fail-fast startup validation for required production secrets
- protected write/admin endpoints require `ADMIN_API_TOKEN`

Development behavior expected by repository code:

- `APP_ENV=development`
- `DEBUG=True`
- local defaults are allowed
- protected write/admin endpoints may be allowed without a token when no token
  is configured

Operational concern:

If the deployed backend is running development mode, the backend may be using
development-class safety assumptions even though it is internet-reachable.

This review did not test protected write endpoints without a token because the
phase is diagnostic and must avoid mutating deployed state.

## 11. V2 Impact Assessment

Observed deployed V2 evidence:

```text
GET https://baseballos-api.onrender.com/api/recommendations/v2/bullpen-state?limit=1
HTTP status: 200
ranking_applied: false
selection_made: false
trust_metadata.governance_state: compliant
freshness.overall_sync_status: success
freshness.overall_sync_data_through: 2026-06-03
```

Assessment:

- V2 read behavior remains reachable.
- V2 governance metadata remains present.
- V2 still reports `ranking_applied = false` and `selection_made = false`.
- No V2 recommendation, ranking, selection, or prediction regression was
  observed in the deployed read endpoint.

Risk:

- Production trust assumptions are weakened while the service reports
  development/debug mode.
- Protected operational write endpoints require separate confirmation after
  configuration remediation.

## 12. V3 Impact Assessment

Observed deployed V3 readiness evidence:

```text
GET https://baseballos-api.onrender.com/api/team-operations/bullpen-readiness
HTTP status: 200
contract_state: degraded
readiness.status_code: data_limited
route_metadata.exposure: internal
route_metadata.production_status: non_production
route_metadata.certification_status: uncertified
route_metadata.public_certified: false
ranking_applied: false
selection_made: false
```

Observed deployed V3 refusal evidence:

```text
GET https://baseballos-api.onrender.com/api/team-operations/bullpen-readiness?best=true
HTTP status: 400
contract_state: refused
refusal.reason: forbidden_request_parameter
fail_closed.failed_closed: true
fail_closed.critical_failure: true
ranking_applied: false
selection_made: false
```

Assessment:

- V3 route behavior remains governed.
- V3 route metadata remains internal, non-production, and uncertified.
- V3 prohibited query intent still fails closed.
- V3 rollout remains blocked because the deployment classification is unsafe
  for rollout evidence.

## 13. Rollout Impact Assessment

Question:

```text
Should Team Operations Bullpen Readiness rollout remain blocked?
```

Answer:

```text
YES
```

Rationale:

- Controlled rollout requires production-safe deployment evidence.
- The deployed backend reports development mode and debug enabled.
- The deployment environment may be bypassing production safety checks.
- Manual rendered Dashboard, mobile, accessibility, and maintainer evidence
  remain pending from Phase 17.
- This review does not authorize runtime remediation or rollout approval.

## 14. Root Cause Analysis

Supported root cause:

```text
The deployed backend selected the development configuration instead of the production configuration.
```

Evidence:

- `backend/app.py` selects `APP_ENV`, defaulting to `development`.
- `backend/config.py` maps `development` to `DevelopmentConfig`.
- `DevelopmentConfig.DEBUG = True`.
- `/api/health` returns the selected app environment and debug flag.
- The deployed `/api/health` endpoint reports `environment: development` and
  `debug: true`.

Most likely operational cause:

```text
APP_ENV is unset, empty, invalid, or set to development in the deployed backend environment.
```

This exact setting cannot be proven from repository evidence because Render
environment variables are not committed.

Rejected conclusions:

- `DEPLOYMENT_CONFIGURATION_CORRECT_HEALTH_ENDPOINT_MISREPORTING` is not
  supported because the health endpoint directly reflects app config.
- `ENVIRONMENT_CLASSIFICATION_LOGIC_INCORRECT` is not the best-supported
  conclusion because the classification behavior matches the code and docs:
  production requires `APP_ENV=production`.
- `UNABLE_TO_DETERMINE_FROM_AVAILABLE_EVIDENCE` is too weak because deployed
  runtime evidence plus source code is enough to show the deployed app selected
  development config.

## 15. Severity Assessment

Severity:

```text
HIGH_OPERATIONAL_RISK
```

Reason:

- The backend is internet-reachable.
- It reports development mode.
- It reports debug enabled.
- Production startup validation may not be running.
- Controlled rollout cannot rely on this deployment as production-safe.

Current impact:

- No read-route governance regression was observed.
- No recommendation, ranking, selection, or prediction behavior was introduced.
- Full production and controlled rollout approval should remain blocked until
  deployment configuration is corrected and reverified.

## 16. Corrective Options

Option A - Correct deployed environment variables:

- Set `APP_ENV=production` in Render.
- Confirm `SECRET_KEY` is strong and non-default.
- Confirm `DATABASE_URL` points to hosted PostgreSQL.
- Confirm `ADMIN_API_TOKEN` is set.
- Redeploy.
- Verify `/api/health` reports `environment: production` and `debug: false`.

Option B - Add stricter environment validation in a later runtime phase:

- Refuse unknown `APP_ENV` values instead of falling back to development.
- Consider a production-host guard that fails if known hosted environment
  variables exist while `APP_ENV` is not production.
- Add tests for invalid environment classification.

Option C - Harden health output in a later runtime phase:

- Add explicit `configuration_state` metadata.
- Add `production_requirements_checked` metadata.
- Avoid exposing sensitive details.

Option D - Add a deployment manifest:

- Add a committed Render deployment guide or manifest if the project decides to
  manage service config from the repository.

## 17. Recommended Remediation

Recommended immediate remediation:

```text
Correct the deployed backend configuration so APP_ENV=production and required production variables are present, then redeploy and capture health evidence.
```

Required verification after remediation:

- `/api/health` returns `environment: production`.
- `/api/health` returns `debug: false`.
- V2 bullpen-state endpoint still passes governance checks.
- V3 readiness route still returns internal, non-production, uncertified
  metadata until rollout approval.
- V3 prohibited-query route still fails closed.
- Backend and frontend test suites pass.
- Protected operational write endpoints are confirmed not anonymously exposed.

Recommended later hardening:

- Add a runtime change to reject invalid `APP_ENV` values instead of silently
  falling back to development.
- Add deployment configuration tests or smoke-review checklist items for
  hosted environment classification.
- Add a retained post-remediation monitoring artifact.

## 18. Recommended Priority

Recommended priority:

```text
P0_BEFORE_CONTROLLED_ROLLOUT
```

The issue should be remediated before any controlled rollout decision is
reopened. It is not a reason to change V2/V3 governance logic, but it is a
deployment readiness blocker.

## 19. Recommended Next Milestone

Recommended next milestone:

```text
Operational Remediation 1 - Deployment Production Configuration Correction and Health Verification
```

That milestone should correct Render environment classification, redeploy,
retain `/api/health` evidence, verify protected write/admin endpoint behavior,
rerun backend and frontend validation, and then decide whether V3 Phase 18
manual browser review can proceed.

## Operational Remediation 1 Follow-Up

Operational Remediation 1 is complete in:

```text
docs/OPERATIONAL_REMEDIATION_1_DEPLOYMENT_PRODUCTION_CONFIG_HEALTH_VERIFICATION.md
```

Remediation assessment:

```text
EXTERNAL_DEPLOYMENT_CONFIG_REQUIRED
```

The follow-up confirms the repository production configuration path returns
`environment = production` and `debug = false` when required production
variables are supplied locally. The deployed backend still reports
`environment = development` and `debug = true`, so Render environment variables
must be corrected externally before controlled rollout can be reopened.

## Governance Confirmation

Operational Review 1 preserves:

```text
ranking_applied === false
selection_made === false
```

It does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

No governance changes are authorized.

## Validation Record

Required validation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-operational-review-1
Result: 299 passed, 0 failed.

cd frontend
npm test
Result: 101 passed, 0 failed.

git diff --check
Result: Passed with line-ending warnings only.

git diff --cached --check
Result: Passed after targeted operational review documentation staging.
```

Root `npm test` is not required when no root `package.json` exists.
