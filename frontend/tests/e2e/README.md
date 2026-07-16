Playwright E2E test scaffolding

Files in this folder provide a Playwright-based E2E testing foundation:

- `playwright.config.ts` — top-level Playwright config with retries, traces, videos, and reporters.
- `tests/e2e/global-setup.ts` — environment-aware global setup.
- `tests/e2e/global-teardown.ts` — global teardown placeholder.
- `tests/e2e/fixtures.ts` — shared fixtures including `authToken` and `login` helper.
- `tests/e2e/pages/` — Page Object Model (POM) foundation.
- `tests/e2e/helpers/` — helpers such as `obtainAuthToken`.

Configure `E2E_BASE_URL` environment variable in CI to point to the deployed app.
