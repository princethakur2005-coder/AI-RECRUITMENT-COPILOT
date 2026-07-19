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
  { value: "decision_pending", label: "Decision Pending" },
  { value: "offer", label: "Offer" },
  { value: "offer_pending", label: "Offer Pending" },
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
  return typeof fallback === "string" ? fallback : null;
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
  const [sortBy, setSortBy] = useState<"name" | "updated" | "status">("updated");
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
        fetch(`${CANDIDATES_ENDPOINT}/${candidateId}`, { headers: { Accept: "application/json" } }),
        fetch(`${CANDIDATES_ENDPOINT}/${candidateId}/timeline?limit=20`, { headers: { Accept: "application/json" } }),
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

  const updateCandidateStatus = async (candidateId: string, status: CandidateStatus) => {
    await authFetch(`${CANDIDATES_ENDPOINT}/${candidateId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ status }),
    });
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
    await updateCandidateStatus(detailCandidate.id, pendingStatus);
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
                          <Button size="sm" onClick={() => void handleUpdateDetailStatus()}>
                            Save Status
                          </Button>
                        </Stack>
                      </Section>

                      <Section>
                        <Stack gap="2">
                          <small className="candidate-management-subtitle">Candidate Meta</small>
                          <p className="candidate-management-subtitle">Email: {detailCandidate.email ?? "-"}</p>
                          <p className="candidate-management-subtitle">Job ID: {detailCandidate.job_id ?? "-"}</p>
                          <p className="candidate-management-subtitle">Updated: {formatDate(detailCandidate.updated_at ?? detailCandidate.created_at)}</p>
                        </Stack>
                      </Section>
                    </div>

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


