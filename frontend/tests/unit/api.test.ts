import {
  authFetch,
  clearAuthSession,
  getAccessToken,
  getAuthPrincipal,
  setAuthSession,
} from "../../lib/api";
import { jsonResponse } from "../fetchMock";

describe("candidate auth session helpers", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.restoreAllMocks();
  });

  it("initializes a candidate session from login", () => {
    setAuthSession("candidate-token", "candidate");

    expect(getAccessToken()).toBe("candidate-token");
    expect(getAuthPrincipal()).toBe("candidate");
  });

  it("defaults legacy token-only sessions to user principal", () => {
    localStorage.setItem("access_token", "legacy-token");

    expect(getAuthPrincipal()).toBe("user");
  });

  it("clears candidate session and redirects to candidate login on 401", async () => {
    setAuthSession("expired-candidate-token", "candidate");

    const fetchMock = jest.fn().mockResolvedValue(jsonResponse({ detail: "Unauthorized" }, 401));
    globalThis.fetch = fetchMock as typeof fetch;

    const locationMock = jest.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        get href() {
          return "";
        },
        set href(value: string) {
          locationMock(value);
        },
      },
    });

    await authFetch("/candidate/applications");

    expect(fetchMock).toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
    expect(getAuthPrincipal()).toBeNull();
    expect(locationMock).toHaveBeenCalledWith("/candidate-login");

    clearAuthSession();
  });
});
