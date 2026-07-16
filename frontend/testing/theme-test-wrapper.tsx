import React from 'react'
import { themeProvider } from '../lib/theme-provider'

export function ThemeWrapper({ children, theme = 'light' }: { children: React.ReactNode; theme?: 'light' | 'dark' }) {
  try {
    themeProvider.setTheme(theme)
  } catch (e) {
    // ignore in non-DOM environments
  }
  return <>{children}</>
}
