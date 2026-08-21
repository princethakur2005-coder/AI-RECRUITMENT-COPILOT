import { authFetch } from "../lib/api";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  Alert,
  AppLayout,
  Badge,
  Button,
  ConfirmDialog,
  ContentContainer,
  EmptyState,
  ErrorState,
  Header,
  LoadingState,
  MetricCard,
  MotionFade,
  Section,
  Stack,
  Table,
  Tabs,
} from "../components";
import {
  CANDIDATE_PORTAL_API as API,
  type CandidateApplication,
  type CandidateInterview,
  type CandidateMe,
  type CandidateOffer,
  type PortalTab,
  formatCurrency,
  formatDate,
  formatDateInTimezone,
  isOfferActionable,
  isOfferExpired,
  parseApiError,
  parsePortalTab,
  statusTone,
  toCandidateOffer,
} from "../lib/candidate-portal";

type LoadOptions = {
  showLoading?: boolean;
  clearSelection?: boolean;
  clearActionFeedback?: boolean;
};

export default function CandidatePortalPage() {
  const router = useRouter();
  const activeTab = parsePortalTab(router.query.tab);
  const loadAbortRef = useRef<AbortController | null>(null);

  const [me, setMe] = useState<CandidateMe | null>(null);
  const [applications, setApplications] = useState<CandidateApplication[]>([]);
  const [interviews, setInterviews] = useState<CandidateInterview[]>([]);
  const [offers, setOffers] = useState<CandidateOffer[]>([]);
  const [selectedApplication, setSelectedApplication] = useState<CandidateApplication | null>(null);
  const [selectedInterview, setSelectedInterview] = useState<CandidateInterview | null>(null);
  const [selectedOffer, setSelectedOffer] = useState<CandidateOffer | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submittingOfferId, setSubmittingOfferId] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<"accept" | "decline" | null>(null);

  const setTab = (tab: PortalTab) => {
    void router.replace(
      { pathname: "/candidate-portal", query: tab === "dashboard" ? {} : { tab } },
      undefined,
      { shallow: true },
    );
  };

  const loadPortal = useCallback(async (options: LoadOptions = {}) => {
    const {
      showLoading = true,
      clearSelection = true,
      clearActionFeedback = true,
    } = options;

    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;

    if (showLoading) setLoading(true);
    setError(null);
    if (clearActionFeedback) {
      setActionMessage(null);
      setActionError(null);
    }

    try {
      const [meRes, appsRes, interviewsRes, offersRes] = await Promise.all([
        authFetch(API.me, { headers: { Accept: "application/json" }, signal: controller.signal }),
        authFetch(API.applications, { headers: { Accept: "application/json" }, signal: controller.signal }),
        authFetch(API.interviews, { headers: { Accept: "application/json" }, signal: controller.signal }),
        authFetch(API.offers, { headers: { Accept: "application/json" }, signal: controller.signal }),
      ]);

      if (controller.signal.aborted) return;

      if (!meRes.ok) {
        throw new Error(`Unable to load candidate profile (${meRes.status})`);
      }
      if (!appsRes.ok || !interviewsRes.ok || !offersRes.ok) {
        throw new Error("Unable to load candidate portal data");
      }

      const mePayload = (await meRes.json()) as CandidateMe;
      const appsPayload = (await appsRes.json()) as CandidateApplication[];
      const interviewsPayload = (await interviewsRes.json()) as CandidateInterview[];
      const offersPayload = (await offersRes.json()) as CandidateOffer[];

      if (controller.signal.aborted) return;

      setMe(mePayload);
      setApplications(Array.isArray(appsPayload) ? appsPayload : []);
      setInterviews(Array.isArray(interviewsPayload) ? interviewsPayload : []);
      setOffers(Array.isArray(offersPayload) ? offersPayload : []);

      if (clearSelection) {
        setSelectedApplication(null);
        setSelectedInterview(null);
        setSelectedOffer(null);
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Unable to load candidate portal");
      setMe(null);
      setApplications([]);
      setInterviews([]);
      setOffers([]);
    } finally {
      if (loadAbortRef.current === controller) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadPortal();
    return () => {
      loadAbortRef.current?.abort();
    };
  }, [loadPortal]);

  const openApplication = async (applicationId: string) => {
    setActionError(null);
    const response = await authFetch(API.application(applicationId), {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setActionError(parseApiError(payload, "Unable to load application details"));
      return;
    }
    setSelectedApplication((await response.json()) as CandidateApplication);
    setTab("applications");
  };

  const openInterview = async (interviewId: string) => {
    setActionError(null);
    const response = await authFetch(API.interview(interviewId), {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setActionError(parseApiError(payload, "Unable to load interview details"));
      return;
    }
    setSelectedInterview((await response.json()) as CandidateInterview);
    setTab("interviews");
  };

  const openOffer = async (offerId: string) => {
    setActionError(null);
    const response = await authFetch(API.offer(offerId), {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      setActionError(parseApiError(payload, "Unable to load offer details"));
      return;
    }
    setSelectedOffer((await response.json()) as CandidateOffer);
    setTab("offers");
  };

  const submitOfferAction = async () => {
    if (!selectedOffer || !confirmAction || submittingOfferId) return;

    const offerId = selectedOffer.id;
    const action = confirmAction;
    setConfirmAction(null);
    setSubmittingOfferId(offerId);
    setActionError(null);
    setActionMessage(null);

    try {
      const endpoint = action === "accept" ? API.accept(offerId) : API.decline(offerId);
      const response = await authFetch(endpoint, {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
      if (!response.ok) {
        throw new Error(parseApiError(payload, `Unable to ${action} offer`));
      }

      const updatedOffer = payload ? toCandidateOffer(payload) : null;
      if (updatedOffer?.id) {
        setSelectedOffer(updatedOffer);
        setOffers((current) => current.map((item) => (item.id === updatedOffer.id ? updatedOffer : item)));
      }

      setActionMessage(action === "accept" ? "Offer accepted successfully." : "Offer declined.");
      await loadPortal({
        showLoading: false,
        clearSelection: false,
        clearActionFeedback: false,
      });

      const refreshed = await authFetch(API.offer(offerId), { headers: { Accept: "application/json" } });
      if (refreshed.ok) {
        const candidateOffer = (await refreshed.json()) as CandidateOffer;
        setSelectedOffer(candidateOffer);
        setOffers((current) => current.map((item) => (item.id === candidateOffer.id ? candidateOffer : item)));
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : `Unable to ${action} offer`);
    } finally {
      setSubmittingOfferId(null);
    }
  };

  const upcomingInterviews = useMemo(() => {
    const now = Date.now();
    return interviews.filter((item) => {
      const parsed = new Date(item.scheduled_start).getTime();
      return !Number.isNaN(parsed) && parsed >= now && String(item.status).toLowerCase() === "scheduled";
    });
  }, [interviews]);

  const pendingOffers = useMemo(
    () => offers.filter((item) => isOfferActionable(item) && !isOfferExpired(item)),
    [offers],
  );

  const dashboardStats = {
    applications: applications.length,
    interviews: interviews.length,
    offers: offers.length,
    pending: pendingOffers.length,
  };

  const offerBusy = submittingOfferId !== null;

  return (
    <AppLayout
      className="candidate-portal-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="candidate-portal-title">Candidate Portal</h1>
              <p className="candidate-portal-subtitle">
                {me ? `Welcome, ${me.full_name}` : "Your applications, interviews, and offers"}
              </p>
            </Stack>
          }
          right={
            <div className="candidate-portal-actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void loadPortal()}
                disabled={loading || offerBusy}
              >
                Refresh
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="candidate-portal-main" fluid>
        {loading ? (
          <LoadingState title="Loading candidate portal" description="Fetching your applications, interviews, and offers." />
        ) : null}
        {!loading && error ? (
          <ErrorState title="Unable to load candidate portal" description={error} onRetry={() => void loadPortal()} />
        ) : null}

        {!loading && !error ? (
          <MotionFade active>
            <Stack gap="5">
              {actionMessage ? <Alert tone="success" description={actionMessage} /> : null}
              {actionError ? <Alert tone="danger" description={actionError} /> : null}

              <Tabs.Root
                value={activeTab}
                defaultValue="dashboard"
                onValueChange={(value) => setTab(value as PortalTab)}
              >
                <Tabs.List aria-label="Candidate portal sections">
                  <Tabs.Trigger value="dashboard">Overview</Tabs.Trigger>
                  <Tabs.Trigger value="applications">Applications</Tabs.Trigger>
                  <Tabs.Trigger value="interviews">Interviews</Tabs.Trigger>
                  <Tabs.Trigger value="offers">Offers</Tabs.Trigger>
                  <Tabs.Trigger value="profile">Profile</Tabs.Trigger>
                </Tabs.List>

                <Tabs.Panel value="dashboard">
                  <Stack gap="4">
                    <div className="candidate-kpi-grid">
                      <MetricCard label="Applications" value={dashboardStats.applications} meta="Your active applications" />
                      <MetricCard label="Interviews" value={dashboardStats.interviews} meta="Scheduled and past interviews" />
                      <MetricCard label="Offers" value={dashboardStats.offers} meta="Offers issued to you" />
                      <MetricCard label="Actionable offers" value={dashboardStats.pending} meta="Ready to accept or decline" />
                    </div>

                    <section className="candidate-two-col" aria-label="Upcoming activity">
                      <Section>
                        <Stack gap="3">
                          <strong>Upcoming interviews</strong>
                          {upcomingInterviews.length ? (
                            <Table
                              columns={[
                                {
                                  key: "scheduled_start",
                                  header: "When",
                                  render: (row: CandidateInterview) =>
                                    formatDateInTimezone(row.scheduled_start, row.timezone),
                                },
                                {
                                  key: "job_title",
                                  header: "Role",
                                  render: (row: CandidateInterview) => (
                                    <span className="candidate-text-clamp">{row.job_title || "-"}</span>
                                  ),
                                },
                                { key: "interview_type", header: "Type" },
                                {
                                  key: "open",
                                  header: "",
                                  render: (row: CandidateInterview) => (
                                    <Button size="sm" variant="secondary" onClick={() => void openInterview(row.id)}>
                                      View
                                    </Button>
                                  ),
                                },
                              ]}
                              data={upcomingInterviews}
                              rowKey="id"
                            />
                          ) : (
                            <EmptyState title="No upcoming interviews" description="Scheduled interviews will appear here." />
                          )}
                        </Stack>
                      </Section>

                      <Section>
                        <Stack gap="3">
                          <strong>Offers needing attention</strong>
                          {pendingOffers.length ? (
                            <Table
                              columns={[
                                {
                                  key: "offer_title",
                                  header: "Offer",
                                  render: (row: CandidateOffer) => (
                                    <span className="candidate-text-clamp">{row.offer_title || "Offer"}</span>
                                  ),
                                },
                                {
                                  key: "status",
                                  header: "Status",
                                  render: (row: CandidateOffer) => (
                                    <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                                  ),
                                },
                                {
                                  key: "expires_at",
                                  header: "Expires",
                                  render: (row: CandidateOffer) => formatDate(row.expires_at),
                                },
                                {
                                  key: "open",
                                  header: "",
                                  render: (row: CandidateOffer) => (
                                    <Button size="sm" variant="secondary" onClick={() => void openOffer(row.id)}>
                                      Review
                                    </Button>
                                  ),
                                },
                              ]}
                              data={pendingOffers}
                              rowKey="id"
                            />
                          ) : (
                            <EmptyState title="No actionable offers" description="Approved offers ready for your response will appear here." />
                          )}
                        </Stack>
                      </Section>
                    </section>
                  </Stack>
                </Tabs.Panel>

                <Tabs.Panel value="applications">
                  <Stack gap="4">
                    {applications.length ? (
                      <Table
                        columns={[
                          {
                            key: "job_title",
                            header: "Role",
                            render: (row: CandidateApplication) => (
                              <span className="candidate-text-clamp">{row.job_title || "-"}</span>
                            ),
                          },
                          {
                            key: "company_name",
                            header: "Company",
                            render: (row: CandidateApplication) => (
                              <span className="candidate-text-clamp">{row.company_name || "-"}</span>
                            ),
                          },
                          {
                            key: "status",
                            header: "Status",
                            render: (row: CandidateApplication) => (
                              <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                            ),
                          },
                          {
                            key: "applied_at",
                            header: "Applied",
                            render: (row: CandidateApplication) => formatDate(row.applied_at),
                          },
                          {
                            key: "open",
                            header: "",
                            render: (row: CandidateApplication) => (
                              <Button size="sm" variant="secondary" onClick={() => void openApplication(row.id)}>
                                Details
                              </Button>
                            ),
                          },
                        ]}
                        data={applications}
                        rowKey="id"
                      />
                    ) : (
                      <EmptyState
                        title="No applications yet"
                        description="When you apply to roles, they will appear here."
                      />
                    )}

                    {selectedApplication ? (
                      <Section elevated>
                        <Stack gap="2">
                          <strong>Application details</strong>
                          <p className="candidate-text-wrap">
                            {selectedApplication.job_title || "Role"} at {selectedApplication.company_name || "Company"}
                          </p>
                          <p>
                            Status: <Badge tone={statusTone(selectedApplication.status)}>{selectedApplication.status}</Badge>
                          </p>
                          <p>Applied: {formatDate(selectedApplication.applied_at)}</p>
                          <p>Updated: {formatDate(selectedApplication.updated_at)}</p>
                          {selectedApplication.source ? <p>Source: {selectedApplication.source}</p> : null}
                        </Stack>
                      </Section>
                    ) : null}
                  </Stack>
                </Tabs.Panel>

                <Tabs.Panel value="interviews">
                  <Stack gap="4">
                    {interviews.length ? (
                      <Table
                        columns={[
                          {
                            key: "scheduled_start",
                            header: "Schedule",
                            render: (row: CandidateInterview) =>
                              formatDateInTimezone(row.scheduled_start, row.timezone),
                          },
                          {
                            key: "job_title",
                            header: "Role",
                            render: (row: CandidateInterview) => (
                              <span className="candidate-text-clamp">{row.job_title || "-"}</span>
                            ),
                          },
                          { key: "interview_type", header: "Type" },
                          {
                            key: "status",
                            header: "Status",
                            render: (row: CandidateInterview) => (
                              <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                            ),
                          },
                          {
                            key: "open",
                            header: "",
                            render: (row: CandidateInterview) => (
                              <Button size="sm" variant="secondary" onClick={() => void openInterview(row.id)}>
                                Details
                              </Button>
                            ),
                          },
                        ]}
                        data={interviews}
                        rowKey="id"
                      />
                    ) : (
                      <EmptyState title="No interviews" description="Interview schedules for your applications will appear here." />
                    )}

                    {selectedInterview ? (
                      <Section elevated>
                        <Stack gap="2">
                          <strong>Interview details</strong>
                          <p className="candidate-text-wrap">
                            {selectedInterview.job_title || "Role"} · {selectedInterview.interview_type}
                          </p>
                          <p>
                            Status: <Badge tone={statusTone(selectedInterview.status)}>{selectedInterview.status}</Badge>
                          </p>
                          <p>
                            Starts: {formatDateInTimezone(selectedInterview.scheduled_start, selectedInterview.timezone)}
                          </p>
                          <p>
                            Ends: {formatDateInTimezone(selectedInterview.scheduled_end, selectedInterview.timezone)}
                          </p>
                          <p>Timezone: {selectedInterview.timezone}</p>
                          {selectedInterview.interviewer_name ? (
                            <p>Interviewer: {selectedInterview.interviewer_name}</p>
                          ) : null}
                          {selectedInterview.location ? (
                            <p className="candidate-text-wrap">Location: {selectedInterview.location}</p>
                          ) : null}
                          {selectedInterview.meeting_link ? (
                            <p className="candidate-text-wrap">
                              Meeting:{" "}
                              <a href={selectedInterview.meeting_link} target="_blank" rel="noreferrer">
                                {selectedInterview.meeting_link}
                              </a>
                            </p>
                          ) : null}
                        </Stack>
                      </Section>
                    ) : null}
                  </Stack>
                </Tabs.Panel>

                <Tabs.Panel value="offers">
                  <Stack gap="4">
                    {offers.length ? (
                      <Table
                        columns={[
                          {
                            key: "offer_title",
                            header: "Offer",
                            render: (row: CandidateOffer) => (
                              <span className="candidate-text-clamp">{row.offer_title || "Offer"}</span>
                            ),
                          },
                          {
                            key: "status",
                            header: "Status",
                            render: (row: CandidateOffer) => (
                              <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                            ),
                          },
                          {
                            key: "compensation",
                            header: "Compensation",
                            render: (row: CandidateOffer) =>
                              `${formatCurrency(row.compensation_min, row.currency || "USD")} – ${formatCurrency(row.compensation_max, row.currency || "USD")}`,
                          },
                          {
                            key: "expires_at",
                            header: "Expires",
                            render: (row: CandidateOffer) => formatDate(row.expires_at),
                          },
                          {
                            key: "revision",
                            header: "Rev",
                            render: (row: CandidateOffer) => String(row.revision),
                          },
                          {
                            key: "open",
                            header: "",
                            render: (row: CandidateOffer) => (
                              <Button size="sm" variant="secondary" onClick={() => void openOffer(row.id)}>
                                Review
                              </Button>
                            ),
                          },
                        ]}
                        data={offers}
                        rowKey="id"
                      />
                    ) : (
                      <EmptyState title="No offers" description="Offers issued to you will appear here." />
                    )}

                    {selectedOffer ? (
                      <Section elevated>
                        <Stack gap="3">
                          <strong className="candidate-text-wrap">{selectedOffer.offer_title || "Offer details"}</strong>
                          <p>
                            Status: <Badge tone={statusTone(selectedOffer.status)}>{selectedOffer.status}</Badge>
                            {isOfferExpired(selectedOffer) ? (
                              <>
                                {" "}
                                <Badge tone="danger">Expired</Badge>
                              </>
                            ) : null}
                          </p>
                          <p>
                            Compensation:{" "}
                            {formatCurrency(selectedOffer.compensation_min, selectedOffer.currency || "USD")} –{" "}
                            {formatCurrency(selectedOffer.compensation_max, selectedOffer.currency || "USD")}
                          </p>
                          <p>Expires: {formatDate(selectedOffer.expires_at)}</p>
                          <p>Revision: {selectedOffer.revision}</p>
                          {selectedOffer.terms ? (
                            <p className="candidate-text-wrap">Terms: {selectedOffer.terms}</p>
                          ) : null}

                          {isOfferActionable(selectedOffer) && !isOfferExpired(selectedOffer) ? (
                            <div className="candidate-portal-actions">
                              <Button
                                onClick={() => setConfirmAction("accept")}
                                disabled={offerBusy}
                                aria-busy={submittingOfferId === selectedOffer.id}
                              >
                                Accept offer
                              </Button>
                              <Button
                                variant="secondary"
                                onClick={() => setConfirmAction("decline")}
                                disabled={offerBusy}
                              >
                                Decline offer
                              </Button>
                            </div>
                          ) : null}
                        </Stack>
                      </Section>
                    ) : null}
                  </Stack>
                </Tabs.Panel>

                <Tabs.Panel value="profile">
                  <Section elevated>
                    {me ? (
                      <Stack gap="2">
                        <strong>Account</strong>
                        <p className="candidate-text-wrap">Name: {me.full_name}</p>
                        <p className="candidate-text-wrap">Email: {me.email}</p>
                        <p>Phone: {me.phone || "-"}</p>
                        <p>
                          Status: <Badge tone={statusTone(me.status)}>{me.status}</Badge>
                        </p>
                        <p>Account activated: {me.account_activated ? "Yes" : "No"}</p>
                      </Stack>
                    ) : (
                      <EmptyState title="Profile unavailable" description="Sign in again to view your candidate profile." />
                    )}
                  </Section>
                </Tabs.Panel>
              </Tabs.Root>
            </Stack>
          </MotionFade>
        ) : null}
      </ContentContainer>

      <ConfirmDialog
        open={confirmAction !== null}
        onOpenChange={(open) => {
          if (!open && !offerBusy) setConfirmAction(null);
        }}
        title={confirmAction === "accept" ? "Accept this offer?" : "Decline this offer?"}
        description={
          confirmAction === "accept"
            ? "Accepting will update your application status. This action follows the server lifecycle rules."
            : "Declining will mark this offer as declined. You may receive a revised offer later."
        }
        confirmLabel={confirmAction === "accept" ? "Accept" : "Decline"}
        cancelLabel="Cancel"
        destructive={confirmAction === "decline"}
        onConfirm={() => {
          void submitOfferAction();
        }}
        onCancel={() => {
          if (!offerBusy) setConfirmAction(null);
        }}
      />
    </AppLayout>
  );
}
