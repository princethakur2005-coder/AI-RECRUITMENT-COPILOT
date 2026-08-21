/**
 * Authenticated fetch and lightweight session helpers.
 * JWT + principal live in localStorage — same pattern as existing recruiter auth.
 */

const TOKEN_KEY = "access_token";
const PRINCIPAL_KEY = "auth_principal";

export type AuthPrincipal = "user" | "candidate";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getAuthPrincipal(): AuthPrincipal | null {
  if (typeof window === "undefined") return null;
  const value = localStorage.getItem(PRINCIPAL_KEY);
  if (value === "candidate" || value === "user") return value;
  // Legacy sessions without principal default to recruiter/user.
  return getAccessToken() ? "user" : null;
}

export function setAuthSession(accessToken: string, principal: AuthPrincipal = "user"): void {
  localStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(PRINCIPAL_KEY, principal);
}

export function clearAuthSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(PRINCIPAL_KEY);
}

function loginPathForPrincipal(principal: AuthPrincipal | null): string {
  return principal === "candidate" ? "/candidate-login" : "/login";
}

/**
 * Authenticated fetch wrapper.
 * Reads the JWT from localStorage, injects `Authorization: Bearer <token>`,
 * and redirects to the matching login page on 401.
 */
export async function authFetch(
  input: string | URL,
  init: RequestInit = {},
): Promise<Response> {
  const token = getAccessToken();
  const principal = getAuthPrincipal();

  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(input, { ...init, headers });

  if (response.status === 401 && typeof window !== "undefined") {
    clearAuthSession();
    window.location.href = loginPathForPrincipal(principal);
  }

  return response;
}
