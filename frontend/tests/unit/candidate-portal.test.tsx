import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

import { setAuthSession } from "../../lib/api";
import CandidatePortalPage from "../../pages/candidate-portal";
import { createFetchMock } from "../fetchMock";

jest.mock("next/router", () => ({
  useRouter: jest.fn(),
}));

const replaceMock = jest.fn();

function mockRouter(tab?: string) {
  (useRouter as jest.Mock).mockReturnValue({
    pathname: "/candidate-portal",
    query: tab ? { tab } : {},
    replace: replaceMock,
    push: jest.fn(),
    prefetch: jest.fn(),
  });
}

const me = {
  id: "c1",
  email: "candidate@example.com",
  full_name: "Casey Candidate",
  first_name: "Casey",
  last_name: "Candidate",
  phone: null,
  is_active: true,
  status: "active",
  account_activated: true,
};

const application = {
  id: "a1",
  status: "interview",
  source: "public_apply",
  applied_at: "2026-01-01T10:00:00.000Z",
  updated_at: "2026-01-02T10:00:00.000Z",
  job_id: "j1",
  job_title: "Backend Engineer",
  company_id: "co1",
  company_name: "Acme",
};

const interview = {
  id: "i1",
  application_id: "a1",
  interview_type: "technical",
  scheduled_start: "2099-06-01T15:00:00.000Z",
  scheduled_end: "2099-06-01T16:00:00.000Z",
  timezone: "UTC",
  meeting_link: "https://meet.example.com/abc",
  location: null,
  status: "scheduled",
  interviewer_name: "Alex Recruiter",
  job_title: "Backend Engineer",
  company_name: "Acme",
};

const offer = {
  id: "o1",
  application_id: "a1",
  job_id: "j1",
  revision: 1,
  is_active: true,
  offer_title: "Backend Engineer Offer",
  compensation_min: 110000,
  compensation_max: 130000,
  currency: "USD",
  expires_at: "2099-12-01T00:00:00.000Z",
  terms: "Full-time remote",
  status: "approved",
  created_at: "2026-01-03T00:00:00.000Z",
  updated_at: "2026-01-03T00:00:00.000Z",
};

function installPortalRoutes(
  fetchMock: ReturnType<typeof createFetchMock>,
  overrides?: {
    applications?: unknown[];
    interviews?: unknown[];
    offers?: unknown[];
    offerDetail?: unknown;
  },
) {
  fetchMock.on("GET", "/auth/candidate/me", () => ({ body: me }));
  fetchMock.on("GET", "/candidate/applications", () => ({
    body: overrides?.applications ?? [application],
  }));
  fetchMock.on("GET", "/candidate/interviews", () => ({
    body: overrides?.interviews ?? [interview],
  }));
  fetchMock.on("GET", "/candidate/offers", () => ({
    body: overrides?.offers ?? [offer],
  }));
  fetchMock.on("GET", "/candidate/offers/o1", () => ({
    body: overrides?.offerDetail ?? offer,
  }));
}

describe("CandidatePortalPage", () => {
  beforeEach(() => {
    localStorage.clear();
    replaceMock.mockReset();
    jest.restoreAllMocks();
    setAuthSession("candidate-token", "candidate");
    mockRouter("offers");
  });

  it("loads applications, interviews, and offers", async () => {
    const fetchMock = createFetchMock();
    installPortalRoutes(fetchMock);
    fetchMock.install();

    mockRouter("applications");
    const { unmount } = render(<CandidatePortalPage />);
    expect(await screen.findByText("Backend Engineer")).toBeInTheDocument();
    unmount();

    mockRouter("interviews");
    const second = render(<CandidatePortalPage />);
    expect(await screen.findByText("technical")).toBeInTheDocument();
    second.unmount();

    mockRouter("offers");
    render(<CandidatePortalPage />);
    expect(await screen.findByText("Backend Engineer Offer")).toBeInTheDocument();
  });

  it("renders empty states when collections are empty", async () => {
    const fetchMock = createFetchMock();
    installPortalRoutes(fetchMock, { applications: [], interviews: [], offers: [] });
    fetchMock.install();

    mockRouter("applications");
    const first = render(<CandidatePortalPage />);
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
    first.unmount();

    mockRouter("interviews");
    const second = render(<CandidatePortalPage />);
    expect(await screen.findByText("No interviews")).toBeInTheDocument();
    second.unmount();

    mockRouter("offers");
    render(<CandidatePortalPage />);
    expect(await screen.findByText("No offers")).toBeInTheDocument();
  });

  it("renders API error state when portal data fails", async () => {
    const fetchMock = createFetchMock();
    fetchMock.on("GET", "/auth/candidate/me", () => ({ body: me }));
    fetchMock.on("GET", "/candidate/applications", () => ({ status: 500, body: { detail: "boom" } }));
    fetchMock.on("GET", "/candidate/interviews", () => ({ body: [] }));
    fetchMock.on("GET", "/candidate/offers", () => ({ body: [] }));
    fetchMock.install();

    render(<CandidatePortalPage />);
    expect(await screen.findByText("Unable to load candidate portal")).toBeInTheDocument();
  });

  it("requires confirmation before accept and refreshes offer state", async () => {
    const user = userEvent.setup();
    let accepted = false;
    const fetchMock = createFetchMock();

    fetchMock.on("GET", "/auth/candidate/me", () => ({ body: me }));
    fetchMock.on("GET", "/candidate/applications", () => ({ body: [application] }));
    fetchMock.on("GET", "/candidate/interviews", () => ({ body: [interview] }));
    fetchMock.on("GET", "/candidate/offers", () => ({
      body: [accepted ? { ...offer, status: "accepted", is_active: false } : offer],
    }));
    fetchMock.on("GET", "/candidate/offers/o1", () => ({
      body: accepted ? { ...offer, status: "accepted", is_active: false } : offer,
    }));
    fetchMock.on("POST", "/offers/o1/accept", () => {
      accepted = true;
      return {
        body: { ...offer, status: "accepted", is_active: false, candidate_id: "c1" },
      };
    });
    fetchMock.install();

    render(<CandidatePortalPage />);
    await user.click((await screen.findAllByRole("button", { name: "Review" }))[0]);
    await user.click(await screen.findByRole("button", { name: "Accept offer" }));

    expect(await screen.findByText("Accept this offer?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => {
      expect(screen.getByText("Offer accepted successfully.")).toBeInTheDocument();
    });
    expect(await screen.findAllByText("accepted")).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Accept offer" })).not.toBeInTheDocument();
  });

  it("requires confirmation before decline", async () => {
    const user = userEvent.setup();
    const fetchMock = createFetchMock();
    installPortalRoutes(fetchMock, {
      offerDetail: { ...offer, status: "declined", is_active: false },
      offers: [{ ...offer, status: "declined", is_active: false }],
    });
    // First load returns actionable offer; after decline refresh returns declined.
    let declined = false;
    fetchMock.on("GET", "/candidate/offers", () => ({
      body: [declined ? { ...offer, status: "declined", is_active: false } : offer],
    }));
    fetchMock.on("GET", "/candidate/offers/o1", () => ({
      body: declined ? { ...offer, status: "declined", is_active: false } : offer,
    }));
    fetchMock.on("POST", "/offers/o1/decline", () => {
      declined = true;
      return { body: { ...offer, status: "declined", is_active: false, candidate_id: "c1" } };
    });
    fetchMock.install();

    render(<CandidatePortalPage />);
    await user.click((await screen.findAllByRole("button", { name: "Review" }))[0]);
    await user.click(await screen.findByRole("button", { name: "Decline offer" }));

    expect(await screen.findByText("Decline this offer?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Decline" }));

    await waitFor(() => {
      expect(screen.getByText("Offer declined.")).toBeInTheDocument();
    });
  });

  it("prevents duplicate offer submission while a mutation is in flight", async () => {
    const user = userEvent.setup();
    let acceptCalls = 0;
    const fetchMock = createFetchMock();
    installPortalRoutes(fetchMock);
    fetchMock.on("POST", "/offers/o1/accept", async () => {
      acceptCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 200));
      return { body: { ...offer, status: "accepted", is_active: false, candidate_id: "c1" } };
    });
    fetchMock.install();

    render(<CandidatePortalPage />);
    await user.click((await screen.findAllByRole("button", { name: "Review" }))[0]);
    await user.click(await screen.findByRole("button", { name: "Accept offer" }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Accept" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Accept offer" })).toBeDisabled();
    });

    await waitFor(() => {
      expect(acceptCalls).toBe(1);
    });
  });
});
