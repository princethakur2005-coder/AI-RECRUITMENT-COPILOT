import '@testing-library/jest-dom/extend-expect'

// Start MSW server for tests
import { server } from './mocks/server'

// Establish API mocking before all tests.
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
// Reset handlers after each test so tests are isolated
afterEach(() => server.resetHandlers())
// Clean up after the tests are finished.
afterAll(() => server.close())
