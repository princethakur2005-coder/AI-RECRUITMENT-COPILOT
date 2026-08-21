type MockResponseInit = {
  status?: number;
  body?: unknown;
};

type RouteHandler = (input: string, init?: RequestInit) => MockResponseInit | Promise<MockResponseInit>;

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    headers: {
      get: (name: string) => (name.toLowerCase() === "content-type" ? "application/json" : null),
    },
    json: async () => body,
    text: async () => JSON.stringify(body),
    clone() {
      return jsonResponse(body, status);
    },
  } as unknown as Response;
}

export function createFetchMock() {
  const routes = new Map<string, RouteHandler>();

  const keyFor = (method: string, url: string) => `${method.toUpperCase()} ${url}`;

  const mock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const exact = routes.get(keyFor(method, url));
    if (exact) {
      const result = await exact(url, init);
      return jsonResponse(result.body ?? null, result.status ?? 200);
    }

    for (const [pattern, handler] of routes.entries()) {
      const [routeMethod, routePath] = pattern.split(" ");
      if (routeMethod !== method) continue;
      if (routePath.endsWith("*") && url.startsWith(routePath.slice(0, -1))) {
        const result = await handler(url, init);
        return jsonResponse(result.body ?? null, result.status ?? 200);
      }
    }

    return jsonResponse({ detail: `Unhandled fetch ${method} ${url}` }, 500);
  });

  return {
    mock,
    on(method: string, url: string, handler: RouteHandler) {
      routes.set(keyFor(method, url), handler);
    },
    install() {
      globalThis.fetch = mock as typeof fetch;
    },
  };
}

export { jsonResponse };
