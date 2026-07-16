from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "resume_intelligence_engine.py"
SPEC = spec_from_file_location("resume_intelligence_engine", MODULE_PATH)
MODULE = module_from_spec(SPEC)
assert SPEC is not None
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
ResumeIntelligenceEngine = MODULE.ResumeIntelligenceEngine


def test_resume_intelligence_builds_canonical_and_scores() -> None:
    engine = ResumeIntelligenceEngine()
    resume_text = """
    John Doe
    john@oldmail.com john@newmail.com
    +1 555-000-1000 +1 555-000-2000
    Bangalore, India

    Experience
    Senior Software Engineer at Acme (2022 - Present)
    Software Engineer at Beta Corp (2019 - 2022)
    Junior Developer at DevWorks (2017 - 2019)

    Education
    Bachelor of Technology, Example University (2013 - 2017)

    Skills: Python, FastAPI, SQL, Leadership, Communication
    """

    structured = {
        "technical_skills": ["Python", "FastAPI", "SQL", "Python"],
        "soft_skills": ["Leadership", "Communication"],
        "education": [
            {
                "degree": "Bachelor of Technology",
                "institution": "Example University",
                "start_year": "2013",
                "end_year": "2017",
            }
        ],
        "experience": [
            {
                "title": "Senior Software Engineer",
                "company": "Acme",
                "start_year": "2022",
                "end_year": "Present",
                "description": "Platform and API ownership",
            },
            {
                "title": "Software Engineer",
                "company": "Beta Corp",
                "start_year": "2019",
                "end_year": "2022",
                "description": "Backend development",
            },
            {
                "title": "Junior Developer",
                "company": "DevWorks",
                "start_year": "2017",
                "end_year": "2019",
                "description": "Internal tools",
            },
        ],
        "certifications": ["AWS Certified Developer"],
        "projects": [{"name": "Recruitment Copilot", "description": "AI hiring workflow", "technologies": ["Python", "FastAPI"]}],
    }

    result = engine.build_intelligence(resume_text=resume_text, structured=structured, summary="Experienced backend engineer")

    canonical = result["canonical"]
    assert canonical["skills"]["technical"] == ["Python", "FastAPI", "SQL"]
    assert canonical["basics"]["email"] == "john@oldmail.com"

    inconsistencies = result["inconsistencies"]
    assert any(item["issue"] == "multiple_emails_detected" for item in inconsistencies)
    assert any(item["issue"] == "multiple_phones_detected" for item in inconsistencies)

    confidences = result["field_confidence_scores"]
    assert 0.0 <= confidences["experience"] <= 1.0
    assert 0.0 <= confidences["technical_skills"] <= 1.0

    employment = result["employment_analysis"]
    assert employment["gaps"] == []
    assert employment["total_experience_years"] >= 7.0

    progression = result["career_progression"]
    assert progression["progression_score"] > 0.0
    assert progression["trend"] in {"strong_upward", "steady", "mixed", "flat_or_downward"}

    ats = result["ats_compatibility_score"]
    assert 0 <= ats["score"] <= 100
    assert ats["rating"] in {"excellent", "strong", "moderate", "needs_improvement"}


def test_resume_intelligence_detects_timeline_conflicts_and_gaps() -> None:
    engine = ResumeIntelligenceEngine()
    structured = {
        "technical_skills": ["Python"],
        "soft_skills": [],
        "education": [
            {
                "degree": "BSc Computer Science",
                "institution": "Example College",
                "start_year": "2018",
                "end_year": "2016",
            }
        ],
        "experience": [
            {
                "title": "Engineer",
                "company": "Acme",
                "start_year": "2021",
                "end_year": "2020",
            },
            {
                "title": "Intern",
                "company": "Beta",
                "start_year": "2017",
                "end_year": "2018",
            },
        ],
        "certifications": [],
        "projects": [],
    }

    result = engine.build_intelligence(resume_text="candidate@example.com", structured=structured)
    issues = result["inconsistencies"]

    assert any(item["field"].startswith("education") and item["issue"] == "start_after_end" for item in issues)
    assert any(item["field"].startswith("experience") and item["issue"] == "start_after_end" for item in issues)

    gaps = result["employment_analysis"]["gaps"]
    assert len(gaps) >= 1
