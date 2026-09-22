import { authFetch } from "../lib/api";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Alert,
  AnalyticsWidget,
  AppLayout,
  Badge,
  Button,
  ChartWrapper,
  ContentContainer,
  EmptyState,
  ErrorState,
  Header,
  Input,
  KPICard,
  LoadingState,
  MetricCard,
  Pagination,
  Section,
  Select,
  Stack,
  Table,
  Tabs,
} from "../components";


type Dict = Record<string, number>;
type ReportType = "recruiter" | "candidate" | "job" | "interview" | "hiring";

interface DashboardSummary {
  overview?: {
    total_candidates?: number;
    total_jobs?: number;
    interview_sessions?: number;
    hired?: number;
    generated_at?: string;
  };
  candidate_metrics?: {
    status_counts?: Dict;
    total?: number;
  };
  job_metrics?: {
    status_counts?: Dict;
    jobs_by_department?: Dict;
    total?: number;
  };
  interview_metrics?: {
    interview_events?: Dict;
    average_interview_duration_minutes?: number;
    interview_sessions?: number;
  };
  hiring_metrics?: {
    hired?: number;
    rejected?: number;
    offers_in_progress?: number;
    interviews_in_progress?: number;
    screening_in_progress?: number;
    new_candidates?: number;
    total_candidates?: number;
    hire_rate?: number;
  };
  ai_insights?: {
    summary?: string;
  };
  hiring_recommendation_summary?: {
    summary?: string;
  };
  generated_at?: string;
}

interface PipelinePayload {
  pipeline_stages?: Dict;
  total_in_pipeline?: number;
}

interface FunnelPayload {
  funnel?: Dict;
  stages?: Dict;
  counts?: Dict;
  total?: number;
}

interface JobsPayload {
  jobs_by_department?: Dict;
  job_status_counts?: Dict;
}

interface InterviewsPayload {
  interview_events?: Dict;
  average_interview_duration_minutes?: number;
  interview_sessions?: number;
}

interface AIActivityPayload {
  items?: Array<Record<string, unknown>>;
  total?: number;
}

interface ReportRow {
  id: string;
  report_type: ReportType;
  title: string;
  owner: string;
  status: string;
  period: string;
  records: number;
  generated_at: string;
}

const ENDPOINTS = {
  summary: "/dashboard/summary",
  pipeline: "/dashboard/pipeline-metrics",
  funnel: "/dashboard/funnel",
  jobs: "/dashboard/job-metrics",
  interviews: "/dashboard/interviews",
  aiActivities: "/dashboard/ai-activities?page=1&page_size=50&sort_order=desc",
} as const;

function formatCount(value: number | undefined): string {
  return new Intl.NumberFormat().format(value ?? 0);
}

function parseDate(input?: string): Date | null {
  if (!input) return null;
  const parsed = new Date(input);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function inDateRange(value: string | undefined, startDate: string, endDate: string): boolean {
  if (!startDate && !endDate) return true;
  const parsed = parseDate(value);
  if (!parsed) return false;

  const start = startDate ? new Date(`${startDate}T00:00:00`) : null;
  const end = endDate ? new Date(`${endDate}T23:59:59`) : null;

  if (start && parsed < start) return false;
  if (end && parsed > end) return false;
  return true;
}

function dictRows(source: Dict | undefined): Array<{ label: string; value: number }> {
  if (!source) return [];
  return Object.entries(source).map(([label, value]) => ({ label, value }));
}

function biggestValue(rows: Array<{ value: number }>): number {
  return rows.reduce((acc, row) => Math.max(acc, row.value), 0);
}

function mapActivityToInsight(activity: Record<string, unknown>): string {
  const action = String(activity.action ?? activity.activity_type ?? "activity").replaceAll("_", " ");
  const resource = String(activity.resource_type ?? activity.entity_type ?? "resource");
  const status = String(activity.status ?? "processed");
  return `${action} on ${resource} (${status})`;
}

async function safeFetchJson<T>(url: string, fallback: T): Promise<T> {
  try {
    const res = await authFetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return fallback;
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const text = await res.text();
      if (text.trim().startsWith("<")) return fallback;
      try {
        return JSON.parse(text) as T;
      } catch {
        return fallback;
      }
    }
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

export default function AnalyticsReportsPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [pipeline, setPipeline] = useState<PipelinePayload | null>(null);
  const [funnel, setFunnel] = useState<FunnelPayload | null>(null);
  const [jobs, setJobs] = useState<JobsPayload | null>(null);
  const [interviews, setInterviews] = useState<InterviewsPayload | null>(null);
  const [aiActivities, setAiActivities] = useState<Array<Record<string, unknown>>>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");

  const [reportType, setReportType] = useState<"all" | ReportType>("all");
  const [reportStatus, setReportStatus] = useState<"all" | "ready" | "queued">("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [summaryPayload, pipelinePayload, funnelPayload, jobsPayload, interviewsPayload, aiPayload] = await Promise.all([
        safeFetchJson<DashboardSummary>(ENDPOINTS.summary, {}),
        safeFetchJson<PipelinePayload>(ENDPOINTS.pipeline, {}),
        safeFetchJson<FunnelPayload>(ENDPOINTS.funnel, {}),
        safeFetchJson<JobsPayload>(ENDPOINTS.jobs, {}),
        safeFetchJson<InterviewsPayload>(ENDPOINTS.interviews, {}),
        safeFetchJson<AIActivityPayload>(ENDPOINTS.aiActivities, {}),
      ]);

      setSummary(summaryPayload);
      setPipeline(pipelinePayload);
      setFunnel(funnelPayload);
      setJobs(jobsPayload);
      setInterviews(interviewsPayload);
      setAiActivities(Array.isArray(aiPayload.items) ? aiPayload.items : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load analytics and reports data");
      setSummary(null);
      setPipeline(null);
      setFunnel(null);
      setJobs(null);
      setInterviews(null);
      setAiActivities([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const funnelRows = useMemo(
    () => dictRows(funnel?.funnel ?? funnel?.stages ?? funnel?.counts),
    [funnel?.counts, funnel?.funnel, funnel?.stages],
  );

  const pipelineRows = useMemo(() => dictRows(pipeline?.pipeline_stages), [pipeline?.pipeline_stages]);
  const sourceRows = useMemo(() => dictRows(summary?.candidate_metrics?.status_counts), [summary?.candidate_metrics?.status_counts]);
  const interviewRows = useMemo(
    () => dictRows(interviews?.interview_events ?? summary?.interview_metrics?.interview_events),
    [interviews?.interview_events, summary?.interview_metrics?.interview_events],
  );

  const aiInsightList = useMemo(() => {
    const fromSummary = [summary?.hiring_recommendation_summary?.summary, summary?.ai_insights?.summary].filter(
      (item): item is string => Boolean(item && item.trim()),
    );
    const fromActivities = aiActivities.slice(0, 4).map(mapActivityToInsight);
    return [...fromSummary, ...fromActivities].slice(0, 6);
  }, [aiActivities, summary?.ai_insights?.summary, summary?.hiring_recommendation_summary?.summary]);

  const jobRecordsCount = useMemo(() => {
    const departmentTotal = Object.values(jobs?.jobs_by_department ?? {}).reduce((sum, value) => sum + value, 0);
    const statusTotal = Object.values(jobs?.job_status_counts ?? {}).reduce((sum, value) => sum + value, 0);
    return Math.max(departmentTotal, statusTotal, summary?.overview?.total_jobs ?? 0);
  }, [jobs?.job_status_counts, jobs?.jobs_by_department, summary?.overview?.total_jobs]);

  const reportRows = useMemo<ReportRow[]>(() => {
    const generatedAt = summary?.overview?.generated_at ?? summary?.generated_at ?? new Date().toISOString();
    const period = dateStart || dateEnd ? `${dateStart || "..."} to ${dateEnd || "..."}` : "Current period";

    const base: ReportRow[] = [
      {
        id: "report-recruiter",
        report_type: "recruiter",
        title: "Recruiter Performance Report",
        owner: "Talent Operations",
        status: "ready",
        period,
        records: aiActivities.length,
        generated_at: generatedAt,
      },
      {
        id: "report-candidate",
        report_type: "candidate",
        title: "Candidate Pipeline Report",
        owner: "Candidate Intelligence",
        status: "ready",
        period,
        records: summary?.overview?.total_candidates ?? 0,
        generated_at: generatedAt,
      },
      {
        id: "report-job",
        report_type: "job",
        title: "Job Distribution Report",
        owner: "Job Operations",
        status: "ready",
        period,
        records: jobRecordsCount,
        generated_at: generatedAt,
      },
      {
        id: "report-interview",
        report_type: "interview",
        title: "Interview Performance Report",
        owner: "Interview Office",
        status: "ready",
        period,
        records: summary?.overview?.interview_sessions ?? 0,
        generated_at: generatedAt,
      },
      {
        id: "report-hiring",
        report_type: "hiring",
        title: "Hiring Outcomes Report",
        owner: "Executive Hiring",
        status: "queued",
        period,
        records: summary?.hiring_metrics?.hired ?? 0,
        generated_at: generatedAt,
      },
    ];

    return base;
  }, [aiActivities.length, dateEnd, dateStart, jobRecordsCount, summary?.generated_at, summary?.hiring_metrics?.hired, summary?.overview?.generated_at, summary?.overview?.interview_sessions, summary?.overview?.total_candidates]);

  const filteredReports = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return reportRows.filter((row) => {
      const byType = reportType === "all" || row.report_type === reportType;
      const byStatus = reportStatus === "all" || row.status === reportStatus;
      const bySearch =
        !normalizedSearch ||
        row.title.toLowerCase().includes(normalizedSearch) ||
        row.owner.toLowerCase().includes(normalizedSearch) ||
        row.report_type.toLowerCase().includes(normalizedSearch);
      const byDate = inDateRange(row.generated_at, dateStart, dateEnd);

      return byType && byStatus && bySearch && byDate;
    });
  }, [dateEnd, dateStart, reportRows, reportStatus, reportType, search]);

  const totalReports = filteredReports.length;
  const totalPages = Math.max(1, Math.ceil(totalReports / pageSize));

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pagedReports = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredReports.slice(start, start + pageSize);
  }, [filteredReports, page, pageSize]);

  const hasAnalyticsData =
    Boolean((summary?.overview?.total_candidates ?? 0) > 0) ||
    funnelRows.length > 0 ||
    pipelineRows.length > 0 ||
    sourceRows.length > 0 ||
    interviewRows.length > 0;

  const timeToHire = summary?.interview_metrics?.average_interview_duration_minutes ?? interviews?.average_interview_duration_minutes ?? 0;
  const timeToHireDays = Math.max(1, Math.round(timeToHire / 60 / 8));

  const funnelMax = Math.max(1, biggestValue(funnelRows));
  const pipelineMax = Math.max(1, biggestValue(pipelineRows));

  return (
    <AppLayout
      className="analytics-reports-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="analytics-reports-title">Analytics & Reports</h1>
              <p className="analytics-reports-subtitle">Executive hiring analytics and operational reporting workspace.</p>
            </Stack>
          }
          right={
            <div className="analytics-reports-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadData()}>
                Refresh
              </Button>
              <Button size="sm" variant="secondary" disabled>
                Export CSV (Placeholder)
              </Button>
              <Button size="sm" variant="secondary" disabled>
                Export PDF (Placeholder)
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="analytics-reports-main" fluid>
        {loading ? <LoadingState title="Loading analytics and reports" description="Fetching dashboard analytics and report inputs." /> : null}
        {!loading && error ? <ErrorState title="Unable to load analytics module" description={error} onRetry={() => void loadData()} /> : null}
        {!loading && !error && !hasAnalyticsData && !reportRows.length ? (
          <EmptyState
            title="No analytics or report data"
            description="Analytics and reports will appear once recruitment activity is available."
            actionLabel="Reload"
            onAction={() => void loadData()}
          />
        ) : null}

        {!loading && !error ? (
          <Stack gap="5">
            <Section>
              <div className="analytics-reports-toolbar">
                <Input
                  label="Search"
                  placeholder="Search reports by title, owner, or type"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setPage(1);
                  }}
                />
                <Input
                  label="Date Range Start"
                  type="date"
                  value={dateStart}
                  onChange={(event) => {
                    setDateStart(event.target.value);
                    setPage(1);
                  }}
                />
                <Input
                  label="Date Range End"
                  type="date"
                  value={dateEnd}
                  onChange={(event) => {
                    setDateEnd(event.target.value);
                    setPage(1);
                  }}
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

            <Tabs.Root defaultValue="analytics">
              <Tabs.List>
                <Tabs.Trigger value="analytics">Analytics</Tabs.Trigger>
                <Tabs.Trigger value="reports">Reports</Tabs.Trigger>
              </Tabs.List>

              <Tabs.Panel value="analytics">
                {!hasAnalyticsData ? (
                  <EmptyState title="No analytics signals" description="Executive dashboard metrics are currently unavailable." />
                ) : (
                  <Stack gap="5">
                    <section aria-label="Executive dashboard and KPI metrics">
                      <div className="analytics-kpi-grid">
                        <MetricCard label="Total Candidates" value={formatCount(summary?.overview?.total_candidates)} meta="Executive dashboard" />
                        <MetricCard label="Open Jobs" value={formatCount(summary?.overview?.total_jobs)} meta="Recruitment pipeline" />
                        <KPICard
                          label="Hiring Rate"
                          value={`${summary?.hiring_metrics?.hire_rate ?? 0}%`}
                          progress={summary?.hiring_metrics?.hire_rate ?? 0}
                          statusLabel="Hiring conversion"
                          statusTone="info"
                        />
                        <KPICard
                          label="Time-to-Hire"
                          value={`${timeToHireDays} days`}
                          progress={timeToHireDays}
                          progressMax={60}
                          statusLabel="Cycle duration"
                          statusTone={timeToHireDays > 30 ? "warning" : "success"}
                        />
                      </div>
                    </section>

                    <section aria-label="Funnel and pipeline charts" className="analytics-chart-grid">
                      <ChartWrapper title="Hiring Funnel" description="Stage distribution across funnel states (interactive via global date range)">
                        {funnelRows.length ? (
                          <div className="analytics-bars">
                            {funnelRows.map((row) => {
                              const width = (row.value / funnelMax) * 100;
                              return (
                                <div key={row.label} className="analytics-bar">
                                  <span className="analytics-bar-label">{row.label}</span>
                                  <span className="analytics-bar-track" title={`${row.label}: ${row.value}`}>
                                    <span className="analytics-bar-fill" style={{ width: `${width}%` }} />
                                  </span>
                                  <span className="analytics-bar-value">{formatCount(row.value)}</span>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <EmptyState title="No funnel metrics" description="Funnel data is not available for the selected range." />
                        )}
                      </ChartWrapper>

                      <ChartWrapper title="Recruitment Pipeline" description="Candidates by active recruitment pipeline stage">
                        {pipelineRows.length ? (
                          <div className="analytics-bars">
                            {pipelineRows.map((row) => {
                              const width = (row.value / pipelineMax) * 100;
                              return (
                                <div key={row.label} className="analytics-bar">
                                  <span className="analytics-bar-label">{row.label}</span>
                                  <span className="analytics-bar-track" title={`${row.label}: ${row.value}`}>
                                    <span className="analytics-bar-fill" style={{ width: `${width}%` }} />
                                  </span>
                                  <span className="analytics-bar-value">{formatCount(row.value)}</span>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <EmptyState title="No pipeline metrics" description="Pipeline data is not available for the selected range." />
                        )}
                      </ChartWrapper>
                    </section>

                    <section aria-label="Source and interview performance metrics" className="analytics-chart-grid">
                      <AnalyticsWidget title="Candidate Source Metrics" description="Distribution by candidate source/status signal">
                        {sourceRows.length ? (
                          <Table
                            columns={[
                              { key: "label", header: "Source" },
                              { key: "value", header: "Candidates", align: "right" },
                            ]}
                            data={sourceRows}
                            rowKey="label"
                          />
                        ) : (
                          <EmptyState title="No candidate source metrics" description="Candidate source data is not available." />
                        )}
                      </AnalyticsWidget>

                      <AnalyticsWidget title="Interview Performance Metrics" description="Interview event distribution and throughput">
                        {interviewRows.length ? (
                          <Table
                            columns={[
                              { key: "label", header: "Interview Metric" },
                              { key: "value", header: "Count", align: "right" },
                            ]}
                            data={interviewRows}
                            rowKey="label"
                          />
                        ) : (
                          <EmptyState title="No interview performance metrics" description="Interview metrics are currently unavailable." />
                        )}
                      </AnalyticsWidget>
                    </section>

                    <section aria-label="AI hiring insights">
                      <AnalyticsWidget title="AI Hiring Insights" description="AI recommendation summary and activity-based insight feed">
                        {aiInsightList.length ? (
                          <ul className="analytics-insight-list">
                            {aiInsightList.map((insight, index) => (
                              <li key={`${insight}-${index}`}>{insight}</li>
                            ))}
                          </ul>
                        ) : (
                          <EmptyState title="No AI hiring insights" description="AI insights will appear when AI activity is available." />
                        )}
                      </AnalyticsWidget>
                    </section>
                  </Stack>
                )}
              </Tabs.Panel>

              <Tabs.Panel value="reports">
                <Stack gap="4">
                  <section aria-label="Report summary cards">
                    <div className="report-summary-grid">
                      <MetricCard label="Recruiter Reports" value={reportRows.filter((item) => item.report_type === "recruiter").length} />
                      <MetricCard label="Candidate Reports" value={reportRows.filter((item) => item.report_type === "candidate").length} />
                      <MetricCard label="Job Reports" value={reportRows.filter((item) => item.report_type === "job").length} />
                      <MetricCard label="Interview Reports" value={reportRows.filter((item) => item.report_type === "interview").length} />
                      <MetricCard label="Hiring Reports" value={reportRows.filter((item) => item.report_type === "hiring").length} />
                    </div>
                  </section>

                  <section aria-label="Report filters and export placeholders">
                    <div className="report-toolbar">
                      <Input
                        label="Report Search"
                        placeholder="Search reports"
                        value={search}
                        onChange={(event) => {
                          setSearch(event.target.value);
                          setPage(1);
                        }}
                      />
                      <Select
                        label="Report Type"
                        value={reportType}
                        onChange={(event) => {
                          setReportType(event.target.value as typeof reportType);
                          setPage(1);
                        }}
                        options={[
                          { value: "all", label: "All Types" },
                          { value: "recruiter", label: "Recruiter" },
                          { value: "candidate", label: "Candidate" },
                          { value: "job", label: "Job" },
                          { value: "interview", label: "Interview" },
                          { value: "hiring", label: "Hiring" },
                        ]}
                      />
                      <Select
                        label="Status"
                        value={reportStatus}
                        onChange={(event) => {
                          setReportStatus(event.target.value as typeof reportStatus);
                          setPage(1);
                        }}
                        options={[
                          { value: "all", label: "All Statuses" },
                          { value: "ready", label: "Ready" },
                          { value: "queued", label: "Queued" },
                        ]}
                      />
                      <div className="report-export-placeholder" role="status" aria-live="polite">
                        Export-ready UI placeholders active
                      </div>
                    </div>
                  </section>

                  {!filteredReports.length ? (
                    <EmptyState title="No reports found" description="Try adjusting report filters, search, or date range." />
                  ) : (
                    <section aria-label="Report table and pagination">
                      <Table
                        caption="Analytics and recruitment reports"
                        columns={[
                          {
                            key: "report_type",
                            header: "Type",
                            render: (row: ReportRow) => <Badge tone="brand">{row.report_type}</Badge>,
                          },
                          { key: "title", header: "Report" },
                          { key: "owner", header: "Owner" },
                          {
                            key: "status",
                            header: "Status",
                            render: (row: ReportRow) => (
                              <Badge tone={row.status === "ready" ? "success" : "warning"}>{row.status}</Badge>
                            ),
                          },
                          { key: "records", header: "Records", align: "right" },
                          { key: "period", header: "Period" },
                          {
                            key: "generated_at",
                            header: "Generated",
                            render: (row: ReportRow) => new Date(row.generated_at).toLocaleString(),
                          },
                        ]}
                        data={pagedReports}
                        rowKey="id"
                      />

                      <Pagination
                        page={page}
                        pageSize={pageSize}
                        total={totalReports}
                        onPageChange={setPage}
                        showPageButtons
                        siblingCount={1}
                      />
                    </section>
                  )}

                  <Alert
                    tone="info"
                    title="Export Functionality"
                    description="Export buttons are placeholders only in this module implementation."
                  />
                </Stack>
              </Tabs.Panel>
            </Tabs.Root>
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}
