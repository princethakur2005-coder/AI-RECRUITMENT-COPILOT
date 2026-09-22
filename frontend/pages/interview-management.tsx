import { authFetch } from "../lib/api";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  AppLayout,
  Badge,
  Button,
  ContentContainer,
  EmptyState,
  ErrorState,
  Header,
  InterviewAIAnalysisPanel,
  LoadingState,
  Section,
  Select,
  Stack,
  Table,
} from "../components";
import type { InterviewRecord, InterviewStatus } from "../components/ApplicationInterviewPanel";

const INTERVIEWS_ENDPOINT = "/api/v1/interviews";

function formatDateTime(value?: string): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatStatus(status: string): string {
  return status.replaceAll("_", " ");
}

function statusTone(status: InterviewStatus): "neutral" | "brand" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "cancelled") return "danger";
  if (status === "no_show") return "warning";
  if (status === "scheduled") return "brand";
  return "neutral";
}

export default function InterviewManagementPage() {
  const [interviews, setInterviews] = useState<InterviewRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [actionId, setActionId] = useState<string | null>(null);
  const [aiPanelInterviewId, setAiPanelInterviewId] = useState<string | null>(null);

  const loadInterviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let response = await authFetch(INTERVIEWS_ENDPOINT, { headers: { Accept: "application/json" } });
      if (!response.ok && response.status === 404) {
        response = await authFetch("/interviews", { headers: { Accept: "application/json" } });
      }
      if (!response.ok) {
        throw new Error(`Failed to load interviews (${response.status})`);
      }
      const payload = (await response.json()) as InterviewRecord[];
      setInterviews(Array.isArray(payload) ? payload : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load interviews");
      setInterviews([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadInterviews();
  }, [loadInterviews]);

  const filtered = useMemo(() => {
    if (statusFilter === "all") return interviews;
    return interviews.filter((item) => item.status === statusFilter);
  }, [interviews, statusFilter]);

  const aiPanelInterview = useMemo(
    () => interviews.find((item) => item.id === aiPanelInterviewId) ?? null,
    [interviews, aiPanelInterviewId],
  );

  const updateStatus = async (interviewId: string, status: InterviewStatus) => {
    setActionId(interviewId);
    setError(null);
    try {
      const response = await authFetch(`/interviews/${interviewId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Update failed (${response.status})`);
      }
      await loadInterviews();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update interview");
    } finally {
      setActionId(null);
    }
  };

  return (
    <AppLayout
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="recruiter-dashboard-title">Interview Management</h1>
              <p className="recruiter-dashboard-subtitle">Company interview schedule and status</p>
            </Stack>
          }
          right={
            <Button variant="secondary" size="sm" onClick={() => void loadInterviews()}>
              Refresh
            </Button>
          }
        />
      }
    >
      <ContentContainer fluid>
        {loading ? <LoadingState title="Loading interviews" description="Fetching scheduled interviews." /> : null}
        {!loading && error ? (
          <ErrorState title="Unable to load interviews" description={error} onRetry={() => void loadInterviews()} />
        ) : null}

        {!loading && !error ? (
          <Stack gap="4">
            <Section>
              <Select
                label="Filter by status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                options={[
                  { value: "all", label: "All statuses" },
                  { value: "scheduled", label: "Scheduled" },
                  { value: "completed", label: "Completed" },
                  { value: "cancelled", label: "Cancelled" },
                  { value: "no_show", label: "No show" },
                ]}
              />
            </Section>

            {filtered.length ? (
              <Table
                columns={[
                  { key: "candidate", header: "Candidate" },
                  { key: "job", header: "Job" },
                  { key: "type", header: "Type" },
                  { key: "schedule", header: "Schedule" },
                  { key: "interviewer", header: "Interviewer" },
                  { key: "score", header: "AI Score" },
                  { key: "status", header: "Status" },
                  { key: "actions", header: "Actions" },
                ]}
                data={filtered.map((interview) => ({
                  id: interview.id,
                  candidate: interview.application?.candidate_name ?? "—",
                  job: interview.application?.job_title ?? "—",
                  type: formatStatus(interview.interview_type),
                  schedule: `${formatDateTime(interview.scheduled_start)} (${interview.timezone})`,
                  interviewer:
                    interview.interviewer?.full_name ??
                    (interview.interview_type === "ai_screening" ? "AI Copilot" : "—"),
                  score:
                    interview.interview_score != null ? (
                      <Badge tone={interview.interview_score >= 60 ? "success" : "warning"}>
                        {interview.interview_score}%
                      </Badge>
                    ) : (
                      "—"
                    ),
                  status: (
                    <Badge tone={statusTone(interview.status)}>{formatStatus(interview.status)}</Badge>
                  ),
                  actions: (
                    <Stack gap="1">
                      <Link href={`/application/${interview.application_id}`}>View application</Link>
                      {interview.status === "scheduled" ? (
                        <>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={actionId === interview.id}
                            onClick={() => void updateStatus(interview.id, "cancelled")}
                          >
                            Cancel
                          </Button>
                          <Button
                            size="sm"
                            disabled={actionId === interview.id}
                            onClick={() => void updateStatus(interview.id, "completed")}
                          >
                            Complete
                          </Button>
                        </>
                      ) : null}
                      {interview.status === "completed" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            setAiPanelInterviewId((current) =>
                              current === interview.id ? null : interview.id,
                            )
                          }
                        >
                          {aiPanelInterviewId === interview.id ? "Hide intelligence" : "Interview intelligence"}
                        </Button>
                      ) : null}
                    </Stack>
                  ),
                }))}
                rowKey="id"
              />
            ) : (
              <EmptyState
                title="No interviews found"
                description="Schedule interviews from the job application pipeline or application detail page."
              />
            )}

            {aiPanelInterview ? (
              <Section elevated>
                <Stack gap="3">
                  <h2 className="recruiter-dashboard-title">
                    Interview intelligence — {aiPanelInterview.application?.candidate_name ?? "Candidate"}
                  </h2>
                  <p className="job-application-card-meta">
                    {formatStatus(aiPanelInterview.interview_type)} ·{" "}
                    {formatDateTime(aiPanelInterview.scheduled_start)}
                    {aiPanelInterview.interview_score != null
                      ? ` · Score: ${aiPanelInterview.interview_score}%`
                      : ""}
                  </p>
                  <InterviewAIAnalysisPanel
                    interviewId={aiPanelInterview.id}
                    interviewStatus={aiPanelInterview.status}
                    applicationStatus={aiPanelInterview.application?.status}
                  />
                  {Array.isArray(aiPanelInterview.questions_json) &&
                  aiPanelInterview.questions_json.length > 0 &&
                  aiPanelInterview.answers_json ? (
                    <div style={{ marginTop: "1rem" }}>
                      <h3 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: "0.75rem" }}>
                        Interview Q&A Transcript
                      </h3>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                        {aiPanelInterview.questions_json.map((q: any, idx: number) => {
                          const answer = aiPanelInterview.answers_json?.[q.id] || "No answer provided.";
                          return (
                            <div
                              key={q.id || idx}
                              style={{
                                border: "1px solid var(--color-border, #e2e8f0)",
                                borderRadius: "6px",
                                padding: "0.75rem",
                                background: "var(--color-bg-subtle, #f8fafc)",
                              }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
                                <strong>
                                  Q{idx + 1} ({q.category || "General"} · {q.competency || "Core"}):
                                </strong>
                              </div>
                              <p style={{ margin: "0.25rem 0", color: "var(--color-text, #0f172a)" }}>
                                {q.question}
                              </p>
                              <div style={{ marginTop: "0.5rem", padding: "0.5rem", background: "#fff", borderRadius: "4px", border: "1px solid #e2e8f0" }}>
                                <small style={{ fontWeight: 600, color: "#64748b" }}>Candidate Response:</small>
                                <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.9rem" }}>{answer}</p>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                </Stack>
              </Section>
            ) : null}
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}
