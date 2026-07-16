import { expect } from '@playwright/test';
import { test } from './fixtures';
import { LoginPage } from './pages/LoginPage';

test.describe('AI Workflow', () => {
  test('should load analytics reports page', async ({ page, login }) => {
    const loginPage = new LoginPage(page);

    await login();
    await loginPage.goto('/analytics-reports');

    await expect(page.locator('h1', { hasText: 'Analytics & Reports' })).toBeVisible();
  });
});
