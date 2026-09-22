import { authFetch } from "../lib/api";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  AppLayout,
  Button,
  ChartWrapper,
  ContentContainer,
  EmptyState,
  ErrorState,
  Grid,
  Header,
  LoadingState,
  MetricCard,
  Section,
  Stack,
  Table,
} from "../components";

interface DashboardStats {
  total_jobs: number;
  active_jobs: number;
  open_jobs: number;
  total_applications: number;
  applied: number;
  screening: number;
  shortlisted: number;
  interview: number;
  offered: number;
  hired: number;
  rejected: number;
}

interface DashboardJob {
  id: string;
  title: string;
  location: string | null;
  department: string | null;
  status: string;
  application_count: number;
  created_at: string;
}

interface DashboardJobsResponse {
  jobs: DashboardJob[];
  jobs_by_department: Record<string, number>;
}

interface DashboardCandidate {
  id: string;
  full_name: string;
  email: string;
}

interface DashboardJobRef {
  id: string;
  title: string;
}

interface DashboardApplication {
  id: string;
  status: string;
  applied_at: string;
  candidate: DashboardCandidate | null;
  job: DashboardJobRef | null;
}

interface DashboardPipelineGroup {
  status: string;
  count: number;
  applications: DashboardApplication[];
}

interface DashboardPipelineResponse {
  groups: DashboardPipelineGroup[];
}

interface DashboardRecentApplicationsResponse {
  applications: DashboardApplication[];
}

interface DashboardUpcomingInterview {
  id: string;
  application_id: string;
  interview_type: string;
  scheduled_start: string;
  scheduled_end: string;
  timezone: string;
  status: string;
  candidate_name?: string | null;
  job_title?: string | null;
  interviewer_name?: string | null;
}

interface DashboardUpcomingInterviewsResponse {
  interviews: DashboardUpcomingInterview[];
  interviews_today_count: number;
}

interface TopCandidate {
  rank: number;
  overall_rank_score: number;
  candidate_name?: string | null;
  job_id: string;
  job_title?: string | null;
  application_id: string;
  recommendation?: string | null;
  confidence?: number | null;
  overall_score?: number | null;
}

interface TopCandidatesResponse {
  candidates: TopCandidate[];
  generated_at: string;
}

const ENDPOINTS = {
  stats: "/dashboard/stats",
  jobs: "/dashboard/jobs",
  pipeline: "/dashboard/pipeline",
  recentApplications: "/dashboard/recent-applications",
  upcomingInterviews: "/dashboard/upcoming-interviews",
  topCandidates: "/dashboard/top-candidates",
} as const;

const PIPELINE_STATUS_ORDER = [
  "applied",
  "screening",
  "shortlisted",
  "interview",
  "offered",
  "hired",
  "rejected",
] as const;

function numberFormat(value: number | undefined): string {
  return new Intl.NumberFormat().format(value ?? 0);
}

function formatStatusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function formatDate(value: string | undefined): string {
  if (!value) {
    return "—";
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function dictRows(source: Record<string, number> | undefined): Array<{ label: string; value: number }> {
  if (!source) {
    return [];
  }
  return Object.entries(source).map(([label, value]) => ({ label, value }));
}

export default function RecruiterDashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [jobsPayload, setJobsPayload] = useState<DashboardJobsResponse | null>(null);
  const [pipeline, setPipeline] = useState<DashboardPipelineResponse | null>(null);
  const [recentApplications, setRecentApplications] = useState<DashboardApplication[]>([]);
  const [upcomingInterviews, setUpcomingInterviews] = useState<DashboardUpcomingInterview[]>([]);
  const [topCandidates, setTopCandidates] = useState<TopCandidate[]>([]);
  const [interviewsTodayCount, setInterviewsTodayCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [statsRes, jobsRes, pipelineRes, recentRes, upcomingRes, topCandidatesRes] = await Promise.all([
        authFetch(ENDPOINTS.stats, { method: "GET" }),
        authFetch(ENDPOINTS.jobs, { method: "GET" }),
        authFetch(ENDPOINTS.pipeline, { method: "GET" }),
        authFetch(ENDPOINTS.recentApplications, { method: "GET" }),
        authFetch(ENDPOINTS.upcomingInterviews, { method: "GET" }),
        authFetch(ENDPOINTS.topCandidates, { method: "GET" }),
      ]);

      if (
        !statsRes.ok ||
        !jobsRes.ok ||
        !pipelineRes.ok ||
        !recentRes.ok ||
        !upcomingRes.ok ||
        !topCandidatesRes.ok
      ) {
        const failed = [
          !statsRes.ok ? `stats (${statsRes.status})` : null,
          !jobsRes.ok ? `jobs (${jobsRes.status})` : null,
          !pipelineRes.ok ? `pipeline (${pipelineRes.status})` : null,
          !recentRes.ok ? `recent applications (${recentRes.status})` : null,
          !upcomingRes.ok ? `upcoming interviews (${upcomingRes.status})` : null,
          !topCandidatesRes.ok ? `top candidates (${topCandidatesRes.status})` : null,
        ]
          .filter(Boolean)
          .join(", ");
        throw new Error(`Dashboard request failed: ${failed}`);
      }

      const statsData = (await statsRes.json()) as DashboardStats;
      const jobsData = (await jobsRes.json()) as DashboardJobsResponse;
      const pipelineData = (await pipelineRes.json()) as DashboardPipelineResponse;
      const recentData = (await recentRes.json()) as DashboardRecentApplicationsResponse;
      const upcomingData = (await upcomingRes.json()) as DashboardUpcomingInterviewsResponse;
      const topCandidatesData = (await topCandidatesRes.json()) as TopCandidatesResponse;

      setStats(statsData);
      setJobsPayload(jobsData);
      setPipeline(pipelineData);
      setRecentApplications(recentData.applications ?? []);
      setUpcomingInterviews(upcomingData.interviews ?? []);
      setTopCandidates(topCandidatesData.candidates ?? []);
      setInterviewsTodayCount(upcomingData.interviews_today_count ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
      setStats(null);
      setJobsPayload(null);
      setPipeline(null);
      setRecentApplications([]);
      setUpcomingInterviews([]);
      setTopCandidates([]);
      setInterviewsTodayCount(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const applicationsByStatus = useMemo(() => {
    if (!stats) {
      return {};
    }
    return {
      applied: stats.applied,
      screening: stats.screening,
      shortlisted: stats.shortlisted,
      interview: stats.interview,
      offered: stats.offered,
      hired: stats.hired,
      rejected: stats.rejected,
    };
  }, [stats]);

  const applicationStatusRows = useMemo(() => {
    const rows = PIPELINE_STATUS_ORDER.map((status) => ({
      label: formatStatusLabel(status),
      value: applicationsByStatus[status] ?? 0,
    }));
    return rows.filter((row) => row.value > 0);
  }, [applicationsByStatus]);

  const jobsByDepartmentRows = useMemo(
    () => dictRows(jobsPayload?.jobs_by_department),
    [jobsPayload?.jobs_by_department],
  );

  const openJobs = useMemo(
    () => (jobsPayload?.jobs ?? []).filter((job) => job.status === "open"),
    [jobsPayload?.jobs],
  );

  const pipelineSummaryRows = useMemo(
    () =>
      (pipeline?.groups ?? []).map((group) => ({
        status: formatStatusLabel(group.status),
        count: group.count,
      })),
    [pipeline?.groups],
  );

  const applicationStatusMax = useMemo(
    () => Math.max(1, ...applicationStatusRows.map((row) => row.value)),
    [applicationStatusRows],
  );

  const departmentMax = useMemo(
    () => Math.max(1, ...jobsByDepartmentRows.map((row) => row.value)),
    [jobsByDepartmentRows],
  );

  const handleCandidateAction = async (applicationId: string, newStatus: "offered" | "hired") => {
    try {
      await authFetch(`/api/v1/applications/${applicationId}/status`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ status: newStatus }),
      });
      await loadDashboard();
    } catch {
      try {
        await authFetch(`/applications/${applicationId}/status`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ status: newStatus }),
        });
        await loadDashboard();
      } catch (err) {
        console.error("Failed to update candidate application status", err);
      }
    }
  };

  return (
    <AppLayout
      className="recruiter-dashboard-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="recruiter-dashboard-title">Recruiter Workspace</h1>
              <p className="recruiter-dashboard-subtitle">Company hiring pipeline and job activity</p>
            </Stack>
          }
          right={
            <div className="recruiter-dashboard-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadDashboard()}>
                Refresh
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="recruiter-dashboard-main" fluid>
        {loading ? (
          <LoadingState title="Loading recruiter workspace" description="Fetching dashboard metrics and pipeline data." />
        ) : null}
        {!loading && error ? (
          <ErrorState title="Unable to load dashboard" description={error} onRetry={() => void loadDashboard()} />
        ) : null}

        {!loading && !error ? (
          <Stack gap="6">
            <section id="kpi-summary" aria-label="KPI summary section">
              <Grid columns={{ mobile: 1, md: 2, lg: 5 }} gap="4">
                <MetricCard label="Total Jobs" value={numberFormat(stats?.total_jobs)} meta="All company jobs" />
                <MetricCard label="Active Jobs" value={numberFormat(stats?.active_jobs)} meta="Currently active postings" />
                <MetricCard
                  label="Applications"
                  value={numberFormat(stats?.total_applications)}
                  meta="Total applications received"
                />
                <MetricCard label="Hired" value={numberFormat(stats?.hired)} meta="Candidates hired" />
                <MetricCard
                  label="Interviews Today"
                  value={numberFormat(interviewsTodayCount)}
                  meta="Scheduled interviews today"
                />
              </Grid>
            </section>

            <section aria-label="Upcoming interviews section">
              <Section elevated>
                <Stack gap="3">
                  <h2 className="recruiter-dashboard-title">Upcoming Interviews</h2>
                  {upcomingInterviews.length ? (
                    <Table
                      columns={[
                        { key: "candidate", header: "Candidate" },
                        { key: "job", header: "Job" },
                        { key: "type", header: "Type" },
                        { key: "schedule", header: "Schedule" },
                        { key: "interviewer", header: "Interviewer" },
                      ]}
                      data={upcomingInterviews.map((interview) => ({
                        id: interview.id,
                        candidate: interview.candidate_name ?? "—",
                        job: interview.job_title ?? "—",
                        type: formatStatusLabel(interview.interview_type),
                        schedule: formatDate(interview.scheduled_start),
                        interviewer: interview.interviewer_name ?? "—",
                      }))}
                      rowKey="id"
                    />
                  ) : (
                    <EmptyState title="No upcoming interviews" description="Scheduled interviews will appear here." />
                  )}
                </Stack>
              </Section>
            </section>

            <section aria-label="Top candidates section">
              <Section elevated>
                <Stack gap="3">
                  <h2 className="recruiter-dashboard-title">Top Candidates</h2>
                  {topCandidates.length ? (
                    <Table
                      columns={[
                        { key: "rank", header: "Rank" },
                        { key: "candidate", header: "Candidate" },
                        { key: "job", header: "Job" },
                        { key: "score", header: "Rank Score", align: "right" },
                        { key: "recommendation", header: "Recommendation" },
                        {
                          key: "actions",
                          header: "Actions",
                          render: (row: Record<string, unknown>) => (
                            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => void handleCandidateAction(String(row.id), "offered")}
                              >
                                Extend Offer
                              </Button>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => void handleCandidateAction(String(row.id), "hired")}
                              >
                                Hire
                              </Button>
                            </div>
                          ),
                        },
                      ]}
                      data={topCandidates.map((candidate) => ({
                        id: candidate.application_id,
                        rank: `#${candidate.rank}`,
                        candidate: candidate.candidate_name ?? "—",
                        job: candidate.job_title ?? "—",
                        score: candidate.overall_rank_score.toFixed(1),
                        recommendation: candidate.recommendation ?? "—",
                      }))}
                      rowKey="id"
                    />
                  ) : (
                    <EmptyState
                      title="No ranked candidates yet"
                      description="Run AI resume analysis on applications to populate ranking."
                    />
                  )}
                </Stack>
              </Section>
            </section>

            <section aria-label="Charts section">
              <Grid columns={{ mobile: 1, lg: 2 }} gap="4">
                <ChartWrapper title="Applications by Status" description="Application counts across pipeline stages">
                  {applicationStatusRows.length ? (
                    <div className="recruiter-dashboard-bars">
                      {applicationStatusRows.map((row) => {
                        const width = (row.value / applicationStatusMax) * 100;
                        return (
                          <div key={row.label} className="recruiter-dashboard-bar">
                            <span className="recruiter-dashboard-bar-label">{row.label}</span>
                            <span className="recruiter-dashboard-bar-track">
                              <span className="recruiter-dashboard-bar-fill" style={{ width: `${width}%` }} />
                            </span>
                            <span className="recruiter-dashboard-bar-value">{numberFormat(row.value)}</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <EmptyState
                      title="No application data"
                      description="Application counts will appear once candidates apply to your jobs."
                    />
                  )}
                </ChartWrapper>

                <ChartWrapper title="Jobs by Department" description="Open and closed jobs grouped by department">
                  {jobsByDepartmentRows.length ? (
                    <div className="recruiter-dashboard-bars">
                      {jobsByDepartmentRows.map((row) => {
                        const width = (row.value / departmentMax) * 100;
                        return (
                          <div key={row.label} className="recruiter-dashboard-bar">
                            <span className="recruiter-dashboard-bar-label">{row.label}</span>
                            <span className="recruiter-dashboard-bar-track">
                              <span className="recruiter-dashboard-bar-fill" style={{ width: `${width}%` }} />
                            </span>
                            <span className="recruiter-dashboard-bar-value">{numberFormat(row.value)}</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <EmptyState title="No job data" description="Job department breakdown will appear once jobs are created." />
                  )}
                </ChartWrapper>
              </Grid>
            </section>

            <section aria-label="Tables section">
              <Grid columns={{ mobile: 1, lg: 2 }} gap="4">
                <Section elevated>
                  <Stack gap="3">
                    <h2 className="recruiter-dashboard-title">Recent Applications</h2>
                    {recentApplications.length ? (
                      <Table
                        columns={[
                          { key: "candidate", header: "Candidate" },
                          { key: "job", header: "Job" },
                          { key: "status", header: "Status" },
                          { key: "applied_at", header: "Applied", align: "right" },
                        ]}
                        data={recentApplications.map((application) => ({
                          id: application.id,
                          candidate: application.candidate?.full_name ?? "—",
                          job: application.job?.title ?? "—",
                          status: formatStatusLabel(application.status),
                          applied_at: formatDate(application.applied_at),
                        }))}
                        rowKey="id"
                      />
                    ) : (
                      <EmptyState title="No recent applications" description="New applications will appear here." />
                    )}
                  </Stack>
                </Section>

                <Section elevated>
                  <Stack gap="3">
                    <h2 className="recruiter-dashboard-title">Open Jobs</h2>
                    {openJobs.length ? (
                      <Table
                        columns={[
                          { key: "title", header: "Title" },
                          { key: "department", header: "Department" },
                          { key: "location", header: "Location" },
                          { key: "application_count", header: "Applications", align: "right" },
                        ]}
                        data={openJobs.map((job) => ({
                          id: job.id,
                          title: job.title,
                          department: job.department ?? "—",
                          location: job.location ?? "—",
                          application_count: numberFormat(job.application_count),
                        }))}
                        rowKey="id"
                      />
                    ) : (
                      <EmptyState title="No open jobs" description="Open job postings will appear here." />
                    )}
                  </Stack>
                </Section>
              </Grid>

              <Section elevated>
                <Stack gap="3">
                  <h2 className="recruiter-dashboard-title">Pipeline Summary</h2>
                  {pipelineSummaryRows.length ? (
                    <Table
                      columns={[
                        { key: "status", header: "Stage" },
                        { key: "count", header: "Applications", align: "right" },
                      ]}
                      data={pipelineSummaryRows}
                      rowKey="status"
                    />
                  ) : (
                    <EmptyState title="No pipeline data" description="Pipeline stages will appear once applications exist." />
                  )}
                </Stack>
              </Section>
            </section>
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}
