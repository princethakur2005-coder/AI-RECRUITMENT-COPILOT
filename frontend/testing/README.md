Frontend testing utilities

Files in this folder provide lightweight test wrappers and helpers for component tests:

- `theme-test-wrapper.tsx` — sets `themeProvider` for tests.
- `router-test-wrapper.tsx` — memory router wrapper.
- `auth-test-wrapper.tsx` — convenience wrapper to set auth token in `localStorage`.
- `api-mock.ts` — small helpers for MSW mock responses.

Use `test-utils.tsx` root-level helper to render components with providers.
