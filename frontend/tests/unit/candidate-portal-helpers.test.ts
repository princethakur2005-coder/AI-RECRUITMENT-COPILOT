import {
  isOfferActionable,
  isOfferExpired,
  parseApiError,
  parsePortalTab,
  toCandidateOffer,
} from "../../lib/candidate-portal";

describe("candidate portal helpers", () => {
  it("parses portal tabs and falls back safely", () => {
    expect(parsePortalTab("offers")).toBe("offers");
    expect(parsePortalTab("unknown")).toBe("dashboard");
  });

  it("treats only active approved offers as actionable", () => {
    expect(isOfferActionable({ status: "approved", is_active: true })).toBe(true);
    expect(isOfferActionable({ status: "sent", is_active: true })).toBe(false);
    expect(isOfferActionable({ status: "approved", is_active: false })).toBe(false);
  });

  it("detects expired offers", () => {
    expect(isOfferExpired({ expires_at: "2000-01-01T00:00:00.000Z" })).toBe(true);
    expect(isOfferExpired({ expires_at: null })).toBe(false);
  });

  it("parses API error payloads", () => {
    expect(parseApiError({ detail: "Nope" }, "fallback")).toBe("Nope");
    expect(parseApiError(null, "fallback")).toBe("fallback");
  });

  it("maps offer mutation payloads into candidate-safe offers", () => {
    const mapped = toCandidateOffer({
      id: "o1",
      application_id: "a1",
      job_id: null,
      revision: 2,
      is_active: true,
      offer_title: "Backend Engineer",
      compensation_min: 100000,
      compensation_max: 120000,
      currency: "USD",
      expires_at: "2099-01-01T00:00:00.000Z",
      terms: "Remote",
      status: "accepted",
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-02T00:00:00.000Z",
      hiring_intelligence: { should_ignore: true },
    });

    expect(mapped.status).toBe("accepted");
    expect(mapped.offer_title).toBe("Backend Engineer");
    expect(mapped).not.toHaveProperty("hiring_intelligence");
  });
});
