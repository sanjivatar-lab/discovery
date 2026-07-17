"""Ingests a codebase from either an uploaded ZIP or a git URL into a
per-analysis working directory the supervisor can scan for .java files."""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


def extract_zip(zip_path: Path, dest_root: Path) -> Path:
    target = dest_root / "src"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)
    return target


def clone_git_repo(git_url: str, dest_root: Path, branch: Optional[str] = None) -> Path:
    target = dest_root / "src"
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [git_url, str(target)]
    logger.info("cloning git repo into %s", target)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")
    return target
