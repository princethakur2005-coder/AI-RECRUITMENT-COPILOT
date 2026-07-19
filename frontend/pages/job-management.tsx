import { authFetch } from "../lib/api";
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
  Pagination,
  Section,
  Select,
  Stack,
  Table,
} from "../components";


type JobStatus = "draft" | "open" | "paused" | "closed" | "archived" | string;

interface JobRecord {
  id: string;
  title?: string;
  description?: string;
  department?: string;
  location?: string;
  employment_type?: string;
  status?: JobStatus;
  created_at?: string;
  updated_at?: string;
  job_intelligence?: Record<string, unknown>;
  [key: string]: unknown;
}

interface JobFormState {
  title: string;
  description: string;
  department: string;
  location: string;
  employment_type: string;
  status: JobStatus;
}

const JOBS_ENDPOINT = "/jobs";

const STATUS_OPTIONS: Array<{ value: JobStatus; label: string }> = [
  { value: "draft", label: "Draft" },
  { value: "open", label: "Open" },
  { value: "paused", label: "Paused" },
  { value: "closed", label: "Closed" },
  { value: "archived", label: "Archived" },
];

const EMPLOYMENT_OPTIONS = [
  { value: "", label: "Any" },
  { value: "full_time", label: "Full Time" },
  { value: "part_time", label: "Part Time" },
  { value: "contract", label: "Contract" },
  { value: "internship", label: "Internship" },
];

function formatDate(value?: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusTone(status?: string): "neutral" | "brand" | "success" | "warning" | "danger" {
  const normalized = String(status ?? "").toLowerCase();
  if (normalized.includes("open")) return "success";
  if (normalized.includes("paused")) return "warning";
  if (normalized.includes("closed") || normalized.includes("archiv")) return "danger";
  if (normalized.includes("draft")) return "brand";
  return "neutral";
}

function extractStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const label = (item as Record<string, unknown>).name ?? (item as Record<string, unknown>).label ?? (item as Record<string, unknown>).skill;
          return typeof label === "string" ? label : "";
        }
        return "";
      })
      .filter(Boolean);
  }
  return [];
}

function readJobIntelligence(job: JobRecord | null): {
  summary: string;
  requiredSkills: string[];
  preferredSkills: string[];
  candidateMatchSummary: string;
} {
  if (!job) {
    return { summary: "", requiredSkills: [], preferredSkills: [], candidateMatchSummary: "" };
  }

  const intelligence = (job.job_intelligence as Record<string, unknown> | undefined) ?? {};

  const summaryCandidate =
    intelligence.summary ?? intelligence.overview ?? intelligence.ai_summary ?? intelligence.intelligence_summary;
  const summary = typeof summaryCandidate === "string" ? summaryCandidate : "";

  const requiredSkills = extractStringList(
    intelligence.required_skills ?? intelligence.skills_required ?? intelligence.must_have_skills,
  );
  const preferredSkills = extractStringList(
    intelligence.preferred_skills ?? intelligence.skills_preferred ?? intelligence.nice_to_have_skills,
  );

  const matchCandidate =
    intelligence.candidate_match_summary ?? intelligence.match_summary ?? intelligence.recommendation_summary;
  const candidateMatchSummary = typeof matchCandidate === "string" ? matchCandidate : "";

  return { summary, requiredSkills, preferredSkills, candidateMatchSummary };
}

function getInitialForm(): JobFormState {
  return {
    title: "",
    description: "",
    department: "",
    location: "",
    employment_type: "",
    status: "open",
  };
}

function normalizeCreatePayload(form: JobFormState): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    title: form.title,
    description: form.description,
    status: form.status,
  };

  if (form.department) payload.department = form.department;
  if (form.location) payload.location = form.location;
  if (form.employment_type) payload.employment_type = form.employment_type;
  return payload;
}

function normalizeUpdatePayload(form: JobFormState): Record<string, unknown> {
  return normalizeCreatePayload(form);
}

export default function JobManagementPage() {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [employmentFilter, setEmploymentFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"title" | "updated" | "status">("updated");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [formMode, setFormMode] = useState<"create" | "edit">("create");
  const [formState, setFormState] = useState<JobFormState>(getInitialForm);
  const [formLoading, setFormLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [bulkStatus, setBulkStatus] = useState<JobStatus>("open");

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await authFetch(JOBS_ENDPOINT, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error(`Failed to load jobs (${response.status})`);
      }

      const payload = (await response.json()) as JobRecord[];
      setJobs(Array.isArray(payload) ? payload : []);

      if (!selectedJobId && payload.length) {
        setSelectedJobId(String(payload[0].id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load jobs");
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, [selectedJobId]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const processedJobs = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    const filtered = jobs.filter((job) => {
      const matchesQuery =
        !normalizedQuery ||
        String(job.title ?? "").toLowerCase().includes(normalizedQuery) ||
        String(job.department ?? "").toLowerCase().includes(normalizedQuery) ||
        String(job.location ?? "").toLowerCase().includes(normalizedQuery) ||
        String(job.id ?? "").toLowerCase().includes(normalizedQuery);

      const matchesStatus = statusFilter === "all" || String(job.status ?? "") === statusFilter;
      const matchesEmployment = employmentFilter === "all" || String(job.employment_type ?? "") === employmentFilter;
      return matchesQuery && matchesStatus && matchesEmployment;
    });

    const sorted = [...filtered].sort((a, b) => {
      const direction = sortOrder === "asc" ? 1 : -1;

      if (sortBy === "title") {
        return String(a.title ?? "").localeCompare(String(b.title ?? "")) * direction;
      }

      if (sortBy === "status") {
        return String(a.status ?? "").localeCompare(String(b.status ?? "")) * direction;
      }

      return String(a.updated_at ?? a.created_at ?? "").localeCompare(String(b.updated_at ?? b.created_at ?? "")) * direction;
    });

    return sorted;
  }, [jobs, query, statusFilter, employmentFilter, sortBy, sortOrder]);

  const total = processedJobs.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const pagedJobs = useMemo(() => {
    const start = (page - 1) * pageSize;
    return processedJobs.slice(start, start + pageSize);
  }, [processedJobs, page, pageSize]);

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  );

  const intelligence = useMemo(() => readJobIntelligence(selectedJob), [selectedJob]);

  const allPageSelected = pagedJobs.length > 0 && pagedJobs.every((job) => selectedIds.includes(job.id));

  const setFormField = <K extends keyof JobFormState>(field: K, value: JobFormState[K]) => {
    setFormState((prev) => ({ ...prev, [field]: value }));
  };

  const resetForm = () => {
    setFormMode("create");
    setFormState(getInitialForm());
    setFormError(null);
    setShowForm(false);
  };

  const openCreateForm = () => {
    setFormMode("create");
    setFormState(getInitialForm());
    setFormError(null);
    setShowForm(true);
    setTimeout(() => {
      document.getElementById("job-form-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  const startEdit = () => {
    if (!selectedJob) return;

    setFormMode("edit");
    setFormError(null);
    setShowForm(true);
    setFormState({
      title: String(selectedJob.title ?? ""),
      description: String(selectedJob.description ?? ""),
      department: String(selectedJob.department ?? ""),
      location: String(selectedJob.location ?? ""),
      employment_type: String(selectedJob.employment_type ?? ""),
      status: String(selectedJob.status ?? "open"),
    });
    setTimeout(() => {
      document.getElementById("job-form-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  const createJob = async () => {
    setFormLoading(true);
    setFormError(null);

    try {
      const response = await authFetch(JOBS_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(normalizeCreatePayload(formState)),
      });

      if (!response.ok) {
        throw new Error(`Create failed (${response.status})`);
      }

      const created = (await response.json()) as JobRecord;
      await loadJobs();
      setSelectedJobId(created.id);
      setShowForm(false);
      resetForm();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create job");
    } finally {
      setFormLoading(false);
    }
  };

  const updateJob = async () => {
    if (!selectedJob?.id) return;

    setFormLoading(true);
    setFormError(null);

    try {
      const response = await authFetch(`${JOBS_ENDPOINT}/${selectedJob.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(normalizeUpdatePayload(formState)),
      });

      if (!response.ok) {
        throw new Error(`Update failed (${response.status})`);
      }

      await loadJobs();
      setSelectedJobId(selectedJob.id);
      setShowForm(false);
      resetForm();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to update job");
    } finally {
      setFormLoading(false);
    }
  };

  const deleteJob = async (jobId: string) => {
    await authFetch(`${JOBS_ENDPOINT}/${jobId}`, { method: "DELETE" });
  };

  const deleteSelected = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;

    await Promise.all(ids.map((id) => deleteJob(id)));
    setSelectedIds([]);
    await loadJobs();

    if (selectedJobId && ids.includes(selectedJobId)) {
      setSelectedJobId(null);
    }
  };

  const applyBulkStatus = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;

    await Promise.all(
      ids.map((id) =>
        authFetch(`${JOBS_ENDPOINT}/${id}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ status: bulkStatus }),
        }),
      ),
    );

    setSelectedIds([]);
    await loadJobs();
  };

  const updateSelectedStatus = async (status: JobStatus) => {
    if (!selectedJob?.id) return;

    await authFetch(`${JOBS_ENDPOINT}/${selectedJob.id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ status }),
    });

    await loadJobs();
  };

  const togglePageSelection = (checked: boolean) => {
    if (checked) {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...pagedJobs.map((job) => job.id)])));
      return;
    }
    setSelectedIds((prev) => prev.filter((id) => !pagedJobs.some((job) => job.id === id)));
  };

  const toggleRowSelection = (jobId: string, checked: boolean) => {
    setSelectedIds((prev) => {
      if (checked) return Array.from(new Set([...prev, jobId]));
      return prev.filter((id) => id !== jobId);
    });
  };

  const requiredSkillRows = intelligence.requiredSkills.map((skill, index) => ({
    label: skill,
    value: Math.max(30, 100 - index * 12),
  }));

  const preferredSkillRows = intelligence.preferredSkills.map((skill, index) => ({
    label: skill,
    value: Math.max(20, 80 - index * 10),
  }));

  return (
    <AppLayout
      className="job-management-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="job-management-title">Job Management</h1>
              <p className="job-management-subtitle">Manage jobs, intelligence summaries, skill requirements, and candidate fit signals</p>
            </Stack>
          }
          right={
            <div className="job-management-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadJobs()}>
                Refresh
              </Button>
              <Button size="sm" onClick={openCreateForm}>
                New Job
              </Button>
              <Button size="sm" variant="secondary" disabled={!selectedJob} onClick={startEdit}>
                Edit Selected
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="job-management-main" fluid>
        {loading ? <LoadingState title="Loading jobs" description="Fetching job records and intelligence data." /> : null}
        {!loading && error ? <ErrorState title="Unable to load jobs" description={error} onRetry={() => void loadJobs()} /> : null}
        {!loading && !error && !jobs.length ? (
          <EmptyState
            title="No jobs available"
            description="Create your first job posting to begin candidate matching and intelligence scoring."
            actionLabel="Reload"
            onAction={() => void loadJobs()}
          />
        ) : null}

        {!loading && !error && jobs.length ? (
          <Stack gap="5">
            <Section>
              <div className="job-management-toolbar">
                <Input label="Search Jobs" placeholder="Search by title, department, location, or ID" value={query} onChange={(event) => setQuery(event.target.value)} />
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
                  label="Employment"
                  value={employmentFilter}
                  onChange={(event) => setEmploymentFilter(event.target.value)}
                  options={[
                    { value: "all", label: "All Types" },
                    ...EMPLOYMENT_OPTIONS.filter((option) => option.value),
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
                    { value: "updated:desc", label: "Updated (Newest)" },
                    { value: "updated:asc", label: "Updated (Oldest)" },
                    { value: "title:asc", label: "Title (A-Z)" },
                    { value: "title:desc", label: "Title (Z-A)" },
                    { value: "status:asc", label: "Status (A-Z)" },
                    { value: "status:desc", label: "Status (Z-A)" },
                  ]}
                />
              </div>
            </Section>

            <Section>
              <div className="job-management-bulk">
                <Badge tone="neutral">Selected: {selectedIds.length}</Badge>
                <Select
                  value={bulkStatus}
                  onChange={(event) => setBulkStatus(event.target.value)}
                  options={STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                />
                <Button size="sm" variant="secondary" disabled={!selectedIds.length} onClick={() => void applyBulkStatus()}>
                  Apply Status
                </Button>
                <Button size="sm" variant="danger" disabled={!selectedIds.length} onClick={() => void deleteSelected()}>
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
                          aria-label="Select all jobs on page"
                          checked={allPageSelected}
                          onChange={(event) => togglePageSelection(event.target.checked)}
                        />
                      ),
                      render: (row: JobRecord) => (
                        <input
                          type="checkbox"
                          aria-label={`Select ${row.title ?? row.id}`}
                          checked={selectedIds.includes(row.id)}
                          onChange={(event) => toggleRowSelection(row.id, event.target.checked)}
                        />
                      ),
                      width: "3rem",
                    },
                    {
                      key: "title",
                      header: "Job",
                      render: (row: JobRecord) => (
                        <button
                          type="button"
                          className="ui-btn ui-btn-ghost ui-btn-sm"
                          onClick={() => setSelectedJobId(row.id)}
                          style={{ justifyContent: "flex-start", paddingInline: 0 }}
                        >
                          {row.title ?? row.id}
                        </button>
                      ),
                    },
                    { key: "department", header: "Department" },
                    { key: "location", header: "Location" },
                    {
                      key: "status",
                      header: "Status",
                      render: (row: JobRecord) => <Badge tone={statusTone(row.status)}>{row.status ?? "unknown"}</Badge>,
                    },
                    {
                      key: "updated_at",
                      header: "Updated",
                      render: (row: JobRecord) => formatDate(row.updated_at ?? row.created_at),
                    },
                  ]}
                  data={pagedJobs}
                  rowKey="id"
                  caption="Job list"
                />

                <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} showPageButtons siblingCount={1} />
                <div style={{ marginTop: "var(--space-3)", maxWidth: "8rem" }}>
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
                {!selectedJob ? <EmptyState title="Select a job" description="Choose a job from the list to view details and manage status." /> : null}

                {selectedJob ? (
                  <Stack gap="4" className="job-management-panel">
                    <Alert
                      tone="info"
                      title={selectedJob.title ?? selectedJob.id}
                      description={`${selectedJob.department ?? "No department"} • ${selectedJob.location ?? "No location"}`}
                    >
                      <div className="job-management-actions">
                        <Badge tone={statusTone(selectedJob.status)}>{selectedJob.status ?? "unknown"}</Badge>
                        {STATUS_OPTIONS.map((option) => (
                          <Button
                            key={option.value}
                            size="sm"
                            variant={String(option.value) === String(selectedJob.status) ? "primary" : "secondary"}
                            onClick={() => void updateSelectedStatus(option.value)}
                          >
                            {option.label}
                          </Button>
                        ))}
                      </div>
                    </Alert>

                    <AnalyticsWidget title="AI Job Intelligence Summary" description="Summary generated from job intelligence pipeline">
                      {intelligence.summary ? (
                        <Alert tone="info" description={intelligence.summary} />
                      ) : (
                        <EmptyState title="No AI summary" description="AI intelligence summary is not available for this job." />
                      )}
                    </AnalyticsWidget>

                    <AnalyticsWidget title="Required vs Preferred Skills" description="Relative weighting of must-have and nice-to-have skills">
                      {requiredSkillRows.length || preferredSkillRows.length ? (
                        <div className="job-management-skills">
                          {requiredSkillRows.map((skill) => (
                            <div key={`required-${skill.label}`} className="job-management-skill-row">
                              <span className="job-management-skill-label">Required: {skill.label}</span>
                              <span className="job-management-skill-track">
                                <span className="job-management-skill-fill" style={{ width: `${skill.value}%` }} />
                              </span>
                              <span className="job-management-skill-value">{skill.value}%</span>
                            </div>
                          ))}
                          {preferredSkillRows.map((skill) => (
                            <div key={`preferred-${skill.label}`} className="job-management-skill-row">
                              <span className="job-management-skill-label">Preferred: {skill.label}</span>
                              <span className="job-management-skill-track">
                                <span
                                  className="job-management-skill-fill"
                                  style={{
                                    width: `${skill.value}%`,
                                    background: "var(--color-status-info)",
                                  }}
                                />
                              </span>
                              <span className="job-management-skill-value">{skill.value}%</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <EmptyState title="No skills visualization" description="Required/preferred skills are not available for this job." />
                      )}
                    </AnalyticsWidget>

                    <AnalyticsWidget title="Candidate Match Summary" description="Current matching signal from intelligence and recommendation outputs">
                      {intelligence.candidateMatchSummary ? (
                        <Alert tone="success" description={intelligence.candidateMatchSummary} />
                      ) : (
                        <EmptyState
                          title="No candidate match summary"
                          description="Candidate match summary is not available for this job yet."
                        />
                      )}
                    </AnalyticsWidget>

                    <Section>
                      <Stack gap="2">
                        <strong>Job Detail</strong>
                        <p className="job-management-subtitle">ID: {selectedJob.id}</p>
                        <p className="job-management-subtitle">Employment Type: {selectedJob.employment_type ?? "-"}</p>
                        <p className="job-management-subtitle">Created: {formatDate(selectedJob.created_at)}</p>
                        <p className="job-management-subtitle">Updated: {formatDate(selectedJob.updated_at ?? selectedJob.created_at)}</p>
                        <p style={{ margin: 0 }}>{selectedJob.description ?? "No description available."}</p>
                      </Stack>
                    </Section>
                  </Stack>
                ) : null}
              </Section>
            </Grid>

          </Stack>
        ) : null}

        {showForm ? (
          <Section id="job-form-section" style={{ marginTop: "var(--space-5)" }}>
            <Stack gap="3">
              <strong>{formMode === "create" ? "Create New Job" : "Edit Job"}</strong>

              {formError ? <Alert tone="danger" title="Form error" description={formError} /> : null}

              <FormWrapper
                onSubmit={(event) => {
                  event.preventDefault();
                  if (formMode === "create") {
                    void createJob();
                  } else {
                    void updateJob();
                  }
                }}
              >
                <div className="job-management-form-grid">
                  <Input
                    label="Title"
                    value={formState.title}
                    onChange={(event) => setFormField("title", event.target.value)}
                    required
                  />
                  <Input
                    label="Department"
                    value={formState.department}
                    onChange={(event) => setFormField("department", event.target.value)}
                  />
                  <Input
                    label="Location"
                    value={formState.location}
                    onChange={(event) => setFormField("location", event.target.value)}
                  />
                  <Select
                    label="Employment Type"
                    value={formState.employment_type}
                    onChange={(event) => setFormField("employment_type", event.target.value)}
                    options={EMPLOYMENT_OPTIONS}
                  />
                  <Select
                    label="Status"
                    value={formState.status}
                    onChange={(event) => setFormField("status", event.target.value)}
                    options={STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                  />
                </div>

                <Input
                  label="Description"
                  value={formState.description}
                  onChange={(event) => setFormField("description", event.target.value)}
                  placeholder="Describe role scope, responsibilities, and outcomes"
                  required
                />

                <FormActions
                  submitting={formLoading}
                  submitLabel={formMode === "create" ? "Create Job" : "Save Changes"}
                  cancelLabel="Cancel"
                  onCancel={resetForm}
                />
              </FormWrapper>
            </Stack>
          </Section>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}


