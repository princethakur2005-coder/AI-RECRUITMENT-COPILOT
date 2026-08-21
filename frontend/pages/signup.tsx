import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Button } from "../components/core/Button";
import { setAuthSession } from "../lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    if (!companyName.trim()) {
      setError("Company name is required.");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: fullName, email, password }),
      });

      let data: { access_token?: string; detail?: string; message?: string } | null = null;
      try {
        data = (await res.json()) as { access_token?: string; detail?: string; message?: string };
      } catch {
        data = null;
      }

      if (!res.ok) {
        const message = data?.detail ?? data?.message ?? "Registration failed. Please try again.";
        setError(typeof message === "string" ? message : "Registration failed. Please try again.");
        return;
      }

      const accessToken = data?.access_token ?? "";
      setAuthSession(accessToken, "user");

      // Existing company onboarding API — required for tenant-scoped dashboard/jobs.
      const companyRes = await fetch("/companies", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ name: companyName.trim() }),
      });

      if (!companyRes.ok) {
        let companyError: { detail?: string; message?: string } | null = null;
        try {
          companyError = (await companyRes.json()) as { detail?: string; message?: string };
        } catch {
          companyError = null;
        }
        setError(
          companyError?.detail ??
            companyError?.message ??
            "Account created, but company setup failed. Please try again from settings.",
        );
        return;
      }

      void router.replace("/dashboard");
    } catch (error) {
      const message = error instanceof Error && error.message ? error.message : "Network error. Please check your connection.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <span className="auth-logo-icon">
            <svg width="32" height="32" viewBox="0 0 28 28" fill="none">
              <rect width="28" height="28" rx="8" fill="url(#signup-grad)" />
              <path d="M8 20L14 8L20 20" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10 17H18" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
              <defs>
                <linearGradient id="signup-grad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#0ea5e9" />
                  <stop offset="1" stopColor="#0891b2" />
                </linearGradient>
              </defs>
            </svg>
          </span>
          <span className="auth-logo-name"><span>AI</span> Recruit</span>
        </div>

        <h1 className="auth-heading">Create an account</h1>
        <p className="auth-subheading">Start your AI-powered recruitment journey</p>

        <form className="auth-form" onSubmit={(e) => void handleSubmit(e)} noValidate>
          {error && <div className="auth-error" role="alert">{error}</div>}

          <div className="auth-field">
            <label className="auth-label" htmlFor="fullName">Full name</label>
            <input
              id="fullName"
              className="auth-input"
              type="text"
              autoComplete="name"
              placeholder="Jane Smith"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="companyName">Company name</label>
            <input
              id="companyName"
              className="auth-input"
              type="text"
              autoComplete="organization"
              placeholder="Acme Hiring"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              required
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="email">Email address</label>
            <input
              id="email"
              className="auth-input"
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="password">Password</label>
            <input
              id="password"
              className="auth-input"
              type="password"
              autoComplete="new-password"
              placeholder="Min. 6 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="confirm">Confirm password</label>
            <input
              id="confirm"
              className="auth-input"
              type="password"
              autoComplete="new-password"
              placeholder="Repeat your password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              aria-invalid={confirm.length > 0 && password !== confirm}
            />
          </div>

          <Button type="submit" variant="primary" className="auth-submit" disabled={loading}>
            {loading ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <div className="auth-footer">
          <span>
            Already have an account?{" "}
            <Link href="/login" className="auth-link">Sign in</Link>
          </span>
        </div>
      </div>
    </div>
  );
}
