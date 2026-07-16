from __future__ import annotations

import re
from dataclasses import field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class RecruiterResumeSummary:
    def __init__(
        self,
        professional_summary: str,
        experience_summary: str,
        skills_summary: str,
        education_summary: str,
        certifications_summary: str,
        strength_highlights: Optional[List[str]] = None,
        potential_concerns: Optional[List[str]] = None,
    ) -> None:
        self.professional_summary = professional_summary
        self.experience_summary = experience_summary
        self.skills_summary = skills_summary
        self.education_summary = education_summary
        self.certifications_summary = certifications_summary
        self.strength_highlights = strength_highlights or []
        self.potential_concerns = potential_concerns or []


class RecruiterAIResumeIntelligence:
    def __init__(
        self,
        skill_gap_analysis: Optional[Dict[str, Any]] = None,
        resume_strength_highlights: Optional[List[str]] = None,
        resume_risk_concerns: Optional[List[str]] = None,
        recruiter_talking_points: Optional[List[str]] = None,
        interview_focus_areas: Optional[List[str]] = None,
    ) -> None:
        self.skill_gap_analysis = skill_gap_analysis or {}
        self.resume_strength_highlights = resume_strength_highlights or []
        self.resume_risk_concerns = resume_risk_concerns or []
        self.recruiter_talking_points = recruiter_talking_points or []
        self.interview_focus_areas = interview_focus_areas or []


class ResumeIntelligenceEngine:
    """Normalize and enrich extracted resume data for downstream ATS workflows."""

    CONTACT_EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}")
    CONTACT_PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{6,}\d")

    TITLE_LEVELS = {
        "intern": 1,
        "junior": 2,
        "associate": 2,
        "engineer": 3,
        "developer": 3,
        "specialist": 3,
        "senior": 4,
        "staff": 5,
        "lead": 6,
        "principal": 7,
        "manager": 7,
        "head": 8,
        "director": 9,
        "vp": 10,
        "vice president": 10,
        "cto": 11,
        "cio": 11,
        "ceo": 12,
        "founder": 10,
    }

    def normalize_terms(self, values: List[Any]) -> List[str]:
        """Public helper to normalize and deduplicate term lists."""
        return self._normalize_string_list(values)

    def build_intelligence(
        self,
        resume_text: str,
        structured: Dict[str, Any],
        summary: str = "",
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        candidate_profile: Optional[Dict[str, Any]] = None,
        evaluation_data: Optional[Dict[str, Any]] = None,
        hiring_recommendation_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        canonical = self._to_canonical(
            structured=structured,
            resume_text=resume_text,
            summary=summary,
            full_name=full_name,
            email=email,
            phone=phone,
        )

        inconsistencies = self._detect_inconsistencies(canonical, resume_text)
        employment_analysis = self._analyze_employment(canonical.get("experience", []))
        career_progression = self._analyze_career_progression(canonical.get("experience", []))
        confidence_scores = self._field_confidence_scores(canonical, inconsistencies)
        ats_score = self._ats_compatibility_score(canonical, confidence_scores, inconsistencies, employment_analysis)
        recruiter_summary = self._build_recruiter_summary(
            canonical=canonical,
            inconsistencies=inconsistencies,
            employment_analysis=employment_analysis,
            career_progression=career_progression,
            ats_score=ats_score,
        )
        recruiter_ai_intelligence = self._build_recruiter_ai_intelligence(
            canonical=canonical,
            inconsistencies=inconsistencies,
            confidence_scores=confidence_scores,
            employment_analysis=employment_analysis,
            career_progression=career_progression,
            ats_score=ats_score,
            candidate_profile=candidate_profile or {},
            evaluation_data=evaluation_data or {},
            hiring_recommendation_data=hiring_recommendation_data or {},
        )

        def _to_dict(obj: object) -> Dict[str, Any]:
            # support both dataclass-like objects and plain objects
            try:
                from dataclasses import asdict as _asdict

                return _asdict(obj)
            except Exception:
                return getattr(obj, "__dict__", {})

        return {
            "canonical": canonical,
            "inconsistencies": inconsistencies,
            "field_confidence_scores": confidence_scores,
            "employment_analysis": employment_analysis,
            "career_progression": career_progression,
            "ats_compatibility_score": ats_score,
            "recruiter_summary": _to_dict(recruiter_summary),
            "recruiter_ai_intelligence": _to_dict(recruiter_ai_intelligence),
        }

    def _build_recruiter_ai_intelligence(
        self,
        canonical: Dict[str, Any],
        inconsistencies: List[Dict[str, Any]],
        confidence_scores: Dict[str, float],
        employment_analysis: Dict[str, Any],
        career_progression: Dict[str, Any],
        ats_score: Dict[str, Any],
        candidate_profile: Dict[str, Any],
        evaluation_data: Dict[str, Any],
        hiring_recommendation_data: Dict[str, Any],
    ) -> RecruiterAIResumeIntelligence:
        skills = canonical.get("skills") or {}
        technical_skills = self._normalize_string_list(skills.get("technical") or [])
        soft_skills = self._normalize_string_list(skills.get("soft") or [])

        expected_technical, expected_soft, missing_qualifications = self._extract_expected_requirements(
            hiring_recommendation_data=hiring_recommendation_data,
            evaluation_data=evaluation_data,
            candidate_profile=candidate_profile,
        )

        technical_set = {item.lower() for item in technical_skills}
        soft_set = {item.lower() for item in soft_skills}
        missing_technical = [item for item in expected_technical if item.lower() not in technical_set]
        missing_soft = [item for item in expected_soft if item.lower() not in soft_set]

        skill_gap_analysis = {
            "missing_technical_skills": missing_technical,
            "missing_soft_skills": missing_soft,
            "missing_qualifications": self._dedupe_strings(missing_qualifications),
            "summary": self._build_skill_gap_summary_text(missing_technical, missing_soft, missing_qualifications),
        }

        resume_strength_highlights = self._dedupe_strings(
            self._derive_resume_strength_highlights(
                technical_skills=technical_skills,
                soft_skills=soft_skills,
                employment_analysis=employment_analysis,
                career_progression=career_progression,
                ats_score=ats_score,
                evaluation_data=evaluation_data,
                hiring_recommendation_data=hiring_recommendation_data,
            )
        )

        resume_risk_concerns = self._dedupe_strings(
            self._derive_resume_risk_concerns(
                inconsistencies=inconsistencies,
                confidence_scores=confidence_scores,
                employment_analysis=employment_analysis,
                missing_technical=missing_technical,
                missing_soft=missing_soft,
                missing_qualifications=missing_qualifications,
                evaluation_data=evaluation_data,
                hiring_recommendation_data=hiring_recommendation_data,
            )
        )

        recruiter_talking_points = self._dedupe_strings(
            self._build_recruiter_talking_points(
                strengths=resume_strength_highlights,
                concerns=resume_risk_concerns,
                skill_gap_analysis=skill_gap_analysis,
                candidate_profile=candidate_profile,
            )
        )

        interview_focus_areas = self._dedupe_strings(
            self._build_interview_focus_areas(
                skill_gap_analysis=skill_gap_analysis,
                concerns=resume_risk_concerns,
                evaluation_data=evaluation_data,
                hiring_recommendation_data=hiring_recommendation_data,
            )
        )

        return RecruiterAIResumeIntelligence(
            skill_gap_analysis=skill_gap_analysis,
            resume_strength_highlights=resume_strength_highlights,
            resume_risk_concerns=resume_risk_concerns,
            recruiter_talking_points=recruiter_talking_points,
            interview_focus_areas=interview_focus_areas,
        )

    def _extract_expected_requirements(
        self,
        hiring_recommendation_data: Dict[str, Any],
        evaluation_data: Dict[str, Any],
        candidate_profile: Dict[str, Any],
    ) -> tuple[List[str], List[str], List[str]]:
        technical_candidates: List[Any] = []
        soft_candidates: List[Any] = []
        missing_qualifications: List[str] = []

        recommendation_items = []
        if isinstance(hiring_recommendation_data.get("items"), list):
            recommendation_items = hiring_recommendation_data.get("items") or []
        elif isinstance(hiring_recommendation_data, dict):
            recommendation_items = [hiring_recommendation_data]

        for item in recommendation_items:
            if not isinstance(item, dict):
                continue
            source = item.get("source") or {}
            ranking = source.get("ranking") or {}
            semantic_match = ranking.get("semantic_match") or {}

            technical_candidates.extend(semantic_match.get("missing_required_skills") or [])
            technical_candidates.extend((semantic_match.get("components") or [{}])[0].get("matched_required") or [])
            technical_candidates.extend(semantic_match.get("preferred_skills_possessed") or [])

            for qualification in item.get("missing_mandatory_qualifications") or []:
                text = str(qualification)
                missing_qualifications.append(text)
                if text.startswith("required_skill:"):
                    technical_candidates.append(text.split(":", maxsplit=1)[1])

        eval_explainability = evaluation_data.get("explainability") or {}
        eval_metadata = evaluation_data.get("metadata") or {}
        technical_candidates.extend(eval_metadata.get("required_technical_skills") or [])
        soft_candidates.extend(eval_metadata.get("required_soft_skills") or [])
        soft_candidates.extend(eval_explainability.get("behavioral_focus") or [])

        technical_candidates.extend(candidate_profile.get("target_technical_skills") or [])
        soft_candidates.extend(candidate_profile.get("target_soft_skills") or [])

        return (
            self._normalize_string_list(technical_candidates),
            self._normalize_string_list(soft_candidates),
            self._dedupe_strings([str(item) for item in missing_qualifications]),
        )

    def _build_skill_gap_summary_text(
        self,
        missing_technical: List[str],
        missing_soft: List[str],
        missing_qualifications: List[str],
    ) -> str:
        parts = []
        if missing_technical:
            parts.append(f"Technical gaps: {', '.join(missing_technical[:6])}")
        if missing_soft:
            parts.append(f"Soft-skill gaps: {', '.join(missing_soft[:4])}")
        if missing_qualifications:
            parts.append(f"Qualification gaps: {', '.join(missing_qualifications[:4])}")
        if not parts:
            return "No critical skill or qualification gaps identified from available recommendation and profile data."
        return "; ".join(parts) + "."

    def _derive_resume_strength_highlights(
        self,
        technical_skills: List[str],
        soft_skills: List[str],
        employment_analysis: Dict[str, Any],
        career_progression: Dict[str, Any],
        ats_score: Dict[str, Any],
        evaluation_data: Dict[str, Any],
        hiring_recommendation_data: Dict[str, Any],
    ) -> List[str]:
        strengths: List[str] = []
        total_years = float(employment_analysis.get("total_experience_years") or 0.0)

        if total_years >= 5:
            strengths.append(f"Demonstrates {round(total_years, 1)} years of cumulative experience.")
        if len(technical_skills) >= 8:
            strengths.append("Strong technical breadth across listed skills.")
        if len(soft_skills) >= 4:
            strengths.append("Multiple soft skills identified, supporting cross-functional collaboration.")
        if career_progression.get("trend") in {"strong_upward", "steady"}:
            strengths.append(f"Career progression trend is {career_progression.get('trend')}.")
        if float(ats_score.get("score") or 0.0) >= 75:
            strengths.append("Resume quality indicates strong ATS readiness.")

        for entry in (evaluation_data.get("explainability") or {}).get("strengths") or []:
            strengths.append(str(entry))

        for item in (hiring_recommendation_data.get("items") or []) if isinstance(hiring_recommendation_data.get("items"), list) else []:
            for strength in item.get("strengths") or []:
                strengths.append(str(strength))

        return strengths

    def _derive_resume_risk_concerns(
        self,
        inconsistencies: List[Dict[str, Any]],
        confidence_scores: Dict[str, float],
        employment_analysis: Dict[str, Any],
        missing_technical: List[str],
        missing_soft: List[str],
        missing_qualifications: List[str],
        evaluation_data: Dict[str, Any],
        hiring_recommendation_data: Dict[str, Any],
    ) -> List[str]:
        concerns: List[str] = []

        if inconsistencies:
            concerns.append(f"Resume contains {len(inconsistencies)} detected data inconsistency issue(s).")
        if (employment_analysis.get("gaps") or []):
            concerns.append("Employment timeline includes one or more potential gaps.")

        low_conf_fields = [field for field, score in confidence_scores.items() if float(score) < 0.5]
        if low_conf_fields:
            concerns.append(f"Low extraction confidence in fields: {', '.join(low_conf_fields[:6])}.")

        if missing_technical:
            concerns.append(f"Potential technical gaps for target role: {', '.join(missing_technical[:6])}.")
        if missing_soft:
            concerns.append(f"Potential soft-skill gaps: {', '.join(missing_soft[:4])}.")
        if missing_qualifications:
            concerns.append(f"Missing mandatory qualifications flagged: {', '.join(missing_qualifications[:4])}.")

        for concern in (evaluation_data.get("explainability") or {}).get("concerns") or []:
            concerns.append(str(concern))

        items = hiring_recommendation_data.get("items") if isinstance(hiring_recommendation_data.get("items"), list) else []
        for item in items:
            for risk in item.get("risks") or []:
                concerns.append(str(risk))
            for weakness in item.get("weaknesses") or []:
                concerns.append(str(weakness))

        return concerns

    def _build_recruiter_talking_points(
        self,
        strengths: List[str],
        concerns: List[str],
        skill_gap_analysis: Dict[str, Any],
        candidate_profile: Dict[str, Any],
    ) -> List[str]:
        talking_points: List[str] = []

        if strengths:
            talking_points.append(f"Validate strongest fit areas: {'; '.join(strengths[:2])}.")
        if concerns:
            talking_points.append(f"Probe major concern areas: {'; '.join(concerns[:2])}.")

        missing_technical = skill_gap_analysis.get("missing_technical_skills") or []
        if missing_technical:
            talking_points.append(
                f"Ask for concrete examples demonstrating capability in: {', '.join(missing_technical[:5])}."
            )

        target_role = candidate_profile.get("target_role") or candidate_profile.get("applied_role")
        if target_role:
            talking_points.append(f"Assess role motivation and fit for target position: {target_role}.")

        return talking_points

    def _build_interview_focus_areas(
        self,
        skill_gap_analysis: Dict[str, Any],
        concerns: List[str],
        evaluation_data: Dict[str, Any],
        hiring_recommendation_data: Dict[str, Any],
    ) -> List[str]:
        focus_areas: List[str] = []

        for skill in skill_gap_analysis.get("missing_technical_skills") or []:
            focus_areas.append(f"Technical deep-dive: {skill}")
        for skill in skill_gap_analysis.get("missing_soft_skills") or []:
            focus_areas.append(f"Behavioral validation: {skill}")

        eval_explainability = evaluation_data.get("explainability") or {}
        for item in eval_explainability.get("interview_focus_areas") or []:
            focus_areas.append(str(item))
        for item in eval_explainability.get("concerns") or []:
            focus_areas.append(f"Risk follow-up: {item}")

        items = hiring_recommendation_data.get("items") if isinstance(hiring_recommendation_data.get("items"), list) else []
        for item in items:
            for risk in item.get("risk_factors") or []:
                if isinstance(risk, dict) and risk.get("message"):
                    focus_areas.append(f"Risk factor follow-up: {risk.get('message')}")

        for concern in concerns[:4]:
            focus_areas.append(f"Clarify concern: {concern}")

        return focus_areas

    def _dedupe_strings(self, values: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for value in values:
            text = self._clean_text(value)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    def _build_recruiter_summary(
        self,
        canonical: Dict[str, Any],
        inconsistencies: List[Dict[str, Any]],
        employment_analysis: Dict[str, Any],
        career_progression: Dict[str, Any],
        ats_score: Dict[str, Any],
    ) -> RecruiterResumeSummary:
        basics = canonical.get("basics") or {}
        skills = canonical.get("skills") or {}
        education = canonical.get("education") or []
        experience = canonical.get("experience") or []
        certifications = canonical.get("certifications") or []

        profile_summary = (basics.get("summary") or "").strip()
        current_title = basics.get("current_title") or "professional"
        total_years = float(employment_analysis.get("total_experience_years") or 0.0)

        if profile_summary:
            professional_summary = profile_summary
        else:
            professional_summary = f"Candidate profile indicates a {current_title} with approximately {round(total_years, 1)} years of experience."

        top_roles = [item.get("title") for item in (employment_analysis.get("timeline") or []) if item.get("title")]
        role_snippet = ", ".join(top_roles[:3]) if top_roles else "role history available"
        experience_summary = (
            f"Total estimated experience is {round(total_years, 1)} years. "
            f"Recent roles include: {role_snippet}."
        )

        technical_skills = skills.get("technical") or []
        soft_skills = skills.get("soft") or []
        skills_summary = (
            f"Technical skills ({len(technical_skills)}): {', '.join(technical_skills[:8]) or 'none listed'}. "
            f"Soft skills ({len(soft_skills)}): {', '.join(soft_skills[:6]) or 'none listed'}."
        )

        edu_parts = []
        for item in education[:4]:
            degree = item.get("degree") or "Degree not specified"
            institution = item.get("institution") or "Institution not specified"
            end_year = item.get("end_year")
            suffix = f" ({end_year})" if end_year else ""
            edu_parts.append(f"{degree} - {institution}{suffix}")
        education_summary = "; ".join(edu_parts) if edu_parts else "No formal education records identified in parsed resume data."

        cert_names = [item.get("name") for item in certifications if item.get("name")]
        certifications_summary = ", ".join(cert_names[:8]) if cert_names else "No certifications identified in parsed resume data."

        strengths: List[str] = []
        if float(ats_score.get("score") or 0) >= 70:
            strengths.append("Resume profile demonstrates strong ATS compatibility.")
        if len(technical_skills) >= 8:
            strengths.append("Broad technical skill coverage identified.")
        if career_progression.get("trend") in {"strong_upward", "steady"}:
            strengths.append(f"Career progression trend appears {career_progression.get('trend')}.")
        if total_years >= 5:
            strengths.append("Substantial accumulated professional experience.")
        if cert_names:
            strengths.append("Relevant certifications are present.")

        concerns: List[str] = []
        if not basics.get("email") or not basics.get("phone"):
            concerns.append("Missing complete contact information (email and phone).")
        gaps = employment_analysis.get("gaps") or []
        if gaps:
            concerns.append(f"Employment gaps detected: {len(gaps)} potential gap(s).")
        if inconsistencies:
            concerns.append(f"Data inconsistencies detected: {len(inconsistencies)} issue(s) need verification.")
        if not education:
            concerns.append("Education details are limited or unavailable.")
        if not technical_skills:
            concerns.append("Technical skills were not clearly extracted.")

        return RecruiterResumeSummary(
            professional_summary=professional_summary,
            experience_summary=experience_summary,
            skills_summary=skills_summary,
            education_summary=education_summary,
            certifications_summary=certifications_summary,
            strength_highlights=self._normalize_string_list(strengths),
            potential_concerns=self._normalize_string_list(concerns),
        )

    def _to_canonical(
        self,
        structured: Dict[str, Any],
        resume_text: str,
        summary: str,
        full_name: Optional[str],
        email: Optional[str],
        phone: Optional[str],
    ) -> Dict[str, Any]:
        technical_skills = self._normalize_string_list(structured.get("technical_skills") or [])
        soft_skills = self._normalize_string_list(structured.get("soft_skills") or [])

        education = [self._normalize_education(item) for item in (structured.get("education") or [])]
        education = [item for item in education if any(v for v in item.values() if v not in (None, "", []))]

        experience = [self._normalize_experience(item) for item in (structured.get("experience") or [])]
        experience = [item for item in experience if any(v for k, v in item.items() if k != "description" and v not in (None, "", []))]

        certifications = [self._normalize_certification(item) for item in (structured.get("certifications") or [])]
        certifications = [item for item in certifications if item.get("name")]

        projects = [self._normalize_project(item) for item in (structured.get("projects") or [])]
        projects = [item for item in projects if item.get("name") or item.get("description")]

        email_candidates = self.CONTACT_EMAIL_RE.findall(resume_text)
        phone_candidates = self.CONTACT_PHONE_RE.findall(resume_text)

        canonical_email = email or (email_candidates[0] if email_candidates else None)
        canonical_phone = phone or (phone_candidates[0] if phone_candidates else None)

        return {
            "basics": {
                "full_name": (full_name or "").strip() or None,
                "email": canonical_email,
                "phone": canonical_phone,
                "location": self._infer_location(resume_text),
                "current_title": self._infer_current_title(experience),
                "summary": summary or None,
            },
            "skills": {
                "technical": technical_skills,
                "soft": soft_skills,
            },
            "education": education,
            "experience": experience,
            "certifications": certifications,
            "projects": projects,
            "metadata": {
                "source": "resume_intelligence_engine",
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
        }

    def _detect_inconsistencies(self, canonical: Dict[str, Any], resume_text: str) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []

        # Contact conflicts.
        all_emails = list(dict.fromkeys(self.CONTACT_EMAIL_RE.findall(resume_text)))
        all_phones = list(dict.fromkeys(self.CONTACT_PHONE_RE.findall(resume_text)))
        if len(all_emails) > 1:
            issues.append({"field": "basics.email", "issue": "multiple_emails_detected", "values": all_emails})
        if len(all_phones) > 1:
            issues.append({"field": "basics.phone", "issue": "multiple_phones_detected", "values": all_phones})

        # Education and experience chronology conflicts.
        for idx, edu in enumerate(canonical.get("education", [])):
            sy = edu.get("start_year")
            ey = edu.get("end_year")
            if sy is not None and ey is not None and sy > ey:
                issues.append({
                    "field": f"education[{idx}]",
                    "issue": "start_after_end",
                    "values": {"start_year": sy, "end_year": ey},
                })

        current_roles = 0
        for idx, exp in enumerate(canonical.get("experience", [])):
            sy = exp.get("start_year")
            ey = exp.get("end_year")
            if sy is not None and ey is not None and sy > ey:
                issues.append({
                    "field": f"experience[{idx}]",
                    "issue": "start_after_end",
                    "values": {"start_year": sy, "end_year": ey},
                })
            if exp.get("is_current"):
                current_roles += 1

        if current_roles > 1:
            issues.append({
                "field": "experience",
                "issue": "multiple_current_roles",
                "values": {"count": current_roles},
            })

        return issues

    def _field_confidence_scores(self, canonical: Dict[str, Any], inconsistencies: List[Dict[str, Any]]) -> Dict[str, float]:
        issue_fields = [item.get("field", "") for item in inconsistencies]

        def penalty(prefix: str) -> float:
            count = sum(1 for field in issue_fields if field.startswith(prefix))
            return min(0.4, count * 0.1)

        basics = canonical.get("basics", {})
        skills = canonical.get("skills", {})
        education = canonical.get("education", [])
        experience = canonical.get("experience", [])
        certifications = canonical.get("certifications", [])
        projects = canonical.get("projects", [])

        scores: Dict[str, float] = {}
        scores["full_name"] = 1.0 if basics.get("full_name") else 0.2
        scores["email"] = max(0.0, 1.0 if basics.get("email") else 0.0 - penalty("basics.email"))
        scores["phone"] = max(0.0, 1.0 if basics.get("phone") else 0.0 - penalty("basics.phone"))
        scores["location"] = 0.8 if basics.get("location") else 0.3
        scores["summary"] = min(1.0, len((basics.get("summary") or "").strip()) / 220.0)

        scores["technical_skills"] = self._list_confidence(skills.get("technical", []), max_count=16)
        scores["soft_skills"] = self._list_confidence(skills.get("soft", []), max_count=10)
        scores["education"] = max(0.0, self._record_confidence(education, ["degree", "institution"], 6) - penalty("education"))
        scores["experience"] = max(0.0, self._record_confidence(experience, ["title", "company"], 8) - penalty("experience"))
        scores["certifications"] = self._record_confidence(certifications, ["name"], 6)
        scores["projects"] = self._record_confidence(projects, ["name", "description"], 8)

        for key, value in list(scores.items()):
            scores[key] = round(min(1.0, max(0.0, float(value))), 2)

        return scores

    def _analyze_employment(self, experience: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not experience:
            return {
                "timeline": [],
                "gaps": [],
                "total_experience_years": 0.0,
            }

        timeline = sorted(experience, key=lambda item: (item.get("start_year") or 0, item.get("end_year") or 9999), reverse=True)

        gaps = []
        prev_start = None
        for idx, role in enumerate(timeline):
            current_end = role.get("end_year") if role.get("end_year") is not None else datetime.now(timezone.utc).year
            current_start = role.get("start_year")

            if idx > 0 and prev_start is not None and current_end is not None:
                gap_years = prev_start - current_end
                if gap_years >= 1:
                    gaps.append({
                        "after_role": timeline[idx - 1].get("title"),
                        "before_role": role.get("title"),
                        "gap_years": gap_years,
                    })

            prev_start = current_start

        total_years = 0.0
        for role in timeline:
            sy = role.get("start_year")
            ey = role.get("end_year") if role.get("end_year") is not None else datetime.now(timezone.utc).year
            if sy is not None and ey is not None and ey >= sy:
                total_years += float(ey - sy)

        return {
            "timeline": timeline,
            "gaps": gaps,
            "total_experience_years": round(total_years, 1),
        }

    def _analyze_career_progression(self, experience: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(experience) < 2:
            return {
                "progression_score": 0.5,
                "trend": "insufficient_data",
                "transitions": [],
            }

        chronological = sorted(experience, key=lambda item: (item.get("start_year") or 0, item.get("end_year") or 0))
        transitions = []
        improvements = 0

        for i in range(1, len(chronological)):
            prev_title = (chronological[i - 1].get("title") or "").lower()
            curr_title = (chronological[i].get("title") or "").lower()
            prev_level = self._title_level(prev_title)
            curr_level = self._title_level(curr_title)
            delta = curr_level - prev_level
            if delta > 0:
                improvements += 1
            transitions.append(
                {
                    "from": chronological[i - 1].get("title"),
                    "to": chronological[i].get("title"),
                    "level_delta": delta,
                }
            )

        ratio = improvements / max(1, len(transitions))
        if ratio >= 0.7:
            trend = "strong_upward"
        elif ratio >= 0.4:
            trend = "steady"
        elif ratio > 0.0:
            trend = "mixed"
        else:
            trend = "flat_or_downward"

        return {
            "progression_score": round(ratio, 2),
            "trend": trend,
            "transitions": transitions,
        }

    def _ats_compatibility_score(
        self,
        canonical: Dict[str, Any],
        confidence: Dict[str, float],
        inconsistencies: List[Dict[str, Any]],
        employment_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        basics = canonical.get("basics", {})
        skills = canonical.get("skills", {})

        section_presence = 0
        for key in ("education", "experience", "projects", "certifications"):
            if canonical.get(key):
                section_presence += 1

        contact_score = 1.0 if basics.get("email") and basics.get("phone") else 0.5 if basics.get("email") or basics.get("phone") else 0.0
        completeness_score = section_presence / 4.0
        skills_score = min(1.0, (len(skills.get("technical", [])) + len(skills.get("soft", []))) / 20.0)
        confidence_score = sum(confidence.values()) / max(1, len(confidence))
        consistency_score = max(0.0, 1.0 - min(1.0, len(inconsistencies) / 5.0))
        gap_penalty = min(0.3, len(employment_analysis.get("gaps", [])) * 0.05)

        weighted = (
            0.2 * contact_score
            + 0.25 * completeness_score
            + 0.2 * skills_score
            + 0.2 * confidence_score
            + 0.15 * consistency_score
            - gap_penalty
        )

        score = int(round(min(1.0, max(0.0, weighted)) * 100))

        return {
            "score": score,
            "components": {
                "contact": round(contact_score, 2),
                "completeness": round(completeness_score, 2),
                "skills_density": round(skills_score, 2),
                "confidence": round(confidence_score, 2),
                "consistency": round(consistency_score, 2),
                "gap_penalty": round(gap_penalty, 2),
            },
            "rating": self._ats_rating(score),
        }

    def _normalize_education(self, item: Any) -> Dict[str, Any]:
        if isinstance(item, dict):
            degree = self._clean_text(item.get("degree"))
            institution = self._clean_text(item.get("institution"))
            start_year = self._parse_year(item.get("start_year"))
            end_year = self._parse_year(item.get("end_year"))
            return {
                "degree": degree,
                "institution": institution,
                "start_year": start_year,
                "end_year": end_year,
            }
        text = self._clean_text(item)
        return {
            "degree": text,
            "institution": None,
            "start_year": self._parse_year(text),
            "end_year": None,
        }

    def _normalize_experience(self, item: Any) -> Dict[str, Any]:
        if isinstance(item, dict):
            title = self._clean_text(item.get("title"))
            company = self._clean_text(item.get("company"))
            start_year = self._parse_year(item.get("start_year"))
            end_year = self._parse_year(item.get("end_year"))
            description = self._clean_text(item.get("description"))
        else:
            text = self._clean_text(item)
            years = re.findall(r"(?:19|20)\d{2}", text)
            title = text
            company = None
            start_year = int(years[0]) if years else None
            end_year = int(years[1]) if len(years) > 1 else None
            description = None

        is_current = False
        if isinstance(item, dict):
            raw_end = item.get("end_year")
            if raw_end is not None and str(raw_end).strip().lower() in {"present", "current", "now", "ongoing"}:
                is_current = True
                end_year = None

        return {
            "title": title,
            "company": company,
            "start_year": start_year,
            "end_year": end_year,
            "is_current": is_current,
            "description": description,
        }

    def _normalize_certification(self, item: Any) -> Dict[str, Any]:
        if isinstance(item, dict):
            return {
                "name": self._clean_text(item.get("name")),
                "issuer": self._clean_text(item.get("issuer")),
                "year": self._parse_year(item.get("year")),
            }

        text = self._clean_text(item)
        return {
            "name": text,
            "issuer": None,
            "year": self._parse_year(text),
        }

    def _normalize_project(self, item: Any) -> Dict[str, Any]:
        if isinstance(item, dict):
            technologies = self._normalize_string_list(item.get("technologies") or [])
            return {
                "name": self._clean_text(item.get("name")),
                "description": self._clean_text(item.get("description")),
                "technologies": technologies,
            }

        text = self._clean_text(item)
        return {
            "name": text,
            "description": None,
            "technologies": [],
        }

    def _normalize_string_list(self, values: List[Any]) -> List[str]:
        cleaned = []
        seen = set()
        for value in values:
            text = self._clean_text(value)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        return cleaned

    def _record_confidence(self, records: List[Dict[str, Any]], required_fields: List[str], target_count: int) -> float:
        if not records:
            return 0.0
        filled = 0
        for record in records:
            completeness = 0
            for field in required_fields:
                if record.get(field):
                    completeness += 1
            filled += completeness / max(1, len(required_fields))

        quality = filled / len(records)
        quantity = min(1.0, len(records) / max(1, target_count))
        return round(0.7 * quality + 0.3 * quantity, 2)

    def _list_confidence(self, values: List[str], max_count: int) -> float:
        if not values:
            return 0.0
        quality = 1.0 if all(isinstance(v, str) and v.strip() for v in values) else 0.6
        quantity = min(1.0, len(values) / max_count)
        return round(0.6 * quality + 0.4 * quantity, 2)

    def _parse_year(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value if 1900 <= value <= 2100 else None

        text = str(value).strip()
        if not text:
            return None
        if text.lower() in {"present", "current", "now", "ongoing"}:
            return None

        m = re.search(r"(?:19|20)\d{2}", text)
        if not m:
            return None
        year = int(m.group(0))
        return year if 1900 <= year <= 2100 else None

    def _clean_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return re.sub(r"\s+", " ", text) if text else None

    def _infer_location(self, resume_text: str) -> Optional[str]:
        for line in resume_text.splitlines()[:20]:
            if re.search(r"\b(city|state|country|india|usa|united states|remote)\b", line, flags=re.I):
                return line.strip()
        return None

    def _infer_current_title(self, experience: List[Dict[str, Any]]) -> Optional[str]:
        for item in experience:
            if item.get("is_current") and item.get("title"):
                return item.get("title")

        latest = sorted(
            experience,
            key=lambda record: (
                1 if record.get("end_year") is None else 0,
                record.get("end_year") or 0,
                record.get("start_year") or 0,
            ),
            reverse=True,
        )
        return latest[0].get("title") if latest else None

    def _title_level(self, title: str) -> int:
        if not title:
            return 0
        for token, level in self.TITLE_LEVELS.items():
            if token in title:
                return level
        return 3

    def _ats_rating(self, score: int) -> str:
        if score >= 85:
            return "excellent"
        if score >= 70:
            return "strong"
        if score >= 50:
            return "moderate"
        return "needs_improvement"
