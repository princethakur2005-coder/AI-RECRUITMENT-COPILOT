import type { FullConfig } from '@playwright/test';

export default async function globalTeardown(config: FullConfig) {
  // Placeholder for global teardown actions such as cleaning seeded test data.
  // Implement as-needed for CI environments.
}
