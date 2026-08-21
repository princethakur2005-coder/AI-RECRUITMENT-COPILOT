import type { UIStatusTone } from "../components/core/types";

export interface CandidateMe {
  id: string;
  email: string;
  full_name: string;
  first_name: string;
  last_name: string;
  phone: string | null;
  is_active: boolean;
  status: string;
  account_activated: boolean;
}

export interface CandidateApplication {
  id: string;
  status: string;
  source: string | null;
  applied_at: string;
  updated_at: string;
  job_id: string;
  job_title: string | null;
  company_id: string;
  company_name: string | null;
}

export interface CandidateInterview {
  id: string;
  application_id: string;
  interview_type: string;
  scheduled_start: string;
  scheduled_end: string;
  timezone: string;
  meeting_link: string | null;
  location: string | null;
  status: string;
  interviewer_name: string | null;
  job_title: string | null;
  company_name: string | null;
}

export interface CandidateOffer {
  id: string;
  application_id: string | null;
  job_id: string | null;
  revision: number;
  is_active: boolean;
  offer_title: string | null;
  compensation_min: number | null;
  compensation_max: number | null;
  currency: string | null;
  expires_at: string | null;
  terms: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export type PortalTab = "dashboard" | "applications" | "interviews" | "offers" | "profile";

export const CANDIDATE_PORTAL_API = {
  me: "/auth/candidate/me",
  applications: "/candidate/applications",
  application: (id: string) => `/candidate/applications/${id}`,
  interviews: "/candidate/interviews",
  interview: (id: string) => `/candidate/interviews/${id}`,
  offers: "/candidate/offers",
  offer: (id: string) => `/candidate/offers/${id}`,
  accept: (id: string) => `/offers/${id}/accept`,
  decline: (id: string) => `/offers/${id}/decline`,
} as const;

const PORTAL_TABS: PortalTab[] = ["dashboard", "applications", "interviews", "offers", "profile"];

export function parsePortalTab(value: unknown): PortalTab {
  return typeof value === "string" && PORTAL_TABS.includes(value as PortalTab)
    ? (value as PortalTab)
    : "dashboard";
}

export function formatDate(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatDateInTimezone(value?: string | null, timezone?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  try {
    return parsed.toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: timezone || undefined,
    });
  } catch {
    return formatDate(value);
  }
}

export function formatCurrency(value?: number | null, currency = "USD"): string {
  if (typeof value !== "number") return "-";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return String(value);
  }
}

export function statusTone(status?: string): UIStatusTone {
  const value = String(status ?? "").toLowerCase();
  if (value.includes("accepted") || value.includes("hired") || value.includes("complete")) return "success";
  if (value.includes("rejected") || value.includes("declined") || value.includes("cancel") || value.includes("no_show")) {
    return "danger";
  }
  if (value.includes("pending") || value.includes("review") || value.includes("scheduled") || value.includes("approved")) {
    return "warning";
  }
  if (value.includes("interview") || value.includes("progress") || value.includes("active")) return "brand";
  return "neutral";
}

export function isOfferActionable(offer: Pick<CandidateOffer, "status" | "is_active">): boolean {
  const status = String(offer.status ?? "").toLowerCase();
  return offer.is_active && status === "approved";
}

export function isOfferExpired(offer: Pick<CandidateOffer, "expires_at">): boolean {
  if (!offer.expires_at) return false;
  const expires = new Date(offer.expires_at).getTime();
  return !Number.isNaN(expires) && expires < Date.now();
}

export function parseApiError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const record = payload as Record<string, unknown>;
  if (typeof record.message === "string") return record.message;
  if (typeof record.detail === "string") return record.detail;
  return fallback;
}

/** Map staff OfferResponse fields into the candidate-safe offer shape used by the portal. */
export function toCandidateOffer(payload: Record<string, unknown>): CandidateOffer {
  return {
    id: String(payload.id ?? ""),
    application_id: payload.application_id == null ? null : String(payload.application_id),
    job_id: payload.job_id == null ? null : String(payload.job_id),
    revision: typeof payload.revision === "number" ? payload.revision : 1,
    is_active: Boolean(payload.is_active),
    offer_title: payload.offer_title == null ? null : String(payload.offer_title),
    compensation_min: typeof payload.compensation_min === "number" ? payload.compensation_min : null,
    compensation_max: typeof payload.compensation_max === "number" ? payload.compensation_max : null,
    currency: payload.currency == null ? null : String(payload.currency),
    expires_at: payload.expires_at == null ? null : String(payload.expires_at),
    terms: payload.terms == null ? null : String(payload.terms),
    status: String(payload.status ?? ""),
    created_at: String(payload.created_at ?? ""),
    updated_at: String(payload.updated_at ?? ""),
  };
}
