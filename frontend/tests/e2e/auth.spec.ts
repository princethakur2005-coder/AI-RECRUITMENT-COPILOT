import { expect } from '@playwright/test';
import { test } from './fixtures';
import { LoginPage } from './pages/LoginPage';

test.describe('Authentication', () => {
  test('should authenticate the user and open the recruiter dashboard', async ({ page, login }) => {
    const loginPage = new LoginPage(page);

    await login();
    await loginPage.goto('/dashboard');

    await expect(page.locator('h1', { hasText: 'Recruiter Dashboard' })).toBeVisible();
    await expect(page.locator('button', { hasText: 'Refresh' })).toBeVisible();
  });
});
