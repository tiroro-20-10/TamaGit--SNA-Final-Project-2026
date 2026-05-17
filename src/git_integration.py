from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitSnapshot:
    is_repo: bool
    repo_root: str | None = None
    branch: str | None = None
    is_dirty: bool = False
    last_commit_hash: str | None = None
    last_commit_timestamp: int | None = None
    last_commit_subject: str | None = None
    upstream_available: bool = False
    unpushed_commits: int = 0
    unpulled_commits: int = 0
    error: str | None = None


def collect_git_snapshot(cwd: str | Path = ".") -> GitSnapshot:
    workdir = Path(cwd)
    root_result = _git(["rev-parse", "--show-toplevel"], workdir)

    if root_result.returncode != 0:
        return GitSnapshot(
            is_repo=False,
            error="This directory is not inside a git repository",
        )

    repo_root = root_result.stdout.strip()
    branch = _git(["branch", "--show-current"], workdir).stdout.strip() or "HEAD"
    status = _git(["status", "--porcelain"], workdir).stdout
    last_commit = _last_commit(workdir)
    upstream_available = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], workdir).returncode == 0

    unpushed_commits = 0
    unpulled_commits = 0
    if upstream_available:
        unpushed_commits = _count_commits(["rev-list", "--count", "@{u}..HEAD"], workdir)
        unpulled_commits = _count_commits(["rev-list", "--count", "HEAD..@{u}"], workdir)

    return GitSnapshot(
        is_repo=True,
        repo_root=repo_root,
        branch=branch,
        is_dirty=bool(status.strip()),
        last_commit_hash=last_commit["hash"],
        last_commit_timestamp=last_commit["timestamp"],
        last_commit_subject=last_commit["subject"],
        upstream_available=upstream_available,
        unpushed_commits=unpushed_commits,
        unpulled_commits=unpulled_commits,
    )


def _last_commit(workdir: Path) -> dict[str, str | int | None]:
    result = _git(["log", "-1", "--format=%H%x1f%ct%x1f%s"], workdir)
    if result.returncode != 0 or not result.stdout.strip():
        return {"hash": None, "timestamp": None, "subject": None}

    commit_hash, timestamp, subject = result.stdout.strip().split("\x1f", 2)
    return {
        "hash": commit_hash,
        "timestamp": int(timestamp),
        "subject": subject,
    }


def _count_commits(args: list[str], workdir: Path) -> int:
    result = _git(args, workdir)
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def _git(args: list[str], workdir: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=workdir,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=["git", *args],
            returncode=127,
            stdout="",
            stderr="Git is not installed or is not available in PATH",
        )
