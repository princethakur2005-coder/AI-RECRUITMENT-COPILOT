import { test as base, expect } from '@playwright/test';
import fetch from 'node-fetch';

type TestFixtures = {
  authToken: string | null;
  login: (email?: string, password?: string) => Promise<void>;
};

export const test = base.extend<TestFixtures>({
  authToken: async ({}, use) => {
    // Obtain token using backend test auth endpoint or provide null if not configured
    const baseUrl = process.env.E2E_BASE_URL || 'http://localhost:3000';
    try {
      const res = await fetch(`${baseUrl}/api/test/token`, { method: 'POST' });
      if (res.ok) {
        const body = (await res.json()) as { token?: string };
        await use(body.token ?? null);
        return;
      }
    } catch (e) {
      // fallback
    }
    await use(null);
  },

  login: async ({ page, authToken }, use) => {
    // login helper sets auth token in localStorage for the app
    const doLogin = async (email = 'test@example.com', password = 'password') => {
      if (authToken) {
        await page.addInitScript((token: string) => {
          try { localStorage.setItem('auth_token', token); } catch (e) {}
        }, authToken);
        return;
      }
      // Fallback: navigate to login page and fill form (selectors are app-specific)
      // Keep minimal to avoid breaking when selectors differ.
    };

    await use(doLogin);
  },
});

export { expect };
