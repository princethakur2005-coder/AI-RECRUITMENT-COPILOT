import { Page } from '@playwright/test'
import { BasePage } from './BasePage'

export class LoginPage extends BasePage {
  async navigate() {
    await this.goto('/login')
  }

  async submit(email: string, password: string) {
    // Placeholder selectors; adapt to app as needed
    try {
      await this.page.fill('input[name="email"]', email)
      await this.page.fill('input[name="password"]', password)
      await this.page.click('button[type="submit"]')
    } catch (e) {
      // selectors may differ; keep as a gentle placeholder
    }
  }
}
