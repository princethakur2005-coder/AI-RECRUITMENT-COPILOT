import { useCallback, useEffect, useMemo, useState } from "react";

import { authFetch } from "../lib/api";
import { InterviewAIAnalysisPanel } from "./InterviewAIAnalysisPanel";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Input,
  LoadingState,
  Select,
  Stack,
  Textarea,
  Timeline,
  type TimelineItem,
} from "./index";

export type InterviewStatus = "scheduled" | "completed" | "cancelled" | "no_show";
export type InterviewType = "phone" | "technical" | "hr" | "managerial" | "final" | "ai_screening" | string;

export interface InterviewRecord {
  id: string;
  application_id: string;
  company_id: string;
  interviewer_member_id?: string | null;
  interview_type: InterviewType;
  scheduled_start: string;
  scheduled_end: string;
  timezone: string;
  meeting_link?: string | null;
  location?: string | null;
  notes?: string | null;
  status: InterviewStatus;
  interview_score?: number | null;
  questions_json?: any[] | null;
  answers_json?: Record<string, any> | null;
  evaluation_json?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
  interviewer?: {
    id: string;
    full_name: string;
    email: string;
    role: string;
  } | null;
  application?: {
    id?: string;
    status?: string;
    candidate_name?: string | null;
    job_title?: string | null;
  } | null;
}

const STATUS_TONE: Record<InterviewStatus, "neutral" | "brand" | "success" | "warning" | "danger"> = {
  scheduled: "brand",
  completed: "success",
  cancelled: "danger",
  no_show: "warning",
};

function formatDateTime(value?: string): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatStatus(status: string): string {
  return status.replaceAll("_", " ");
}

interface ApplicationInterviewPanelProps {
  applicationId: string;
  applicationStatus?: string;
  onInterviewChange?: () => void;
}

export function ApplicationInterviewPanel({
  applicationId,
  applicationStatus,
  onInterviewChange,
}: ApplicationInterviewPanelProps) {
  const [interviews, setInterviews] = useState<InterviewRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [actionId, setActionId] = useState<string | null>(null);
  const [expandedAiInterviewId, setExpandedAiInterviewId] = useState<string | null>(null);

  const [editForm, setEditForm] = useState({
    interview_type: "phone" as InterviewType,
    date: "",
    start_time: "",
    end_time: "",
    timezone: "UTC",
    meeting_link: "",
    location: "",
    notes: "",
  });

  const loadInterviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch(`/applications/${applicationId}/interviews`, {
        headers: { Accept: "application/json" },
      });
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
  }, [applicationId]);

  useEffect(() => {
    void loadInterviews();
  }, [loadInterviews]);

  const timelineItems = useMemo((): TimelineItem[] => {
    return interviews.map((interview) => ({
      id: interview.id,
      title: `${formatStatus(interview.interview_type)} interview`,
      description: [
        formatDateTime(interview.scheduled_start),
        interview.interviewer?.full_name ? `Interviewer: ${interview.interviewer.full_name}` : null,
        interview.location ? `Location: ${interview.location}` : null,
        interview.meeting_link ? `Link: ${interview.meeting_link}` : null,
        interview.notes ? interview.notes : null,
      ]
        .filter(Boolean)
        .join(" · "),
      timestamp: interview.scheduled_start,
      meta: formatStatus(interview.status),
    }));
  }, [interviews]);

  const startEdit = (interview: InterviewRecord) => {
    const start = new Date(interview.scheduled_start);
    const end = new Date(interview.scheduled_end);
    setEditingId(interview.id);
    setEditForm({
      interview_type: interview.interview_type,
      date: start.toISOString().slice(0, 10),
      start_time: start.toTimeString().slice(0, 5),
      end_time: end.toTimeString().slice(0, 5),
      timezone: interview.timezone,
      meeting_link: interview.meeting_link ?? "",
      location: interview.location ?? "",
      notes: interview.notes ?? "",
    });
  };

  const updateInterview = async (interviewId: string, payload: Record<string, unknown>) => {
    setActionId(interviewId);
    setError(null);
    try {
      const response = await authFetch(`/interviews/${interviewId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Update failed (${response.status})`);
      }
      setEditingId(null);
      await loadInterviews();
      onInterviewChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update interview");
    } finally {
      setActionId(null);
    }
  };

  const saveEdit = async (interviewId: string) => {
    await updateInterview(interviewId, {
      interview_type: editForm.interview_type,
      scheduled_start: `${editForm.date}T${editForm.start_time}:00`,
      scheduled_end: `${editForm.date}T${editForm.end_time}:00`,
      timezone: editForm.timezone,
      meeting_link: editForm.meeting_link || null,
      location: editForm.location || null,
      notes: editForm.notes || null,
    });
  };

  const cancelInterview = async (interviewId: string) => {
    await updateInterview(interviewId, { status: "cancelled" });
  };

  const completeInterview = async (interviewId: string) => {
    await updateInterview(interviewId, { status: "completed" });
  };

  const deleteInterview = async (interviewId: string) => {
    setActionId(interviewId);
    setError(null);
    try {
      const response = await authFetch(`/interviews/${interviewId}`, { method: "DELETE" });
      if (!response.ok && response.status !== 204) {
        throw new Error(`Delete failed (${response.status})`);
      }
      await loadInterviews();
      onInterviewChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete interview");
    } finally {
      setActionId(null);
    }
  };

  const schedulingBlocked =
    applicationStatus === "hired" || applicationStatus === "rejected";

  if (loading) {
    return <LoadingState title="Loading interviews" description="Fetching interview timeline for this application." />;
  }

  return (
    <Stack gap="4">
      {error ? <Alert tone="danger" description={error} /> : null}
      {schedulingBlocked ? (
        <Alert
          tone="warning"
          title="Scheduling restricted"
          description="Interviews cannot be scheduled for hired or rejected applications."
        />
      ) : null}

      {timelineItems.length ? (
        <Timeline items={timelineItems} />
      ) : (
        <EmptyState title="No interviews scheduled" description="Schedule the first interview for this candidate." />
      )}

      {interviews.map((interview) => (
        <div key={interview.id} className="application-interview-card">
          <Stack gap="2">
            <div className="application-interview-card-header">
              <strong>{formatStatus(interview.interview_type)}</strong>
              <Badge tone={STATUS_TONE[interview.status]}>{formatStatus(interview.status)}</Badge>
            </div>
            <p className="job-application-card-meta">
              {formatDateTime(interview.scheduled_start)} – {formatDateTime(interview.scheduled_end)} ({interview.timezone})
            </p>

            {editingId === interview.id ? (
              <Stack gap="2">
                <Select
                  label="Type"
                  value={editForm.interview_type}
                  onChange={(event) =>
                    setEditForm((prev) => ({ ...prev, interview_type: event.target.value as InterviewType }))
                  }
                  options={[
                    { value: "phone", label: "Phone" },
                    { value: "technical", label: "Technical" },
                    { value: "hr", label: "HR" },
                    { value: "managerial", label: "Managerial" },
                    { value: "final", label: "Final" },
                  ]}
                />
                <Input
                  label="Date"
                  type="date"
                  value={editForm.date}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, date: event.target.value }))}
                />
                <Input
                  label="Start"
                  type="time"
                  value={editForm.start_time}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, start_time: event.target.value }))}
                />
                <Input
                  label="End"
                  type="time"
                  value={editForm.end_time}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, end_time: event.target.value }))}
                />
                <Input
                  label="Timezone"
                  value={editForm.timezone}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, timezone: event.target.value }))}
                />
                <Input
                  label="Meeting link"
                  value={editForm.meeting_link}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, meeting_link: event.target.value }))}
                />
                <Input
                  label="Location"
                  value={editForm.location}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, location: event.target.value }))}
                />
                <Textarea
                  label="Notes"
                  value={editForm.notes}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, notes: event.target.value }))}
                  rows={2}
                />
                <div className="job-application-card-actions">
                  <Button size="sm" onClick={() => void saveEdit(interview.id)} disabled={actionId === interview.id}>
                    Save
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setEditingId(null)}>
                    Cancel edit
                  </Button>
                </div>
              </Stack>
            ) : (
              <div className="job-application-card-actions">
                {interview.status === "scheduled" ? (
                  <>
                    <Button size="sm" variant="secondary" onClick={() => startEdit(interview)}>
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void cancelInterview(interview.id)}
                      disabled={actionId === interview.id}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => void completeInterview(interview.id)}
                      disabled={actionId === interview.id}
                    >
                      Mark completed
                    </Button>
                  </>
                ) : null}
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void deleteInterview(interview.id)}
                  disabled={actionId === interview.id}
                >
                  Delete
                </Button>
              </div>
            )}

            {interview.status === "completed" ? (
              <div className="application-interview-ai-panel">
                <div className="job-application-card-actions">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      setExpandedAiInterviewId((current) =>
                        current === interview.id ? null : interview.id,
                      )
                    }
                  >
                    {expandedAiInterviewId === interview.id
                      ? "Hide intelligence"
                      : "Interview intelligence"}
                  </Button>
                </div>
                {expandedAiInterviewId === interview.id ? (
                  <InterviewAIAnalysisPanel
                    interviewId={interview.id}
                    interviewStatus={interview.status}
                    applicationStatus={applicationStatus ?? interview.application?.status}
                  />
                ) : null}
              </div>
            ) : null}
          </Stack>
        </div>
      ))}
    </Stack>
  );
}
