import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { authFetch } from "../lib/api";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Grid,
  LoadingState,
  Pagination,
  Stack,
} from "./index";

interface DecisionConfidence {
  overall: number;
  ranking_confidence: number;
  semantic_confidence: number;
  evaluation_confidence: number;
}

interface ExplainableDecisionReasons {
  ranking_contribution: number;
  evaluation_contribution: number;
  semantic_contribution: number;
  risk_penalty: number;
  final_score: number;
}

interface RecruiterRecommendationMetadata {
  summary: string;
  next_step_hint: string;
  ranking_position?: number | null;
}

interface RiskFactor {
  code: string;
  category: string;
  severity: string;
  message: string;
  source: string;
}

interface AIHiringSummary {
  executive_summary: string;
  hiring_recommendation_summary: string;
  candidate_strengths: string[];
  candidate_concerns: string[];
  skill_gap_summary: string;
  interview_highlights: string[];
  final_decision_rationale: string;
}

interface ApplicationCandidateSummary {
  id: string;
  full_name: string;
  email: string;
}

export interface JobHiringDecisionItem {
  id: string;
  application_id: string;
  candidate_id: string;
  job_id: string;
  recommendation: string;
  overall_score: number;
  decision_confidence: DecisionConfidence;
  strengths: string[];
  weaknesses: string[];
  missing_mandatory_qualifications: string[];
  risk_factors: RiskFactor[];
  reasons: ExplainableDecisionReasons;
  recruiter_metadata: RecruiterRecommendationMetadata;
  ai_hiring_summary?: AIHiringSummary | null;
  decision_detail?: Record<string, unknown>;
  policy_version: string;
  created_at: string;
  updated_at: string;
  is_stale: boolean;
  recommendation_position?: number | null;
  candidate?: ApplicationCandidateSummary | null;
}

interface HiringRecommendationPagination {
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface JobHiringDecisionList {
  job_id: string;
  job_title?: string | null;
  items: JobHiringDecisionItem[];
  total: number;
  generated_at: string;
  pagination: HiringRecommendationPagination;
  policy: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

type ViewMode = "preview" | "persisted";

interface JobHiringRecommendationsPanelProps {
  jobId: string;
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function recommendationTone(
  recommendation: string,
): "neutral" | "brand" | "success" | "warning" | "danger" {
  const normalized = recommendation.toLowerCase();
  if (normalized.includes("strong hire")) return "success";
  if (normalized.includes("hire")) return "brand";
  if (normalized.includes("consider")) return "warning";
  if (normalized.includes("reject")) return "danger";
  return "neutral";
}

export function JobHiringRecommendationsPanel({ jobId }: JobHiringRecommendationsPanelProps) {
  const [result, setResult] = useState<JobHiringDecisionList | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("preview");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const fetchPreview = useCallback(
    async (targetPage: number, showLoading = true) => {
      if (showLoading) {
        setLoading(true);
      }
      setError(null);
      try {
        const response = await authFetch(
          `/jobs/${jobId}/hiring-recommendations?page=${targetPage}&page_size=${pageSize}`,
          { headers: { Accept: "application/json" } },
        );
        if (!response.ok) {
          const data = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(data?.detail ?? `Request failed (${response.status})`);
        }
        const payload = (await response.json()) as JobHiringDecisionList;
        setResult(payload);
        setViewMode("preview");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load hiring recommendations");
        setResult(null);
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [jobId, pageSize],
  );

  const fetchPersisted = useCallback(
    async (targetPage: number, showLoading = true) => {
      if (showLoading) {
        setLoading(true);
      }
      setError(null);
      try {
        const response = await authFetch(
          `/jobs/${jobId}/hiring-decisions?page=${targetPage}&page_size=${pageSize}`,
          { headers: { Accept: "application/json" } },
        );
        if (!response.ok) {
          const data = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(data?.detail ?? `Request failed (${response.status})`);
        }
        const payload = (await response.json()) as JobHiringDecisionList;
        setResult(payload);
        setViewMode("persisted");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load persisted hiring decisions");
        setResult(null);
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [jobId, pageSize],
  );

  useEffect(() => {
    if (viewMode === "preview") {
      void fetchPreview(page);
      return;
    }
    void fetchPersisted(page);
  }, [fetchPersisted, fetchPreview, page, viewMode]);

  const loadPreview = () => {
    setViewMode("preview");
    if (page !== 1) {
      setPage(1);
      return;
    }
    void fetchPreview(1);
  };

  const loadPersisted = () => {
    setViewMode("persisted");
    if (page !== 1) {
      setPage(1);
      return;
    }
    void fetchPersisted(1);
  };

  const generateDecisions = async (force = false) => {
    setGenerating(true);
    setError(null);
    try {
      const response = await authFetch(
        `/jobs/${jobId}/hiring-recommendations/generate?page=1&page_size=${pageSize}&force=${force ? "true" : "false"}&use_ai_narrative=false`,
        {
          method: "POST",
          headers: { Accept: "application/json" },
        },
      );
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Generation failed (${response.status})`);
      }
      setPage(1);
      await fetchPersisted(1, false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to generate hiring recommendations");
    } finally {
      setGenerating(false);
    }
  };

  if (loading && !result) {
    return <LoadingState title="Loading hiring recommendations" description="Fetching hiring decisions." />;
  }

  return (
    <Stack gap="4">
      <div className="application-ai-actions">
        <Button size="sm" variant="secondary" onClick={loadPreview} disabled={generating || loading}>
          Preview rankings
        </Button>
        <Button size="sm" variant="secondary" onClick={loadPersisted} disabled={generating || loading}>
          View persisted
        </Button>
        <Button size="sm" onClick={() => void generateDecisions(false)} disabled={generating}>
          {generating ? "Saving..." : "Generate & persist"}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => void generateDecisions(true)} disabled={generating}>
          Force regenerate
        </Button>
      </div>

      {viewMode === "preview" ? (
        <Alert
          tone="info"
          title="Preview mode"
          description="These recommendations are computed live and are not saved until you generate and persist."
        />
      ) : (
        <Alert
          tone="success"
          title="Persisted decisions"
          description="Displayed recommendations reflect saved application hiring decisions for this job."
        />
      )}

      {error ? <Alert tone="danger" description={error} /> : null}
      {generating ? (
        <LoadingState title="Generating hiring recommendations" description="Scoring and persisting decisions." />
      ) : null}

      {result ? (
        <p className="job-application-card-meta">
          {result.job_title ?? "Job"} · {result.total} candidates · Generated{" "}
          {new Date(result.generated_at).toLocaleString()}
        </p>
      ) : null}

      {!generating && result && !result.items.length ? (
        <EmptyState
          title={viewMode === "persisted" ? "No persisted hiring decisions" : "No hiring recommendations"}
          description={
            viewMode === "persisted"
              ? "Generate and persist hiring decisions for analyzed applications to see them here."
              : "Ensure applications have completed resume intelligence analysis before generating recommendations."
          }
        />
      ) : null}

      {!generating && result?.items.length ? (
        <div className="job-ranking-list">
          {result.items.map((item) => {
            const candidateName = item.candidate?.full_name ?? "Unknown candidate";
            return (
              <article key={`${item.application_id}-${item.id}`} className="job-ranking-card">
                <div className="job-ranking-card-header">
                  <div className="job-ranking-rank-badge">
                    {item.recommendation_position != null ? (
                      <Badge tone="brand">#{item.recommendation_position}</Badge>
                    ) : (
                      <Badge tone="neutral">—</Badge>
                    )}
                  </div>
                  <Stack gap="1">
                    <strong>{candidateName}</strong>
                    <span className="job-application-card-meta">{item.candidate?.email ?? "—"}</span>
                  </Stack>
                  <div className="application-ai-actions">
                    <Badge tone={recommendationTone(item.recommendation)}>{item.recommendation}</Badge>
                    {viewMode === "preview" ? (
                      <Badge tone="warning">Preview</Badge>
                    ) : (
                      <Badge tone="success">Persisted</Badge>
                    )}
                    {item.is_stale ? <Badge tone="warning">Stale</Badge> : null}
                  </div>
                  <Link href={`/application/${item.application_id}`} className="job-application-link">
                    View application
                  </Link>
                </div>

                <Stack gap="2">
                  <Grid columns={{ mobile: 2, md: 4 }} gap="2">
                    <div>
                      <small className="job-application-card-meta">Overall score</small>
                      <strong>{item.overall_score}</strong>
                    </div>
                    <div>
                      <small className="job-application-card-meta">Confidence</small>
                      <strong>{formatPercent(item.decision_confidence.overall)}</strong>
                    </div>
                    <div>
                      <small className="job-application-card-meta">Ranking contrib.</small>
                      <strong>{item.reasons.ranking_contribution.toFixed(3)}</strong>
                    </div>
                    <div>
                      <small className="job-application-card-meta">Risk penalty</small>
                      <strong>{item.reasons.risk_penalty.toFixed(3)}</strong>
                    </div>
                  </Grid>
                  <p className="job-application-card-meta">{item.recruiter_metadata.summary}</p>
                  {item.strengths.length ? (
                    <p className="job-application-card-meta">
                      <strong>Strengths:</strong> {item.strengths.slice(0, 3).join("; ")}
                    </p>
                  ) : null}
                  {item.weaknesses.length ? (
                    <p className="job-application-card-meta">
                      <strong>Concerns:</strong> {item.weaknesses.slice(0, 3).join("; ")}
                    </p>
                  ) : null}
                </Stack>
              </article>
            );
          })}
        </div>
      ) : null}

      {result?.pagination ? (
        <Pagination
          page={result.pagination.page}
          pageSize={result.pagination.page_size}
          total={result.pagination.total}
          onPageChange={setPage}
          showPageButtons
          siblingCount={1}
        />
      ) : null}
    </Stack>
  );
}
