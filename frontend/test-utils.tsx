import React, { ReactElement } from 'react'

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

export function RouterTestWrapper({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}

export function renderWithProviders(ui: ReactElement): ReactElement {
  return React.createElement(
    ThemeTestWrapper,
    null,
    React.createElement(RouterTestWrapper, null, ui),
  )
}
