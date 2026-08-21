import { useCallback, useEffect, useState } from "react";

import { authFetch } from "../lib/api";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Grid,
  LoadingState,
  MetricCard,
  Section,
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

interface RecruiterOverrideInfo {
  recommendation: string;
  reason: string;
  comment?: string | null;
  overridden_by_user_id: string;
  overridden_at: string;
  original_recommendation?: string | null;
}

export interface ApplicationHiringDecision {
  id: string;
  application_id: string;
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
  recruiter_override?: RecruiterOverrideInfo | null;
  policy_version: string;
  created_at: string;
  updated_at: string;
  is_stale: boolean;
}

const OVERRIDE_OPTIONS = ["Strong Hire", "Hire", "Consider", "Reject"] as const;

interface ApplicationHiringDecisionPanelProps {
  applicationId: string;
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

export function ApplicationHiringDecisionPanel({ applicationId }: ApplicationHiringDecisionPanelProps) {
  const [decision, setDecision] = useState<ApplicationHiringDecision | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [savingOverride, setSavingOverride] = useState(false);
  const [overrideRecommendation, setOverrideRecommendation] = useState<(typeof OVERRIDE_OPTIONS)[number]>("Hire");
  const [overrideReason, setOverrideReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadDecision = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch(`/applications/${applicationId}/hiring-decision`, {
        headers: { Accept: "application/json" },
      });
      if (response.status === 404) {
        setDecision(null);
        return;
      }
      if (!response.ok) {
        throw new Error(`Failed to load hiring decision (${response.status})`);
      }
      const payload = (await response.json()) as ApplicationHiringDecision;
      setDecision(payload);
      const effective = payload.recruiter_override?.recommendation ?? payload.recommendation;
      if (OVERRIDE_OPTIONS.includes(effective as (typeof OVERRIDE_OPTIONS)[number])) {
        setOverrideRecommendation(effective as (typeof OVERRIDE_OPTIONS)[number]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load hiring decision");
      setDecision(null);
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    void loadDecision();
  }, [loadDecision]);

  const generateDecision = async (force = false) => {
    setGenerating(true);
    setError(null);
    try {
      const response = await authFetch(
        `/applications/${applicationId}/hiring-decision/generate?force=${force ? "true" : "false"}&use_ai_narrative=false`,
        {
          method: "POST",
          headers: { Accept: "application/json" },
        },
      );
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Generation failed (${response.status})`);
      }
      const payload = (await response.json()) as ApplicationHiringDecision;
      setDecision(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to generate hiring decision");
    } finally {
      setGenerating(false);
    }
  };

  const saveOverride = async () => {
    const reason = overrideReason.trim();
    if (!reason) {
      setError("Override reason is required.");
      return;
    }
    setSavingOverride(true);
    setError(null);
    try {
      const response = await authFetch(`/applications/${applicationId}/hiring-decision/override`, {
        method: "PUT",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          recommendation: overrideRecommendation,
          reason,
        }),
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail ?? `Override failed (${response.status})`);
      }
      const payload = (await response.json()) as ApplicationHiringDecision;
      setDecision(payload);
      setOverrideReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save recruiter override");
    } finally {
      setSavingOverride(false);
    }
  };

  if (loading) {
    return <LoadingState title="Loading hiring decision" description="Fetching stored hiring recommendation." />;
  }

  return (
    <Stack gap="4">
      <div className="application-ai-actions">
        <Button size="sm" onClick={() => void generateDecision(false)} disabled={generating}>
          {generating ? "Generating..." : decision ? "Refresh decision" : "Generate hiring decision"}
        </Button>
        {decision ? (
          <Button size="sm" variant="secondary" onClick={() => void generateDecision(true)} disabled={generating}>
            Regenerate
          </Button>
        ) : null}
        <Button size="sm" variant="secondary" onClick={() => void loadDecision()} disabled={generating}>
          Reload
        </Button>
      </div>

      {error ? <Alert tone="danger" description={error} /> : null}
      {decision?.is_stale ? (
        <Alert
          tone="warning"
          title="Decision may be outdated"
          description="Underlying resume or interview intelligence has changed since this decision was saved. Regenerate to refresh."
        />
      ) : null}
      {generating ? (
        <LoadingState title="Generating hiring decision" description="Scoring stored intelligence signals." />
      ) : null}

      {!generating && decision ? (
        <Stack gap="4">
          <div className="application-ai-actions">
            <Badge tone={recommendationTone(decision.recommendation)}>{decision.recommendation}</Badge>
            {decision.is_stale ? <Badge tone="warning">Stale</Badge> : <Badge tone="success">Current</Badge>}
          </div>

          <Grid columns={{ mobile: 2, md: 3, lg: 5 }} gap="3">
            <MetricCard label="Overall score" value={String(decision.overall_score)} meta="Hiring recommendation" />
            <MetricCard
              label="Confidence"
              value={formatPercent(decision.decision_confidence.overall)}
              meta="Decision confidence"
            />
            <MetricCard
              label="Ranking signal"
              value={formatPercent(decision.decision_confidence.ranking_confidence)}
              meta="Ranking contribution"
            />
            <MetricCard
              label="Resume signal"
              value={formatPercent(decision.decision_confidence.semantic_confidence)}
              meta="Resume intelligence"
            />
            <MetricCard
              label="Evaluation"
              value={formatPercent(decision.decision_confidence.evaluation_confidence)}
              meta="Evaluation confidence"
            />
          </Grid>

          <Section>
            <Stack gap="2">
              <p className="job-application-card-meta">
                Policy v{decision.policy_version} · Updated {new Date(decision.updated_at).toLocaleString()}
              </p>
              <div>
                <strong>Recruiter summary</strong>
                <p className="job-application-card-meta">{decision.recruiter_metadata.summary}</p>
              </div>
              <div>
                <strong>Next step</strong>
                <p className="job-application-card-meta">{decision.recruiter_metadata.next_step_hint}</p>
              </div>
            </Stack>
          </Section>

          <Section>
            <Stack gap="2">
              <strong>Score breakdown</strong>
              <Grid columns={{ mobile: 2, md: 5 }} gap="2">
                <div>
                  <small className="job-application-card-meta">Ranking</small>
                  <strong>{decision.reasons.ranking_contribution.toFixed(3)}</strong>
                </div>
                <div>
                  <small className="job-application-card-meta">Evaluation</small>
                  <strong>{decision.reasons.evaluation_contribution.toFixed(3)}</strong>
                </div>
                <div>
                  <small className="job-application-card-meta">Resume</small>
                  <strong>{decision.reasons.semantic_contribution.toFixed(3)}</strong>
                </div>
                <div>
                  <small className="job-application-card-meta">Risk penalty</small>
                  <strong>{decision.reasons.risk_penalty.toFixed(3)}</strong>
                </div>
                <div>
                  <small className="job-application-card-meta">Final score</small>
                  <strong>{decision.reasons.final_score.toFixed(3)}</strong>
                </div>
              </Grid>
            </Stack>
          </Section>

          {decision.ai_hiring_summary ? (
            <Section>
              <Stack gap="2">
                <strong>AI hiring summary</strong>
                <p className="job-application-card-meta">{decision.ai_hiring_summary.executive_summary}</p>
                <p className="job-application-card-meta">{decision.ai_hiring_summary.hiring_recommendation_summary}</p>
                <p className="job-application-card-meta">{decision.ai_hiring_summary.skill_gap_summary}</p>
                <p className="job-application-card-meta">{decision.ai_hiring_summary.final_decision_rationale}</p>
              </Stack>
            </Section>
          ) : null}

          <Grid columns={{ mobile: 1, md: 2 }} gap="4">
            <ListBlock title="Strengths" items={decision.strengths} />
            <ListBlock title="Weaknesses" items={decision.weaknesses} />
            <ListBlock title="Missing mandatory qualifications" items={decision.missing_mandatory_qualifications} />
          </Grid>

          {decision.risk_factors.length ? (
            <Section>
              <Stack gap="2">
                <strong>Risk factors</strong>
                <ul className="application-ai-list">
                  {decision.risk_factors.map((factor) => (
                    <li key={`${factor.code}-${factor.message}`}>
                      <Badge tone={factor.severity === "high" ? "danger" : "warning"}>{factor.severity}</Badge>{" "}
                      {factor.message}
                    </li>
                  ))}
                </ul>
              </Stack>
            </Section>
          ) : null}
        </Stack>
      ) : null}

      {!generating && !decision && !error ? (
        <EmptyState
          title="No hiring decision yet"
          description="Generate from stored intelligence, or record a recruiter decision below when AI analysis is unavailable."
        />
      ) : null}

      <Section>
        <Stack gap="3">
          <strong>Recruiter decision</strong>
          <p className="job-application-card-meta">
            Record or override the hiring recommendation. This unlocks offer creation when the recommendation is Hire
            or Strong Hire.
          </p>
          {decision?.recruiter_override ? (
            <Alert
              tone="info"
              title={`Override: ${decision.recruiter_override.recommendation}`}
              description={decision.recruiter_override.reason}
            />
          ) : null}
          <label className="job-application-card-meta" htmlFor={`hiring-override-${applicationId}`}>
            Recommendation
          </label>
          <select
            id={`hiring-override-${applicationId}`}
            value={overrideRecommendation}
            onChange={(event) =>
              setOverrideRecommendation(event.target.value as (typeof OVERRIDE_OPTIONS)[number])
            }
            disabled={savingOverride || generating}
          >
            {OVERRIDE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <label className="job-application-card-meta" htmlFor={`hiring-override-reason-${applicationId}`}>
            Reason
          </label>
          <textarea
            id={`hiring-override-reason-${applicationId}`}
            rows={3}
            value={overrideReason}
            onChange={(event) => setOverrideReason(event.target.value)}
            placeholder="Explain the hiring decision"
            disabled={savingOverride || generating}
          />
          <div className="application-ai-actions">
            <Button size="sm" onClick={() => void saveOverride()} disabled={savingOverride || generating}>
              {savingOverride ? "Saving..." : decision ? "Save override" : "Record recruiter decision"}
            </Button>
          </div>
        </Stack>
      </Section>
    </Stack>
  );
}
