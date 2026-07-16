from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 5 * 1024 * 1024
UPLOAD_ROOT = Path("uploads") / "resumes"


def ensure_upload_dir() -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def validate_resume_file(file: UploadFile) -> None:
    if not file.filename:
        raise ValueError("File name is required")

    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only PDF and DOCX files are supported")

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise ValueError("Unsupported file type")


def save_resume_file(file: UploadFile) -> str:
    ensure_upload_dir()
    validate_resume_file(file)

    file_bytes = file.file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("File size exceeds the 5MB limit")

    safe_name = Path(file.filename).name
    unique_name = f"{uuid4().hex}_{Path(safe_name).stem}{Path(safe_name).suffix.lower()}"
    destination_dir = UPLOAD_ROOT / "incoming"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / unique_name

    with destination.open("wb") as handle:
        handle.write(file_bytes)

    return str(destination)
