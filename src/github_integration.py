from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GitHubEvent:
    type: str           # "push", "pr_merged", "issue_closed", "ci_success", "ci_failed", "ignored"
    message: str
    count: int = 1      # кол-во коммитов (для push-событий)
    ignored: bool = False
    contributor: str = ""   # GitHub username того, кто сделал действие


def parse_github_webhook(event_name: str, payload: dict[str, Any]) -> GitHubEvent:
    """Парсим сырой payload от GitHub в удобный GitHubEvent.

    GitHub всегда кладёт отправителя в 'sender.login'.
    Нас интересуют только push, PR, issues и workflow_run.
    Всё остальное игнорируем.
    """
    contributor = payload.get("sender", {}).get("login", "someone")

    if event_name == "push":
        commits = payload.get("commits") or []
        count  = len(commits)
        branch = payload.get("ref", "").replace("refs/heads/", "")
        msg = f"{contributor} pushed {count} commit(s) to '{branch}'"
        return GitHubEvent(type="push", message=msg, count=count, contributor=contributor)

    if event_name == "pull_request":
        action = payload.get("action", "")
        pr     = payload.get("pull_request") or {}
        title  = pr.get("title", "PR")
        if action == "closed" and pr.get("merged"):
            msg = f"{contributor} merged PR: \"{title}\""
            return GitHubEvent(type="pr_merged", message=msg, contributor=contributor)
        msg = f"{contributor}: PR activity ({action})"
        return GitHubEvent(type="pr_activity", message=msg, ignored=True, contributor=contributor)

    if event_name == "issues":
        action = payload.get("action", "")
        issue  = payload.get("issue") or {}
        title  = issue.get("title", "issue")
        if action == "closed":
            msg = f"{contributor} closed issue: \"{title}\""
            return GitHubEvent(type="issue_closed", message=msg, contributor=contributor)
        msg = f"{contributor}: issue activity ({action})"
        return GitHubEvent(type="issue_activity", message=msg, ignored=True, contributor=contributor)

    if event_name == "workflow_run":
        action = payload.get("action", "")
        run    = payload.get("workflow_run") or {}
        name   = run.get("name", "workflow")
        conclusion = run.get("conclusion", "unknown")
        if action == "completed":
            if conclusion == "success":
                msg = f"CI '{name}' passed (triggered by {contributor})"
                return GitHubEvent(type="ci_success", message=msg, contributor=contributor)
            msg = f"CI '{name}' failed — {conclusion} (triggered by {contributor})"
            return GitHubEvent(type="ci_failed", message=msg, contributor=contributor)

    # Ping приходит при первом подключении webhook — просто подтверждаем
    if event_name == "ping":
        return GitHubEvent(
            type="ping",
            message="Webhook connected — TamaGit is watching!",
            ignored=True,
        )

    return GitHubEvent(
        type="ignored",
        message=f"Event '{event_name}' by {contributor} — ignored",
        ignored=True,
        contributor=contributor,
    )
