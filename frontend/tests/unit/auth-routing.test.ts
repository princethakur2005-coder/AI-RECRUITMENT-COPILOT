import { resolveAuthRedirect } from "../../lib/auth-routing";

describe("resolveAuthRedirect", () => {
  it("allows candidate JWT on candidate portal", () => {
    expect(
      resolveAuthRedirect({
        pathname: "/candidate-portal",
        token: "tok",
        principal: "candidate",
      }),
    ).toBeNull();
  });

  it("rejects recruiter JWT on candidate portal", () => {
    expect(
      resolveAuthRedirect({
        pathname: "/candidate-portal",
        token: "tok",
        principal: "user",
      }),
    ).toBe("/dashboard");
  });

  it("rejects candidate JWT on recruiter routes", () => {
    expect(
      resolveAuthRedirect({
        pathname: "/dashboard",
        token: "tok",
        principal: "candidate",
      }),
    ).toBe("/candidate-portal");
  });

  it("sends unauthenticated candidate-route visitors to candidate login", () => {
    expect(
      resolveAuthRedirect({
        pathname: "/candidate-portal",
        token: null,
        principal: null,
      }),
    ).toBe("/candidate-login");
  });

  it("sends authenticated candidates away from candidate login", () => {
    expect(
      resolveAuthRedirect({
        pathname: "/candidate-login",
        token: "tok",
        principal: "candidate",
      }),
    ).toBe("/candidate-portal");
  });
});
