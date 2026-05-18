"""
GitHub API wrapper — stdlib only (no extra dependencies).

All functions return parsed JSON or raise GithubAPIError.
The token is passed explicitly so this module has no side effects.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


class GithubAPIError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"GitHub API {status}: {message}")


_BASE = "https://api.github.com"


def _request(method: str, path: str, token: str, body: dict | None = None) -> Any:
    url = f"{_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "TamaGit/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode()
        raise GithubAPIError(exc.code, msg) from exc


def get_repo(owner: str, repo: str, token: str) -> dict:
    """Basic repo info: pushed_at, open_issues_count, description."""
    return _request("GET", f"/repos/{owner}/{repo}", token)


def get_latest_ci_run(owner: str, repo: str, token: str) -> dict | None:
    """Latest workflow run (for CI status check)."""
    data = _request("GET", f"/repos/{owner}/{repo}/actions/runs?per_page=1", token)
    runs = data.get("workflow_runs", [])
    return runs[0] if runs else None


def get_open_issues(owner: str, repo: str, token: str) -> list[dict]:
    """Open issues (excludes PRs). Max 30 returned."""
    return _request("GET", f"/repos/{owner}/{repo}/issues?state=open&per_page=30", token)


def get_open_prs(owner: str, repo: str, token: str) -> list[dict]:
    """Open pull requests. Max 30 returned."""
    return _request("GET", f"/repos/{owner}/{repo}/pulls?state=open&per_page=30", token)


def create_webhook(
    owner: str, repo: str, token: str, webhook_url: str, secret: str
) -> dict:
    """Create a GitHub webhook on the repository.

    Requires the token to have admin:repo_hook or repo scope.
    Returns the created hook object.
    """
    return _request(
        "POST",
        f"/repos/{owner}/{repo}/hooks",
        token,
        body={
            "name": "web",
            "active": True,
            "events": ["push", "pull_request", "issues", "workflow_run"],
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": secret,
            },
        },
    )


def create_issue(
    owner: str, repo: str, token: str, title: str, body: str,
    labels: list[str] | None = None,
) -> dict:
    """Open a GitHub issue (used for pet birth/death notifications)."""
    payload: dict[str, Any] = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    return _request("POST", f"/repos/{owner}/{repo}/issues", token, body=payload)


def compute_initial_stats(
    owner: str, repo: str, token: str
) -> dict[str, float]:
    """Compute realistic initial pet stats based on actual repo state.

    - hunger  reflects commit recency   (stale repo → hungry pet)
    - mood    reflects open issues load  (many issues → sad pet)
    - energy  reflects CI health         (failing CI → tired pet)
    - health  derived from the average   (overall neglect → sick pet)
    """
    stats = {"hunger": 80.0, "energy": 80.0, "mood": 80.0, "health": 100.0}

    try:
        repo_info = get_repo(owner, repo, token)

        # Days since last push → affects hunger
        pushed_at = repo_info.get("pushed_at", "")
        if pushed_at:
            dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - dt).days
            # 0 days → 80, 5 days → 40, 10 days → 0
            stats["hunger"] = max(5.0, 80.0 - days * 8.0)

        # Open issues count → affects mood
        open_issues = repo_info.get("open_issues_count", 0)
        # 0 issues → 80, 10 issues → 60, 40 issues → ~0
        stats["mood"] = max(5.0, 80.0 - open_issues * 2.0)

        # CI status → affects energy
        run = get_latest_ci_run(owner, repo, token)
        if run:
            conclusion = run.get("conclusion")
            if conclusion == "failure":
                stats["energy"] = 35.0
            elif conclusion == "success":
                stats["energy"] = 85.0
            # None / in_progress → leave at 80

        # Health = f(average) — deliberately lower for bad repos
        avg = (stats["hunger"] + stats["energy"] + stats["mood"]) / 3
        if avg >= 60:
            stats["health"] = 100.0
        elif avg >= 40:
            stats["health"] = 70.0
        elif avg >= 20:
            stats["health"] = 40.0
        else:
            stats["health"] = 15.0   # very sick from the start

    except Exception:
        # API unavailable or token missing — use defaults, pet will adjust
        pass

    return stats
