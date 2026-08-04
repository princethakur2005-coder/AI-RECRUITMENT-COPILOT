import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Button } from "../components/core/Button";

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

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<PublicApplySuccess | null>(null);
  const [loading, setLoading] = useState(false);

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

  if (!router.isReady) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <p className="auth-subtitle">Loading application form...</p>
        </div>
      </div>
    );
  }

  if (!jobId) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-title">Invalid apply link</h1>
          <p className="auth-subtitle">This page requires a job reference in the URL.</p>
          <Link href="/login" className="auth-link">Recruiter sign in</Link>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-title">Application submitted</h1>
          <p className="auth-subtitle">
            {success.message ?? "Your application has been received. Our recruiting team will review it soon."}
          </p>
          <div className="auth-subtitle" style={{ marginTop: "1rem" }}>
            <p>Application ID: {success.application_id}</p>
            <p>Status: {success.status}</p>
            <p>Submitted: {new Date(success.applied_at).toLocaleString()}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Apply for this role</h1>
        <p className="auth-subtitle">Submit your resume to apply. Job reference: {jobId}</p>

        {error ? <div className="auth-error" role="alert">{error}</div> : null}

        <form className="auth-form" onSubmit={(e) => void handleSubmit(e)} noValidate>
          <label className="auth-label">
            Full name
            <input
              className="auth-input"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              maxLength={255}
            />
            {fieldErrors.full_name ? <span className="auth-error">{fieldErrors.full_name}</span> : null}
          </label>

          <label className="auth-label">
            Email
            <input
              className="auth-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            {fieldErrors.email ? <span className="auth-error">{fieldErrors.email}</span> : null}
          </label>

          <label className="auth-label">
            Phone (optional)
            <input
              className="auth-input"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              maxLength={50}
            />
          </label>

          <label className="auth-label">
            Resume (PDF or DOCX, max 5MB)
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
            {loading ? "Submitting..." : "Submit application"}
          </Button>
        </form>

        <p className="auth-footer">
          Recruiter? <Link href="/login" className="auth-link">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
