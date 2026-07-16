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
  Grid,
  Header,
  KPICard,
  LoadingState,
  MetricCard,
  Section,
  SidebarLayout,
  Stack,
  Table,
  Timeline,
  type TimelineItem,
} from "../components";
import "./dashboard.css";

type Dict = Record<string, number>;

interface DashboardResponse {
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
    recent_candidates?: Array<Record<string, unknown>>;
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
  recent_activity_summary?: {
    items?: Array<Record<string, unknown>>;
  };
  notification_summary?: {
    total?: number;
    unread?: number;
    read?: number;
    high_priority?: number;
  };
  pipeline?: {
    pipeline_stages?: Dict;
    total_in_pipeline?: number;
  };
  job_statistics?: {
    jobs_by_department?: Dict;
    job_status_counts?: Dict;
  };
  ai_insights?: {
    summary?: string;
  };
  hiring_recommendation_summary?: {
    summary?: string;
  };
  generated_at?: string;
}

const DASHBOARD_SUMMARY_ENDPOINT = "/dashboard/summary";

function numberFormat(value: number | undefined): string {
  return new Intl.NumberFormat().format(value ?? 0);
}

function toTimelineItems(events: Array<Record<string, unknown>> | undefined): TimelineItem[] {
  if (!events?.length) {
    return [];
  }

  return events.slice(0, 8).map((event, index) => {
    const action = String(event.action ?? "Activity");
    const actor = String(event.actor_id ?? "system");
    const resourceType = String(event.entity_type ?? event.resource_type ?? "entity");
    const resourceId = String(event.entity_id ?? event.resource_id ?? "");
    const ts = typeof event.timestamp === "string" ? event.timestamp : undefined;

    return {
      id: String(event.id ?? `${action}-${index}`),
      title: action.replaceAll("_", " "),
      description: `${actor} updated ${resourceType}${resourceId ? ` ${resourceId}` : ""}`,
      timestamp: ts,
      meta: resourceType,
    };
  });
}

function toTableRows(source: Dict | undefined): Array<{ label: string; value: number }> {
  if (!source) {
    return [];
  }
  return Object.entries(source).map(([label, value]) => ({ label, value }));
}

export default function RecruiterDashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(DASHBOARD_SUMMARY_ENDPOINT, {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`Dashboard request failed (${response.status})`);
      }

      const payload = (await response.json()) as DashboardResponse;
      setDashboard(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
      setDashboard(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const timelineItems = useMemo(
    () => toTimelineItems(dashboard?.recent_activity_summary?.items),
    [dashboard?.recent_activity_summary?.items],
  );

  const hasData = useMemo(() => {
    if (!dashboard) {
      return false;
    }

    const topCounts = [
      dashboard.overview?.total_candidates,
      dashboard.overview?.total_jobs,
      dashboard.hiring_metrics?.total_candidates,
      dashboard.notification_summary?.total,
    ];

    return topCounts.some((value) => (value ?? 0) > 0) || timelineItems.length > 0;
  }, [dashboard, timelineItems.length]);

  const generatedAt = dashboard?.overview?.generated_at ?? dashboard?.generated_at;
  const recommendationSummary =
    dashboard?.hiring_recommendation_summary?.summary ?? dashboard?.ai_insights?.summary ?? "";

  const pipelineRows = toTableRows(dashboard?.pipeline?.pipeline_stages);
  const jobDeptRows = toTableRows(dashboard?.job_statistics?.jobs_by_department ?? dashboard?.job_metrics?.jobs_by_department);
  const jobStatusRows = toTableRows(dashboard?.job_statistics?.job_status_counts ?? dashboard?.job_metrics?.status_counts);
  const interviewRows = toTableRows(dashboard?.interview_metrics?.interview_events);

  return (
    <AppLayout
      className="recruiter-dashboard-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="recruiter-dashboard-title">Recruiter Dashboard</h1>
              <p className="recruiter-dashboard-subtitle">Unified recruitment operations and hiring signals</p>
            </Stack>
          }
          right={
            <div className="recruiter-dashboard-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadDashboard()}>
                Refresh
              </Button>
              <Button variant="primary" size="sm">
                New Candidate
              </Button>
            </div>
          }
        />
      }
      sidebar={
        <SidebarLayout sticky className="recruiter-dashboard-sidebar">
          <Section elevated>
            <Stack gap="3">
              <strong>Quick Navigation</strong>
              <nav className="recruiter-dashboard-nav" aria-label="Dashboard navigation">
                <a href="#kpi-summary">KPI Summary</a>
                <a href="#pipeline-overview">Pipeline Overview</a>
                <a href="#hiring-activity">Hiring Activity</a>
                <a href="#notifications">Notifications</a>
              </nav>
            </Stack>
          </Section>
          <Section>
            <Stack gap="2">
              <strong>Quick Actions</strong>
              <Button variant="secondary" size="sm">Create Job</Button>
              <Button variant="secondary" size="sm">Schedule Interview</Button>
              <Button variant="secondary" size="sm">Review Offers</Button>
            </Stack>
          </Section>
        </SidebarLayout>
      }
    >
      <ContentContainer className="recruiter-dashboard-main" fluid>
        {loading ? <LoadingState title="Loading recruiter dashboard" description="Fetching dashboard data and metrics." /> : null}
        {!loading && error ? <ErrorState title="Unable to load dashboard" description={error} onRetry={() => void loadDashboard()} /> : null}
        {!loading && !error && !hasData ? (
          <EmptyState
            title="No dashboard data available"
            description="Once candidates, jobs, interviews, and notifications are available they will appear here."
            actionLabel="Reload"
            onAction={() => void loadDashboard()}
          />
        ) : null}

        {!loading && !error && hasData ? (
          <Stack gap="6">
            <section id="kpi-summary" aria-label="KPI summary section">
              <Grid columns={{ mobile: 1, md: 2, lg: 4 }} gap="4">
                <MetricCard
                  label="Total Candidates"
                  value={numberFormat(dashboard?.overview?.total_candidates)}
                  meta="Active candidate pool"
                />
                <MetricCard
                  label="Open Jobs"
                  value={numberFormat(dashboard?.overview?.total_jobs)}
                  meta="Total tracked jobs"
                />
                <KPICard
                  label="Hiring Rate"
                  value={`${dashboard?.hiring_metrics?.hire_rate ?? 0}%`}
                  progress={dashboard?.hiring_metrics?.hire_rate ?? 0}
                  statusLabel="Conversion performance"
                  statusTone="info"
                />
                <KPICard
                  label="Pending Offers"
                  value={numberFormat(dashboard?.hiring_metrics?.offers_in_progress)}
                  progress={dashboard?.hiring_metrics?.offers_in_progress ?? 0}
                  progressMax={Math.max(1, dashboard?.hiring_metrics?.total_candidates ?? 1)}
                  statusLabel="Offer pipeline"
                  statusTone="warning"
                />
              </Grid>
            </section>

            <section id="pipeline-overview" aria-label="Pipeline overview section">
              <Grid columns={{ mobile: 1, lg: 2 }} gap="4">
                <ChartWrapper title="Candidate Pipeline Overview" description="Current candidates across recruitment stages">
                  {pipelineRows.length ? (
                    <div className="recruiter-dashboard-bars">
                      {pipelineRows.map((row) => {
                        const total = Math.max(1, dashboard?.pipeline?.total_in_pipeline ?? 1);
                        const width = (row.value / total) * 100;
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
                    <EmptyState title="No pipeline data" description="Pipeline metrics will appear once stage data is available." />
                  )}
                </ChartWrapper>

                <AnalyticsWidget title="Hiring Recommendation Summary" description="Summary composed from available dashboard recommendation signals">
                  {recommendationSummary ? (
                    <Alert tone="info" title="Recommendation" description={recommendationSummary} />
                  ) : (
                    <EmptyState
                      title="No recommendation summary"
                      description="Recommendation details are not available in the current dashboard payload."
                    />
                  )}
                </AnalyticsWidget>
              </Grid>
            </section>

            <section id="hiring-activity" aria-label="Activity and statistics section">
              <Grid columns={{ mobile: 1, lg: 2 }} gap="4">
                <AnalyticsWidget title="Recent Hiring Activity" description="Most recent recruiter and system events">
                  {timelineItems.length ? (
                    <Timeline items={timelineItems} />
                  ) : (
                    <EmptyState title="No recent activity" description="Recent hiring activity will appear here." />
                  )}
                </AnalyticsWidget>

                <AnalyticsWidget title="Interview Statistics" description="Interview status and completion signals">
                  {interviewRows.length ? (
                    <Table
                      columns={[
                        { key: "label", header: "Interview Event" },
                        { key: "value", header: "Count", align: "right" },
                      ]}
                      data={interviewRows}
                      rowKey="label"
                    />
                  ) : (
                    <EmptyState title="No interview statistics" description="Interview metrics are currently unavailable." />
                  )}
                </AnalyticsWidget>
              </Grid>
            </section>

            <section aria-label="Job and notifications section">
              <Grid columns={{ mobile: 1, lg: 2 }} gap="4">
                <AnalyticsWidget title="Job Statistics" description="Distribution by department and current status">
                  {jobDeptRows.length || jobStatusRows.length ? (
                    <Stack gap="4">
                      {jobDeptRows.length ? (
                        <Table
                          caption="Jobs by Department"
                          columns={[
                            { key: "label", header: "Department" },
                            { key: "value", header: "Jobs", align: "right" },
                          ]}
                          data={jobDeptRows}
                          rowKey="label"
                        />
                      ) : null}
                      {jobStatusRows.length ? (
                        <Table
                          caption="Jobs by Status"
                          columns={[
                            { key: "label", header: "Status" },
                            { key: "value", header: "Count", align: "right" },
                          ]}
                          data={jobStatusRows}
                          rowKey="label"
                        />
                      ) : null}
                    </Stack>
                  ) : (
                    <EmptyState title="No job statistics" description="Job statistics will appear once job data is available." />
                  )}
                </AnalyticsWidget>

                <AnalyticsWidget id="notifications" title="Recent Notifications" description="Unread and high-priority notification overview">
                  {(dashboard?.notification_summary?.total ?? 0) > 0 ? (
                    <Grid columns={{ mobile: 2, md: 4 }} gap="3">
                      <Section>
                        <Stack gap="1">
                          <small className="recruiter-dashboard-subtitle">Total</small>
                          <strong>{numberFormat(dashboard?.notification_summary?.total)}</strong>
                        </Stack>
                      </Section>
                      <Section>
                        <Stack gap="1">
                          <small className="recruiter-dashboard-subtitle">Unread</small>
                          <strong>{numberFormat(dashboard?.notification_summary?.unread)}</strong>
                        </Stack>
                      </Section>
                      <Section>
                        <Stack gap="1">
                          <small className="recruiter-dashboard-subtitle">Read</small>
                          <strong>{numberFormat(dashboard?.notification_summary?.read)}</strong>
                        </Stack>
                      </Section>
                      <Section>
                        <Stack gap="1">
                          <small className="recruiter-dashboard-subtitle">High Priority</small>
                          <strong>{numberFormat(dashboard?.notification_summary?.high_priority)}</strong>
                        </Stack>
                      </Section>
                    </Grid>
                  ) : (
                    <EmptyState title="No recent notifications" description="Notifications will appear here when available." />
                  )}
                </AnalyticsWidget>
              </Grid>
            </section>

            <section aria-label="Quick actions section">
              <AnalyticsWidget
                title="Quick Actions"
                description="Recruiter shortcuts for common workflows"
                action={<Badge tone="brand">Operational</Badge>}
              >
                <div className="recruiter-dashboard-actions">
                  <Button>Start Candidate Review</Button>
                  <Button variant="secondary">Open Candidate Pipeline</Button>
                  <Button variant="secondary">Open Interview Queue</Button>
                  <Button variant="secondary">Open Offer Review</Button>
                </div>
              </AnalyticsWidget>
            </section>

            {generatedAt ? <p className="recruiter-dashboard-generated">Last updated: {generatedAt}</p> : null}
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}
