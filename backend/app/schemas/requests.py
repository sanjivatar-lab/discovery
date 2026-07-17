"""API request schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AnalyzeGitRequest(BaseModel):
    git_url: str
    branch: Optional[str] = None
