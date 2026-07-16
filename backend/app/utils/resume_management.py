from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.utils.storage import save_resume_file


class ResumeManager:
    """Simple modular resume manager for candidate resume lifecycle operations."""

    def upload_resume(self, file: UploadFile) -> dict[str, Any]:
        stored_path = save_resume_file(file)
        return {
            "path": stored_path,
            "filename": Path(stored_path).name,
            "status": "uploaded",
        }

    def download_resume(self, resume_path: str) -> str:
        return resume_path

    def update_resume(self, current_path: str, file: UploadFile) -> dict[str, Any]:
        stored_path = save_resume_file(file)
        return {
            "previous_path": current_path,
            "path": stored_path,
            "filename": Path(stored_path).name,
            "status": "updated",
        }

    def delete_resume(self, resume_path: str) -> dict[str, Any]:
        path = Path(resume_path)
        if path.exists():
            path.unlink()

        return {
            "path": resume_path,
            "status": "deleted",
        }
