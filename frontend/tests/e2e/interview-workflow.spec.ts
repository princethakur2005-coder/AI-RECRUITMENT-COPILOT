import { expect } from '@playwright/test';
import { test } from './fixtures';
import { LoginPage } from './pages/LoginPage';

test.describe('Interview Workflow', () => {
  test('should load interview management workspace', async ({ page, login }) => {
    const loginPage = new LoginPage(page);

    await login();
    await loginPage.goto('/interview-management');

    await expect(page.locator('h1', { hasText: 'Interview Management' })).toBeVisible();
    await expect(page.locator('button', { hasText: 'Refresh' })).toBeVisible();
    await expect(page.locator('button', { hasText: 'New Interview' })).toBeVisible();
  });
});
