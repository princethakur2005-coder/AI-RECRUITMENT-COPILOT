import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { authFetch } from "../lib/api";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Grid,
  Input,
  LoadingState,
  Select,
  Stack,
} from "./index";

export interface CandidateRankingItem {
  rank: number | null;
  overall_rank_score: number | null;
  analysis_status: "complete" | "pending";
  candidate?: {
    id: string;
    full_name: string;
    email: string;
  } | null;
  application: {
    id: string;
    status: string;
    applied_at: string;
  };
  summary?: string | null;
  recommendation?: string | null;
  confidence?: number | null;
  strengths?: string[];
  weaknesses?: string[];
  missing_skills?: string[];
  matched_skills?: string[];
  skills_score?: number | null;
  experience_score?: number | null;
  overall_score?: number | null;
}

interface JobRankingResponse {
  job_id: string;
  items: CandidateRankingItem[];
  analyzed_count: number;
  pending_count: number;
}

type SortMode = "ai_rank" | "applied_at" | "name";
type AnalysisFilter = "all" | "complete" | "pending";

interface JobCandidateRankingPanelProps {
  jobId: string;
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

export function JobCandidateRankingPanel({ jobId }: JobCandidateRankingPanelProps) {
  const [ranking, setRanking] = useState<JobRankingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState("");
  const [recommendationFilter, setRecommendationFilter] = useState("");
  const [analysisFilter, setAnalysisFilter] = useState<AnalysisFilter>("all");
  const [sortMode, setSortMode] = useState<SortMode>("ai_rank");

  const loadRanking = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch(`/jobs/${jobId}/ranking`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Failed to load ranking (${response.status})`);
      }
      const payload = (await response.json()) as JobRankingResponse;
      setRanking(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load candidate ranking");
      setRanking(null);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void loadRanking();
  }, [loadRanking]);

  const filteredItems = useMemo(() => {
    if (!ranking?.items) return [];

    let items = [...ranking.items];

    if (analysisFilter === "complete") {
      items = items.filter((item) => item.analysis_status === "complete");
    } else if (analysisFilter === "pending") {
      items = items.filter((item) => item.analysis_status === "pending");
    }

    const min = minScore.trim() ? Number(minScore) : null;
    if (min !== null && !Number.isNaN(min)) {
      items = items.filter(
        (item) =>
          item.analysis_status === "pending" ||
          (item.overall_rank_score != null && item.overall_rank_score >= min),
      );
    }

    if (recommendationFilter.trim()) {
      const needle = recommendationFilter.trim().toLowerCase();
      items = items.filter(
        (item) =>
          item.analysis_status === "pending" ||
          String(item.recommendation ?? "").toLowerCase().includes(needle),
      );
    }

    if (sortMode === "applied_at") {
      items.sort((a, b) => String(b.application.applied_at).localeCompare(String(a.application.applied_at)));
    } else if (sortMode === "name") {
      items.sort((a, b) =>
        String(a.candidate?.full_name ?? "").localeCompare(String(b.candidate?.full_name ?? "")),
      );
    } else {
      const analyzed = items
        .filter((item) => item.analysis_status === "complete")
        .sort((a, b) => {
          const aScore = a.overall_rank_score ?? -1;
          const bScore = b.overall_rank_score ?? -1;
          if (aScore !== bScore) return bScore - aScore;
          return String(b.application.applied_at).localeCompare(String(a.application.applied_at));
        });
      const pending = items.filter((item) => item.analysis_status === "pending");
      items = [...analyzed, ...pending];
    }

    return items;
  }, [ranking?.items, analysisFilter, minScore, recommendationFilter, sortMode]);

  if (loading) {
    return <LoadingState title="Loading AI ranking" description="Computing candidate ranks from stored analysis." />;
  }

  if (error) {
    return (
      <Stack gap="3">
        <Alert tone="danger" description={error} />
        <Button size="sm" variant="secondary" onClick={() => void loadRanking()}>Retry</Button>
      </Stack>
    );
  }

  return (
    <Stack gap="4">
      <div className="job-ranking-filters">
        <Input
          label="Minimum score"
          type="number"
          min={0}
          max={100}
          value={minScore}
          onChange={(event) => setMinScore(event.target.value)}
          placeholder="0-100"
        />
        <Input
          label="Recommendation contains"
          value={recommendationFilter}
          onChange={(event) => setRecommendationFilter(event.target.value)}
          placeholder="e.g. strong fit"
        />
        <Select
          label="Analysis status"
          value={analysisFilter}
          onChange={(event) => setAnalysisFilter(event.target.value as AnalysisFilter)}
          options={[
            { value: "all", label: "All" },
            { value: "complete", label: "Analysis complete" },
            { value: "pending", label: "Analysis pending" },
          ]}
        />
        <Select
          label="Sort by"
          value={sortMode}
          onChange={(event) => setSortMode(event.target.value as SortMode)}
          options={[
            { value: "ai_rank", label: "AI Rank" },
            { value: "applied_at", label: "Applied Date" },
            { value: "name", label: "Name" },
          ]}
        />
        <Button size="sm" variant="secondary" onClick={() => void loadRanking()}>Refresh</Button>
      </div>

      {ranking ? (
        <p className="job-application-card-meta">
          {ranking.analyzed_count} analyzed · {ranking.pending_count} pending analysis
        </p>
      ) : null}

      {!filteredItems.length ? (
        <EmptyState
          title="No candidates match filters"
          description="Adjust filters or run AI resume analysis on applications first."
        />
      ) : (
        <div className="job-ranking-list">
          {filteredItems.map((item) => {
            const candidateName = item.candidate?.full_name ?? "Unknown candidate";
            const isPending = item.analysis_status === "pending";
            return (
              <article key={item.application.id} className="job-ranking-card">
                <div className="job-ranking-card-header">
                  <div className="job-ranking-rank-badge">
                    {isPending ? (
                      <Badge tone="warning">Analysis Pending</Badge>
                    ) : (
                      <Badge tone="brand">#{item.rank}</Badge>
                    )}
                  </div>
                  <Stack gap="1">
                    <strong>{candidateName}</strong>
                    <span className="job-application-card-meta">{item.candidate?.email ?? "—"}</span>
                  </Stack>
                  <Link href={`/application/${item.application.id}`} className="job-application-link">
                    View application
                  </Link>
                </div>

                {isPending ? (
                  <p className="job-application-card-meta">
                    Resume intelligence has not been run for this application yet.
                  </p>
                ) : (
                  <Stack gap="2">
                    <Grid columns={{ mobile: 2, md: 4 }} gap="2">
                      <div>
                        <small className="job-application-card-meta">Overall rank score</small>
                        <strong>{item.overall_rank_score?.toFixed(1) ?? "—"}</strong>
                      </div>
                      <div>
                        <small className="job-application-card-meta">Overall AI score</small>
                        <strong>{item.overall_score ?? "—"}</strong>
                      </div>
                      <div>
                        <small className="job-application-card-meta">Skills</small>
                        <strong>{item.skills_score ?? "—"}</strong>
                      </div>
                      <div>
                        <small className="job-application-card-meta">Experience</small>
                        <strong>{item.experience_score ?? "—"}</strong>
                      </div>
                    </Grid>
                    <p className="job-application-card-meta">
                      Confidence: {formatPercent(item.confidence)} · Applied:{" "}
                      {new Date(item.application.applied_at).toLocaleString()}
                    </p>
                    {item.recommendation ? (
                      <p className="job-application-card-meta"><strong>Recommendation:</strong> {item.recommendation}</p>
                    ) : null}
                    {item.summary ? <p className="job-application-card-meta">{item.summary}</p> : null}
                  </Stack>
                )}
              </article>
            );
          })}
        </div>
      )}
    </Stack>
  );
}
