# Operational Remediation 1 - Deployment Production Configuration Correction and Health Verification

Remediation date: June 3, 2026

## Remediation Assessment

```text
EXTERNAL_DEPLOYMENT_CONFIG_REQUIRED
```

Repository evidence shows that the backend health endpoint reports production
state correctly when the production configuration is selected locally. The
deployed backend still reports `environment = development` and `debug = true`,
which points to external Render service configuration that must be corrected
outside the repository.

Controlled rollout remains blocked until deployed health verifies:

```text
environment: production
debug: false
```

Operational Verification 1 later verified that deployed health target. The
remaining rollout blockers are now non-configuration evidence gaps.

This remediation does not modify runtime behavior.

## 1. Remediation Purpose

Operational Remediation 1 converts the Operational Review 1 finding into an
actionable production configuration correction plan and health verification
target.

The purpose is to:

- identify which remediation is repository-controlled
- identify which remediation must happen in Render service settings
- define the exact production health target
- retain local production-mode health evidence
- keep Team Operations Bullpen Readiness rollout blocked until deployed health
  is corrected and manually reviewed

## 2. Scope

In scope:

- deployment production configuration guidance
- Render environment-variable requirements
- health endpoint verification target
- local production-mode health verification
- rollout impact documentation
- V2 and V3 governance preservation

Out of scope:

- runtime code changes
- Render dashboard edits from within this repository
- Recommendation Engine V2 contract changes
- Team Operations readiness route changes
- frontend behavior changes
- fatigue formula changes
- ranking behavior
- selection behavior
- prediction behavior
- controlled rollout approval
- full production rollout approval

## 3. Relationship to Operational Review 1

Operational Review 1 concluded:

```text
DEPLOYMENT_CONFIGURATION_INCORRECT
```

Operational Review 1 found that:

- `backend/app.py` selects configuration from `APP_ENV`, defaulting to
  `development`.
- `backend/config.py` maps `development` to `DevelopmentConfig`.
- `DevelopmentConfig.DEBUG = True`.
- `ProductionConfig.DEBUG = False`.
- `ProductionConfig` fails fast unless production secrets and database settings
  are present.
- `/api/health` reports the selected application environment and debug flag.
- deployed `/api/health` reported `environment = development` and
  `debug = true`.

Operational Remediation 1 verifies that repository code already produces the
expected production health response when `APP_ENV=production` and required
production variables are present. The remaining correction is therefore an
external deployment configuration action.

## 4. Root Cause Summary

Supported root cause:

```text
The deployed backend selected the development configuration instead of the production configuration.
```

Most likely operational cause:

```text
APP_ENV is unset, empty, invalid, or set to development in the deployed Render backend environment.
```

The exact Render environment-variable values are not committed in the
repository and cannot be directly inspected from repository evidence.

## 5. Repository-Controlled Remediation Performed

Repository-controlled remediation performed in this phase:

- Created this Operational Remediation 1 record.
- Updated setup guidance with explicit Render production environment-variable
  requirements.
- Updated setup guidance with the exact health endpoint success target.
- Updated project status surfaces to retain the blocked rollout decision.
- Updated Operational Review 1 with the remediation follow-up status.

Repository runtime changes performed:

```text
None.
```

Runtime changes are not required for the immediate remediation because local
production-mode verification confirms the existing application config and
health endpoint behave correctly when production variables are supplied.

## 6. External Deployment-Variable Remediation Required

External Render service settings must be corrected before controlled rollout
can be reopened.

Required action:

1. Open the Render backend service environment settings.
2. Set `APP_ENV=production`.
3. Confirm `SECRET_KEY` is a strong, non-default secret.
4. Confirm `DATABASE_URL` points to the hosted PostgreSQL database.
5. Confirm `ADMIN_API_TOKEN` is set.
6. Confirm the external scheduler secret `BASEBALLOS_ADMIN_API_TOKEN` matches
   the backend `ADMIN_API_TOKEN`.
7. Redeploy or restart the backend service.
8. Verify `GET https://baseballos-api.onrender.com/api/health` reports
   `environment = production` and `debug = false`.
9. Re-run V2 and V3 deployed route smoke checks after the service is healthy.

Do not store secret values in this repository or in retained documentation.

## 7. Required Render Environment Variables

Required backend Render variables:

| Variable | Required value or expectation | Verification |
| --- | --- | --- |
| `APP_ENV` | `production` | `/api/health` reports `environment = production`. |
| `SECRET_KEY` | Strong, unique, non-default secret | App starts in production mode; value is not documented. |
| `DATABASE_URL` | Hosted PostgreSQL connection string | App starts in production mode; database routes remain reachable. |
| `ADMIN_API_TOKEN` | Non-empty admin token | Production startup validation passes and protected write endpoints remain gated. |

Recommended backend Render variables:

| Variable | Recommended value or expectation | Rationale |
| --- | --- | --- |
| `AUTO_SYNC` | `false` or unset | Hosted sync should use the external scheduler rather than an in-process job. |
| `CORS_ORIGINS` | Include any additional deployed frontend origins not already allowed | Keeps hosted frontend access explicit. |
| `MLB_API_BASE` | Omit unless overriding the default MLB Stats API base | The repository default is expected. |

External scheduler requirement:

| Secret | Required value or expectation | Rationale |
| --- | --- | --- |
| `BASEBALLOS_ADMIN_API_TOKEN` | Same value as backend `ADMIN_API_TOKEN` | Allows the scheduled sync workflow to authenticate without exposing the token. |

## 8. Health Endpoint Verification Target

Verification endpoint:

```text
GET https://baseballos-api.onrender.com/api/health
```

Required production health response fields:

```text
status: ok
environment: production
debug: false
```

Any deployed result with `environment = development`, `debug = true`, an
unreachable route, or a startup error is not acceptable controlled-rollout
evidence.

## 9. Local Verification Result

Local production-mode verification was performed with temporary process-level
environment variables:

```text
APP_ENV=production
DATABASE_URL=postgresql://u:p@h/db
SECRET_KEY=strong-value-for-local-verification
ADMIN_API_TOKEN=admin-secret-for-local-verification
AUTO_SYNC=false
```

Local command exercised `create_app()` and `GET /api/health` through Flask's
test client.

Observed local health result:

```text
status: ok
environment: production
debug: false
message: BaseballOS API is live
```

Assessment:

```text
LOCAL_PRODUCTION_HEALTH_TARGET_VERIFIED
```

This supports the conclusion that the repository-controlled health endpoint and
production configuration path are functioning as expected when required
production variables are present.

## 10. Deployment Verification Result If Available

Deployment verification was refreshed against:

```text
GET https://baseballos-api.onrender.com/api/health
```

Observed deployed health result:

```text
status: ok
environment: development
debug: true
message: BaseballOS API is live
```

Deployment verification assessment:

```text
DEPLOYED_PRODUCTION_HEALTH_TARGET_NOT_MET
```

The deployed backend must remain a rollout blocker until Render configuration is
corrected and the health target is reverified.

## Operational Verification 1 Follow-Up

Operational Verification 1 is complete in:

```text
docs/OPERATIONAL_VERIFICATION_1_RENDER_PRODUCTION_HEALTH_EVIDENCE_CAPTURE_AND_ROLLOUT_BLOCKER_REASSESSMENT.md
docs/monitoring/team_operations_bullpen_readiness/OPERATIONAL_VERIFICATION_1_PRODUCTION_HEALTH_ARTIFACT.md
```

Verification conclusion:

```text
DEPLOYMENT_CONFIGURATION_VERIFIED_CORRECT
```

Retained production health evidence:

```text
GET https://baseballos-api.onrender.com/api/health
status: ok
environment: production
debug: false
```

Deployment-configuration blocker reassessment:

```text
Should deployment configuration remain a rollout blocker?
NO
```

Controlled rollout is still not approved by Operational Verification 1.
Remaining evidence must cover rendered Dashboard review, mobile/responsive
review, accessibility smoke review, explicit maintainer review, and protected
write/admin endpoint gating confirmation.

## 11. V2 Impact Review

Operational Remediation 1 does not modify the certified Recommendation Engine
V2 contract, ranking metadata, selection metadata, fail-closed behavior,
freshness behavior, trust behavior, or Dashboard V2 rendering behavior.

V2 production impact:

- No V2 runtime behavior was changed.
- V2 deployed trust assumptions remain weakened while the backend reports
  development/debug state.
- V2 read-route governance evidence from Operational Review 1 remains
  unchanged.
- Protected write/admin endpoint behavior should be rechecked after the Render
  service is redeployed with `APP_ENV=production`.

## 12. V3 Impact Review

Operational Remediation 1 does not modify Team Operations Bullpen Readiness
domain logic, internal route behavior, frontend client normalization, Dashboard
UI behavior, or certification status.

V3 impact:

- Team Operations Bullpen Readiness remains internal, non-production, and
  uncertified for public rollout.
- Controlled rollout remains blocked.
- The V3 readiness route must not proceed to rollout review until deployed
  backend health reports production/debug-safe state.
- Manual browser, mobile, accessibility, and maintainer evidence remain
  required after deployment health is corrected.

## 13. Rollout Impact Review

Rollout impact decision:

```text
CONTROLLED_ROLLOUT_REMAINS_BLOCKED
```

Rationale:

- Current deployed health still reports `environment = development`.
- Current deployed health still reports `debug = true`.
- Production-safe deployment evidence is a prerequisite for controlled rollout.
- This phase does not perform external Render configuration changes.
- This phase does not retain successful post-remediation deployment evidence.
- Manual rendered Dashboard, mobile, accessibility, and maintainer evidence
  remain pending.

## 14. Remaining Risks

Remaining blocking risks:

- Render backend service configuration still needs to be corrected externally.
- Deployed `/api/health` must be reverified after redeploy.
- If production startup fails after `APP_ENV=production`, one or more required
  production variables may still be missing or invalid.
- Protected write/admin endpoint gating still needs post-remediation deployed
  verification.
- Manual browser, mobile, accessibility, and maintainer evidence remain
  pending.

Remaining non-blocking risks:

- The repository has no committed Render deployment manifest, so Render service
  settings remain externally managed.
- Future runtime hardening could reject invalid `APP_ENV` values instead of
  falling back to development, but that is outside this remediation scope.
- Future health metadata could expose a non-sensitive production requirement
  checklist, but that would require a separate runtime authorization.

## 15. Recommended Next Milestone

Recommended next milestone:

```text
Operational Verification 1 - Render Production Health Evidence Capture and Rollout Blocker Reassessment
```

That milestone should:

- apply the required Render environment-variable corrections
- redeploy or restart the backend service
- retain deployed `/api/health` evidence showing `environment = production` and
  `debug = false`
- recheck protected write/admin endpoint gating without mutating production data
- recheck V2 deployed governance metadata
- recheck V3 internal route metadata and prohibited-query refusal
- decide whether V3 deployment manual review can resume

## Governance Confirmation

Operational Remediation 1 preserves:

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
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-operational-remediation-1
Result: 299 passed, 0 failed.

cd frontend
npm test
Result: 101 passed, 0 failed.

git diff --check
Result: Passed with line-ending warnings only.

git diff --cached --check
Result: Passed.
```

Root `npm test` is not required when no root `package.json` exists.
