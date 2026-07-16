import React from 'react'

/**
 * Simple auth test wrapper that injects an Authorization header into `window.fetch` calls
 * or sets localStorage for token-based clients. This is intentionally minimal; adapt to
 * your auth strategy (context/provider) as needed.
 */
export function withAuthToken(token: string | null) {
  return function AuthWrapper({ children }: { children: React.ReactNode }) {
    if (typeof window !== 'undefined') {
      if (token) {
        window.localStorage.setItem('auth_token', token)
      } else {
        window.localStorage.removeItem('auth_token')
      }
    }
    return <>{children}</>
  }
}
