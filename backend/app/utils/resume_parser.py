from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


class ResumeParser:
    """Foundational resume parser for structured candidate extraction.

    The parser is designed for future AI integration by exposing a consistent
    text extraction pipeline before applying rule-based enrichment.
    """

    def __init__(self) -> None:
        self.skills_keywords = [
            "python",
            "java",
            "javascript",
            "typescript",
            "sql",
            "postgresql",
            "fastapi",
            "docker",
            "kubernetes",
            "aws",
            "azure",
            "machine learning",
            "ai",
            "react",
            "node",
            "devops",
            "microservices",
        ]

    def parse_file(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {path}")

        text = self.extract_text(path)
        parsed = self.parse(text)
        parsed.update(
            {
                "file_path": str(path),
                "source_format": path.suffix.lower().lstrip("."),
                "ready_for_ai": True,
            }
        )
        return parsed

    def extract_text(self, file_path: str | Path) -> str:
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_text_from_pdf(path)
        if suffix in {".docx", ".doc"}:
            return self._extract_text_from_docx(path)
        if suffix in {".txt", ".text"}:
            return path.read_text(encoding="utf-8", errors="ignore")

        raise ValueError(f"Unsupported resume format: {suffix}")

    def parse(self, text: str) -> dict[str, Any]:
        normalized_text = text.lower()
        skills = self._extract_skills(normalized_text)
        education = self._extract_education(text)
        experience = self._extract_experience(text)

        return {
            "skills": ", ".join(skills),
            "education": education,
            "experience": experience,
            "raw_text": text,
        }

    def _extract_text_from_pdf(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def _extract_text_from_docx(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                with archive.open("word/document.xml") as document_file:
                    tree = ET.parse(document_file)
        except (KeyError, zipfile.BadZipFile, ET.ParseError):
            return ""

        root = tree.getroot()
        namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespaces):
            texts = [node.text or "" for node in paragraph.findall(".//w:t", namespaces)]
            paragraph_text = "".join(texts).strip()
            if paragraph_text:
                paragraphs.append(paragraph_text)

        return "\n".join(paragraphs)

    def _extract_skills(self, text: str) -> list[str]:
        found_skills: list[str] = []
        for skill in self.skills_keywords:
            if re.search(rf"\b{re.escape(skill)}\b", text):
                found_skills.append(skill)
        return found_skills

    def _extract_education(self, text: str) -> list[str]:
        patterns = [
            r"bsc(?:\.?|\s)",
            r"ba(?:\.?|\s)",
            r"master(?:'s)?",
            r"phd",
            r"bachelor(?:'s)?",
            r"university",
            r"college",
        ]
        matches = []
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(pattern)
        return matches

    def _extract_experience(self, text: str) -> list[str]:
        patterns = [
            r"\b\d+\s+years?\s+of\s+experience\b",
            r"\bsenior\b",
            r"\blead\b",
            r"\bmanager\b",
            r"\bengineer\b",
            r"\bdeveloper\b",
        ]
        matches = []
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(pattern)
        return matches
