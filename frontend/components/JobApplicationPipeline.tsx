import { useCallback, useEffect, useMemo, useState } from "react";

import { authFetch } from "../lib/api";
import { Alert, Badge, Button, EmptyState, LoadingState, Select } from "./index";
import { InterviewScheduleForm } from "./InterviewScheduleForm";

export type ApplicationStatus =
  | "applied"
  | "screening"
  | "shortlisted"
  | "interview"
  | "offered"
  | "hired"
  | "rejected";

interface ApplicationCandidate {
  id: string;
  full_name: string;
  email: string;
}

export interface JobApplicationRecord {
  id: string;
  company_id: string;
  job_id: string;
  candidate_id: string;
  resume_path?: string | null;
  status: ApplicationStatus;
  applied_at: string;
  updated_at: string;
  candidate?: ApplicationCandidate | null;
}

const PIPELINE_COLUMNS: Array<{ key: ApplicationStatus; label: string }> = [
  { key: "applied", label: "Applied" },
  { key: "screening", label: "Screening" },
  { key: "shortlisted", label: "Shortlisted" },
  { key: "interview", label: "Interview" },
  { key: "offered", label: "Offered" },
  { key: "hired", label: "Hired" },
  { key: "rejected", label: "Rejected" },
];

const ALLOWED_TRANSITIONS: Record<ApplicationStatus, ApplicationStatus[]> = {
  applied: ["screening", "rejected"],
  screening: ["shortlisted", "rejected"],
  shortlisted: ["interview", "rejected"],
  interview: ["offered", "rejected"],
  offered: ["hired", "rejected"],
  hired: [],
  rejected: [],
};

function formatDate(value?: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

interface JobApplicationPipelineProps {
  jobId: string;
}

export function JobApplicationPipeline({ jobId }: JobApplicationPipelineProps) {
  const [applications, setApplications] = useState<JobApplicationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [scheduleApplicationId, setScheduleApplicationId] = useState<string | null>(null);
  const [scheduleCompanyId, setScheduleCompanyId] = useState<string | null>(null);

  const loadApplications = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch(`/jobs/${jobId}/applications`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Failed to load applications (${response.status})`);
      }
      const payload = (await response.json()) as JobApplicationRecord[];
      setApplications(Array.isArray(payload) ? payload : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load applications");
      setApplications([]);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  const grouped = useMemo(() => {
    const map = new Map<ApplicationStatus, JobApplicationRecord[]>();
    for (const column of PIPELINE_COLUMNS) {
      map.set(column.key, []);
    }
    for (const application of applications) {
      const status = application.status as ApplicationStatus;
      const bucket = map.get(status);
      if (bucket) bucket.push(application);
    }
    return map;
  }, [applications]);

  const updateStatus = async (applicationId: string, status: ApplicationStatus) => {
    setUpdatingId(applicationId);
    setError(null);
    try {
      const response = await authFetch(`/applications/${applicationId}/status`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Status update failed (${response.status})`);
      }
      const updated = (await response.json()) as JobApplicationRecord;
      setApplications((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update application status");
    } finally {
      setUpdatingId(null);
    }
  };

  const downloadResume = async (applicationId: string, filenameHint?: string) => {
    try {
      const response = await authFetch(`/applications/${applicationId}/resume`);
      if (!response.ok) {
        throw new Error(`Resume download failed (${response.status})`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filenameHint ?? `resume-${applicationId}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to download resume");
    }
  };

  if (loading) {
    return <LoadingState title="Loading applications" description="Fetching candidate applications for this job." />;
  }

  return (
    <div className="job-application-pipeline">
      <div className="job-application-pipeline-header">
        <strong>Application Pipeline</strong>
        <Button size="sm" variant="secondary" onClick={() => void loadApplications()}>
          Refresh
        </Button>
      </div>

      {error ? <Alert tone="danger" description={error} /> : null}

      {!applications.length ? (
        <EmptyState title="No applications yet" description="Applications submitted for this job will appear in the pipeline." />
      ) : (
        <div className="job-application-kanban">
          {PIPELINE_COLUMNS.map((column) => {
            const items = grouped.get(column.key) ?? [];
            return (
              <section key={column.key} className="job-application-column" aria-label={column.label}>
                <header className="job-application-column-header">
                  <span>{column.label}</span>
                  <Badge tone="neutral">{items.length}</Badge>
                </header>
                <div className="job-application-column-body">
                  {items.map((application) => {
                    const candidateName = application.candidate?.full_name ?? "Unknown candidate";
                    const candidateEmail = application.candidate?.email ?? "-";
                    const nextStatuses = ALLOWED_TRANSITIONS[application.status as ApplicationStatus] ?? [];
                    return (
                      <article key={application.id} className="job-application-card">
                        <strong>{candidateName}</strong>
                        <p className="job-application-card-meta">{candidateEmail}</p>
                        <p className="job-application-card-meta">Applied: {formatDate(application.applied_at)}</p>
                        <Badge tone="brand">{application.status}</Badge>
                        <div className="job-application-card-actions">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setScheduleApplicationId(application.id);
                              setScheduleCompanyId(application.company_id);
                            }}
                            disabled={application.status === "hired" || application.status === "rejected"}
                          >
                            Schedule interview
                          </Button>
                          <a className="job-application-link" href={`/application/${application.id}`}>
                            View application
                          </a>
                          {nextStatuses.length ? (
                            <Select
                              label="Move to"
                              value=""
                              disabled={updatingId === application.id}
                              onChange={(event) => {
                                const value = event.target.value as ApplicationStatus;
                                if (value) void updateStatus(application.id, value);
                              }}
                              options={[
                                { value: "", label: "Select status..." },
                                ...nextStatuses.map((status) => ({
                                  value: status,
                                  label: status.replaceAll("_", " "),
                                })),
                              ]}
                            />
                          ) : null}
                          {application.resume_path ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => void downloadResume(application.id, candidateName)}
                            >
                              Download resume
                            </Button>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      )}

      {scheduleApplicationId && scheduleCompanyId ? (
        <div className="job-application-schedule-modal" role="dialog" aria-label="Schedule interview">
          <InterviewScheduleForm
            applicationId={scheduleApplicationId}
            companyId={scheduleCompanyId}
            onCancel={() => {
              setScheduleApplicationId(null);
              setScheduleCompanyId(null);
            }}
            onSuccess={() => {
              setScheduleApplicationId(null);
              setScheduleCompanyId(null);
              void loadApplications();
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
