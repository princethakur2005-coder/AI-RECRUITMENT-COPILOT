import { HttpResponse, http } from 'msw'

// Basic placeholder handlers for API mocking in tests.
export const handlers = [
  http.get('/api/health', () => {
    return new HttpResponse(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  }),
]
