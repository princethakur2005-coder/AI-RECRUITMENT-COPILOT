import type { AppProps } from "next/app";
import { useRouter } from "next/router";
import { useEffect, type ReactNode } from "react";
import { GlobalNav } from "../components/layout/GlobalNav";

// Base global styles (reset, fonts, global nav)
import "../styles/design-tokens.css";
import "../styles/global.css";
import "../styles/auth.css";

// Page-level styles
import "./dashboard.css";
import "./candidate-management.css";
import "./candidate-portal.css";
import "./interview-management.css";
import "./job-management.css";
import "./analytics-reports.css";
import "./notifications.css";
import "./settings.css";
import "./user-profile.css";

// Component-level styles
import "../components/core/core-ui.css";
import "../components/layout/layout.css";
import "../components/surface/surface.css";
import "../components/forms/forms.css";
import "../components/feedback/feedback.css";
import "../components/data-display/data-display.css";
import "../components/motion/motion.css";
import "../components/analytics/analytics.css";

// Pages that do not require authentication
const PUBLIC_PATHS = new Set(["/login", "/signup", "/forgot-password"]);

function AuthGuard({ children, pathname }: { children: ReactNode; pathname: string }) {
  const router = useRouter();

  useEffect(() => {
    const isPublic = PUBLIC_PATHS.has(pathname);
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

    if (!isPublic && !token) {
      void router.replace("/login");
    }
  }, [pathname, router]);

  return <>{children}</>;
}

export default function App({ Component, pageProps, router }: AppProps) {
  const isPublic = PUBLIC_PATHS.has(router.pathname);

  return (
    <AuthGuard pathname={router.pathname}>
      {!isPublic && <GlobalNav />}
      <Component {...pageProps} />
    </AuthGuard>
  );
}
