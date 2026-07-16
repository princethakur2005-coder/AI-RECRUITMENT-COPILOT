import { rest } from 'msw'

export function jsonResponse(status: number, body: any) {
  return (req: any, res: any, ctx: any) => res(ctx.status(status), ctx.json(body))
}

export const mockGet = (url: string, body: any) => rest.get(url, jsonResponse(200, body))
