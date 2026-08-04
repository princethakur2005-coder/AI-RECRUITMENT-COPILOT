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
  LoadingState,
  Section,
  Select,
  Stack,
  Table,
} from "../components";
import type { InterviewRecord, InterviewStatus } from "../components/ApplicationInterviewPanel";

const INTERVIEWS_ENDPOINT = "/interviews";

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

  const loadInterviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch(INTERVIEWS_ENDPOINT, { headers: { Accept: "application/json" } });
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
                  { key: "status", header: "Status" },
                  { key: "actions", header: "Actions" },
                ]}
                data={filtered.map((interview) => ({
                  id: interview.id,
                  candidate: interview.application?.candidate_name ?? "—",
                  job: interview.application?.job_title ?? "—",
                  type: formatStatus(interview.interview_type),
                  schedule: `${formatDateTime(interview.scheduled_start)} (${interview.timezone})`,
                  interviewer: interview.interviewer?.full_name ?? "—",
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
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}
