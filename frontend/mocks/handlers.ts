import { rest } from 'msw'

// Basic placeholder handlers for API mocking in tests.
export const handlers = [
  rest.get('/api/health', (req, res, ctx) => {
    return res(ctx.status(200), ctx.json({ status: 'ok' }))
  }),
]
