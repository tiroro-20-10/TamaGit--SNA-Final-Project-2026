from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Iterable

from .git_integration import GitSnapshot
from .github_integration import GitHubEvent
from .models import PetState


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ── Скорость деградации ───────────────────────────────────────────────────────
# Без активности питомец выживает:
#   hunger — ~5 дней, energy — ~8 дней, mood — ~12 дней
_HUNGER_DECAY = 80.0 / (5 * 24 * 60)
_ENERGY_DECAY = 80.0 / (8 * 24 * 60)
_MOOD_DECAY   = 80.0 / (12 * 24 * 60)
_HEALTH_RECOVER = 80.0 / (20 * 24 * 60)   # медленное восстановление
_HEALTH_DECAY   = 80.0 / (3 * 24 * 60)    # быстрое падение при плохих статах


# ── Daily quests ──────────────────────────────────────────────────────────────
DAILY_QUESTS = [
    ("Push your latest changes to remote",  "git_push"),
    ("Make at least 1 new commit",          "git_commit"),
    ("Pull the latest changes from remote", "git_pull"),
    ("Close an open GitHub issue",          "issue_closed"),
    ("Get the CI pipeline green",           "ci_success"),
    ("Merge an open pull request",          "pr_merged"),
]


def update_from_time(pet: PetState) -> None:
    """Применяет decay по прошедшему времени. Вызывается при каждой загрузке."""
    if not pet.alive:
        pet.last_updated = datetime.now().isoformat()
        return

    now = datetime.now()
    try:
        last = datetime.fromisoformat(pet.last_updated)
    except (ValueError, TypeError):
        last = now

    minutes = (now - last).total_seconds() / 60
    if minutes < 1:
        return

    pet.hunger = _clamp(pet.hunger - minutes * _HUNGER_DECAY)
    pet.energy = _clamp(pet.energy - minutes * _ENERGY_DECAY)
    pet.mood   = _clamp(pet.mood   - minutes * _MOOD_DECAY)

    avg = (pet.hunger + pet.energy + pet.mood) / 3
    if avg >= 60:
        pet.health = _clamp(pet.health + minutes * _HEALTH_RECOVER)
    elif avg < 30:
        pet.health = _clamp(pet.health - minutes * _HEALTH_DECAY)

    pet.last_updated = now.isoformat()

    if pet.health <= 0:
        pet.alive = False
        pet.add_event("💀 Pet died — stats drained from inactivity")


def update_streak(pet: PetState) -> None:
    """Обновляет streak при позитивном событии (push/commit).

    Если сегодня уже был streak — не увеличиваем (один раз в день).
    Если вчера — инкремент. Если пропустили день — сброс.
    """
    today     = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    if pet.last_streak_date == today:
        return

    if pet.last_streak_date == yesterday:
        pet.streak_days += 1
    else:
        if pet.streak_days > 1 and pet.last_streak_date:
            pet.add_event(f"Streak of {pet.streak_days} day(s) broken — reset to 1")
        pet.streak_days = 1

    pet.last_streak_date = today
    if pet.streak_days > 1:
        pet.add_event(f"🔥 Streak: {pet.streak_days} days in a row!")
    pet.check_achievements()


def get_or_refresh_daily_quest(pet: PetState) -> None:
    """Генерирует новый квест на сегодня если его ещё нет."""
    if not pet.alive:
        return
    if pet.daily_quest_date == date.today().isoformat():
        return
    text, trigger = random.choice(DAILY_QUESTS)
    pet.daily_quest_text    = text
    pet.daily_quest_trigger = trigger
    pet.daily_quest_date    = date.today().isoformat()
    pet.daily_quest_done    = False
    pet.add_event(f"🎯 New daily quest: {text}")


def try_complete_quest(pet: PetState, trigger: str) -> bool:
    """Проверяет выполнение квеста по триггеру. True если только что выполнили."""
    if (
        pet.daily_quest_done
        or pet.daily_quest_trigger != trigger
        or pet.daily_quest_date != date.today().isoformat()
    ):
        return False

    pet.daily_quest_done = True
    pet.quests_completed += 1
    pet.mood   = _clamp(pet.mood   + 20.0)
    pet.hunger = _clamp(pet.hunger + 10.0)
    pet.add_event(f"🎯 Quest done: {pet.daily_quest_text} (+Mood +Hunger)")
    pet.check_achievements()
    return True


def apply_git_snapshot(pet: PetState, snapshot: GitSnapshot) -> list[str]:
    """Реагирует на результат сканирования локального репозитория."""

    if not pet.alive:
        msgs = ["Ghost mode: git activity noted toward resurrection"]
        if snapshot.is_repo and snapshot.last_commit_hash:
            repo_key = snapshot.repo_root or "."
            prev = pet.git_repos.get(repo_key, {})
            if prev.get("last_commit_hash") != snapshot.last_commit_hash:
                pet.cooldown_commits = min(3, pet.cooldown_commits + 1)
                msgs.append(f"Cooldown commits: {pet.cooldown_commits}/3")
                pet.git_repos[repo_key] = {"last_commit_hash": snapshot.last_commit_hash}
        if pet.cooldown_done:
            msgs.append("All cooldown tasks done! Run: tamagit init")
        return msgs

    if not snapshot.is_repo:
        msg = snapshot.error or "Not inside a git repository"
        pet.add_event(msg)
        return [msg]

    repo_key  = snapshot.repo_root or "."
    prev      = pet.git_repos.get(repo_key, {})
    messages: list[str] = []
    first_scan = "last_commit_hash" not in prev

    if first_scan:
        messages.append(f"Baseline saved for '{repo_key}'")
    elif snapshot.last_commit_hash and prev.get("last_commit_hash") != snapshot.last_commit_hash:
        pet.hunger = _clamp(pet.hunger + 20.0)
        pet.mood   = _clamp(pet.mood   + 10.0)
        messages.append(f"New commit on '{snapshot.branch}' — nom nom!")
        update_streak(pet)
        try_complete_quest(pet, "git_commit")
        pet.last_activity_at = datetime.now().isoformat()

    if snapshot.is_dirty:
        pet.mood = _clamp(pet.mood - 5.0)
        messages.append("Uncommitted changes — pet is uneasy")

    if snapshot.unpushed_commits > 0:
        pet.energy = _clamp(pet.energy - min(15.0, snapshot.unpushed_commits * 3.0))
        messages.append(f"{snapshot.unpushed_commits} commit(s) not pushed — pet feels stuck")

    if snapshot.unpulled_commits > 0:
        pet.hunger = _clamp(pet.hunger - min(10.0, snapshot.unpulled_commits * 2.0))
        messages.append(f"{snapshot.unpulled_commits} remote commit(s) not pulled")

    if not snapshot.upstream_available:
        messages.append("No upstream branch configured")

    if not messages:
        pet.health = _clamp(pet.health + 3.0)
        messages.append("Repository is clean — pet is pleased")

    # Сохраняем все параметры репо для отображения в status
    pet.git_repos[repo_key] = {
        "branch":           snapshot.branch,
        "last_commit_hash": snapshot.last_commit_hash,
        "last_commit_subj": snapshot.last_commit_subject or "",
        "last_scanned_at":  datetime.now().isoformat(),
        "is_dirty":         snapshot.is_dirty,
        "unpushed":         snapshot.unpushed_commits,
        "unpulled":         snapshot.unpulled_commits,
    }

    for msg in messages:
        pet.add_event(msg)
    pet.check_achievements()
    return messages


def apply_github_event(pet: PetState, event: GitHubEvent) -> list[str]:
    """Применяет событие GitHub webhook к состоянию питомца."""

    if event.ignored:
        pet.add_event(event.message)
        return [event.message]

    # Ghost-режим: считаем cooldown прогресс
    if not pet.alive:
        msgs = [event.message, "Ghost mode: activity counted toward resurrection"]
        if event.type == "push":
            pet.cooldown_commits = min(3, pet.cooldown_commits + max(1, event.count))
            msgs.append(f"Cooldown commits: {pet.cooldown_commits}/3")
        elif event.type == "issue_closed":
            pet.cooldown_issues = min(1, pet.cooldown_issues + 1)
            msgs.append(f"Cooldown issues: {pet.cooldown_issues}/1")
        elif event.type == "ci_success":
            pet.cooldown_ci_ok = min(1, pet.cooldown_ci_ok + 1)
            msgs.append(f"Cooldown CI: {pet.cooldown_ci_ok}/1")
        pet.add_event(event.message)
        if pet.cooldown_done:
            msgs.append("All cooldown tasks done! Run: tamagit init")
        return msgs

    # Нормальный режим
    if event.type == "push":
        count = max(1, event.count)
        pet.hunger = _clamp(pet.hunger + min(25.0, count * 5.0))
        pet.mood   = _clamp(pet.mood   + min(15.0, count * 3.0))
        update_streak(pet)
        try_complete_quest(pet, "git_push")
        if event.contributor:
            pet.last_fed_by = event.contributor
            pet.last_fed_at = datetime.now().isoformat()
            pet.last_activity_at = datetime.now().isoformat()

    elif event.type == "pr_merged":
        pet.health = _clamp(pet.health + 15.0)
        pet.energy = _clamp(pet.energy + 10.0)
        pet.mood   = _clamp(pet.mood   + 10.0)
        try_complete_quest(pet, "pr_merged")
        if event.contributor:
            pet.last_fed_by = event.contributor
            pet.last_fed_at = datetime.now().isoformat()
            pet.last_activity_at = datetime.now().isoformat()

    elif event.type == "issue_closed":
        pet.mood   = _clamp(pet.mood   + 15.0)
        pet.hunger = _clamp(pet.hunger +  5.0)
        try_complete_quest(pet, "issue_closed")
        if event.contributor:
            pet.last_activity_at = datetime.now().isoformat()

    elif event.type == "ci_success":
        pet.health = _clamp(pet.health + 10.0)
        pet.energy = _clamp(pet.energy +  5.0)
        try_complete_quest(pet, "ci_success")
        pet.last_activity_at = datetime.now().isoformat()

    elif event.type == "ci_failed":
        pet.health = _clamp(pet.health - 20.0)
        pet.energy = _clamp(pet.energy - 10.0)

    pet.add_event(event.message)
    pet.check_achievements()
    return [event.message]


def summarize_messages(messages: Iterable[str]) -> str:
    return "\n".join(f"  - {m}" for m in messages)
