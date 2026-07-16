import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Alert,
  AnalyticsWidget,
  AppLayout,
  Badge,
  Button,
  ContentContainer,
  EmptyState,
  ErrorState,
  FormActions,
  FormWrapper,
  Grid,
  Header,
  Input,
  LoadingState,
  MetricCard,
  Pagination,
  Section,
  Select,
  Stack,
  Table,
  Tabs,
  Textarea,
  Timeline,
  type TimelineItem,
} from "../components";
import "./interview-management.css";

type InterviewStatus = "scheduled" | "in_progress" | "completed" | "cancelled" | "needs_review" | string;

interface InterviewRecord {
  id: string;
  candidate_id?: string;
  candidate_name?: string;
  job_id?: string;
  job_title?: string;
  interviewer_id?: string;
  interviewer_name?: string;
  mode?: string;
  status?: InterviewStatus;
  scheduled_at?: string;
  started_at?: string;
  ended_at?: string;
  duration_minutes?: number;
  ai_evaluation_summary?: string;
  evaluation_summary?: string;
  recruiter_feedback?: string;
  score?: number;
  confidence?: number;
  questions?: Array<{ id?: string; text?: string; level?: string; rubric?: string }>;
  responses?: Array<{ id?: string; question?: string; answer?: string; timestamp?: string; score?: number }>;
  timeline?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

interface CandidateRecord {
  id: string;
  full_name?: string;
  email?: string;
}

interface JobRecord {
  id: string;
  title?: string;
}

interface ScheduleFormState {
  candidate_id: string;
  job_id: string;
  interviewer_name: string;
  mode: string;
  scheduled_at: string;
  status: InterviewStatus;
}

interface FeedbackFormState {
  feedback: string;
  score: string;
}

const INTERVIEWS_ENDPOINT = "/interviews";
const CANDIDATES_ENDPOINT = "/candidates";
const JOBS_ENDPOINT = "/jobs";

const STATUS_OPTIONS: Array<{ value: InterviewStatus; label: string }> = [
  { value: "scheduled", label: "Scheduled" },
  { value: "in_progress", label: "In Progress" },
  { value: "needs_review", label: "Needs Review" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

function formatDate(value?: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusTone(status?: string): "neutral" | "brand" | "success" | "warning" | "danger" {
  const normalized = String(status ?? "").toLowerCase();
  if (normalized.includes("completed")) return "success";
  if (normalized.includes("cancel") || normalized.includes("reject")) return "danger";
  if (normalized.includes("review") || normalized.includes("progress")) return "warning";
  if (normalized.includes("scheduled")) return "brand";
  return "neutral";
}

function getScheduleDefaults(): ScheduleFormState {
  const nextHour = new Date();
  nextHour.setHours(nextHour.getHours() + 1);
  nextHour.setMinutes(0, 0, 0);

  return {
    candidate_id: "",
    job_id: "",
    interviewer_name: "",
    mode: "video",
    scheduled_at: nextHour.toISOString().slice(0, 16),
    status: "scheduled",
  };
}

function getFeedbackDefaults(): FeedbackFormState {
  return {
    feedback: "",
    score: "",
  };
}

function toTimelineItems(interview: InterviewRecord | null): TimelineItem[] {
  if (!interview) return [];

  const source = Array.isArray(interview.timeline) ? interview.timeline : Array.isArray(interview.responses) ? interview.responses : [];

  return source.map((item, index) => {
    const question = String((item.question as string | undefined) ?? (item.action as string | undefined) ?? "Interview activity");
    const answer = String((item.answer as string | undefined) ?? (item.detail as string | undefined) ?? "");
    const timestamp = typeof item.timestamp === "string" ? item.timestamp : undefined;

    return {
      id: String((item.id as string | undefined) ?? `${question}-${index}`),
      title: question,
      description: answer,
      timestamp,
      meta: item.score !== undefined ? `Score: ${item.score}` : undefined,
    };
  });
}

function extractAiEvaluationSummary(interview: InterviewRecord | null): string {
  if (!interview) return "";
  const direct = interview.ai_evaluation_summary ?? interview.evaluation_summary;
  if (typeof direct === "string") return direct;

  const payload = (interview.evaluation as Record<string, unknown> | undefined) ?? {};
  const nested = payload.summary ?? payload.ai_summary ?? payload.overview;
  return typeof nested === "string" ? nested : "";
}

function normalizeQuestions(interview: InterviewRecord | null): Array<{ id: string; text: string; level: string; rubric?: string }> {
  if (!interview) return [];

  const direct = Array.isArray(interview.questions) ? interview.questions : [];
  if (direct.length) {
    return direct.map((question, index) => ({
      id: String(question.id ?? `q-${index}`),
      text: String(question.text ?? ""),
      level: String(question.level ?? "medium"),
      rubric: question.rubric,
    }));
  }

  const generated = (interview.ai_questions as Array<Record<string, unknown>> | undefined) ?? [];
  return generated.map((question, index) => ({
    id: String(question.id ?? `ai-${index}`),
    text: String(question.text ?? question.prompt ?? ""),
    level: String(question.level ?? question.difficulty ?? "medium"),
    rubric: typeof question.rubric === "string" ? question.rubric : undefined,
  }));
}

export default function InterviewManagementPage() {
  const [interviews, setInterviews] = useState<InterviewRecord[]>([]);
  const [candidates, setCandidates] = useState<CandidateRecord[]>([]);
  const [jobs, setJobs] = useState<JobRecord[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"scheduled" | "status" | "candidate">("scheduled");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedInterviewId, setSelectedInterviewId] = useState<string | null>(null);

  const [scheduleForm, setScheduleForm] = useState<ScheduleFormState>(getScheduleDefaults);
  const [feedbackForm, setFeedbackForm] = useState<FeedbackFormState>(getFeedbackDefaults);

  const [formMode, setFormMode] = useState<"create" | "edit">("create");
  const [formLoading, setFormLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [bulkStatus, setBulkStatus] = useState<InterviewStatus>("scheduled");

  const loadFoundationData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [interviewsRes, candidatesRes, jobsRes] = await Promise.all([
        fetch(INTERVIEWS_ENDPOINT, { headers: { Accept: "application/json" } }),
        fetch(CANDIDATES_ENDPOINT, { headers: { Accept: "application/json" } }),
        fetch(JOBS_ENDPOINT, { headers: { Accept: "application/json" } }),
      ]);

      if (!interviewsRes.ok) {
        throw new Error(`Failed to load interviews (${interviewsRes.status})`);
      }

      const interviewsPayload = (await interviewsRes.json()) as InterviewRecord[];
      setInterviews(Array.isArray(interviewsPayload) ? interviewsPayload : []);

      if (candidatesRes.ok) {
        const candidatesPayload = (await candidatesRes.json()) as CandidateRecord[];
        setCandidates(Array.isArray(candidatesPayload) ? candidatesPayload : []);
      } else {
        setCandidates([]);
      }

      if (jobsRes.ok) {
        const jobsPayload = (await jobsRes.json()) as JobRecord[];
        setJobs(Array.isArray(jobsPayload) ? jobsPayload : []);
      } else {
        setJobs([]);
      }

      if (!selectedInterviewId && interviewsPayload.length) {
        setSelectedInterviewId(String(interviewsPayload[0].id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load interview management data");
      setInterviews([]);
      setCandidates([]);
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, [selectedInterviewId]);

  useEffect(() => {
    void loadFoundationData();
  }, [loadFoundationData]);

  const filteredInterviews = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    const filtered = interviews.filter((interview) => {
      const matchesQuery =
        !normalized ||
        String(interview.candidate_name ?? "").toLowerCase().includes(normalized) ||
        String(interview.job_title ?? "").toLowerCase().includes(normalized) ||
        String(interview.interviewer_name ?? "").toLowerCase().includes(normalized) ||
        String(interview.id ?? "").toLowerCase().includes(normalized);

      const matchesStatus = statusFilter === "all" || String(interview.status ?? "") === statusFilter;
      return matchesQuery && matchesStatus;
    });

    const sorted = [...filtered].sort((a, b) => {
      const direction = sortOrder === "asc" ? 1 : -1;

      if (sortBy === "candidate") {
        return String(a.candidate_name ?? "").localeCompare(String(b.candidate_name ?? "")) * direction;
      }

      if (sortBy === "status") {
        return String(a.status ?? "").localeCompare(String(b.status ?? "")) * direction;
      }

      return String(a.scheduled_at ?? "").localeCompare(String(b.scheduled_at ?? "")) * direction;
    });

    return sorted;
  }, [interviews, query, statusFilter, sortBy, sortOrder]);

  const total = filteredInterviews.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pagedInterviews = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredInterviews.slice(start, start + pageSize);
  }, [filteredInterviews, page, pageSize]);

  const selectedInterview = useMemo(
    () => interviews.find((item) => item.id === selectedInterviewId) ?? null,
    [interviews, selectedInterviewId],
  );

  const allPageSelected = pagedInterviews.length > 0 && pagedInterviews.every((item) => selectedIds.includes(item.id));

  const timelineItems = useMemo(() => toTimelineItems(selectedInterview), [selectedInterview]);
  const aiEvaluationSummary = useMemo(() => extractAiEvaluationSummary(selectedInterview), [selectedInterview]);
  const questionItems = useMemo(() => normalizeQuestions(selectedInterview), [selectedInterview]);

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    interviews.forEach((interview) => {
      const key = String(interview.status ?? "unknown");
      map.set(key, (map.get(key) ?? 0) + 1);
    });
    return {
      total: interviews.length,
      scheduled: map.get("scheduled") ?? 0,
      inProgress: map.get("in_progress") ?? 0,
      completed: map.get("completed") ?? 0,
      needsReview: map.get("needs_review") ?? 0,
    };
  }, [interviews]);

  const candidateOptions = candidates.map((candidate) => ({
    value: candidate.id,
    label: candidate.full_name || candidate.email || candidate.id,
  }));

  const jobOptions = jobs.map((job) => ({ value: job.id, label: job.title || job.id }));

  const setScheduleField = <K extends keyof ScheduleFormState>(field: K, value: ScheduleFormState[K]) => {
    setScheduleForm((prev) => ({ ...prev, [field]: value }));
  };

  const setFeedbackField = <K extends keyof FeedbackFormState>(field: K, value: FeedbackFormState[K]) => {
    setFeedbackForm((prev) => ({ ...prev, [field]: value }));
  };

  const resetScheduleForm = () => {
    setFormMode("create");
    setScheduleForm(getScheduleDefaults());
    setFormError(null);
  };

  const loadFormFromSelected = () => {
    if (!selectedInterview) return;
    setFormMode("edit");
    setFormError(null);
    setScheduleForm({
      candidate_id: String(selectedInterview.candidate_id ?? ""),
      job_id: String(selectedInterview.job_id ?? ""),
      interviewer_name: String(selectedInterview.interviewer_name ?? ""),
      mode: String(selectedInterview.mode ?? "video"),
      scheduled_at: String(selectedInterview.scheduled_at ?? "").slice(0, 16),
      status: String(selectedInterview.status ?? "scheduled"),
    });
  };

  const submitSchedule = async () => {
    setFormLoading(true);
    setFormError(null);

    try {
      const payload = {
        candidate_id: scheduleForm.candidate_id,
        job_id: scheduleForm.job_id,
        interviewer_name: scheduleForm.interviewer_name,
        mode: scheduleForm.mode,
        scheduled_at: scheduleForm.scheduled_at,
        status: scheduleForm.status,
      };

      if (formMode === "create") {
        const response = await fetch(INTERVIEWS_ENDPOINT, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error(`Failed to schedule interview (${response.status})`);
        }

        const created = (await response.json()) as InterviewRecord;
        await loadFoundationData();
        setSelectedInterviewId(created.id);
        resetScheduleForm();
        return;
      }

      if (!selectedInterview?.id) {
        throw new Error("No selected interview to update");
      }

      const response = await fetch(`${INTERVIEWS_ENDPOINT}/${selectedInterview.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`Failed to update interview (${response.status})`);
      }

      await loadFoundationData();
      resetScheduleForm();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to save interview schedule");
    } finally {
      setFormLoading(false);
    }
  };

  const deleteInterview = async (id: string) => {
    await fetch(`${INTERVIEWS_ENDPOINT}/${id}`, { method: "DELETE" });
  };

  const deleteSelectedInterviews = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;

    await Promise.all(ids.map((id) => deleteInterview(id)));
    setSelectedIds([]);
    await loadFoundationData();

    if (selectedInterviewId && ids.includes(selectedInterviewId)) {
      setSelectedInterviewId(null);
    }
  };

  const updateInterviewStatus = async (id: string, status: InterviewStatus) => {
    await fetch(`${INTERVIEWS_ENDPOINT}/${id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ status }),
    });
  };

  const applyBulkStatus = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;

    await Promise.all(ids.map((id) => updateInterviewStatus(id, bulkStatus)));
    setSelectedIds([]);
    await loadFoundationData();
  };

  const submitFeedback = async () => {
    if (!selectedInterview?.id) return;

    await fetch(`${INTERVIEWS_ENDPOINT}/${selectedInterview.id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        recruiter_feedback: feedbackForm.feedback,
        score: feedbackForm.score ? Number(feedbackForm.score) : undefined,
        status: "needs_review",
      }),
    });

    setFeedbackForm(getFeedbackDefaults());
    await loadFoundationData();
  };

  const loadAiQuestions = async () => {
    if (!selectedInterview?.id) return;

    await fetch(`${INTERVIEWS_ENDPOINT}/${selectedInterview.id}/ai-questions`, {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    });

    await loadFoundationData();
  };

  const pushMockResponse = async () => {
    if (!selectedInterview?.id) return;

    await fetch(`${INTERVIEWS_ENDPOINT}/${selectedInterview.id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        responses: [
          ...(Array.isArray(selectedInterview.responses) ? selectedInterview.responses : []),
          {
            id: `r-${Date.now()}`,
            question: questionItems[0]?.text ?? "Adaptive follow-up",
            answer: "Candidate response captured from workspace.",
            timestamp: new Date().toISOString(),
          },
        ],
      }),
    });

    await loadFoundationData();
  };

  return (
    <AppLayout
      className="interview-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="interview-title">Interview Management</h1>
              <p className="interview-subtitle">Coordinate interviews, adaptive sessions, AI questions, evaluation summaries, and recruiter feedback.</p>
            </Stack>
          }
          right={
            <div className="interview-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadFoundationData()}>
                Refresh
              </Button>
              <Button size="sm" onClick={resetScheduleForm}>
                New Interview
              </Button>
              <Button variant="secondary" size="sm" disabled={!selectedInterview} onClick={loadFormFromSelected}>
                Edit Selected
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="interview-main" fluid>
        {loading ? <LoadingState title="Loading interviews" description="Fetching interview data, candidates, and jobs." /> : null}
        {!loading && error ? <ErrorState title="Unable to load interviews" description={error} onRetry={() => void loadFoundationData()} /> : null}
        {!loading && !error && !interviews.length ? (
          <EmptyState
            title="No interviews available"
            description="Schedule an interview to start adaptive sessions and evaluation tracking."
            actionLabel="Reload"
            onAction={() => void loadFoundationData()}
          />
        ) : null}

        {!loading && !error && interviews.length ? (
          <Stack gap="5">
            <section aria-label="Interview dashboard">
              <div className="interview-dashboard-grid">
                <MetricCard label="Total Interviews" value={counts.total} meta="Across all statuses" />
                <MetricCard label="Scheduled" value={counts.scheduled} meta="Upcoming interviews" trendTone="brand" />
                <MetricCard label="In Progress" value={counts.inProgress} meta="Active sessions" trendTone="warning" />
                <MetricCard label="Completed" value={counts.completed} meta="Finished interviews" trendTone="success" />
              </div>
            </section>

            <Section>
              <div className="interview-toolbar">
                <Input label="Search Interviews" placeholder="Search by candidate, job, interviewer, or ID" value={query} onChange={(event) => setQuery(event.target.value)} />
                <Select
                  label="Status"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  options={[
                    { value: "all", label: "All Statuses" },
                    ...STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label })),
                  ]}
                />
                <Select
                  label="Sort"
                  value={`${sortBy}:${sortOrder}`}
                  onChange={(event) => {
                    const [nextSortBy, nextSortOrder] = event.target.value.split(":") as [typeof sortBy, typeof sortOrder];
                    setSortBy(nextSortBy);
                    setSortOrder(nextSortOrder);
                  }}
                  options={[
                    { value: "scheduled:desc", label: "Scheduled (Newest)" },
                    { value: "scheduled:asc", label: "Scheduled (Oldest)" },
                    { value: "candidate:asc", label: "Candidate (A-Z)" },
                    { value: "candidate:desc", label: "Candidate (Z-A)" },
                    { value: "status:asc", label: "Status (A-Z)" },
                    { value: "status:desc", label: "Status (Z-A)" },
                  ]}
                />
                <Select
                  label="Page Size"
                  value={String(pageSize)}
                  onChange={(event) => {
                    setPageSize(Number(event.target.value));
                    setPage(1);
                  }}
                  options={[
                    { value: "10", label: "10" },
                    { value: "20", label: "20" },
                    { value: "50", label: "50" },
                  ]}
                />
              </div>
            </Section>

            <Section>
              <div className="interview-bulk">
                <Badge tone="neutral">Selected: {selectedIds.length}</Badge>
                <Select
                  value={bulkStatus}
                  onChange={(event) => setBulkStatus(event.target.value)}
                  options={STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                />
                <Button size="sm" variant="secondary" disabled={!selectedIds.length} onClick={() => void applyBulkStatus()}>
                  Apply Status
                </Button>
                <Button size="sm" variant="danger" disabled={!selectedIds.length} onClick={() => void deleteSelectedInterviews()}>
                  Delete Selected
                </Button>
              </div>
            </Section>

            <Grid columns={{ mobile: 1, lg: 2 }} gap="4">
              <Section>
                <Table
                  columns={[
                    {
                      key: "select",
                      header: (
                        <input
                          type="checkbox"
                          aria-label="Select all interviews on page"
                          checked={allPageSelected}
                          onChange={(event) => {
                            if (event.target.checked) {
                              setSelectedIds((prev) => Array.from(new Set([...prev, ...pagedInterviews.map((item) => item.id)])));
                            } else {
                              setSelectedIds((prev) => prev.filter((id) => !pagedInterviews.some((item) => item.id === id)));
                            }
                          }}
                        />
                      ),
                      render: (row: InterviewRecord) => (
                        <input
                          type="checkbox"
                          aria-label={`Select interview ${row.id}`}
                          checked={selectedIds.includes(row.id)}
                          onChange={(event) => {
                            setSelectedIds((prev) => {
                              if (event.target.checked) return Array.from(new Set([...prev, row.id]));
                              return prev.filter((id) => id !== row.id);
                            });
                          }}
                        />
                      ),
                      width: "3rem",
                    },
                    {
                      key: "candidate_name",
                      header: "Candidate",
                      render: (row: InterviewRecord) => (
                        <button
                          type="button"
                          className="ui-btn ui-btn-ghost ui-btn-sm"
                          style={{ justifyContent: "flex-start", paddingInline: 0 }}
                          onClick={() => setSelectedInterviewId(row.id)}
                        >
                          {row.candidate_name || row.candidate_id || "Unknown"}
                        </button>
                      ),
                    },
                    { key: "job_title", header: "Job" },
                    {
                      key: "status",
                      header: "Status",
                      render: (row: InterviewRecord) => <Badge tone={statusTone(row.status)}>{row.status ?? "unknown"}</Badge>,
                    },
                    {
                      key: "scheduled_at",
                      header: "Scheduled",
                      render: (row: InterviewRecord) => formatDate(row.scheduled_at),
                    },
                  ]}
                  data={pagedInterviews}
                  rowKey="id"
                  caption="Interview list"
                />
                <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} showPageButtons siblingCount={1} />
              </Section>

              <Section>
                {!selectedInterview ? <EmptyState title="Select an interview" description="Choose an interview from the list to open detail workspace." /> : null}

                {selectedInterview ? (
                  <Stack gap="4" className="interview-detail">
                    <Alert
                      tone="info"
                      title={`${selectedInterview.candidate_name ?? selectedInterview.candidate_id ?? "Candidate"} • ${selectedInterview.job_title ?? selectedInterview.job_id ?? "Job"}`}
                      description={`Interviewer: ${selectedInterview.interviewer_name ?? selectedInterview.interviewer_id ?? "Unassigned"}`}
                    >
                      <div className="interview-actions">
                        <Badge tone={statusTone(selectedInterview.status)}>{selectedInterview.status ?? "unknown"}</Badge>
                        {STATUS_OPTIONS.map((option) => (
                          <Button
                            key={option.value}
                            size="sm"
                            variant={String(option.value) === String(selectedInterview.status) ? "primary" : "secondary"}
                            onClick={() => void updateInterviewStatus(selectedInterview.id, option.value)}
                          >
                            {option.label}
                          </Button>
                        ))}
                      </div>
                    </Alert>

                    <AnalyticsWidget title="Interview Detail View" description="Interview metadata and session signals">
                      <div className="interview-meta">
                        <p className="interview-subtitle">Interview ID: {selectedInterview.id}</p>
                        <p className="interview-subtitle">Scheduled: {formatDate(selectedInterview.scheduled_at)}</p>
                        <p className="interview-subtitle">Started: {formatDate(selectedInterview.started_at)}</p>
                        <p className="interview-subtitle">Ended: {formatDate(selectedInterview.ended_at)}</p>
                        <p className="interview-subtitle">Mode: {selectedInterview.mode ?? "-"}</p>
                      </div>
                    </AnalyticsWidget>

                    <Tabs.Root defaultValue="workspace">
                      <Tabs.List>
                        <Tabs.Trigger value="workspace">Adaptive Session Workspace</Tabs.Trigger>
                        <Tabs.Trigger value="questions">AI Questions</Tabs.Trigger>
                        <Tabs.Trigger value="timeline">Response Timeline</Tabs.Trigger>
                        <Tabs.Trigger value="evaluation">AI Evaluation + Feedback</Tabs.Trigger>
                      </Tabs.List>

                      <Tabs.Panel value="workspace">
                        <AnalyticsWidget title="Adaptive Interview Session Workspace" description="Run and track adaptive interview progression">
                          <div className="interview-actions">
                            <Button onClick={() => void loadAiQuestions()}>Generate AI Questions</Button>
                            <Button variant="secondary" onClick={() => void pushMockResponse()}>
                              Capture Candidate Response
                            </Button>
                          </div>
                        </AnalyticsWidget>
                      </Tabs.Panel>

                      <Tabs.Panel value="questions">
                        <AnalyticsWidget title="AI-Generated Interview Questions" description="Question list sourced from AI interview engine outputs">
                          {questionItems.length ? (
                            <div className="interview-question-list">
                              {questionItems.map((question) => (
                                <article key={question.id} className="interview-question-item">
                                  <Stack gap="2">
                                    <Badge tone="brand">{question.level}</Badge>
                                    <strong>{question.text}</strong>
                                    {question.rubric ? <p className="interview-subtitle">Rubric: {question.rubric}</p> : null}
                                  </Stack>
                                </article>
                              ))}
                            </div>
                          ) : (
                            <EmptyState title="No AI questions" description="Generate questions to start adaptive interview sessions." />
                          )}
                        </AnalyticsWidget>
                      </Tabs.Panel>

                      <Tabs.Panel value="timeline">
                        <AnalyticsWidget title="Candidate Response Timeline" description="Chronological response and event view">
                          {timelineItems.length ? (
                            <Timeline items={timelineItems} />
                          ) : (
                            <EmptyState title="No timeline events" description="Candidate response timeline will appear as the session progresses." />
                          )}
                        </AnalyticsWidget>
                      </Tabs.Panel>

                      <Tabs.Panel value="evaluation">
                        <Stack gap="4">
                          <AnalyticsWidget title="AI Evaluation Summary" description="Evaluation intelligence overview from interview outputs">
                            {aiEvaluationSummary ? (
                              <Alert tone="success" description={aiEvaluationSummary} />
                            ) : (
                              <EmptyState title="No AI evaluation summary" description="Evaluation summary is not yet available for this interview." />
                            )}
                          </AnalyticsWidget>

                          <AnalyticsWidget title="Recruiter Feedback Panel" description="Capture recruiter notes and score for review and decisioning">
                            <FormWrapper
                              onSubmit={(event) => {
                                event.preventDefault();
                                void submitFeedback();
                              }}
                            >
                              <div className="interview-feedback-grid">
                                <Textarea
                                  label="Recruiter Feedback"
                                  value={feedbackForm.feedback}
                                  onChange={(event) => setFeedbackField("feedback", event.target.value)}
                                  placeholder="Add strengths, concerns, and decision notes"
                                />
                                <Input
                                  label="Score"
                                  type="number"
                                  min={0}
                                  max={100}
                                  value={feedbackForm.score}
                                  onChange={(event) => setFeedbackField("score", event.target.value)}
                                  placeholder="0 - 100"
                                />
                              </div>
                              <FormActions submitLabel="Save Feedback" />
                            </FormWrapper>
                          </AnalyticsWidget>
                        </Stack>
                      </Tabs.Panel>
                    </Tabs.Root>
                  </Stack>
                ) : null}
              </Section>
            </Grid>

            <Section>
              <Stack gap="3">
                <strong>{formMode === "create" ? "Interview Scheduling" : "Edit Interview Schedule"}</strong>
                {formError ? <Alert tone="danger" title="Scheduling error" description={formError} /> : null}

                <FormWrapper
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submitSchedule();
                  }}
                >
                  <div className="interview-form-grid">
                    <Select
                      label="Candidate"
                      value={scheduleForm.candidate_id}
                      onChange={(event) => setScheduleField("candidate_id", event.target.value)}
                      options={candidateOptions.length ? candidateOptions : [{ value: "", label: "No candidates" }]}
                    />
                    <Select
                      label="Job"
                      value={scheduleForm.job_id}
                      onChange={(event) => setScheduleField("job_id", event.target.value)}
                      options={jobOptions.length ? jobOptions : [{ value: "", label: "No jobs" }]}
                    />
                    <Input
                      label="Interviewer"
                      value={scheduleForm.interviewer_name}
                      onChange={(event) => setScheduleField("interviewer_name", event.target.value)}
                      placeholder="Interviewer name"
                    />
                    <Select
                      label="Interview Mode"
                      value={scheduleForm.mode}
                      onChange={(event) => setScheduleField("mode", event.target.value)}
                      options={[
                        { value: "video", label: "Video" },
                        { value: "voice", label: "Voice" },
                        { value: "onsite", label: "Onsite" },
                        { value: "async", label: "Async" },
                      ]}
                    />
                    <Input
                      label="Scheduled At"
                      type="datetime-local"
                      value={scheduleForm.scheduled_at}
                      onChange={(event) => setScheduleField("scheduled_at", event.target.value)}
                    />
                    <Select
                      label="Status"
                      value={scheduleForm.status}
                      onChange={(event) => setScheduleField("status", event.target.value)}
                      options={STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                    />
                  </div>

                  <FormActions
                    submitting={formLoading}
                    submitLabel={formMode === "create" ? "Schedule Interview" : "Save Interview"}
                    cancelLabel={formMode === "create" ? "Reset" : "Cancel Edit"}
                    onCancel={resetScheduleForm}
                  />
                </FormWrapper>
              </Stack>
            </Section>
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}
