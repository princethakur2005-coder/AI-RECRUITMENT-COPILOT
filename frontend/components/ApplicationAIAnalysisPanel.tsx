import { useCallback, useEffect, useState } from "react";

import { authFetch } from "../lib/api";
import {
  Alert,
  Button,
  EmptyState,
  Grid,
  LoadingState,
  MetricCard,
  Section,
  Stack,
} from "./index";

export interface ApplicationAIAnalysis {
  id: string;
  application_id: string;
  overall_score: number;
  skills_score: number;
  experience_score: number;
  education_score: number;
  keyword_score: number;
  strengths: string[];
  weaknesses: string[];
  missing_skills: string[];
  matched_skills: string[];
  summary: string;
  recommendation: string;
  confidence: number;
  ai_provider: string;
  ai_model: string;
  prompt_version: string;
  created_at: string;
  updated_at: string;
}

interface ApplicationAIAnalysisPanelProps {
  applicationId: string;
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  if (!items.length) {
    return (
      <div>
        <strong>{title}</strong>
        <p className="job-application-card-meta">None identified</p>
      </div>
    );
  }
  return (
    <div>
      <strong>{title}</strong>
      <ul className="application-ai-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function ApplicationAIAnalysisPanel({ applicationId }: ApplicationAIAnalysisPanelProps) {
  const [analysis, setAnalysis] = useState<ApplicationAIAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch(`/applications/${applicationId}/ai`, {
        headers: { Accept: "application/json" },
      });
      if (response.status === 404) {
        setAnalysis(null);
        return;
      }
      if (!response.ok) {
        throw new Error(`Failed to load AI analysis (${response.status})`);
      }
      const payload = (await response.json()) as ApplicationAIAnalysis;
      setAnalysis(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load AI analysis");
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    void loadAnalysis();
  }, [loadAnalysis]);

  const runAnalysis = async (force = false) => {
    if (analyzing) return;
    setAnalyzing(true);
    setError(null);
    try {
      const response = await authFetch(
        `/applications/${applicationId}/ai/analyze?force=${force ? "true" : "false"}`,
        {
          method: "POST",
          headers: { Accept: "application/json" },
        },
      );
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Analysis failed (${response.status})`);
      }
      const payload = (await response.json()) as ApplicationAIAnalysis;
      setAnalysis(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run resume analysis");
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) {
    return <LoadingState title="Loading AI analysis" description="Checking for existing resume intelligence." />;
  }

  return (
    <Stack gap="4">
      <div className="application-ai-actions">
        <Button size="sm" onClick={() => void runAnalysis(false)} disabled={analyzing}>
          {analyzing ? "Analyzing..." : analysis ? "Refresh analysis" : "Run AI analysis"}
        </Button>
        {analysis ? (
          <Button size="sm" variant="secondary" onClick={() => void runAnalysis(true)} disabled={analyzing}>
            Regenerate
          </Button>
        ) : null}
      </div>

      {error ? <Alert tone="danger" description={error} /> : null}
      {analyzing ? (
        <LoadingState title="Running resume intelligence" description="Analyzing resume against the job description." />
      ) : null}

      {!analyzing && analysis ? (
        <Stack gap="4">
          <Grid columns={{ mobile: 2, md: 3, lg: 5 }} gap="3">
            <MetricCard label="Overall" value={String(analysis.overall_score)} meta="Composite fit score" />
            <MetricCard label="Skills" value={String(analysis.skills_score)} meta="Skills alignment" />
            <MetricCard label="Experience" value={String(analysis.experience_score)} meta="Experience fit" />
            <MetricCard label="Education" value={String(analysis.education_score)} meta="Education fit" />
            <MetricCard label="Keywords" value={String(analysis.keyword_score)} meta="Keyword overlap" />
          </Grid>

          <Section>
            <Stack gap="2">
              <p className="job-application-card-meta">
                Confidence: {formatPercent(analysis.confidence)} · Provider: {analysis.ai_provider} · Model:{" "}
                {analysis.ai_model}
              </p>
              <div>
                <strong>Summary</strong>
                <p className="job-application-card-meta">{analysis.summary}</p>
              </div>
              <div>
                <strong>Recommendation</strong>
                <p className="job-application-card-meta">{analysis.recommendation}</p>
              </div>
            </Stack>
          </Section>

          <Grid columns={{ mobile: 1, md: 2 }} gap="4">
            <ListBlock title="Strengths" items={analysis.strengths} />
            <ListBlock title="Weaknesses" items={analysis.weaknesses} />
            <ListBlock title="Matched skills" items={analysis.matched_skills} />
            <ListBlock title="Missing skills" items={analysis.missing_skills} />
          </Grid>
        </Stack>
      ) : null}

      {!analyzing && !analysis && !error ? (
        <EmptyState
          title="No AI analysis yet"
          description="Run resume intelligence to score this application against the job description."
        />
      ) : null}
    </Stack>
  );
}
