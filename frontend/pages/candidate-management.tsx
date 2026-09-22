import { authFetch } from "../lib/api";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Alert,
  AppLayout,
  Badge,
  Button,
  ContentContainer,
  EmptyState,
  ErrorState,
  Grid,
  Header,
  Input,
  LoadingState,
  Pagination,
  Section,
  Select,
  Stack,
  Table,
  Timeline,
  type TimelineItem,
} from "../components";


type CandidateStatus =
  | "new"
  | "screening"
  | "interview"
  | "offer"
  | "hired"
  | "rejected"
  | "decision_pending"
  | "offer_pending"
  | string;

interface CandidateRecord {
  id: string;
  full_name?: string;
  email?: string;
  status?: CandidateStatus;
  job_id?: string | null;
  summary?: string;
  created_at?: string;
  updated_at?: string;
  resume_url?: string;
  resume_link?: string;
  resume_preview_url?: string;
  ai_evaluation_summary?: string;
  evaluation_summary?: string;
  hiring_recommendation_summary?: string;
  recommendation_summary?: string;
  candidate_match_summary?: string;
  match_summary?: string;
  fit_score?: number | null;
  assessment_score?: number | null;
  assessment_breakdown?: Record<string, any> | null;
  interview_score?: number | null;
  interview_feedback?: Record<string, any> | null;
  composite_score?: number | null;
  final_recommendation?: string | null;
  hiring_decision?: Record<string, any> | null;
  application_id?: string | null;
  skills?: string | null;
  matched_skills?: string[];
  missing_skills?: string[];
  [key: string]: unknown;
}

interface TimelineEvent {
  id?: string;
  timestamp?: string;
  action?: string;
  actor_id?: string;
  resource_type?: string;
  resource_id?: string;
  entity_type?: string;
  entity_id?: string;
  metadata?: Record<string, unknown>;
}

const CANDIDATES_ENDPOINT = "/candidates";

const STATUS_OPTIONS: Array<{ value: CandidateStatus; label: string }> = [
  { value: "new", label: "New" },
  { value: "screening", label: "Screening" },
  { value: "interview", label: "Interview" },
  { value: "decision_ready", label: "Decision Ready" },
  { value: "decision_pending", label: "Decision Pending" },
  { value: "offer_pending", label: "Offer Pending" },
  { value: "offered", label: "Offered" },
  { value: "offer", label: "Offer" },
  { value: "hired", label: "Hired" },
  { value: "rejected", label: "Rejected" },
];

function formatDate(value?: string): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

function statusTone(status?: string): "neutral" | "brand" | "success" | "warning" | "danger" {
  const normalized = String(status ?? "").toLowerCase();
  if (normalized.includes("hire")) return "success";
  if (normalized.includes("reject")) return "danger";
  if (normalized.includes("offer") || normalized.includes("interview") || normalized.includes("pending")) return "warning";
  if (normalized.includes("screen")) return "brand";
  return "neutral";
}

function extractResumeUrl(candidate: CandidateRecord | null): string | null {
  if (!candidate) return null;

  const direct =
    (candidate.resume_preview_url as string | undefined) ??
    (candidate.resume_url as string | undefined) ??
    (candidate.resume_link as string | undefined);

  if (direct) return direct;

  const metadata = (candidate.metadata as Record<string, unknown> | undefined) ?? {};
  const fallback = metadata.resume_url ?? metadata.resume_preview_url ?? metadata.resume_link;
  if (typeof fallback === "string") return fallback;

  if (candidate.id && (candidate.resume_path || candidate.resume_preview_url || candidate.resume_url)) {
    return `/candidates/${candidate.id}/resume`;
  }
  return null;
}

function extractEvaluationSummary(candidate: CandidateRecord | null): string {
  if (!candidate) return "";

  const direct =
    (candidate.ai_evaluation_summary as string | undefined) ??
    (candidate.evaluation_summary as string | undefined);
  if (direct) return direct;

  const payload = (candidate.evaluation_intelligence as Record<string, unknown> | undefined) ?? {};
  const summary = payload.summary ?? payload.overview;
  return typeof summary === "string" ? summary : "";
}

function extractRecommendationSummary(candidate: CandidateRecord | null): string {
  if (!candidate) return "";

  const direct =
    (candidate.hiring_recommendation_summary as string | undefined) ??
    (candidate.recommendation_summary as string | undefined);
  if (direct) return direct;

  const payload = (candidate.hiring_recommendation as Record<string, unknown> | undefined) ?? {};
  const summary = payload.summary ?? payload.recommendation;
  return typeof summary === "string" ? summary : "";
}

function extractMatchSummary(candidate: CandidateRecord | null): string {
  if (!candidate) return "";

  const direct =
    (candidate.candidate_match_summary as string | undefined) ??
    (candidate.match_summary as string | undefined);
  if (direct) return direct;

  const payload = (candidate.evaluation_intelligence as Record<string, unknown> | undefined) ?? {};
  const summary = payload.match_summary ?? payload.candidate_match_summary;
  if (typeof summary === "string") return summary;

  if (candidate.fit_score != null) {
    const matched = Array.isArray(candidate.matched_skills) ? candidate.matched_skills : [];
    const skillsPart = matched.length > 0 ? ` Matched skills: ${matched.join(", ")}.` : "";
    return `Candidate match score: ${candidate.fit_score}%.${skillsPart}`;
  }
  return "";
}

function extractCandidateSkills(candidate: CandidateRecord | null): string[] {
  if (!candidate) return [];
  if (Array.isArray(candidate.matched_skills) && candidate.matched_skills.length > 0) {
    return candidate.matched_skills;
  }
  if (typeof candidate.skills === "string" && candidate.skills.trim()) {
    return candidate.skills.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

function fitScoreTone(score?: number | null): "success" | "brand" | "warning" | "danger" | "neutral" {
  if (score == null) return "neutral";
  if (score >= 80) return "success";
  if (score >= 65) return "brand";
  if (score >= 50) return "warning";
  return "danger";
}

function toTimelineItems(events: TimelineEvent[]): TimelineItem[] {
  return events.map((event, index) => ({
    id: String(event.id ?? `${event.action ?? "event"}-${index}`),
    title: String(event.action ?? "Activity"),
    description: `${event.actor_id ?? "system"} on ${event.entity_type ?? event.resource_type ?? "candidate"}`,
    timestamp: event.timestamp,
    meta: String(event.entity_id ?? event.resource_id ?? ""),
  }));
}

export default function CandidateManagementPage() {
  const [candidates, setCandidates] = useState<CandidateRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"name" | "updated" | "status" | "composite">("updated");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);

  const [detailCandidate, setDetailCandidate] = useState<CandidateRecord | null>(null);
  const [detailTimeline, setDetailTimeline] = useState<TimelineEvent[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [pendingStatus, setPendingStatus] = useState<CandidateStatus>("screening");
  const [bulkStatus, setBulkStatus] = useState<CandidateStatus>("screening");

  const loadCandidates = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await authFetch(CANDIDATES_ENDPOINT, {
        headers: { Accept: "application/json" },
      });

      if (!response.ok) {
        throw new Error(`Failed to load candidates (${response.status})`);
      }

      const payload = (await response.json()) as CandidateRecord[];
      setCandidates(Array.isArray(payload) ? payload : []);

      if (!selectedCandidateId && payload.length) {
        setSelectedCandidateId(String(payload[0].id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load candidates");
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, [selectedCandidateId]);

  const loadCandidateDetail = useCallback(async (candidateId: string) => {
    setDetailLoading(true);
    setDetailError(null);

    try {
      const [candidateRes, timelineRes] = await Promise.all([
        authFetch(`${CANDIDATES_ENDPOINT}/${candidateId}`, { headers: { Accept: "application/json" } }),
        authFetch(`${CANDIDATES_ENDPOINT}/${candidateId}/timeline?limit=20`, { headers: { Accept: "application/json" } }),
      ]);

      if (!candidateRes.ok) {
        throw new Error(`Failed to load candidate detail (${candidateRes.status})`);
      }

      const candidatePayload = (await candidateRes.json()) as CandidateRecord;
      setDetailCandidate(candidatePayload);
      setPendingStatus((candidatePayload.status as CandidateStatus) ?? "screening");

      if (timelineRes.ok) {
        const timelinePayload = (await timelineRes.json()) as TimelineEvent[];
        setDetailTimeline(Array.isArray(timelinePayload) ? timelinePayload : []);
      } else {
        setDetailTimeline([]);
      }
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Unable to load candidate details");
      setDetailCandidate(null);
      setDetailTimeline([]);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates]);

  useEffect(() => {
    if (!selectedCandidateId) {
      setDetailCandidate(null);
      setDetailTimeline([]);
      return;
    }
    void loadCandidateDetail(selectedCandidateId);
  }, [selectedCandidateId, loadCandidateDetail]);

  const processedCandidates = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    const filtered = candidates.filter((candidate) => {
      const matchesQuery =
        !normalizedQuery ||
        String(candidate.full_name ?? "").toLowerCase().includes(normalizedQuery) ||
        String(candidate.email ?? "").toLowerCase().includes(normalizedQuery) ||
        String(candidate.id ?? "").toLowerCase().includes(normalizedQuery);

      const matchesStatus = statusFilter === "all" || String(candidate.status ?? "") === statusFilter;
      return matchesQuery && matchesStatus;
    });

    const sorted = [...filtered].sort((a, b) => {
      const direction = sortOrder === "asc" ? 1 : -1;

      if (sortBy === "composite") {
        const scoreA = a.composite_score ?? a.fit_score ?? -1;
        const scoreB = b.composite_score ?? b.fit_score ?? -1;
        return (scoreA - scoreB) * direction;
      }

      if (sortBy === "name") {
        return String(a.full_name ?? "").localeCompare(String(b.full_name ?? "")) * direction;
      }

      if (sortBy === "status") {
        return String(a.status ?? "").localeCompare(String(b.status ?? "")) * direction;
      }

      return String(a.updated_at ?? a.created_at ?? "").localeCompare(String(b.updated_at ?? b.created_at ?? "")) * direction;
    });

    return sorted;
  }, [candidates, query, statusFilter, sortBy, sortOrder]);

  const total = processedCandidates.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const pagedCandidates = useMemo(() => {
    const start = (page - 1) * pageSize;
    return processedCandidates.slice(start, start + pageSize);
  }, [processedCandidates, page, pageSize]);

  const allPageSelected = pagedCandidates.length > 0 && pagedCandidates.every((candidate) => selectedIds.includes(candidate.id));

  const timelineItems = useMemo(() => toTimelineItems(detailTimeline), [detailTimeline]);

  const resumePreviewUrl = extractResumeUrl(detailCandidate);
  const evaluationSummary = extractEvaluationSummary(detailCandidate);
  const recommendationSummary = extractRecommendationSummary(detailCandidate);
  const matchSummary = extractMatchSummary(detailCandidate);
  const candidateSkills = extractCandidateSkills(detailCandidate);

  const togglePageSelection = (checked: boolean) => {
    if (checked) {
      const ids = Array.from(new Set([...selectedIds, ...pagedCandidates.map((candidate) => candidate.id)]));
      setSelectedIds(ids);
      return;
    }

    setSelectedIds((prev) => prev.filter((id) => !pagedCandidates.some((candidate) => candidate.id === id)));
  };

  const toggleCandidateSelection = (candidateId: string, checked: boolean) => {
    setSelectedIds((prev) => {
      if (checked) {
        return Array.from(new Set([...prev, candidateId]));
      }
      return prev.filter((id) => id !== candidateId);
    });
  };

  const updateCandidateStatus = async (candidateId: string, status: CandidateStatus, applicationId?: string | null) => {
    await authFetch(`${CANDIDATES_ENDPOINT}/${candidateId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ status }),
    });

    const appId = applicationId || detailCandidate?.application_id;
    if (appId) {
      let appStatus = status;
      if (appStatus === "offer") appStatus = "offered";
      try {
        await authFetch(`/api/v1/applications/${appId}/status`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ status: appStatus }),
        });
      } catch {
        try {
          await authFetch(`/applications/${appId}/status`, {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              Accept: "application/json",
            },
            body: JSON.stringify({ status: appStatus }),
          });
        } catch {}
      }
    }
  };

  const handleQuickStatusTransition = async (status: CandidateStatus) => {
    if (!detailCandidate?.id) return;
    setPendingStatus(status);
    await updateCandidateStatus(detailCandidate.id, status, detailCandidate.application_id);
    await loadCandidates();
    await loadCandidateDetail(detailCandidate.id);
  };

  const handleApplyBulkStatus = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;

    await Promise.all(ids.map((id) => updateCandidateStatus(id, bulkStatus)));
    setSelectedIds([]);
    await loadCandidates();
    if (selectedCandidateId) {
      await loadCandidateDetail(selectedCandidateId);
    }
  };

  const handleBulkDelete = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;

    await Promise.all(
      ids.map((id) =>
        fetch(`${CANDIDATES_ENDPOINT}/${id}`, {
          method: "DELETE",
        }),
      ),
    );

    setSelectedIds([]);
    await loadCandidates();
    setSelectedCandidateId(null);
  };

  const handleUpdateDetailStatus = async () => {
    if (!detailCandidate?.id) return;
    await updateCandidateStatus(detailCandidate.id, pendingStatus, detailCandidate.application_id);
    await loadCandidates();
    await loadCandidateDetail(detailCandidate.id);
  };

  const statusOptions = [{ value: "all", label: "All Statuses" }, ...STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))];

  return (
    <AppLayout
      className="candidate-management-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="candidate-management-title">Candidate Management</h1>
              <p className="candidate-management-subtitle">Manage pipeline, evaluations, recommendations, and candidate actions</p>
            </Stack>
          }
          right={
            <Button variant="secondary" size="sm" onClick={() => void loadCandidates()}>
              Refresh
            </Button>
          }
        />
      }
    >
      <ContentContainer className="candidate-management-main" fluid>
        {loading ? <LoadingState title="Loading candidates" description="Fetching candidate records and dashboard data." /> : null}
        {!loading && error ? <ErrorState title="Unable to load candidates" description={error} onRetry={() => void loadCandidates()} /> : null}
        {!loading && !error && !candidates.length ? (
          <EmptyState
            title="No candidates found"
            description="Candidates will appear here once created in the recruitment pipeline."
            actionLabel="Reload"
            onAction={() => void loadCandidates()}
          />
        ) : null}

        {!loading && !error && candidates.length ? (
          <Stack gap="5">
            <Section>
              <div className="candidate-management-toolbar">
                <Input label="Search Candidates" placeholder="Search by name, email, or ID" value={query} onChange={(event) => setQuery(event.target.value)} />
                <Select
                  label="Status Filter"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  options={statusOptions.map((option) => ({ value: option.value, label: option.label }))}
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
                    { value: "composite:desc", label: "Composite Score (High to Low)" },
                    { value: "composite:asc", label: "Composite Score (Low to High)" },
                    { value: "updated:desc", label: "Updated (Newest)" },
                    { value: "updated:asc", label: "Updated (Oldest)" },
                    { value: "name:asc", label: "Name (A-Z)" },
                    { value: "name:desc", label: "Name (Z-A)" },
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
              <div className="candidate-management-bulk">
                <Badge tone="neutral">Selected: {selectedIds.length}</Badge>
                <Select
                  value={bulkStatus}
                  onChange={(event) => setBulkStatus(event.target.value)}
                  options={STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                />
                <Button variant="secondary" size="sm" disabled={!selectedIds.length} onClick={() => void handleApplyBulkStatus()}>
                  Apply Status
                </Button>
                <Button variant="danger" size="sm" disabled={!selectedIds.length} onClick={() => void handleBulkDelete()}>
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
                          aria-label="Select all on page"
                          checked={allPageSelected}
                          onChange={(event) => togglePageSelection(event.target.checked)}
                        />
                      ),
                      render: (row: CandidateRecord) => (
                        <input
                          type="checkbox"
                          aria-label={`Select ${row.full_name ?? row.id}`}
                          checked={selectedIds.includes(row.id)}
                          onChange={(event) => toggleCandidateSelection(row.id, event.target.checked)}
                        />
                      ),
                      width: "3rem",
                    },
                    {
                      key: "full_name",
                      header: "Candidate",
                      render: (row: CandidateRecord) => (
                        <button
                          type="button"
                          className="ui-btn ui-btn-ghost ui-btn-sm"
                          onClick={() => setSelectedCandidateId(row.id)}
                          style={{ justifyContent: "flex-start", paddingInline: 0 }}
                        >
                          {row.full_name ?? row.email ?? row.id}
                        </button>
                      ),
                    },
                    { key: "email", header: "Email" },
                    {
                      key: "status",
                      header: "Status",
                      render: (row: CandidateRecord) => <Badge tone={statusTone(row.status)}>{row.status ?? "unknown"}</Badge>,
                    },
                    {
                      key: "composite_score",
                      header: "Composite / AI Rank",
                      render: (row: CandidateRecord) => {
                        const score = row.composite_score ?? row.fit_score;
                        const rec = row.final_recommendation ?? (row.hiring_decision as any)?.recommendation;
                        if (score == null) return <span style={{ color: "var(--color-text-muted)" }}>—</span>;
                        return (
                          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", flexWrap: "wrap" }}>
                            <Badge tone={fitScoreTone(score)}>{score}%</Badge>
                            {rec ? (
                              <Badge tone={rec === "strong_hire" || rec === "hire" ? "success" : rec === "review" ? "warning" : "danger"}>
                                {String(rec).replaceAll("_", " ")}
                              </Badge>
                            ) : null}
                          </div>
                        );
                      },
                    },
                    {
                      key: "updated_at",
                      header: "Updated",
                      render: (row: CandidateRecord) => formatDate(row.updated_at ?? row.created_at),
                    },
                  ]}
                  data={pagedCandidates}
                  rowKey="id"
                  caption="Candidate list"
                />

                <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} showPageButtons siblingCount={1} />
              </Section>

              <Section>
                {detailLoading ? <LoadingState title="Loading candidate details" /> : null}
                {!detailLoading && detailError ? <ErrorState title="Unable to load candidate detail" description={detailError} /> : null}
                {!detailLoading && !detailError && !detailCandidate ? (
                  <EmptyState title="Select a candidate" description="Choose a candidate from the list to view details." />
                ) : null}

                {!detailLoading && !detailError && detailCandidate ? (
                  <Stack gap="4" className="candidate-management-detail">
                    <Alert
                      tone="info"
                      title={detailCandidate.full_name ?? detailCandidate.email ?? detailCandidate.id}
                      description={`Candidate ID: ${detailCandidate.id}`}
                    />

                    <div className="candidate-management-meta-grid">
                      <Section>
                        <Stack gap="2">
                          <small className="candidate-management-subtitle">Current Status</small>
                          <Badge tone={statusTone(detailCandidate.status)}>{detailCandidate.status ?? "unknown"}</Badge>
                          <Select
                            label="Update Status"
                            value={pendingStatus}
                            onChange={(event) => setPendingStatus(event.target.value)}
                            options={STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                          />
                          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "8px" }}>
                            <Button size="sm" onClick={() => void handleUpdateDetailStatus()}>
                              Save Status
                            </Button>
                            <Button size="sm" variant="secondary" onClick={() => void handleQuickStatusTransition("offered")}>
                              Extend Offer
                            </Button>
                            <Button size="sm" variant="secondary" onClick={() => void handleQuickStatusTransition("hired")}>
                              Mark Hired
                            </Button>
                          </div>
                        </Stack>
                      </Section>

                      <Section>
                        <Stack gap="2">
                          <small className="candidate-management-subtitle">Candidate Meta</small>
                          <p className="candidate-management-subtitle">Email: {detailCandidate.email ?? "-"}</p>
                          <p className="candidate-management-subtitle">Job ID: {detailCandidate.job_id ?? "-"}</p>
                          {detailCandidate.fit_score != null ? (
                            <p className="candidate-management-subtitle">
                              AI Fit Score:{" "}
                              <Badge tone={fitScoreTone(detailCandidate.fit_score)}>
                                {detailCandidate.fit_score}%
                              </Badge>
                            </p>
                          ) : null}
                          {detailCandidate.assessment_score != null ? (
                            <p className="candidate-management-subtitle">
                              Assessment Score:{" "}
                              <Badge tone={detailCandidate.assessment_score >= 60 ? "success" : "warning"}>
                                {detailCandidate.assessment_score}%
                              </Badge>
                            </p>
                          ) : null}
                          {detailCandidate.interview_score != null ? (
                            <p className="candidate-management-subtitle">
                              Interview Score:{" "}
                              <Badge tone={detailCandidate.interview_score >= 60 ? "success" : "warning"}>
                                {detailCandidate.interview_score}%
                              </Badge>
                            </p>
                          ) : null}
                          {detailCandidate.composite_score != null ? (
                            <p className="candidate-management-subtitle">
                              Composite Score:{" "}
                              <Badge tone={fitScoreTone(detailCandidate.composite_score)}>
                                {detailCandidate.composite_score}%
                              </Badge>
                            </p>
                          ) : null}
                          {detailCandidate.final_recommendation || (detailCandidate.hiring_decision as any)?.recommendation ? (
                            <p className="candidate-management-subtitle">
                              Final Recommendation:{" "}
                              <Badge tone={(detailCandidate.final_recommendation || (detailCandidate.hiring_decision as any)?.recommendation) === "strong_hire" || (detailCandidate.final_recommendation || (detailCandidate.hiring_decision as any)?.recommendation) === "hire" ? "success" : (detailCandidate.final_recommendation || (detailCandidate.hiring_decision as any)?.recommendation) === "review" ? "warning" : "danger"}>
                                {String(detailCandidate.final_recommendation || (detailCandidate.hiring_decision as any)?.recommendation).toUpperCase().replaceAll("_", " ")}
                              </Badge>
                            </p>
                          ) : null}
                          <p className="candidate-management-subtitle">Updated: {formatDate(detailCandidate.updated_at ?? detailCandidate.created_at)}</p>
                        </Stack>
                      </Section>
                    </div>

                    {candidateSkills.length > 0 ? (
                      <Section>
                        <Stack gap="2">
                          <strong>Extracted Skills & Competencies</strong>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                            {candidateSkills.map((skill, index) => (
                              <Badge key={`${skill}-${index}`} tone="neutral">
                                {skill}
                              </Badge>
                            ))}
                          </div>
                        </Stack>
                      </Section>
                    ) : null}

                    <Section>
                      <Stack gap="2">
                        <strong>Resume Preview</strong>
                        {resumePreviewUrl ? (
                          <iframe
                            src={resumePreviewUrl}
                            title="Candidate resume preview"
                            className="candidate-management-resume-frame"
                          />
                        ) : (
                          <EmptyState title="No resume preview" description="Resume preview URL is not available for this candidate." />
                        )}
                      </Stack>
                    </Section>

                    <Section>
                      <Stack gap="2">
                        <strong>AI Evaluation Summary</strong>
                        {evaluationSummary ? (
                          <Alert tone="info" description={evaluationSummary} />
                        ) : (
                          <EmptyState title="No evaluation summary" description="AI evaluation summary is unavailable for this candidate." />
                        )}
                      </Stack>
                    </Section>

                    <Section>
                      <Stack gap="2">
                        <strong>Role-Based AI Assessment & Auto-Scoring</strong>
                        {detailCandidate.assessment_score != null ? (
                          <Stack gap="2">
                            <Alert
                              tone={detailCandidate.assessment_score >= 60 ? "success" : "warning"}
                              title={`Assessment Score: ${detailCandidate.assessment_score}% (${detailCandidate.assessment_score >= 60 ? "Passed" : "Needs Review"})`}
                              description={
                                detailCandidate.assessment_breakdown
                                  ? `Answered ${detailCandidate.assessment_breakdown.correct_count ?? 0} of ${detailCandidate.assessment_breakdown.total_questions ?? 0} questions correctly.`
                                  : `Overall assessment score: ${detailCandidate.assessment_score}%.`
                              }
                            />
                            {Array.isArray(detailCandidate.assessment_breakdown?.details) && detailCandidate.assessment_breakdown.details.length > 0 ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                                {detailCandidate.assessment_breakdown.details.map((q: any, idx: number) => (
                                  <div
                                    key={q.question_id || idx}
                                    style={{
                                      border: "1px solid var(--color-border, #e2e8f0)",
                                      borderRadius: "6px",
                                      padding: "0.75rem",
                                      background: q.is_correct ? "rgba(16, 185, 129, 0.05)" : "rgba(239, 68, 68, 0.05)",
                                    }}
                                  >
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                                      <strong>Q{idx + 1}: {q.question}</strong>
                                      <Badge tone={q.is_correct ? "success" : "danger"}>
                                        {q.is_correct ? "Correct" : "Incorrect"}
                                      </Badge>
                                    </div>
                                    <small style={{ color: "var(--color-text-secondary, #64748b)" }}>
                                      Selected: <strong>{q.selected_option || "None"}</strong> | Correct: <strong>{q.correct_option}</strong>
                                    </small>
                                    {q.explanation ? (
                                      <p style={{ marginTop: "0.25rem", fontSize: "0.85rem" }}>
                                        {q.explanation}
                                      </p>
                                    ) : null}
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </Stack>
                        ) : (
                          <EmptyState
                            title="No assessment completed"
                            description="Candidate has not yet completed the role-based pre-screening assessment."
                          />
                        )}
                      </Stack>
                    </Section>

                    <Section>
                      <Stack gap="2">
                        <strong>Role-Based AI Interview & Evaluation</strong>
                        {detailCandidate.interview_score != null ? (
                          <Stack gap="3">
                            <Alert
                              tone={detailCandidate.interview_score >= 70 ? "success" : detailCandidate.interview_score >= 50 ? "warning" : "danger"}
                              title={`Interview Score: ${detailCandidate.interview_score}% — Recommendation: ${String(detailCandidate.interview_feedback?.recommendation ?? "evaluated").toUpperCase().replaceAll("_", " ")}`}
                              description={
                                (detailCandidate.interview_feedback?.overall_feedback as string | undefined) ||
                                `AI-evaluated interview completed with score ${detailCandidate.interview_score}%.`
                              }
                            />

                            {Array.isArray(detailCandidate.interview_feedback?.key_strengths) &&
                            detailCandidate.interview_feedback.key_strengths.length > 0 ? (
                              <div>
                                <small style={{ fontWeight: 600, color: "var(--color-text-secondary, #64748b)" }}>
                                  Observed Strengths:
                                </small>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.25rem" }}>
                                  {detailCandidate.interview_feedback.key_strengths.map((s: string, idx: number) => (
                                    <Badge key={idx} tone="success">
                                      {s}
                                    </Badge>
                                  ))}
                                </div>
                              </div>
                            ) : null}

                            {Array.isArray(detailCandidate.interview_feedback?.growth_areas) &&
                            detailCandidate.interview_feedback.growth_areas.length > 0 ? (
                              <div>
                                <small style={{ fontWeight: 600, color: "var(--color-text-secondary, #64748b)" }}>
                                  Growth Areas / Recommendations:
                                </small>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.25rem" }}>
                                  {detailCandidate.interview_feedback.growth_areas.map((g: string, idx: number) => (
                                    <Badge key={idx} tone="warning">
                                      {g}
                                    </Badge>
                                  ))}
                                </div>
                              </div>
                            ) : null}

                            {Array.isArray(detailCandidate.interview_feedback?.question_evaluations) &&
                            detailCandidate.interview_feedback.question_evaluations.length > 0 ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
                                <small style={{ fontWeight: 600, color: "var(--color-text-secondary, #64748b)" }}>
                                  Interview Q&A Breakdown:
                                </small>
                                {detailCandidate.interview_feedback.question_evaluations.map((qe: any, idx: number) => (
                                  <div
                                    key={qe.question_id || idx}
                                    style={{
                                      border: "1px solid var(--color-border, #e2e8f0)",
                                      borderRadius: "6px",
                                      padding: "0.75rem",
                                      background: "var(--color-bg-subtle, #f8fafc)",
                                    }}
                                  >
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                                      <strong>
                                        Q{idx + 1}: {qe.question || qe.competency || "Question"}
                                      </strong>
                                      {qe.score != null ? (
                                        <Badge tone={qe.score >= 60 ? "success" : "warning"}>
                                          {qe.score}%
                                        </Badge>
                                      ) : null}
                                    </div>
                                    {qe.answer ? (
                                      <div style={{ marginTop: "0.25rem", padding: "0.5rem", background: "#fff", borderRadius: "4px", border: "1px solid #e2e8f0" }}>
                                        <small style={{ fontWeight: 600, color: "#64748b" }}>Candidate Answer:</small>
                                        <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.85rem" }}>{qe.answer}</p>
                                      </div>
                                    ) : null}
                                    {qe.feedback ? (
                                      <p style={{ marginTop: "0.35rem", fontSize: "0.85rem", color: "#334155" }}>
                                        {qe.feedback}
                                      </p>
                                    ) : null}
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </Stack>
                        ) : (
                          <EmptyState
                            title="No interview completed"
                            description="Candidate has not yet completed the role-based AI interview."
                          />
                        )}
                      </Stack>
                    </Section>

                    <Section>
                      <Stack gap="2">
                        <strong>Candidate Match Summary</strong>
                        {matchSummary ? (
                          <Alert tone="success" description={matchSummary} />
                        ) : (
                          <EmptyState
                            title="No candidate match summary"
                            description="Candidate match summary is not available for this candidate."
                          />
                        )}
                      </Stack>
                    </Section>

                    <Section>
                      <Stack gap="2">
                        <strong>Final AI Hiring Decision & Composite Score</strong>
                        {detailCandidate.composite_score != null ? (
                          <Stack gap="3">
                            <Alert
                              tone={detailCandidate.composite_score >= 70 ? "success" : detailCandidate.composite_score >= 55 ? "warning" : "danger"}
                              title={`Composite Score: ${detailCandidate.composite_score}% — Decision: ${String(detailCandidate.final_recommendation || (detailCandidate.hiring_decision as any)?.recommendation || "evaluated").toUpperCase().replaceAll("_", " ")}`}
                              description={
                                ((detailCandidate.hiring_decision as any)?.summary as string | undefined) ||
                                `Composite hiring score computed from multi-stage recruitment pipeline (${detailCandidate.composite_score}%).`
                              }
                            />
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.75rem" }}>
                              <div style={{ padding: "0.5rem", border: "1px solid var(--color-border, #e2e8f0)", borderRadius: "6px", textAlign: "center" }}>
                                <small style={{ color: "var(--color-text-secondary, #64748b)" }}>Resume Fit (30%)</small>
                                <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{detailCandidate.fit_score != null ? `${detailCandidate.fit_score}%` : "—"}</div>
                              </div>
                              <div style={{ padding: "0.5rem", border: "1px solid var(--color-border, #e2e8f0)", borderRadius: "6px", textAlign: "center" }}>
                                <small style={{ color: "var(--color-text-secondary, #64748b)" }}>Assessment (35%)</small>
                                <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{detailCandidate.assessment_score != null ? `${detailCandidate.assessment_score}%` : "—"}</div>
                              </div>
                              <div style={{ padding: "0.5rem", border: "1px solid var(--color-border, #e2e8f0)", borderRadius: "6px", textAlign: "center" }}>
                                <small style={{ color: "var(--color-text-secondary, #64748b)" }}>Interview (35%)</small>
                                <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{detailCandidate.interview_score != null ? `${detailCandidate.interview_score}%` : "—"}</div>
                              </div>
                            </div>
                          </Stack>
                        ) : (
                          <EmptyState
                            title="No composite score yet"
                            description="Complete resume screening, assessment, and interview to generate the final composite decision."
                          />
                        )}
                      </Stack>
                    </Section>

                    <Section>
                      <Stack gap="2">
                        <strong>Hiring Recommendation Summary</strong>
                        {recommendationSummary ? (
                          <Alert tone="success" description={recommendationSummary} />
                        ) : (
                          <EmptyState
                            title="No recommendation summary"
                            description="Hiring recommendation summary is unavailable for this candidate."
                          />
                        )}
                      </Stack>
                    </Section>

                    <Section>
                      <Stack gap="2">
                        <strong>Recent Candidate Activity</strong>
                        {timelineItems.length ? (
                          <Timeline items={timelineItems} />
                        ) : (
                          <EmptyState title="No timeline events" description="No recent activity found for this candidate." />
                        )}
                      </Stack>
                    </Section>
                  </Stack>
                ) : null}
              </Section>
            </Grid>
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}


