from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .git_integration import GitSnapshot
from .github_integration import GitHubEvent
from .models import PetState


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def update_from_time(pet: PetState) -> None:
    now = datetime.now()
    last = datetime.fromisoformat(pet.last_updated)
    minutes_passed = (now - last).total_seconds() / 60

    if minutes_passed < 1:
        return

    decay = int(minutes_passed * 0.8)
    pet.hunger = clamp(pet.hunger + decay)
    pet.energy = clamp(pet.energy + decay)
    pet.mood = clamp(pet.mood + decay // 2)
    pet.health = clamp(pet.health - decay // 3)
    pet.last_updated = now.isoformat()


def feed(pet: PetState, amount: int = 15) -> str:
    pet.hunger = clamp(pet.hunger - amount)
    message = f"Fed {amount}"
    pet.add_event(message)
    check_achievements(pet)
    return message


def play(pet: PetState, amount: int = 15) -> str:
    pet.mood = clamp(pet.mood - amount)
    pet.energy = clamp(pet.energy - 5)
    message = "Played"
    pet.add_event(message)
    check_achievements(pet)
    return message


def sleep(pet: PetState) -> str:
    pet.energy = clamp(pet.energy - 40)
    message = "The pet slept well"
    pet.add_event(message)
    check_achievements(pet)
    return message


def clean(pet: PetState) -> str:
    pet.health = clamp(pet.health + 10)
    message = "Repository cleaned"
    pet.add_event(message)
    check_achievements(pet)
    return message


def apply_git_snapshot(pet: PetState, snapshot: GitSnapshot) -> list[str]:
    if not snapshot.is_repo:
        message = snapshot.error or "This directory is not a git repository"
        pet.add_event(message)
        return [message]

    repo_key = snapshot.repo_root or "."
    previous = pet.git_repos.get(repo_key, {})
    messages: list[str] = []

    is_first_scan = "last_commit_hash" not in previous

    if is_first_scan:
        messages.append("Git repository baseline saved")
    elif snapshot.last_commit_hash and previous.get("last_commit_hash") != snapshot.last_commit_hash:
        pet.hunger = clamp(pet.hunger - 20)
        pet.mood = clamp(pet.mood - 10)
        messages.append(f"New local commit detected on {snapshot.branch or 'unknown branch'}")

    if snapshot.is_dirty:
        pet.mood = clamp(pet.mood + 5)
        messages.append("Working tree has uncommitted changes")

    if snapshot.unpushed_commits > 0:
        pet.mood = clamp(pet.mood + min(15, snapshot.unpushed_commits * 3))
        messages.append(f"{snapshot.unpushed_commits} local commit(s) are not pushed")

    if snapshot.unpulled_commits > 0:
        pet.energy = clamp(pet.energy + min(15, snapshot.unpulled_commits * 3))
        messages.append(f"{snapshot.unpulled_commits} remote commit(s) are not pulled")

    if not snapshot.upstream_available:
        messages.append("No upstream branch is configured")

    if not messages:
        pet.health = clamp(pet.health + 3)
        messages.append("Git repository looks clean")

    pet.git_repos[repo_key] = {
        "branch": snapshot.branch,
        "last_commit_hash": snapshot.last_commit_hash,
        "last_scanned_at": datetime.now().isoformat(),
    }

    for message in messages:
        pet.add_event(message)
    check_achievements(pet)
    return messages


def apply_github_event(pet: PetState, event: GitHubEvent) -> list[str]:
    if event.ignored:
        pet.add_event(event.message)
        return [event.message]

    if event.type == "push":
        commit_count = max(0, event.count)
        pet.hunger = clamp(pet.hunger - min(25, commit_count * 5))
        pet.mood = clamp(pet.mood - min(15, commit_count * 3))
    elif event.type == "pr_merged":
        pet.health = clamp(pet.health + 15)
        pet.energy = clamp(pet.energy - 5)
    elif event.type == "issue_closed":
        pet.mood = clamp(pet.mood - 15)
        pet.hunger = clamp(pet.hunger - 5)
    elif event.type == "ci_success":
        pet.health = clamp(pet.health + 10)
    elif event.type == "ci_failed":
        pet.health = clamp(pet.health - 20)
        pet.mood = clamp(pet.mood + 10)

    pet.add_event(event.message)
    check_achievements(pet)
    return [event.message]


def check_achievements(pet: PetState) -> None:
    new_achievements = []
    logs = "\n".join(pet.events_log).lower()

    if "First Commit" not in pet.achievements and "commit" in logs:
        new_achievements.append("First Commit")
    if "Healthy Repo" not in pet.achievements and pet.health >= 80:
        new_achievements.append("Healthy Repo")
    if "Happy Pet" not in pet.achievements and pet.mood <= 30:
        new_achievements.append("Happy Pet")
    if "CI Hero" not in pet.achievements and "ci" in logs:
        new_achievements.append("CI Hero")

    for achievement in new_achievements:
        pet.achievements.append(achievement)
        pet.add_event(f"Got achievement: {achievement}")


def summarize_messages(messages: Iterable[str]) -> str:
    return "\n".join(f"- {message}" for message in messages)
