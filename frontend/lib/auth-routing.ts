import type { AuthPrincipal } from "./api";

const PUBLIC_PATHS = new Set([
  "/login",
  "/signup",
  "/forgot-password",
  "/candidate-login",
  "/candidate-signup",
]);

const CANDIDATE_PATHS = new Set(["/candidate-portal"]);

export function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.has(pathname)) return true;
  if (pathname.startsWith("/apply/")) return true;
  return false;
}

export function isCandidatePath(pathname: string): boolean {
  return CANDIDATE_PATHS.has(pathname);
}

/**
 * UX-only route guard. Backend authorization remains authoritative.
 * Returns a redirect path, or null when the current route is allowed.
 */
export function resolveAuthRedirect(input: {
  pathname: string;
  token: string | null;
  principal: AuthPrincipal | null;
}): string | null {
  const { pathname, token, principal } = input;
  const isPublic = isPublicPath(pathname);

  if (isPublic) {
    if (token && principal === "candidate" && (pathname === "/candidate-login" || pathname === "/candidate-signup")) {
      return "/candidate-portal";
    }
    if (token && principal === "user" && (pathname === "/login" || pathname === "/signup")) {
      return "/dashboard";
    }
    return null;
  }

  if (!token) {
    return isCandidatePath(pathname) ? "/candidate-login" : "/login";
  }

  if (isCandidatePath(pathname) && principal !== "candidate") {
    return "/dashboard";
  }

  if (!isCandidatePath(pathname) && principal === "candidate") {
    return "/candidate-portal";
  }

  return null;
}
