from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GitHubEvent:
    type: str
    message: str
    count: int = 1
    conclusion: str | None = None
    ignored: bool = False


def parse_github_webhook(event_name: str, payload: dict[str, Any]) -> GitHubEvent:
    if event_name == "push":
        commits = payload.get("commits") or []
        count = len(commits)
        return GitHubEvent(
            type="push",
            message=f"GitHub push received with {count} commit(s)",
            count=count,
        )

    if event_name == "pull_request":
        action = payload.get("action")
        pull_request = payload.get("pull_request") or {}
        if action == "closed" and pull_request.get("merged"):
            return GitHubEvent(type="pr_merged", message="GitHub pull request merged")
        return GitHubEvent(
            type="pr_activity",
            message=f"GitHub pull request activity: {action or 'unknown'}",
            ignored=True,
        )

    if event_name == "issues":
        action = payload.get("action")
        if action == "closed":
            return GitHubEvent(type="issue_closed", message="GitHub issue closed")
        return GitHubEvent(
            type="issue_activity",
            message=f"GitHub issue activity: {action or 'unknown'}",
            ignored=True,
        )

    if event_name == "workflow_run":
        action = payload.get("action")
        workflow_run = payload.get("workflow_run") or {}
        if action == "completed":
            conclusion = workflow_run.get("conclusion") or "unknown"
            if conclusion == "success":
                return GitHubEvent(
                    type="ci_success",
                    message="GitHub workflow completed successfully",
                    conclusion=conclusion,
                )
            return GitHubEvent(
                type="ci_failed",
                message=f"GitHub workflow completed with conclusion: {conclusion}",
                conclusion=conclusion,
            )

    return GitHubEvent(
        type="ignored",
        message=f"GitHub event ignored: {event_name}",
        ignored=True,
    )
