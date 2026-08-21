import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Button } from "../components/core/Button";
import { setAuthSession } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = (await res.json()) as {
        access_token?: string;
        principal?: string;
        detail?: string;
        message?: string;
      };

      if (!res.ok) {
        setError(data.detail ?? data.message ?? "Login failed. Please try again.");
        return;
      }

      setAuthSession(data.access_token ?? "", data.principal === "candidate" ? "candidate" : "user");
      void router.replace("/dashboard");
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
              <rect width="28" height="28" rx="8" fill="url(#login-grad)" />
              <path d="M8 20L14 8L20 20" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10 17H18" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
              <defs>
                <linearGradient id="login-grad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#0ea5e9" />
                  <stop offset="1" stopColor="#0891b2" />
                </linearGradient>
              </defs>
            </svg>
          </span>
          <span className="auth-logo-name"><span>AI</span> Recruit</span>
        </div>

        <h1 className="auth-heading">Welcome back</h1>
        <p className="auth-subheading">Sign in to your recruiter account to continue</p>

        <form className="auth-form" onSubmit={(e) => void handleSubmit(e)} noValidate>
          {error && <div className="auth-error" role="alert">{error}</div>}

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
              aria-invalid={!!error}
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="password">Password</label>
            <input
              id="password"
              className="auth-input"
              type="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <Button type="submit" variant="primary" className="auth-submit" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <div className="auth-footer">
          <span>
            <Link href="/forgot-password" className="auth-link">Forgot your password?</Link>
          </span>
          <div className="auth-divider">or</div>
          <span>
            Don&apos;t have an account?{" "}
            <Link href="/signup" className="auth-link">Create one</Link>
          </span>
          <div className="auth-divider">or</div>
          <span>
            Looking for the candidate portal?{" "}
            <Link href="/candidate-login" className="auth-link">Candidate sign in</Link>
          </span>
        </div>
      </div>
    </div>
  );
}
