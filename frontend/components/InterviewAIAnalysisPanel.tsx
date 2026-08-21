import { useCallback, useEffect, useState } from "react";

import { authFetch } from "../lib/api";
import type { InterviewStatus } from "./ApplicationInterviewPanel";
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

export interface InterviewPerformanceSignal {
  interview_id: string;
  application_id?: string | null;
  avg_score: number;
  score: number;
  avg_confidence: number;
  confidence: number;
  completion_ratio: number;
}

export interface InterviewAIAnalysis {
  id: string;
  interview_id: string;
  overall_score: number;
  technical_score: number;
  communication_score: number;
  problem_solving_score: number;
  behavioral_score: number;
  strengths: string[];
  weaknesses: string[];
  gaps_identified: string[];
  demonstrated_competencies: string[];
  summary: string;
  recommendation: string;
  confidence: number;
  ai_provider: string;
  ai_model: string;
  prompt_version: string;
  created_at: string;
  updated_at: string;
  is_stale?: boolean;
  performance_signal?: InterviewPerformanceSignal | null;
}

interface InterviewAIAnalysisPanelProps {
  interviewId: string;
  interviewStatus?: InterviewStatus;
  applicationStatus?: string;
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

export function InterviewAIAnalysisPanel({
  interviewId,
  interviewStatus,
  applicationStatus,
}: InterviewAIAnalysisPanelProps) {
  const [analysis, setAnalysis] = useState<InterviewAIAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analysisBlocked =
    applicationStatus === "hired" || applicationStatus === "rejected";
  // Analysis is only available for completed interviews that are not on a terminal application.
  const canAnalyze = !analysisBlocked && interviewStatus === "completed";

  const loadAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch(`/interviews/${interviewId}/ai`, {
        headers: { Accept: "application/json" },
      });
      if (response.status === 404) {
        setAnalysis(null);
        return;
      }
      if (!response.ok) {
        throw new Error(`Failed to load interview AI analysis (${response.status})`);
      }
      const payload = (await response.json()) as InterviewAIAnalysis;
      setAnalysis(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load interview AI analysis");
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }, [interviewId]);

  useEffect(() => {
    void loadAnalysis();
  }, [loadAnalysis]);

  const runAnalysis = async (force = false) => {
    if (analyzing) return;
    setAnalyzing(true);
    setError(null);
    try {
      const response = await authFetch(
        `/interviews/${interviewId}/ai/analyze?force=${force ? "true" : "false"}`,
        {
          method: "POST",
          headers: { Accept: "application/json" },
        },
      );
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Analysis failed (${response.status})`);
      }
      const payload = (await response.json()) as InterviewAIAnalysis;
      setAnalysis(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run interview intelligence analysis");
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) {
    return (
      <LoadingState
        title="Loading interview intelligence"
        description="Checking for existing interview AI analysis."
      />
    );
  }

  return (
    <Stack gap="4">
      <div className="application-ai-actions">
        <Button
          size="sm"
          onClick={() => void runAnalysis(false)}
          disabled={analyzing || !canAnalyze}
        >
          {analyzing ? "Analyzing..." : analysis ? "Refresh analysis" : "Run interview intelligence"}
        </Button>
        {analysis ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void runAnalysis(true)}
            disabled={analyzing || !canAnalyze}
          >
            Regenerate
          </Button>
        ) : null}
      </div>

      {analysisBlocked ? (
        <Alert
          tone="warning"
          title="Analysis restricted"
          description="Interview intelligence cannot be run for hired or rejected applications."
        />
      ) : null}

      {!analysisBlocked && interviewStatus && interviewStatus !== "completed" ? (
        <Alert
          tone="warning"
          title="Interview not completed"
          description="Mark the interview as completed and add interviewer notes before running intelligence analysis."
        />
      ) : null}

      {error ? <Alert tone="danger" description={error} /> : null}
      {analyzing ? (
        <LoadingState
          title="Running interview intelligence"
          description="Analyzing interview evidence against job requirements."
        />
      ) : null}

      {!analyzing && analysis ? (
        <Stack gap="4">
          {analysis.is_stale ? (
            <Alert
              tone="warning"
              title="Analysis may be outdated"
              description="The interview was updated after this analysis. Regenerate for the latest results."
            />
          ) : null}

          <Grid columns={{ mobile: 2, md: 3, lg: 5 }} gap="3">
            <MetricCard label="Overall" value={String(analysis.overall_score)} meta="Composite interview score" />
            <MetricCard label="Technical" value={String(analysis.technical_score)} meta="Technical depth" />
            <MetricCard
              label="Communication"
              value={String(analysis.communication_score)}
              meta="Communication clarity"
            />
            <MetricCard
              label="Problem solving"
              value={String(analysis.problem_solving_score)}
              meta="Problem solving ability"
            />
            <MetricCard label="Behavioral" value={String(analysis.behavioral_score)} meta="Behavioral fit" />
          </Grid>

          <Section>
            <Stack gap="2">
              <p className="job-application-card-meta">
                Confidence: {formatPercent(analysis.confidence)} · Provider: {analysis.ai_provider} · Model:{" "}
                {analysis.ai_model} · Prompt: {analysis.prompt_version}
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
            <ListBlock title="Gaps identified" items={analysis.gaps_identified} />
            <ListBlock title="Demonstrated competencies" items={analysis.demonstrated_competencies} />
          </Grid>
        </Stack>
      ) : null}

      {!analyzing && !analysis && !error ? (
        <EmptyState
          title="No interview intelligence yet"
          description={
            canAnalyze
              ? "Run interview intelligence to evaluate this interview round against the job requirements."
              : "Complete the interview and add notes to enable intelligence analysis."
          }
        />
      ) : null}
    </Stack>
  );
}
