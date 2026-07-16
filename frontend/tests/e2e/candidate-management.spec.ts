import { expect } from '@playwright/test';
import { test } from './fixtures';
import { LoginPage } from './pages/LoginPage';

test.describe('Candidate Management', () => {
  test('should load candidate management page', async ({ page, login }) => {
    const loginPage = new LoginPage(page);

    await login();
    await loginPage.goto('/candidate-management');

    await expect(page.locator('h1', { hasText: 'Candidate Management' })).toBeVisible();
    await expect(page.locator('text=Manage pipeline, evaluations, recommendations, and candidate actions')).toBeVisible();
  });
});
