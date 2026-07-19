import { authFetch } from "../lib/api";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Alert,
  AnalyticsWidget,
  AppLayout,
  Avatar,
  Badge,
  Button,
  ChartWrapper,
  ContentContainer,
  EmptyState,
  ErrorState,
  FormActions,
  FormWrapper,
  Header,
  Input,
  LoadingState,
  MetricCard,
  MotionFade,
  MotionScale,
  MotionSlide,
  Pagination,
  Section,
  Select,
  Stack,
  Table,
  Tabs,
  Textarea,
  Timeline,
  type TimelineItem,
} from "../components";


type Dict = Record<string, number>;

interface CandidateRecord {
  id: string;
  full_name?: string;
  email?: string;
  phone?: string;
  location?: string;
  current_title?: string;
  experience_years?: number;
  summary?: string;
  status?: string;
  skills?: string[];
  resume_text?: string;
  resume_url?: string;
  avatar_url?: string;
  preferences?: Record<string, unknown>;
  [key: string]: unknown;
}

interface OfferRecord {
  id: string;
  candidate_id?: string;
  job_id?: string;
  offer_title?: string;
  status?: string;
  compensation_min?: number;
  compensation_max?: number;
  currency?: string;
  expires_at?: string;
  terms?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

interface ResumeRecord {
  id: string;
  candidate_id?: string;
  file_name?: string;
  status?: string;
  text?: string;
  uploaded_at?: string;
  feedback_summary?: string;
  [key: string]: unknown;
}

interface InterviewRecord {
  id: string;
  candidate_id?: string;
  interviewer_name?: string;
  mode?: string;
  status?: string;
  scheduled_at?: string;
  [key: string]: unknown;
}

interface ApplicationRecord {
  id: string;
  candidate_id?: string;
  job_title?: string;
  company?: string;
  status?: string;
  applied_at?: string;
  updated_at?: string;
  details?: string;
  [key: string]: unknown;
}

interface TimelineRecord {
  id?: string;
  action?: string;
  description?: string;
  timestamp?: string;
  entity_type?: string;
  resource_type?: string;
  entity_id?: string;
  [key: string]: unknown;
}

const API = {
  candidates: "/candidates",
  offersByCandidate: (candidateId: string) => `/offers/candidate/${candidateId}`,
  candidateTimeline: (candidateId: string) => `/candidates/${candidateId}/timeline`,
  resumesByCandidate: (candidateId: string) => `/resumes/candidate/${candidateId}`,
  resumeFeedback: "/resumes/feedback",
  applicationsByCandidate: (candidateId: string) => `/applications/candidate/${candidateId}`,
  interviewsByCandidate: (candidateId: string) => `/interviews/candidate/${candidateId}`,
} as const;

function formatDate(value?: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatCurrency(value?: number, currency = "USD"): string {
  if (typeof value !== "number") return "-";
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

function mapTimeline(records: TimelineRecord[]): TimelineItem[] {
  return records.slice(0, 12).map((item, index) => ({
    id: String(item.id ?? `${item.action ?? "activity"}-${index}`),
    title: String(item.action ?? "Activity").replaceAll("_", " "),
    description: String(item.description ?? item.entity_type ?? item.resource_type ?? "Candidate activity"),
    timestamp: typeof item.timestamp === "string" ? item.timestamp : undefined,
    meta: String(item.entity_id ?? ""),
  }));
}

function statusTone(status?: string): "neutral" | "brand" | "success" | "warning" | "danger" {
  const value = String(status ?? "").toLowerCase();
  if (value.includes("accepted") || value.includes("complete") || value.includes("hired")) return "success";
  if (value.includes("rejected") || value.includes("withdraw") || value.includes("failed")) return "danger";
  if (value.includes("pending") || value.includes("review") || value.includes("scheduled")) return "warning";
  if (value.includes("progress") || value.includes("interview")) return "brand";
  return "neutral";
}

function toStatusCount(rows: Array<{ status?: string }>): Dict {
  return rows.reduce<Dict>((acc, row) => {
    const key = String(row.status ?? "unknown").toLowerCase();
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
}

function barRows(data: Dict): Array<{ label: string; value: number }> {
  return Object.entries(data).map(([label, value]) => ({ label, value }));
}

function maxValue(rows: Array<{ value: number }>): number {
  return rows.reduce((acc, row) => Math.max(acc, row.value), 0);
}

export default function CandidatePortalPage() {
  const [candidates, setCandidates] = useState<CandidateRecord[]>([]);
  const [activeCandidateId, setActiveCandidateId] = useState<string>("");

  const [timeline, setTimeline] = useState<TimelineRecord[]>([]);
  const [offers, setOffers] = useState<OfferRecord[]>([]);
  const [resumes, setResumes] = useState<ResumeRecord[]>([]);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [interviews, setInterviews] = useState<InterviewRecord[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [appSearch, setAppSearch] = useState("");
  const [offerSearch, setOfferSearch] = useState("");
  const [resumeSearch, setResumeSearch] = useState("");
  const [interviewSearch, setInterviewSearch] = useState("");

  const [applicationsPage, setApplicationsPage] = useState(1);
  const [offersPage, setOffersPage] = useState(1);

  const [resumePreview, setResumePreview] = useState("");
  const [resumeFeedback, setResumeFeedback] = useState("");
  const [resumeUploadName, setResumeUploadName] = useState("");
  const [resumeUploadFile, setResumeUploadFile] = useState<File | null>(null);

  const [profileSaving, setProfileSaving] = useState(false);
  const [resumeFeedbackLoading, setResumeFeedbackLoading] = useState(false);
  const [resumeActionMessage, setResumeActionMessage] = useState<string | null>(null);

  const [profileName, setProfileName] = useState("");
  const [profileEmail, setProfileEmail] = useState("");
  const [profilePhone, setProfilePhone] = useState("");
  const [profileLocation, setProfileLocation] = useState("");
  const [profileTitle, setProfileTitle] = useState("");
  const [profileSummary, setProfileSummary] = useState("");
  const [profileSkills, setProfileSkills] = useState("");
  const [profileExperience, setProfileExperience] = useState("0");
  const [profilePreferences, setProfilePreferences] = useState("{}");
  const [profileAvatarUrl, setProfileAvatarUrl] = useState("");

  const activeCandidate = useMemo(
    () => candidates.find((item) => item.id === activeCandidateId) ?? null,
    [activeCandidateId, candidates],
  );

  const hydrateProfile = useCallback((candidate: CandidateRecord | null) => {
    setProfileName(String(candidate?.full_name ?? ""));
    setProfileEmail(String(candidate?.email ?? ""));
    setProfilePhone(String(candidate?.phone ?? ""));
    setProfileLocation(String(candidate?.location ?? ""));
    setProfileTitle(String(candidate?.current_title ?? ""));
    setProfileSummary(String(candidate?.summary ?? ""));
    setProfileSkills(Array.isArray(candidate?.skills) ? candidate!.skills!.join(", ") : "");
    setProfileExperience(String(candidate?.experience_years ?? 0));
    setProfilePreferences(JSON.stringify(candidate?.preferences ?? {}, null, 2));
    setProfileAvatarUrl(String(candidate?.avatar_url ?? ""));
    setResumePreview(String(candidate?.resume_text ?? ""));
  }, []);

  const loadCandidateData = useCallback(
    async (candidateId: string) => {
      const [timelineRes, offersRes, resumesRes, applicationsRes, interviewsRes] = await Promise.all([
        fetch(API.candidateTimeline(candidateId), { headers: { Accept: "application/json" } }),
        fetch(API.offersByCandidate(candidateId), { headers: { Accept: "application/json" } }),
        fetch(API.resumesByCandidate(candidateId), { headers: { Accept: "application/json" } }),
        fetch(API.applicationsByCandidate(candidateId), { headers: { Accept: "application/json" } }),
        fetch(API.interviewsByCandidate(candidateId), { headers: { Accept: "application/json" } }),
      ]);

      if (timelineRes.ok) {
        const payload = (await timelineRes.json()) as TimelineRecord[];
        setTimeline(Array.isArray(payload) ? payload : []);
      } else {
        setTimeline([]);
      }

      if (offersRes.ok) {
        const payload = (await offersRes.json()) as OfferRecord[];
        setOffers(Array.isArray(payload) ? payload : []);
      } else {
        setOffers([]);
      }

      if (resumesRes.ok) {
        const payload = (await resumesRes.json()) as ResumeRecord[];
        const rows = Array.isArray(payload) ? payload : [];
        setResumes(rows);
        if (rows.length) {
          setResumePreview(String(rows[0].text ?? resumePreview));
        }
      } else {
        setResumes([]);
      }

      if (applicationsRes.ok) {
        const payload = (await applicationsRes.json()) as ApplicationRecord[];
        setApplications(Array.isArray(payload) ? payload : []);
      } else {
        setApplications([]);
      }

      if (interviewsRes.ok) {
        const payload = (await interviewsRes.json()) as InterviewRecord[];
        setInterviews(Array.isArray(payload) ? payload : []);
      } else {
        setInterviews([]);
      }
    },
    [resumePreview],
  );

  const loadPortal = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResumeActionMessage(null);

    try {
      const candidatesResponse = await authFetch(API.candidates, {
        headers: {
          Accept: "application/json",
        },
      });

      if (!candidatesResponse.ok) {
        throw new Error(`Failed to load candidates (${candidatesResponse.status})`);
      }

      const candidatesPayload = (await candidatesResponse.json()) as CandidateRecord[];
      const list = Array.isArray(candidatesPayload) ? candidatesPayload : [];
      setCandidates(list);

      const resolvedId = activeCandidateId || list[0]?.id || "";
      if (!resolvedId) {
        setActiveCandidateId("");
        setTimeline([]);
        setOffers([]);
        setResumes([]);
        setApplications([]);
        setInterviews([]);
        hydrateProfile(null);
        return;
      }

      setActiveCandidateId(resolvedId);
      const selected = list.find((item) => item.id === resolvedId) ?? list[0] ?? null;
      hydrateProfile(selected);

      await loadCandidateData(resolvedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load candidate portal");
      setCandidates([]);
      setTimeline([]);
      setOffers([]);
      setResumes([]);
      setApplications([]);
      setInterviews([]);
    } finally {
      setLoading(false);
    }
  }, [activeCandidateId, hydrateProfile, loadCandidateData]);

  useEffect(() => {
    void loadPortal();
  }, [loadPortal]);

  const onCandidateChange = async (candidateId: string) => {
    setActiveCandidateId(candidateId);
    const selected = candidates.find((item) => item.id === candidateId) ?? null;
    hydrateProfile(selected);
    setLoading(true);
    setError(null);
    try {
      await loadCandidateData(candidateId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load selected candidate data");
    } finally {
      setLoading(false);
    }
  };

  const dashboardTimeline = useMemo(() => mapTimeline(timeline), [timeline]);

  const applicationStatusRows = useMemo(() => barRows(toStatusCount(applications)), [applications]);
  const offerStatusRows = useMemo(() => barRows(toStatusCount(offers)), [offers]);

  const filteredApplications = useMemo(() => {
    const normalized = appSearch.trim().toLowerCase();
    return applications.filter((item) => {
      if (!normalized) return true;
      return (
        String(item.job_title ?? "").toLowerCase().includes(normalized) ||
        String(item.company ?? "").toLowerCase().includes(normalized) ||
        String(item.status ?? "").toLowerCase().includes(normalized)
      );
    });
  }, [appSearch, applications]);

  const filteredOffers = useMemo(() => {
    const normalized = offerSearch.trim().toLowerCase();
    return offers.filter((item) => {
      if (!normalized) return true;
      return (
        String(item.offer_title ?? "").toLowerCase().includes(normalized) ||
        String(item.status ?? "").toLowerCase().includes(normalized) ||
        String(item.job_id ?? "").toLowerCase().includes(normalized)
      );
    });
  }, [offerSearch, offers]);

  const filteredResumes = useMemo(() => {
    const normalized = resumeSearch.trim().toLowerCase();
    return resumes.filter((item) => {
      if (!normalized) return true;
      return (
        String(item.file_name ?? "").toLowerCase().includes(normalized) ||
        String(item.status ?? "").toLowerCase().includes(normalized)
      );
    });
  }, [resumeSearch, resumes]);

  const filteredInterviews = useMemo(() => {
    const normalized = interviewSearch.trim().toLowerCase();
    return interviews.filter((item) => {
      if (!normalized) return true;
      return (
        String(item.interviewer_name ?? "").toLowerCase().includes(normalized) ||
        String(item.mode ?? "").toLowerCase().includes(normalized) ||
        String(item.status ?? "").toLowerCase().includes(normalized)
      );
    });
  }, [interviewSearch, interviews]);

  const applicationsPageSize = 8;
  const offersPageSize = 8;

  const applicationsTotalPages = Math.max(1, Math.ceil(filteredApplications.length / applicationsPageSize));
  const offersTotalPages = Math.max(1, Math.ceil(filteredOffers.length / offersPageSize));

  useEffect(() => {
    if (applicationsPage > applicationsTotalPages) setApplicationsPage(applicationsTotalPages);
  }, [applicationsPage, applicationsTotalPages]);

  useEffect(() => {
    if (offersPage > offersTotalPages) setOffersPage(offersTotalPages);
  }, [offersPage, offersTotalPages]);

  const pagedApplications = useMemo(() => {
    const start = (applicationsPage - 1) * applicationsPageSize;
    return filteredApplications.slice(start, start + applicationsPageSize);
  }, [applicationsPage, filteredApplications]);

  const pagedOffers = useMemo(() => {
    const start = (offersPage - 1) * offersPageSize;
    return filteredOffers.slice(start, start + offersPageSize);
  }, [filteredOffers, offersPage]);

  const upcomingInterviews = useMemo(() => {
    const now = Date.now();
    return filteredInterviews.filter((item) => {
      if (!item.scheduled_at) return false;
      const parsed = new Date(item.scheduled_at).getTime();
      return !Number.isNaN(parsed) && parsed >= now;
    });
  }, [filteredInterviews]);

  const dashboardStats = useMemo(
    () => ({
      applications: applications.length,
      interviews: interviews.length,
      offers: offers.length,
      pending: offers.filter((item) => String(item.status ?? "").toLowerCase().includes("pending")).length,
    }),
    [applications.length, interviews.length, offers],
  );

  const saveProfile = async () => {
    if (!activeCandidateId) return;

    setProfileSaving(true);
    setResumeActionMessage(null);
    try {
      const parsedPrefs = (() => {
        try {
          return JSON.parse(profilePreferences || "{}");
        } catch {
          return {};
        }
      })();

      const response = await authFetch(`${API.candidates}/${activeCandidateId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          full_name: profileName,
          email: profileEmail,
          phone: profilePhone,
          location: profileLocation,
          current_title: profileTitle,
          summary: profileSummary,
          skills: profileSkills
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          experience_years: Number(profileExperience) || 0,
          preferences: parsedPrefs,
          avatar_url: profileAvatarUrl,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to update profile (${response.status})`);
      }

      setResumeActionMessage("Profile updated successfully.");
      await loadPortal();
    } catch (err) {
      setResumeActionMessage(err instanceof Error ? err.message : "Failed to update profile");
    } finally {
      setProfileSaving(false);
    }
  };

  const requestResumeFeedback = async () => {
    if (!activeCandidateId) return;

    setResumeFeedbackLoading(true);
    setResumeFeedback("");
    try {
      const response = await authFetch(API.resumeFeedback, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          candidate_id: activeCandidateId,
          resume_text: resumePreview,
        }),
      });

      if (!response.ok) {
        throw new Error(`AI resume feedback is currently unavailable (${response.status})`);
      }

      const payload = (await response.json()) as { summary?: string; feedback?: string; content?: string };
      setResumeFeedback(String(payload.feedback ?? payload.summary ?? payload.content ?? "No feedback returned."));
    } catch (err) {
      setResumeFeedback(err instanceof Error ? err.message : "Unable to generate resume feedback");
    } finally {
      setResumeFeedbackLoading(false);
    }
  };

  const applicationBarMax = Math.max(1, maxValue(applicationStatusRows));
  const offerBarMax = Math.max(1, maxValue(offerStatusRows));

  const hasData = Boolean(candidates.length);

  return (
    <AppLayout
      className="candidate-portal-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="candidate-portal-title">Candidate Portal</h1>
              <p className="candidate-portal-subtitle">Application journey, resume intelligence, interviews, offers, and profile in one workspace.</p>
            </Stack>
          }
          right={
            <div className="candidate-portal-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadPortal()}>
                Refresh
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="candidate-portal-main" fluid>
        {loading ? <LoadingState title="Loading candidate portal" description="Fetching dashboard, applications, interviews, offers, resume, and profile data." /> : null}
        {!loading && error ? <ErrorState title="Unable to load candidate portal" description={error} onRetry={() => void loadPortal()} /> : null}
        {!loading && !error && !hasData ? (
          <EmptyState
            title="No candidate records"
            description="Candidate portal will appear once candidate records are available."
            actionLabel="Reload"
            onAction={() => void loadPortal()}
          />
        ) : null}

        {!loading && !error && hasData ? (
          <MotionFade active>
            <Stack gap="5">
              <Section>
                <div className="candidate-portal-toolbar">
                  <Select
                    label="Candidate"
                    value={activeCandidateId}
                    onChange={(event) => {
                      void onCandidateChange(event.target.value);
                    }}
                    options={candidates.map((item) => ({
                      value: item.id,
                      label: item.full_name || item.email || item.id,
                    }))}
                  />
                  <Input label="Candidate Email" value={activeCandidate?.email || "-"} disabled />
                  <Input label="Current Status" value={activeCandidate?.status || "-"} disabled />
                </div>
              </Section>

              <Tabs.Root defaultValue="dashboard">
                <Tabs.List>
                  <Tabs.Trigger value="dashboard">Dashboard</Tabs.Trigger>
                  <Tabs.Trigger value="resume">Resume</Tabs.Trigger>
                  <Tabs.Trigger value="applications">Applications</Tabs.Trigger>
                  <Tabs.Trigger value="interviews">Interviews</Tabs.Trigger>
                  <Tabs.Trigger value="offers">Offers</Tabs.Trigger>
                  <Tabs.Trigger value="profile">Profile</Tabs.Trigger>
                </Tabs.List>

                <Tabs.Panel value="dashboard">
                  <MotionSlide active>
                    <Stack gap="4">
                      <section aria-label="Candidate dashboard summary">
                        <div className="candidate-kpi-grid">
                          <MetricCard label="Applications" value={dashboardStats.applications} meta="Application overview" />
                          <MetricCard label="Interviews" value={dashboardStats.interviews} meta="Interview schedule" />
                          <MetricCard label="Offers" value={dashboardStats.offers} meta="Offer overview" />
                          <MetricCard label="Pending Offers" value={dashboardStats.pending} meta="Status summary" />
                        </div>
                      </section>

                      <section className="candidate-two-col" aria-label="Status and activity">
                        <ChartWrapper title="Application Status Progression" description="Status progression from candidate application tracking">
                          {applicationStatusRows.length ? (
                            <div className="candidate-chart-bars">
                              {applicationStatusRows.map((row) => {
                                const width = (row.value / applicationBarMax) * 100;
                                return (
                                  <div key={row.label} className="candidate-chart-row">
                                    <span className="candidate-chart-label">{row.label}</span>
                                    <span className="candidate-chart-track" title={`${row.label}: ${row.value}`}>
                                      <span className="candidate-chart-fill" style={{ width: `${width}%` }} />
                                    </span>
                                    <span className="candidate-chart-value">{row.value}</span>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <EmptyState title="No application status data" description="Application progression metrics will appear here." />
                          )}
                        </ChartWrapper>

                        <AnalyticsWidget title="Recent Activity" description="Latest candidate portal activities and status events">
                          {dashboardTimeline.length ? (
                            <Timeline items={dashboardTimeline} />
                          ) : (
                            <EmptyState title="No recent activity" description="Candidate activity timeline will appear here." />
                          )}
                        </AnalyticsWidget>
                      </section>
                    </Stack>
                  </MotionSlide>
                </Tabs.Panel>

                <Tabs.Panel value="resume">
                  <MotionScale active>
                    <Stack gap="4">
                      <section aria-label="Resume upload and management">
                        <div className="resume-upload-row">
                          <Input
                            label="Resume Name"
                            placeholder="Candidate_Resume.pdf"
                            value={resumeUploadName}
                            onChange={(event) => setResumeUploadName(event.target.value)}
                          />
                          <input
                            aria-label="Resume file upload"
                            type="file"
                            onChange={(event) => setResumeUploadFile(event.target.files?.[0] ?? null)}
                          />
                        </div>
                        <div className="candidate-portal-actions" style={{ marginTop: "var(--space-3)" }}>
                          <Button
                            variant="secondary"
                            onClick={() => {
                              const fileLabel = resumeUploadFile?.name || resumeUploadName || "resume";
                              setResumeActionMessage(`Resume upload UI captured for ${fileLabel}. Backend upload is not enabled in this implementation.`);
                            }}
                          >
                            Upload Resume (UI)
                          </Button>
                          <Button onClick={() => void requestResumeFeedback()} disabled={resumeFeedbackLoading || !resumePreview.trim()}>
                            {resumeFeedbackLoading ? "Generating..." : "Get AI Resume Feedback"}
                          </Button>
                        </div>
                      </section>

                      {resumeActionMessage ? <Alert tone="info" description={resumeActionMessage} /> : null}

                      <section className="candidate-two-col" aria-label="Resume management and preview">
                        <AnalyticsWidget title="Resume Management" description="Manage and search uploaded resumes">
                          <div className="portal-mini-toolbar">
                            <Input
                              label="Search Resumes"
                              placeholder="Search by filename or status"
                              value={resumeSearch}
                              onChange={(event) => setResumeSearch(event.target.value)}
                            />
                            <Input label="Total Resumes" value={String(filteredResumes.length)} disabled />
                            <Input label="Latest Upload" value={formatDate(filteredResumes[0]?.uploaded_at)} disabled />
                          </div>

                          {filteredResumes.length ? (
                            <Table
                              columns={[
                                { key: "file_name", header: "File" },
                                {
                                  key: "status",
                                  header: "Status",
                                  render: (row: ResumeRecord) => <Badge tone={statusTone(row.status)}>{row.status || "unknown"}</Badge>,
                                },
                                {
                                  key: "uploaded_at",
                                  header: "Uploaded",
                                  render: (row: ResumeRecord) => formatDate(row.uploaded_at),
                                },
                                {
                                  key: "preview",
                                  header: "Preview",
                                  render: (row: ResumeRecord) => (
                                    <Button
                                      size="sm"
                                      variant="secondary"
                                      onClick={() => setResumePreview(String(row.text ?? activeCandidate?.resume_text ?? ""))}
                                    >
                                      Open
                                    </Button>
                                  ),
                                },
                              ]}
                              data={filteredResumes}
                              rowKey="id"
                            />
                          ) : (
                            <EmptyState title="No resumes found" description="Upload or sync resumes to manage them here." />
                          )}
                        </AnalyticsWidget>

                        <AnalyticsWidget title="Resume Preview & AI Feedback" description="Preview resume content and generated AI feedback">
                          <div className="resume-preview" role="region" aria-label="Resume preview panel">
                            {resumePreview || "No resume preview available."}
                          </div>
                          {resumeFeedback ? <Alert tone="success" title="AI Resume Feedback" description={resumeFeedback} /> : null}
                        </AnalyticsWidget>
                      </section>
                    </Stack>
                  </MotionScale>
                </Tabs.Panel>

                <Tabs.Panel value="applications">
                  <MotionSlide active>
                    <Stack gap="4">
                      <section>
                        <div className="portal-mini-toolbar">
                          <Input
                            label="Search Applications"
                            placeholder="Search by job, company, or status"
                            value={appSearch}
                            onChange={(event) => {
                              setAppSearch(event.target.value);
                              setApplicationsPage(1);
                            }}
                          />
                          <Input label="Total" value={String(filteredApplications.length)} disabled />
                          <Input label="Current Status" value={activeCandidate?.status || "-"} disabled />
                        </div>
                      </section>

                      <section className="candidate-two-col" aria-label="Application tracking and timeline">
                        <AnalyticsWidget title="Application Tracking" description="Application details and status progression">
                          {pagedApplications.length ? (
                            <>
                              <Table
                                columns={[
                                  { key: "job_title", header: "Job" },
                                  { key: "company", header: "Company" },
                                  {
                                    key: "status",
                                    header: "Status",
                                    render: (row: ApplicationRecord) => <Badge tone={statusTone(row.status)}>{row.status || "unknown"}</Badge>,
                                  },
                                  {
                                    key: "applied_at",
                                    header: "Applied",
                                    render: (row: ApplicationRecord) => formatDate(row.applied_at),
                                  },
                                  {
                                    key: "details",
                                    header: "Details",
                                    render: (row: ApplicationRecord) => row.details || "-",
                                  },
                                ]}
                                data={pagedApplications}
                                rowKey="id"
                              />
                              <Pagination
                                page={applicationsPage}
                                pageSize={applicationsPageSize}
                                total={filteredApplications.length}
                                onPageChange={setApplicationsPage}
                                siblingCount={1}
                                showPageButtons
                              />
                            </>
                          ) : (
                            <EmptyState title="No applications" description="Applications will appear when application tracking data is available." />
                          )}
                        </AnalyticsWidget>

                        <AnalyticsWidget title="Application Timeline" description="Chronological application and candidate events">
                          {dashboardTimeline.length ? <Timeline items={dashboardTimeline} /> : <EmptyState title="No timeline entries" description="Application timeline entries will appear here." />}
                        </AnalyticsWidget>
                      </section>
                    </Stack>
                  </MotionSlide>
                </Tabs.Panel>

                <Tabs.Panel value="interviews">
                  <MotionFade active>
                    <Stack gap="4">
                      <section>
                        <div className="portal-mini-toolbar">
                          <Input
                            label="Search Interviews"
                            placeholder="Search by interviewer, mode, or status"
                            value={interviewSearch}
                            onChange={(event) => setInterviewSearch(event.target.value)}
                          />
                          <Input label="Upcoming" value={String(upcomingInterviews.length)} disabled />
                          <Input label="Total Interviews" value={String(filteredInterviews.length)} disabled />
                        </div>
                      </section>

                      <section className="candidate-two-col" aria-label="Interview schedule and details">
                        <AnalyticsWidget title="Interview Schedule" description="Upcoming interviews and schedules">
                          {filteredInterviews.length ? (
                            <Table
                              columns={[
                                {
                                  key: "scheduled_at",
                                  header: "Schedule",
                                  render: (row: InterviewRecord) => formatDate(row.scheduled_at),
                                },
                                { key: "interviewer_name", header: "Interviewer" },
                                { key: "mode", header: "Mode" },
                                {
                                  key: "status",
                                  header: "Status",
                                  render: (row: InterviewRecord) => <Badge tone={statusTone(row.status)}>{row.status || "unknown"}</Badge>,
                                },
                              ]}
                              data={filteredInterviews}
                              rowKey="id"
                            />
                          ) : (
                            <EmptyState title="No interview schedule" description="Interview schedule appears once interviews are planned." />
                          )}
                        </AnalyticsWidget>

                        <AnalyticsWidget title="Upcoming Interviews" description="Focused list of upcoming interviews and details">
                          {upcomingInterviews.length ? (
                            <Table
                              columns={[
                                {
                                  key: "scheduled_at",
                                  header: "Scheduled",
                                  render: (row: InterviewRecord) => formatDate(row.scheduled_at),
                                },
                                { key: "interviewer_name", header: "Interviewer" },
                                { key: "mode", header: "Mode" },
                                {
                                  key: "status",
                                  header: "Status",
                                  render: (row: InterviewRecord) => <Badge tone={statusTone(row.status)}>{row.status || "upcoming"}</Badge>,
                                },
                              ]}
                              data={upcomingInterviews}
                              rowKey="id"
                            />
                          ) : (
                            <EmptyState title="No upcoming interviews" description="There are no upcoming interviews for this candidate." />
                          )}
                        </AnalyticsWidget>
                      </section>
                    </Stack>
                  </MotionFade>
                </Tabs.Panel>

                <Tabs.Panel value="offers">
                  <MotionScale active>
                    <Stack gap="4">
                      <section>
                        <div className="portal-mini-toolbar">
                          <Input
                            label="Search Offers"
                            placeholder="Search by title, status, or job"
                            value={offerSearch}
                            onChange={(event) => {
                              setOfferSearch(event.target.value);
                              setOffersPage(1);
                            }}
                          />
                          <Input label="Total Offers" value={String(filteredOffers.length)} disabled />
                          <Input
                            label="Accepted"
                            value={String(filteredOffers.filter((item) => String(item.status ?? "").toLowerCase().includes("accepted")).length)}
                            disabled
                          />
                        </div>
                      </section>

                      <section className="candidate-two-col" aria-label="Offer overview and details">
                        <AnalyticsWidget title="Offer Overview" description="Offer status and key compensation details">
                          {pagedOffers.length ? (
                            <>
                              <Table
                                columns={[
                                  { key: "offer_title", header: "Offer" },
                                  {
                                    key: "status",
                                    header: "Status",
                                    render: (row: OfferRecord) => <Badge tone={statusTone(row.status)}>{row.status || "unknown"}</Badge>,
                                  },
                                  {
                                    key: "compensation",
                                    header: "Compensation",
                                    render: (row: OfferRecord) =>
                                      `${formatCurrency(row.compensation_min, row.currency || "USD")} - ${formatCurrency(row.compensation_max, row.currency || "USD")}`,
                                  },
                                  {
                                    key: "expires_at",
                                    header: "Expires",
                                    render: (row: OfferRecord) => formatDate(row.expires_at),
                                  },
                                ]}
                                data={pagedOffers}
                                rowKey="id"
                              />
                              <Pagination
                                page={offersPage}
                                pageSize={offersPageSize}
                                total={filteredOffers.length}
                                onPageChange={setOffersPage}
                                siblingCount={1}
                                showPageButtons
                              />
                            </>
                          ) : (
                            <EmptyState title="No offers" description="Offer overview appears when offers are issued." />
                          )}
                        </AnalyticsWidget>

                        <ChartWrapper title="Offer Status" description="Status summary for all candidate offers">
                          {offerStatusRows.length ? (
                            <div className="candidate-chart-bars">
                              {offerStatusRows.map((row) => {
                                const width = (row.value / offerBarMax) * 100;
                                return (
                                  <div key={row.label} className="candidate-chart-row">
                                    <span className="candidate-chart-label">{row.label}</span>
                                    <span className="candidate-chart-track" title={`${row.label}: ${row.value}`}>
                                      <span className="candidate-chart-fill" style={{ width: `${width}%` }} />
                                    </span>
                                    <span className="candidate-chart-value">{row.value}</span>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <EmptyState title="No offer status data" description="Offer status chart appears when offers are available." />
                          )}
                        </ChartWrapper>
                      </section>
                    </Stack>
                  </MotionScale>
                </Tabs.Panel>

                <Tabs.Panel value="profile">
                  <MotionSlide active>
                    <Stack gap="4">
                      <section className="profile-grid" aria-label="Candidate profile and account info">
                        <Section elevated>
                          <Stack gap="3">
                            <strong>Candidate Profile</strong>
                            <div className="profile-avatar-block">
                              <Avatar src={profileAvatarUrl} name={profileName || profileEmail || "Candidate"} size="lg" />
                              <Input
                                label="Avatar URL"
                                value={profileAvatarUrl}
                                onChange={(event) => setProfileAvatarUrl(event.target.value)}
                                placeholder="https://example.com/avatar.png"
                              />
                              <p className="profile-meta">Avatar management UI only. No file-upload backend is implemented here.</p>
                            </div>

                            <FormWrapper
                              columns={2}
                              onSubmit={(event) => {
                                event.preventDefault();
                                void saveProfile();
                              }}
                            >
                              <Input label="Full Name" value={profileName} onChange={(event) => setProfileName(event.target.value)} />
                              <Input label="Email" type="email" value={profileEmail} onChange={(event) => setProfileEmail(event.target.value)} />
                              <Input label="Phone" value={profilePhone} onChange={(event) => setProfilePhone(event.target.value)} />
                              <Input label="Location" value={profileLocation} onChange={(event) => setProfileLocation(event.target.value)} />
                              <Input label="Current Title" value={profileTitle} onChange={(event) => setProfileTitle(event.target.value)} />
                              <Input
                                label="Experience (Years)"
                                type="number"
                                min={0}
                                value={profileExperience}
                                onChange={(event) => setProfileExperience(event.target.value)}
                              />
                              <Input
                                label="Skills"
                                value={profileSkills}
                                onChange={(event) => setProfileSkills(event.target.value)}
                                placeholder="React, TypeScript, SQL"
                              />
                              <Textarea
                                label="Summary"
                                value={profileSummary}
                                onChange={(event) => setProfileSummary(event.target.value)}
                                placeholder="Candidate summary"
                              />
                              <Textarea
                                label="Preferences (JSON)"
                                value={profilePreferences}
                                onChange={(event) => setProfilePreferences(event.target.value)}
                                placeholder='{"remote": true, "location": "Bangalore"}'
                              />
                              <FormActions submitLabel="Save Profile" submitting={profileSaving} />
                            </FormWrapper>
                          </Stack>
                        </Section>

                        <Section elevated>
                          <Stack gap="3">
                            <strong>Account Information & Activity Summary</strong>
                            <Table
                              columns={[
                                { key: "field", header: "Field" },
                                { key: "value", header: "Value" },
                              ]}
                              data={[
                                { field: "Candidate ID", value: activeCandidate?.id || "-" },
                                { field: "Status", value: activeCandidate?.status || "-" },
                                { field: "Current Title", value: activeCandidate?.current_title || "-" },
                                { field: "Experience", value: `${activeCandidate?.experience_years ?? 0} years` },
                                { field: "Offers", value: offers.length },
                                { field: "Interviews", value: interviews.length },
                              ]}
                              rowKey="field"
                            />

                            {dashboardTimeline.length ? (
                              <Timeline items={dashboardTimeline} />
                            ) : (
                              <EmptyState title="No activity summary" description="Candidate activity summary appears when events are available." />
                            )}
                          </Stack>
                        </Section>
                      </section>
                    </Stack>
                  </MotionSlide>
                </Tabs.Panel>
              </Tabs.Root>
            </Stack>
          </MotionFade>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}


