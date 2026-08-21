import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Button } from "../components/core/Button";
import { setAuthSession } from "../lib/api";

export default function CandidateSignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
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

    setLoading(true);
    try {
      const res = await fetch("/auth/candidate/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: fullName, email, password }),
      });

      const data = (await res.json()) as {
        access_token?: string;
        principal?: string;
        detail?: string;
        message?: string;
      };

      if (!res.ok) {
        setError(data.detail ?? data.message ?? "Registration failed. Please try again.");
        return;
      }

      setAuthSession(data.access_token ?? "", "candidate");
      void router.replace("/candidate-portal");
    } catch {
      setError("Network error. Please check your connection.");
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
              <rect width="28" height="28" rx="8" fill="url(#cand-signup-grad)" />
              <path d="M8 20L14 8L20 20" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10 17H18" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
              <defs>
                <linearGradient id="cand-signup-grad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#0ea5e9" />
                  <stop offset="1" stopColor="#0891b2" />
                </linearGradient>
              </defs>
            </svg>
          </span>
          <span className="auth-logo-name"><span>AI</span> Recruit</span>
        </div>

        <h1 className="auth-heading">Create candidate account</h1>
        <p className="auth-subheading">Track applications, interviews, and offers in one place</p>

        <form className="auth-form" onSubmit={(e) => void handleSubmit(e)} noValidate>
          {error ? <div className="auth-error" role="alert">{error}</div> : null}

          <div className="auth-field">
            <label className="auth-label" htmlFor="fullName">Full name</label>
            <input
              id="fullName"
              className="auth-input"
              type="text"
              autoComplete="name"
              placeholder="Ada Lovelace"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
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
              placeholder="you@example.com"
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
            />
          </div>

          <Button type="submit" variant="primary" className="auth-submit" disabled={loading}>
            {loading ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <div className="auth-footer">
          <span>
            Already have an account?{" "}
            <Link href="/candidate-login" className="auth-link">Sign in</Link>
          </span>
        </div>
      </div>
    </div>
  );
}
