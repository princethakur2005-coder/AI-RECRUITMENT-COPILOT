/**
 * Authenticated fetch wrapper.
 * Reads the JWT from localStorage, injects `Authorization: Bearer <token>`,
 * and redirects to /login on 401.
 */
export async function authFetch(
  input: string | URL,
  init: RequestInit = {},
): Promise<Response> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(input, { ...init, headers });

  if (response.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    window.location.href = "/login";
  }

  return response;
}
