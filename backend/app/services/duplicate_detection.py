from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.candidate_profile import CandidateProfileGenerator
from app.services.resume_analysis import ResumeAnalysisService


class DuplicateDetector:
    """Detect duplicate candidates using multiple signals and provide explanations.

    Signals used (in order of importance):
    - email exact match
    - phone exact match
    - LinkedIn/GitHub handles present in profile or resume
    - resume similarity (token overlap & skills overlap)

    The detector returns a set of candidate matches with per-signal scores and
    a combined score. A combined score above the `threshold` is considered a duplicate.
    """

    def __init__(self, threshold: float = 0.8) -> None:
        self.threshold = threshold
        self.ras = ResumeAnalysisService()
        self.profile_gen = CandidateProfileGenerator()

    def detect(self, candidate: Dict[str, Any], existing_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return a list of potential duplicates with explanations and scores."""
        results: List[Dict[str, Any]] = []

        cand_profile = candidate.get("structured_resume")
        if cand_profile is None:
            cand_profile = self.ras.extract_structured(candidate.get("resume_text", "") or "")

        cand_email = (candidate.get("email") or cand_profile.get("email") if isinstance(cand_profile, dict) else None) or ""
        cand_phone = (candidate.get("phone") or cand_profile.get("phone") if isinstance(cand_profile, dict) else None) or ""

        cand_tech = [t.lower() for t in (cand_profile.get("technical_skills") or [])]
        cand_text = (candidate.get("resume_text", "") or "")

        for existing in existing_candidates:
            score, breakdown = self._compare(candidate, existing, cand_email, cand_phone, cand_tech, cand_text)
            if score > 0:
                results.append({"existing_id": existing.get("id") or existing.get("email"), "score": round(score, 3), "breakdown": breakdown})

        # sort high to low
        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        return results

    def _compare(self, candidate: Dict[str, Any], existing: Dict[str, Any], cand_email: str, cand_phone: str, cand_tech: List[str], cand_text: str) -> Tuple[float, Dict[str, Any]]:
        existing_profile = existing.get("structured_resume")
        if existing_profile is None:
            existing_profile = self.ras.extract_structured(existing.get("resume_text", "") or "")

        existing_email = existing.get("email") or existing_profile.get("email") or ""
        existing_phone = existing.get("phone") or existing_profile.get("phone") or ""
        existing_tech = [t.lower() for t in (existing_profile.get("technical_skills") or [])]
        existing_text = (existing.get("resume_text", "") or "")

        breakdown: Dict[str, float] = {"email": 0.0, "phone": 0.0, "linkedin": 0.0, "github": 0.0, "skills": 0.0, "text": 0.0}

        # Email exact match
        if cand_email and existing_email and cand_email.strip().lower() == existing_email.strip().lower():
            breakdown["email"] = 1.0

        # Phone exact match (digits only)
        def normalize_phone(p: str) -> str:
            return "".join(ch for ch in (p or "") if ch.isdigit())

        if cand_phone and existing_phone and normalize_phone(cand_phone) == normalize_phone(existing_phone):
            breakdown["phone"] = 1.0

        # LinkedIn/GitHub handle match: look for handles in resume text or profile
        def find_handle(text: str, service: str) -> Optional[str]:
            text = (text or "").lower()
            if service == "linkedin":
                m = None
                for token in ("linkedin.com/in/", "linkedin.com/dir/", "linkedin.com/pub/"):
                    if token in text:
                        idx = text.find(token)
                        tail = text[idx + len(token):].split()[0].strip("/,.")
                        return tail
                return None
            if service == "github":
                if "github.com/" in text:
                    idx = text.find("github.com/")
                    tail = text[idx + len("github.com/"):].split()[0].strip("/,.")
                    return tail
                return None
            return None

        cand_text_lower = cand_text.lower()
        existing_text_lower = existing_text.lower()

        cand_linkedin = find_handle(cand_text_lower, "linkedin") or (candidate.get("linkedin") or "")
        existing_linkedin = find_handle(existing_text_lower, "linkedin") or (existing.get("linkedin") or "")
        if cand_linkedin and existing_linkedin and cand_linkedin.strip().lower() == existing_linkedin.strip().lower():
            breakdown["linkedin"] = 0.9

        cand_github = find_handle(cand_text_lower, "github") or (candidate.get("github") or "")
        existing_github = find_handle(existing_text_lower, "github") or (existing.get("github") or "")
        if cand_github and existing_github and cand_github.strip().lower() == existing_github.strip().lower():
            breakdown["github"] = 0.9

        # Skills overlap score (Jaccard)
        skills_score = 0.0
        if cand_tech or existing_tech:
            set_a = set([s.strip().lower() for s in cand_tech if s])
            set_b = set([s.strip().lower() for s in existing_tech if s])
            if set_a or set_b:
                inter = set_a & set_b
                union = set_a | set_b
                skills_score = len(inter) / max(1, len(union))
        breakdown["skills"] = round(skills_score, 3)

        # Resume text similarity (token Jaccard)
        def text_jaccard(a: str, b: str) -> float:
            toks_a = set(t for t in re.findall(r"[a-zA-Z0-9#+.]+", (a or "").lower()) if len(t) > 1)
            toks_b = set(t for t in re.findall(r"[a-zA-Z0-9#+.]+", (b or "").lower()) if len(t) > 1)
            if not toks_a and not toks_b:
                return 0.0
            inter = toks_a & toks_b
            union = toks_a | toks_b
            return len(inter) / max(1, len(union))

        text_sim = text_jaccard(cand_text, existing_text)
        breakdown["text"] = round(text_sim, 3)

        # Combined score: weighted
        weights = {"email": 0.4, "phone": 0.25, "linkedin": 0.12, "github": 0.08, "skills": 0.1, "text": 0.05}
        combined = sum(breakdown[k] * w for k, w in weights.items())

        # If any high-confidence identifier matches, ensure high combined score
        if breakdown["email"] >= 1.0 or breakdown["phone"] >= 1.0:
            combined = max(combined, 0.95)

        return combined, breakdown


class ResumeVersioning:
    """Maintain resume version history on the filesystem under `backend/data/resume_versions.json`.

    This is a lightweight version store recording (candidate_id, version_id, timestamp, hash, text).
    """

    STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "resume_versions.json")

    def __init__(self) -> None:
        os.makedirs(os.path.dirname(self.STORAGE_PATH), exist_ok=True)
        if not os.path.exists(self.STORAGE_PATH):
            with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
                json.dump({}, fh)

    def _load(self) -> Dict[str, List[Dict[str, Any]]]:
        try:
            with open(self.STORAGE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        with open(self.STORAGE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    def store_version(self, candidate_id: str, resume_text: str) -> Dict[str, Any]:
        data = self._load()
        versions = data.get(candidate_id) or []
        content_hash = hashlib.sha256((resume_text or "").encode("utf-8")).hexdigest()
        timestamp = int(time.time())
        version_id = f"v{len(versions)+1}"
        entry = {"version_id": version_id, "timestamp": timestamp, "hash": content_hash, "text_summary": (resume_text or "")[:200]}

        # Avoid storing duplicate content
        if versions and versions[-1].get("hash") == content_hash:
            return {"stored": False, "reason": "no_change", "latest": versions[-1]}

        versions.append(entry)
        data[candidate_id] = versions
        self._save(data)
        return {"stored": True, "entry": entry}

    def get_versions(self, candidate_id: str) -> List[Dict[str, Any]]:
        data = self._load()
        return data.get(candidate_id) or []

    def latest_version(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        versions = self.get_versions(candidate_id)
        return versions[-1] if versions else None


class DuplicateGuard:
    """High-level helper to prevent duplicate candidate creation.

    Usage:
      guard = DuplicateGuard()
      dup = guard.find_duplicate_or_none(new_candidate, existing_candidates)
      if dup: handle duplicate
      else: create new candidate and call guard.record_new_candidate(candidate_id, resume_text)
    """

    def __init__(self, threshold: float = 0.8) -> None:
        self.detector = DuplicateDetector(threshold=threshold)
        self.versioning = ResumeVersioning()

    def find_duplicates(self, candidate: Dict[str, Any], existing_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.detector.detect(candidate, existing_candidates)

    def find_duplicate_or_none(self, candidate: Dict[str, Any], existing_candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        matches = self.find_duplicates(candidate, existing_candidates)
        if not matches:
            return None
        # pick top match
        top = matches[0]
        if top.get("score", 0) >= self.detector.threshold:
            return top
        return None

    def record_new_candidate(self, candidate_id: str, resume_text: str) -> Dict[str, Any]:
        return self.versioning.store_version(candidate_id, resume_text)
