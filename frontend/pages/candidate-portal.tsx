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
  type CandidateAssessmentData,
  type AssessmentSubmitResult,
  type CandidateAIInterviewData,
  type CandidateAIInterviewSubmitResult,
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

  const [assessmentData, setAssessmentData] = useState<CandidateAssessmentData | null>(null);
  const [assessmentLoading, setAssessmentLoading] = useState(false);
  const [assessmentSubmitting, setAssessmentSubmitting] = useState(false);
  const [assessmentAnswers, setAssessmentAnswers] = useState<Record<string, string>>({});
  const [assessmentResult, setAssessmentResult] = useState<AssessmentSubmitResult | null>(null);

  const [aiInterviewData, setAiInterviewData] = useState<CandidateAIInterviewData | null>(null);
  const [aiInterviewLoading, setAiInterviewLoading] = useState(false);
  const [aiInterviewSubmitting, setAiInterviewSubmitting] = useState(false);
  const [aiInterviewAnswers, setAiInterviewAnswers] = useState<Record<string, string>>({});
  const [aiInterviewResult, setAiInterviewResult] = useState<CandidateAIInterviewSubmitResult | null>(null);

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

  const loadAssessmentForApp = async (appId: string) => {
    setAssessmentLoading(true);
    setAssessmentResult(null);
    try {
      const res = await authFetch(API.assessment(appId), { headers: { Accept: "application/json" } });
      if (res.ok) {
        const data = (await res.json()) as CandidateAssessmentData;
        setAssessmentData(data);
        setAssessmentAnswers({});
      } else {
        setAssessmentData(null);
      }
    } catch {
      setAssessmentData(null);
    } finally {
      setAssessmentLoading(false);
    }
  };

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
    const app = (await response.json()) as CandidateApplication;
    setSelectedApplication(app);
    setTab("applications");
    void loadAssessmentForApp(applicationId);
    void loadAIInterviewForApp(applicationId);
  };

  const loadAIInterviewForApp = async (appId: string) => {
    setAiInterviewLoading(true);
    try {
      const res = await authFetch(API.aiInterview(appId), { headers: { Accept: "application/json" } });
      if (res.ok) {
        const data = (await res.json()) as CandidateAIInterviewData;
        setAiInterviewData(data);
        setAiInterviewAnswers({});
      } else {
        setAiInterviewData(null);
      }
    } catch {
      setAiInterviewData(null);
    } finally {
      setAiInterviewLoading(false);
    }
  };

  const handleSubmitAssessment = async () => {
    if (!selectedApplication) return;
    setAssessmentSubmitting(true);
    setActionError(null);
    try {
      const res = await authFetch(API.submitAssessment(selectedApplication.id), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ answers: assessmentAnswers }),
      });
      const payload = (await res.json().catch(() => null)) as Record<string, unknown> | null;
      if (!res.ok) {
        throw new Error(parseApiError(payload, "Unable to submit assessment"));
      }
      const result = payload as unknown as AssessmentSubmitResult;
      setAssessmentResult(result);
      setActionMessage(`Assessment submitted successfully! You scored ${result.score}%.`);
      await loadPortal({ showLoading: false, clearSelection: false, clearActionFeedback: false });
      const refreshedApp = await authFetch(API.application(selectedApplication.id), { headers: { Accept: "application/json" } });
      if (refreshedApp.ok) {
        setSelectedApplication((await refreshedApp.json()) as CandidateApplication);
      }
      await loadAssessmentForApp(selectedApplication.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unable to submit assessment");
    } finally {
      setAssessmentSubmitting(false);
    }
  };

  const handleSubmitAIInterview = async () => {
    if (!selectedApplication) return;
    setAiInterviewSubmitting(true);
    setActionError(null);
    try {
      const res = await authFetch(API.submitAIInterview(selectedApplication.id), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ answers: aiInterviewAnswers }),
      });
      const payload = (await res.json().catch(() => null)) as Record<string, unknown> | null;
      if (!res.ok) {
        throw new Error(parseApiError(payload, "Unable to submit AI interview"));
      }
      const result = payload as unknown as CandidateAIInterviewSubmitResult;
      setAiInterviewResult(result);
      setActionMessage(`AI Interview submitted successfully! You scored ${result.score}%.`);
      await loadPortal({ showLoading: false, clearSelection: false, clearActionFeedback: false });
      const refreshedApp = await authFetch(API.application(selectedApplication.id), { headers: { Accept: "application/json" } });
      if (refreshedApp.ok) {
        setSelectedApplication((await refreshedApp.json()) as CandidateApplication);
      }
      await loadAIInterviewForApp(selectedApplication.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unable to submit AI interview");
    } finally {
      setAiInterviewSubmitting(false);
    }
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
                      <>
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

                      <Section elevated>
                        <Stack gap="3">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <strong>Role-Based Skills Screening Assessment</strong>
                            {assessmentData?.status === "completed" || selectedApplication.assessment_score != null ? (
                              <Badge tone={(selectedApplication.assessment_score ?? assessmentData?.score ?? 0) >= 60 ? "success" : "warning"}>
                                Score: {selectedApplication.assessment_score ?? assessmentData?.score}%
                              </Badge>
                            ) : (
                              <Badge tone="brand">Assessment Pending</Badge>
                            )}
                          </div>

                          {assessmentLoading ? (
                            <LoadingState title="Loading assessment..." />
                          ) : null}

                          {!assessmentLoading && (assessmentData?.status === "completed" || selectedApplication.assessment_score != null) ? (
                            <Stack gap="2">
                              <Alert
                                tone={(selectedApplication.assessment_score ?? assessmentData?.score ?? 0) >= 60 ? "success" : "warning"}
                                title={`Assessment Completed - Score: ${selectedApplication.assessment_score ?? assessmentData?.score}%`}
                                description={
                                  (selectedApplication.assessment_score ?? assessmentData?.score ?? 0) >= 60
                                    ? "Great job! You have met the minimum screening score for this role."
                                    : "Thank you for completing the assessment. Your score has been submitted to the recruiting team."
                                }
                              />
                            </Stack>
                          ) : null}

                          {!assessmentLoading && assessmentData && assessmentData.status !== "completed" && selectedApplication.assessment_score == null ? (
                            <Stack gap="3">
                              <p style={{ color: "var(--color-text-secondary, #64748b)" }}>
                                Please complete the screening questions below for <strong>{selectedApplication.job_title}</strong>. Select your answer for each question and click Submit.
                              </p>

                              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                                {assessmentData.questions.map((q, qIndex) => (
                                  <div
                                    key={q.id}
                                    style={{
                                      border: "1px solid var(--color-border, #e2e8f0)",
                                      borderRadius: "8px",
                                      padding: "1rem",
                                      background: "var(--color-surface, #ffffff)",
                                    }}
                                  >
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                                      <strong>Question {qIndex + 1}: {q.question}</strong>
                                      {q.skill_tag ? <Badge tone="neutral">{q.skill_tag}</Badge> : null}
                                    </div>

                                    <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "0.5rem", marginTop: "0.75rem" }}>
                                      {Object.entries(q.options).map(([optKey, optText]) => {
                                        const isSelected = assessmentAnswers[q.id] === optKey;
                                        return (
                                          <button
                                            key={optKey}
                                            type="button"
                                            onClick={() =>
                                              setAssessmentAnswers((prev) => ({
                                                ...prev,
                                                [q.id]: optKey,
                                              }))
                                            }
                                            style={{
                                              textAlign: "left",
                                              padding: "0.6rem 0.8rem",
                                              borderRadius: "6px",
                                              border: isSelected
                                                ? "2px solid var(--color-primary, #3b82f6)"
                                                : "1px solid var(--color-border, #cbd5e1)",
                                              background: isSelected
                                                ? "rgba(59, 130, 246, 0.08)"
                                                : "var(--color-bg, #ffffff)",
                                              cursor: "pointer",
                                              display: "flex",
                                              alignItems: "center",
                                              gap: "0.5rem",
                                            }}
                                          >
                                            <span
                                              style={{
                                                fontWeight: "bold",
                                                color: isSelected ? "var(--color-primary, #3b82f6)" : "inherit",
                                              }}
                                            >
                                              {optKey}.
                                            </span>
                                            <span>{optText}</span>
                                          </button>
                                        );
                                      })}
                                    </div>
                                  </div>
                                ))}
                              </div>

                              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.5rem" }}>
                                <Button
                                  variant="primary"
                                  disabled={
                                    assessmentSubmitting ||
                                    Object.keys(assessmentAnswers).length < (assessmentData?.questions?.length || 1)
                                  }
                                  onClick={() => void handleSubmitAssessment()}
                                >
                                  {assessmentSubmitting ? "Submitting Assessment..." : "Submit Assessment"}
                                </Button>
                              </div>
                            </Stack>
                          ) : null}
                        </Stack>
                      </Section>

                      <Section elevated>
                        <Stack gap="3">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <strong>Role-Based AI-Guided Interview</strong>
                            {aiInterviewData?.status === "completed" || selectedApplication.interview_score != null ? (
                              <Badge tone={(selectedApplication.interview_score ?? aiInterviewData?.score ?? 0) >= 60 ? "success" : "warning"}>
                                Interview Score: {selectedApplication.interview_score ?? aiInterviewData?.score}%
                              </Badge>
                            ) : (
                              <Badge tone="brand">Interview Ready</Badge>
                            )}
                          </div>

                          {aiInterviewLoading ? (
                            <LoadingState title="Loading AI interview..." />
                          ) : null}

                          {!aiInterviewLoading && (aiInterviewData?.status === "completed" || selectedApplication.interview_score != null) ? (
                            <Stack gap="2">
                              <Alert
                                tone={(selectedApplication.interview_score ?? aiInterviewData?.score ?? 0) >= 70 ? "success" : "warning"}
                                title={`AI Interview Completed — Score: ${selectedApplication.interview_score ?? aiInterviewData?.score}%`}
                                description={
                                  (aiInterviewData?.evaluation?.overall_feedback as string | undefined) ||
                                  "Thank you for completing your AI interview. Your structured responses and synthesized evaluation have been recorded for the recruiting team."
                                }
                              />
                              {Array.isArray(aiInterviewData?.evaluation?.key_strengths) && aiInterviewData.evaluation.key_strengths.length > 0 ? (
                                <div>
                                  <small style={{ fontWeight: 600, color: "var(--color-text-secondary, #64748b)" }}>
                                    Key Strengths:
                                  </small>
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.25rem" }}>
                                    {aiInterviewData.evaluation.key_strengths.map((s: string, idx: number) => (
                                      <Badge key={idx} tone="success">
                                        {s}
                                      </Badge>
                                    ))}
                                  </div>
                                </div>
                              ) : null}
                            </Stack>
                          ) : null}

                          {!aiInterviewLoading && aiInterviewData && aiInterviewData.status !== "completed" && selectedApplication.interview_score == null ? (
                            <Stack gap="3">
                              <p style={{ color: "var(--color-text-secondary, #64748b)" }}>
                                Please provide thoughtful, detailed answers to the structured interview questions below for <strong>{selectedApplication.job_title}</strong>. Your responses will be objectively evaluated by the AI Copilot.
                              </p>

                              <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
                                {aiInterviewData.questions.map((q, qIndex) => (
                                  <div
                                    key={q.id}
                                    style={{
                                      border: "1px solid var(--color-border, #e2e8f0)",
                                      borderRadius: "8px",
                                      padding: "1rem",
                                      background: "var(--color-surface, #ffffff)",
                                    }}
                                  >
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                                      <strong>
                                        Question {qIndex + 1}: {q.question}
                                      </strong>
                                      <Badge tone="neutral">{q.competency || q.category}</Badge>
                                    </div>
                                    {q.context ? (
                                      <small style={{ color: "var(--color-text-secondary, #64748b)", display: "block", marginBottom: "0.5rem" }}>
                                        {q.context}
                                      </small>
                                    ) : null}
                                    <textarea
                                      rows={4}
                                      placeholder="Type your response here... (elaborate with specific technical and situational details)"
                                      value={aiInterviewAnswers[q.id] || ""}
                                      onChange={(e) =>
                                        setAiInterviewAnswers((prev) => ({
                                          ...prev,
                                          [q.id]: e.target.value,
                                        }))
                                      }
                                      style={{
                                        width: "100%",
                                        padding: "0.6rem",
                                        borderRadius: "6px",
                                        border: "1px solid var(--color-border, #cbd5e1)",
                                        fontSize: "0.9rem",
                                        fontFamily: "inherit",
                                        resize: "vertical",
                                      }}
                                    />
                                  </div>
                                ))}
                              </div>

                              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.5rem" }}>
                                <Button
                                  variant="primary"
                                  disabled={
                                    aiInterviewSubmitting ||
                                    Object.values(aiInterviewAnswers).filter((v) => v.trim().length > 0).length <
                                      (aiInterviewData?.questions?.length || 1)
                                  }
                                  onClick={() => void handleSubmitAIInterview()}
                                >
                                  {aiInterviewSubmitting ? "Submitting Interview..." : "Submit Interview Responses"}
                                </Button>
                              </div>
                            </Stack>
                          ) : null}
                        </Stack>
                      </Section>
                    </>
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
