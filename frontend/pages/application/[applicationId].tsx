import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/router";

import { authFetch } from "../../lib/api";
import {
  AppLayout,
  ApplicationAIAnalysisPanel,
  ApplicationHiringDecisionPanel,
  ApplicationInterviewPanel,
  Badge,
  Button,
  ContentContainer,
  ErrorState,
  Header,
  InterviewScheduleForm,
  LoadingState,
  Section,
  Stack,
} from "../../components";

interface ApplicationDetail {
  id: string;
  company_id: string;
  job_id: string;
  candidate_id: string;
  status: string;
  applied_at: string;
  updated_at: string;
  resume_path?: string | null;
  candidate?: {
    id: string;
    full_name: string;
    email: string;
  } | null;
}

export default function ApplicationDetailPage() {
  const router = useRouter();
  const applicationId = typeof router.query.applicationId === "string" ? router.query.applicationId : "";

  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showScheduleForm, setShowScheduleForm] = useState(false);

  const loadApplication = useCallback(async () => {
    if (!applicationId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch(`/applications/${applicationId}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Failed to load application (${response.status})`);
      }
      const payload = (await response.json()) as ApplicationDetail;
      setApplication(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load application");
      setApplication(null);
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    void loadApplication();
  }, [loadApplication]);

  const schedulingBlocked = application?.status === "hired" || application?.status === "rejected";

  return (
    <AppLayout
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="recruiter-dashboard-title">Application Detail</h1>
              <p className="recruiter-dashboard-subtitle">Interview timeline and scheduling</p>
            </Stack>
          }
          right={
            <Button variant="secondary" size="sm" onClick={() => router.back()}>
              Back
            </Button>
          }
        />
      }
    >
      <ContentContainer fluid>
        {loading ? <LoadingState title="Loading application" description="Fetching application details." /> : null}
        {!loading && error ? (
          <ErrorState title="Unable to load application" description={error} onRetry={() => void loadApplication()} />
        ) : null}

        {!loading && !error && application ? (
          <Stack gap="6">
            <Section elevated>
              <Stack gap="2">
                <strong>{application.candidate?.full_name ?? "Candidate"}</strong>
                <p className="job-application-card-meta">{application.candidate?.email ?? "—"}</p>
                <Badge tone="brand">{application.status.replaceAll("_", " ")}</Badge>
                <p className="job-application-card-meta">
                  Applied: {new Date(application.applied_at).toLocaleString()}
                </p>
                {!schedulingBlocked ? (
                  <Button size="sm" variant="secondary" onClick={() => setShowScheduleForm((prev) => !prev)}>
                    {showScheduleForm ? "Hide schedule form" : "Schedule interview"}
                  </Button>
                ) : null}
              </Stack>
            </Section>

            {showScheduleForm && !schedulingBlocked ? (
              <InterviewScheduleForm
                applicationId={application.id}
                companyId={application.company_id}
                onCancel={() => setShowScheduleForm(false)}
                onSuccess={() => {
                  setShowScheduleForm(false);
                  void loadApplication();
                }}
              />
            ) : null}

            <Section elevated>
              <Stack gap="3">
                <h2 className="recruiter-dashboard-title">AI Resume Analysis</h2>
                <ApplicationAIAnalysisPanel applicationId={application.id} />
              </Stack>
            </Section>

            <Section elevated>
              <Stack gap="3">
                <h2 className="recruiter-dashboard-title">Hiring Decision</h2>
                <ApplicationHiringDecisionPanel applicationId={application.id} />
              </Stack>
            </Section>

            <Section elevated>
              <Stack gap="3">
                <h2 className="recruiter-dashboard-title">Interview Timeline</h2>
                <ApplicationInterviewPanel
                  applicationId={application.id}
                  applicationStatus={application.status}
                  onInterviewChange={() => void loadApplication()}
                />
              </Stack>
            </Section>
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}
