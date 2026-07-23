import { HttpResponse, http } from 'msw'

export function jsonResponse(status: number, body: any) {
  return () => new HttpResponse(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  })
}

export const mockGet = (url: string, body: any) => http.get(url, jsonResponse(200, body))
