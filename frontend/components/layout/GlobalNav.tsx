import { useRouter } from "next/router";
import Link from "next/link";
import { clearAuthSession, getAuthPrincipal, getAccessToken } from "../../lib/api";
import { useEffect, useState } from "react";

const RECRUITER_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/candidate-management", label: "Candidates" },
  { href: "/job-management", label: "Jobs" },
  { href: "/interview-management", label: "Interviews" },
  { href: "/analytics-reports", label: "Analytics" },
  { href: "/notifications", label: "Notifications" },
  { href: "/settings", label: "Settings" },
];

const CANDIDATE_LINKS = [
  { href: "/candidate-portal", label: "Overview", tab: "dashboard" },
  { href: "/candidate-portal?tab=applications", label: "Applications", tab: "applications" },
  { href: "/candidate-portal?tab=interviews", label: "Interviews", tab: "interviews" },
  { href: "/candidate-portal?tab=offers", label: "Offers", tab: "offers" },
  { href: "/candidate-portal?tab=profile", label: "Profile", tab: "profile" },
];

function BrandLink({ href }: { href: string }) {
  return (
    <Link href={href} className="gnav-brand" aria-label="AI Recruitment Copilot home">
      <span className="gnav-brand-logo" aria-hidden="true">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="28" height="28" rx="8" fill="url(#gnav-grad)" />
          <path d="M8 20L14 8L20 20" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M10 17H18" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
          <defs>
            <linearGradient id="gnav-grad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
              <stop stopColor="#0ea5e9" />
              <stop offset="1" stopColor="#0891b2" />
            </linearGradient>
          </defs>
        </svg>
      </span>
      <span className="gnav-brand-name">
        <span className="gnav-brand-ai">AI</span> Recruit
      </span>
    </Link>
  );
}

function CandidateNav() {
  const router = useRouter();
  const activeTab = typeof router.query.tab === "string" ? router.query.tab : "dashboard";

  const handleLogout = () => {
    clearAuthSession();
    void router.replace("/candidate-login");
  };

  return (
    <nav className="gnav-root" aria-label="Candidate navigation">
      <div className="gnav-inner">
        <BrandLink href="/candidate-portal" />
        <ul className="gnav-links" role="list">
          {CANDIDATE_LINKS.map(({ href, label, tab }) => {
            const active = activeTab === tab || (tab === "dashboard" && !router.query.tab);
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={`gnav-link${active ? " gnav-link-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
        <div className="gnav-right">
          <button type="button" className="gnav-logout-btn" onClick={handleLogout} aria-label="Log out" title="Log out">
            <span>Logout</span>
          </button>
        </div>
      </div>
    </nav>
  );
}

function RecruiterNav() {
  const router = useRouter();
  const [userEmail, setUserEmail] = useState<string>("");

  useEffect(() => {
    try {
      const token = getAccessToken();
      if (token) {
        const payload = JSON.parse(atob(token.split(".")[1])) as { sub?: string };
        setUserEmail(String(payload.sub ?? ""));
      }
    } catch {
      // ignore decode errors
    }
  }, []);

  const handleLogout = () => {
    clearAuthSession();
    void router.replace("/login");
  };

  const initials = userEmail ? userEmail.charAt(0).toUpperCase() : "U";

  return (
    <nav className="gnav-root" aria-label="Main navigation">
      <div className="gnav-inner">
        <BrandLink href="/dashboard" />
        <ul className="gnav-links" role="list">
          {RECRUITER_LINKS.map(({ href, label }) => {
            const active = router.pathname === href;
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={`gnav-link${active ? " gnav-link-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
        <div className="gnav-right">
          <Link href="/notifications" className="gnav-icon-btn" aria-label="Notifications">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
          </Link>
          <Link href="/user-profile" className="gnav-avatar" aria-label="User profile" title={userEmail}>
            <span>{initials}</span>
          </Link>
          <button type="button" className="gnav-logout-btn" onClick={handleLogout} aria-label="Log out" title="Log out">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>Logout</span>
          </button>
        </div>
      </div>
    </nav>
  );
}

export function GlobalNav() {
  const router = useRouter();
  const [principal, setPrincipal] = useState<"user" | "candidate" | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setPrincipal(getAuthPrincipal());
    setReady(true);
  }, []);

  // Avoid recruiter-nav flash on candidate routes before localStorage hydration.
  if (!ready) {
    return router.pathname === "/candidate-portal" ? <CandidateNav /> : <RecruiterNav />;
  }

  if (principal === "candidate") {
    return <CandidateNav />;
  }
  return <RecruiterNav />;
}
