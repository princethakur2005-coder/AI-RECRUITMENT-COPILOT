import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Button } from "../../components/core/Button";
import { Badge } from "../../components/core/Badge";

interface PublicJobDetails {
  id: string;
  title: string;
  department?: string | null;
  location?: string | null;
  employment_type?: string | null;
  experience_level?: string | null;
  description?: string | null;
  requirements?: string[];
  company_name?: string | null;
  status: string;
}

interface PublicApplySuccess {
  application_id: string;
  job_id: string;
  candidate_id: string;
  status: string;
  applied_at: string;
  message?: string;
}

function readErrorMessage(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const record = data as Record<string, unknown>;
  const detail = record.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "object" && item !== null && "msg" in item) {
          return String((item as { msg?: string }).msg ?? "");
        }
        return String(item);
      })
      .filter(Boolean)
      .join("; ");
  }
  if (typeof record.message === "string") return record.message;
  return fallback;
}

export default function PublicApplyPage() {
  const router = useRouter();
  const jobId = typeof router.query.jobId === "string" ? router.query.jobId : "";

  const [job, setJob] = useState<PublicJobDetails | null>(null);
  const [jobLoading, setJobLoading] = useState(true);
  const [jobNotFound, setJobNotFound] = useState(false);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<PublicApplySuccess | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!router.isReady) return;
    if (!jobId) {
      setJobLoading(false);
      setJobNotFound(true);
      return;
    }

    let isMounted = true;
    setJobLoading(true);
    setJobNotFound(false);

    fetch(`/public/jobs/${jobId}`)
      .then(async (res) => {
        if (!res.ok) {
          if (res.status === 404) {
            if (isMounted) setJobNotFound(true);
            return null;
          }
          throw new Error(`Failed to load job details (${res.status})`);
        }
        return res.json() as Promise<PublicJobDetails>;
      })
      .then((data) => {
        if (isMounted && data) {
          setJob(data);
        }
      })
      .catch(() => {
        if (isMounted) setJobNotFound(true);
      })
      .finally(() => {
        if (isMounted) setJobLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [router.isReady, jobId]);

  function validateClient(): boolean {
    const errors: Record<string, string> = {};
    if (!fullName.trim()) errors.full_name = "Full name is required.";
    if (!email.trim()) errors.email = "Email is required.";
    if (!resumeFile) errors.resume = "Resume file is required (PDF or DOCX).";
    else {
      const name = resumeFile.name.toLowerCase();
      if (!name.endsWith(".pdf") && !name.endsWith(".docx")) {
        errors.resume = "Only PDF and DOCX files are supported.";
      }
      if (resumeFile.size > 5 * 1024 * 1024) {
        errors.resume = "Resume must be 5MB or smaller.";
      }
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!jobId) {
      setError("Job reference is missing. Use a valid apply link.");
      return;
    }

    if (!validateClient()) return;

    setLoading(true);

    try {
      const formData = new FormData();
      formData.append("email", email.trim());
      formData.append("full_name", fullName.trim());
      if (phone.trim()) formData.append("phone", phone.trim());
      formData.append("resume", resumeFile as File);

      const response = await fetch(`/public/jobs/${jobId}/apply`, {
        method: "POST",
        body: formData,
      });

      let data: unknown = null;
      try {
        data = await response.json();
      } catch {
        data = null;
      }

      if (response.status === 409) {
        setError(readErrorMessage(data, "You have already applied to this job."));
        return;
      }

      if (!response.ok) {
        setError(readErrorMessage(data, `Application failed (${response.status})`));
        return;
      }

      setSuccess(data as PublicApplySuccess);
      setFullName("");
      setEmail("");
      setPhone("");
      setResumeFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (!router.isReady || jobLoading) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <p className="auth-subtitle">Loading position details...</p>
        </div>
      </div>
    );
  }

  if (jobNotFound || !jobId) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-title">Position Not Available</h1>
          <p className="auth-subtitle">
            This job posting is not currently accepting applications or does not exist.
          </p>
          <div style={{ marginTop: "1.5rem" }}>
            <Link href="/login" className="auth-link">
              Recruiter sign in
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ maxWidth: "34rem" }}>
          <div style={{ display: "inline-block", marginBottom: "1rem" }}>
            <Badge tone="success" size="md">
              Application Submitted
            </Badge>
          </div>
          <h1 className="auth-title">Thank you for applying!</h1>
          <p className="auth-subtitle">
            {success.message ?? "Your application has been received. Our recruiting team will review your profile shortly."}
          </p>
          <div
            style={{
              marginTop: "1.5rem",
              padding: "1rem",
              background: "var(--color-bg-canvas, #f8fafc)",
              borderRadius: "var(--radius-md, 8px)",
              border: "1px solid var(--color-border-subtle, #e2e8f0)",
              fontSize: "0.875rem",
              lineHeight: "1.6",
            }}
          >
            <p>
              <strong>Position:</strong> {job?.title ?? jobId}
            </p>
            {job?.company_name ? (
              <p>
                <strong>Company:</strong> {job.company_name}
              </p>
            ) : null}
            <p>
              <strong>Application ID:</strong> {success.application_id}
            </p>
            <p>
              <strong>Status:</strong> {success.status}
            </p>
            <p>
              <strong>Submitted:</strong> {new Date(success.applied_at).toLocaleString()}
            </p>
          </div>
          <div style={{ marginTop: "1.5rem" }}>
            <Button variant="secondary" onClick={() => setSuccess(null)}>
              Submit Another Application
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ maxWidth: "42rem" }}>
        {/* Job Header */}
        <div style={{ marginBottom: "1.5rem", borderBottom: "1px solid var(--color-border-subtle, #e2e8f0)", paddingBottom: "1rem" }}>
          {job?.company_name ? (
            <p style={{ fontSize: "0.875rem", color: "var(--color-text-secondary, #64748b)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.25rem" }}>
              {job.company_name}
            </p>
          ) : null}
          <h1 className="auth-title" style={{ marginBottom: "0.5rem" }}>
            {job?.title ?? "Job Application"}
          </h1>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
            {job?.department ? <Badge tone="brand">{job.department}</Badge> : null}
            {job?.location ? <Badge tone="neutral">{job.location}</Badge> : null}
            {job?.employment_type ? (
              <Badge tone="neutral">{job.employment_type.replace(/_/g, " ")}</Badge>
            ) : null}
            {job?.experience_level ? <Badge tone="neutral">{job.experience_level}</Badge> : null}
          </div>
        </div>

        {/* Job Description */}
        {job?.description ? (
          <div style={{ marginBottom: "1.5rem" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-text-primary, #0f172a)", marginBottom: "0.5rem" }}>
              About the Role
            </h2>
            <div
              style={{
                fontSize: "0.875rem",
                color: "var(--color-text-secondary, #475569)",
                lineHeight: "1.6",
                whiteSpace: "pre-line",
              }}
            >
              {job.description}
            </div>
          </div>
        ) : null}

        {/* Requirements */}
        {job?.requirements && job.requirements.length > 0 ? (
          <div style={{ marginBottom: "1.5rem" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--color-text-primary, #0f172a)", marginBottom: "0.5rem" }}>
              Key Requirements & Skills
            </h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
              {job.requirements.map((req, idx) => (
                <Badge key={idx} tone="neutral" size="sm">
                  {req}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {/* Application Form Section */}
        <div style={{ borderTop: "1px solid var(--color-border-subtle, #e2e8f0)", paddingTop: "1.25rem" }}>
          <h2 style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--color-text-primary, #0f172a)", marginBottom: "0.25rem" }}>
            Submit Your Application
          </h2>
          <p className="auth-subtitle" style={{ marginBottom: "1rem" }}>
            Please fill out your details and attach your resume.
          </p>

          {error ? (
            <div className="auth-error" role="alert" style={{ marginBottom: "1rem" }}>
              {error}
            </div>
          ) : null}

          <form className="auth-form" onSubmit={(e) => void handleSubmit(e)} noValidate>
            <label className="auth-label">
              Full name *
              <input
                className="auth-input"
                type="text"
                placeholder="Jane Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                maxLength={255}
              />
              {fieldErrors.full_name ? <span className="auth-error">{fieldErrors.full_name}</span> : null}
            </label>

            <label className="auth-label">
              Email address *
              <input
                className="auth-input"
                type="email"
                placeholder="jane.doe@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              {fieldErrors.email ? <span className="auth-error">{fieldErrors.email}</span> : null}
            </label>

            <label className="auth-label">
              Phone number (optional)
              <input
                className="auth-input"
                type="tel"
                placeholder="+1 (555) 000-0000"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                maxLength={50}
              />
            </label>

            <label className="auth-label">
              Resume * (PDF or DOCX, max 5MB)
              <input
                className="auth-input"
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
                required
              />
              {fieldErrors.resume ? <span className="auth-error">{fieldErrors.resume}</span> : null}
            </label>

            <Button type="submit" disabled={loading} className="auth-submit">
              {loading ? "Submitting application..." : "Submit Application"}
            </Button>
          </form>

          <p className="auth-footer" style={{ marginTop: "1rem" }}>
            Recruiter? <Link href="/login" className="auth-link">Sign in to Recruitment Copilot</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

