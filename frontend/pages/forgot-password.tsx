import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Button } from "../components/core/Button";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    if (newPassword.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch("/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, new_password: newPassword }),
      });

      const data = (await res.json()) as { message?: string; detail?: string };

      if (!res.ok) {
        setError(data.detail ?? "Failed to reset password. Please try again.");
        return;
      }

      setSuccess(true);
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
              <rect width="28" height="28" rx="8" fill="url(#fp-grad)" />
              <path d="M8 20L14 8L20 20" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M10 17H18" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
              <defs>
                <linearGradient id="fp-grad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#0ea5e9" />
                  <stop offset="1" stopColor="#0891b2" />
                </linearGradient>
              </defs>
            </svg>
          </span>
          <span className="auth-logo-name"><span>AI</span> Recruit</span>
        </div>

        <h1 className="auth-heading">Reset password</h1>
        <p className="auth-subheading">Enter your email and choose a new password</p>

        {success ? (
          <div className="auth-success" role="status">
            ✓ Password updated successfully. You can now{" "}
            <Link href="/login" className="auth-link" style={{ marginLeft: "0.25rem" }}>sign in</Link>.
          </div>
        ) : (
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
              <label className="auth-label" htmlFor="newPassword">New password</label>
              <input
                id="newPassword"
                className="auth-input"
                type="password"
                autoComplete="new-password"
                placeholder="Min. 6 characters"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="confirm">Confirm new password</label>
              <input
                id="confirm"
                className="auth-input"
                type="password"
                autoComplete="new-password"
                placeholder="Repeat new password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                aria-invalid={confirm.length > 0 && newPassword !== confirm}
              />
            </div>

            <Button type="submit" variant="primary" className="auth-submit" disabled={loading}>
              {loading ? "Updating…" : "Reset password"}
            </Button>
          </form>
        )}

        <div className="auth-footer">
          <span>
            <Link href="/login" className="auth-link">← Back to sign in</Link>
          </span>
        </div>
      </div>
    </div>
  );
}
