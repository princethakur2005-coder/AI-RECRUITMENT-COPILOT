import fetch from 'node-fetch'

export async function obtainAuthToken(baseUrl = process.env.E2E_BASE_URL || 'http://localhost:3000') {
  try {
    const res = await fetch(`${baseUrl}/api/test/token`, { method: 'POST' })
    if (res.ok) {
      const body = (await res.json()) as { token?: string };
      return body.token ?? null;
    }
  } catch (e) {
    // ignore
  }
  return null
}
