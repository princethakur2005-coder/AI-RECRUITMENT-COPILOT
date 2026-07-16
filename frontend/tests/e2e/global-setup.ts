import type { FullConfig } from '@playwright/test';

export default async function globalSetup(config: FullConfig) {
  // Environment-aware setup: ensure backend is reachable and optionally seed test data.
  const base = process.env.E2E_BASE_URL || 'http://localhost:3000';
  try {
    const res = await fetch(`${base}/health`);
    if (!res.ok) {
      console.warn('E2E global-setup: backend health check returned', res.status);
    }
  } catch (err) {
    console.warn('E2E global-setup: could not reach backend at', base);
  }

  // Optionally perform additional bootstrapping like creating test users via API endpoints
  // Keep this idempotent and lightweight to support parallel workers.
}
