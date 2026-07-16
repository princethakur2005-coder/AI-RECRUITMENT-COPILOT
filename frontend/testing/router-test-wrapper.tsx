import React from 'react'
import { MemoryRouter } from 'react-router-dom'

export function RouterWrapper({ children, route = '/' }: { children: React.ReactNode; route?: string }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}
