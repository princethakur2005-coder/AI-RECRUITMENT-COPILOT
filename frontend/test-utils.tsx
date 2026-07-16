import React, { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { themeProvider } from './lib/theme-provider'

type RenderOptions = {
  route?: string
}

export function ThemeTestWrapper({ children }: { children: React.ReactNode }) {
  // Ensure theme provider uses a deterministic storage key for tests
  try {
    themeProvider.setTheme('light')
  } catch (e) {
    // ignore DOM-less environments
  }
  return <>{children}</>
}

export function RouterTestWrapper({ children, route = '/' }: { children: React.ReactNode; route?: string }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: RenderOptions = {}) {
  return render(
    <ThemeTestWrapper>
      <RouterTestWrapper route={route}>{ui}</RouterTestWrapper>
    </ThemeTestWrapper>
  )
}

export * from '@testing-library/react'
