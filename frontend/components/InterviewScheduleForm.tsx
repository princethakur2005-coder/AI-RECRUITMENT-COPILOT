import { useCallback, useEffect, useState, type ReactNode } from "react";

import { authFetch } from "../lib/api";
import { Alert, Button, FormActions, FormWrapper, Input, Select, Stack, Textarea } from "./index";

export type InterviewType = "phone" | "technical" | "hr" | "managerial" | "final";

export interface CompanyMemberOption {
  id: string;
  label: string;
}

export interface InterviewScheduleFormValues {
  interview_type: InterviewType;
  date: string;
  start_time: string;
  end_time: string;
  timezone: string;
  interviewer_member_id: string;
  meeting_link: string;
  location: string;
  notes: string;
}

const INTERVIEW_TYPE_OPTIONS: Array<{ value: InterviewType; label: string }> = [
  { value: "phone", label: "Phone" },
  { value: "technical", label: "Technical" },
  { value: "hr", label: "HR" },
  { value: "managerial", label: "Managerial" },
  { value: "final", label: "Final" },
];

const TIMEZONE_OPTIONS = [
  { value: "UTC", label: "UTC" },
  { value: "America/New_York", label: "America/New_York" },
  { value: "America/Los_Angeles", label: "America/Los_Angeles" },
  { value: "Europe/London", label: "Europe/London" },
  { value: "Asia/Kolkata", label: "Asia/Kolkata" },
  { value: "Asia/Singapore", label: "Asia/Singapore" },
];

function defaultFormValues(): InterviewScheduleFormValues {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const date = tomorrow.toISOString().slice(0, 10);
  return {
    interview_type: "phone",
    date,
    start_time: "10:00",
    end_time: "11:00",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    interviewer_member_id: "",
    meeting_link: "",
    location: "",
    notes: "",
  };
}

function combineDateAndTime(date: string, time: string): string {
  return `${date}T${time}:00`;
}

interface InterviewScheduleFormProps {
  applicationId: string;
  companyId: string;
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function InterviewScheduleForm({
  applicationId,
  companyId,
  onSuccess,
  onCancel,
}: InterviewScheduleFormProps) {
  const [form, setForm] = useState<InterviewScheduleFormValues>(defaultFormValues);
  const [members, setMembers] = useState<CompanyMemberOption[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMembers = useCallback(async () => {
    setLoadingMembers(true);
    try {
      const response = await authFetch(`/companies/${companyId}/members`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Failed to load company members (${response.status})`);
      }
      const payload = (await response.json()) as Array<{
        id: string;
        user?: { full_name?: string; email?: string };
      }>;
      setMembers(
        payload.map((member) => ({
          id: member.id,
          label: member.user?.full_name ?? member.user?.email ?? member.id,
        })),
      );
    } catch (err) {
      setMembers([]);
      setError(err instanceof Error ? err.message : "Unable to load interviewers");
    } finally {
      setLoadingMembers(false);
    }
  }, [companyId]);

  useEffect(() => {
    void loadMembers();
  }, [loadMembers]);

  const setField = <K extends keyof InterviewScheduleFormValues>(field: K, value: InterviewScheduleFormValues[K]) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      if (!form.interviewer_member_id) {
        throw new Error("Select an interviewer");
      }

      const scheduledStart = combineDateAndTime(form.date, form.start_time);
      const scheduledEnd = combineDateAndTime(form.date, form.end_time);

      const response = await authFetch("/interviews", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          application_id: applicationId,
          interviewer_member_id: form.interviewer_member_id,
          interview_type: form.interview_type,
          scheduled_start: scheduledStart,
          scheduled_end: scheduledEnd,
          timezone: form.timezone,
          meeting_link: form.meeting_link || null,
          location: form.location || null,
          notes: form.notes || null,
        }),
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Schedule failed (${response.status})`);
      }

      setForm(defaultFormValues());
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to schedule interview");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <FormWrapper title="Schedule Interview" description="Book an interview for this application.">
      <Stack gap="3">
        {error ? <Alert tone="danger" description={error} /> : null}

        <Select
          label="Interview type"
          value={form.interview_type}
          onChange={(event) => setField("interview_type", event.target.value as InterviewType)}
          options={INTERVIEW_TYPE_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
        />

        <Input label="Date" type="date" value={form.date} onChange={(event) => setField("date", event.target.value)} />

        <GridLike>
          <Input
            label="Start time"
            type="time"
            value={form.start_time}
            onChange={(event) => setField("start_time", event.target.value)}
          />
          <Input
            label="End time"
            type="time"
            value={form.end_time}
            onChange={(event) => setField("end_time", event.target.value)}
          />
        </GridLike>

        <Select
          label="Timezone"
          value={form.timezone}
          onChange={(event) => setField("timezone", event.target.value)}
          options={TIMEZONE_OPTIONS}
        />

        <Select
          label="Interviewer"
          value={form.interviewer_member_id}
          disabled={loadingMembers}
          onChange={(event) => setField("interviewer_member_id", event.target.value)}
          options={[
            { value: "", label: loadingMembers ? "Loading..." : "Select interviewer..." },
            ...members.map((member) => ({ value: member.id, label: member.label })),
          ]}
        />

        <Input
          label="Meeting link"
          value={form.meeting_link}
          onChange={(event) => setField("meeting_link", event.target.value)}
          placeholder="https://..."
        />

        <Input
          label="Location"
          value={form.location}
          onChange={(event) => setField("location", event.target.value)}
          placeholder="Office, room, or address"
        />

        <Textarea
          label="Notes"
          value={form.notes}
          onChange={(event) => setField("notes", event.target.value)}
          rows={3}
        />

        <FormActions>
          {onCancel ? (
            <Button variant="secondary" onClick={onCancel} disabled={submitting}>
              Cancel
            </Button>
          ) : null}
          <Button onClick={() => void handleSubmit()} disabled={submitting || loadingMembers}>
            {submitting ? "Scheduling..." : "Schedule interview"}
          </Button>
        </FormActions>
      </Stack>
    </FormWrapper>
  );
}

function GridLike({ children }: { children: ReactNode }) {
  return <div className="interview-form-grid">{children}</div>;
}
