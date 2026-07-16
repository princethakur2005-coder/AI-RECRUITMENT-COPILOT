import { expect } from '@playwright/test';
import { test } from './fixtures';
import { LoginPage } from './pages/LoginPage';

test.describe('Dashboard', () => {
  test('should render the recruiter dashboard page', async ({ page, login }) => {
    const loginPage = new LoginPage(page);

    await login();
    await loginPage.goto('/dashboard');

    await expect(page.locator('h1', { hasText: 'Recruiter Dashboard' })).toBeVisible();
    await expect(page.locator('text=Total Candidates')).toBeVisible();
    await expect(page.locator('text=Open Jobs')).toBeVisible();
  });
});
