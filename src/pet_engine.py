"""
Core game logic — stat decay, events, streak, quests.

Key architectural rule (VPS vs local):
  - Webhook server calls apply_github_event()  → modifies stats, streak, quest, achievements
  - Local CLI calls apply_git_snapshot()        → updates git_repos metadata ONLY (no stat changes)
  - update_from_time()                          → decay, runs both locally and on VPS
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Iterable

from .git_integration import GitSnapshot
from .github_integration import GitHubEvent
from .models import PetState, TEAM_QUESTS


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ── Decay rates ────────────────────────────────────────────────────────────────
# Without any activity the pet survives roughly:
#   hunger  ~5 days,  energy  ~8 days,  mood  ~12 days
_HUNGER_DECAY   = 80.0 / (5 * 24 * 60)
_ENERGY_DECAY   = 80.0 / (8 * 24 * 60)
_MOOD_DECAY     = 80.0 / (12 * 24 * 60)
_HEALTH_RECOVER = 80.0 / (20 * 24 * 60)
_HEALTH_DECAY   = 80.0 / (3 * 24 * 60)

# Additional mood penalty per minute while a repo is dirty (after 2h grace period).
_DIRTY_MOOD_RATE = 0.5 / 60.0


def update_from_time(pet: PetState) -> None:
    """Apply time-based stat decay. Safe to call on dead pets (no-op except timestamp)."""
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
        pet.add_event("Pet died — health reached zero from neglect")


# ── Streak ─────────────────────────────────────────────────────────────────────

def update_streak(pet: PetState) -> None:
    """Increment streak on first positive event per day. Called on VPS only."""
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
        pet.add_event(f"Team streak: {pet.streak_days} days in a row!")
    pet.check_achievements()


# ── Daily quest (server-side only) ────────────────────────────────────────────

def refresh_daily_quest(pet: PetState, context: dict | None = None) -> None:
    """Generate a new team quest for today if one hasn't been set yet.

    context (from GitHub API) can filter out quests that don't make sense,
    e.g. "close 3 issues" won't be assigned if there are fewer than 3 open issues.

    Should only be called inside the webhook handler (VPS side).
    """
    if not pet.alive:
        return
    today = date.today().isoformat()
    if pet.daily_quest_date == today:
        return   # quest already set for today

    # Reset daily counters when a new day starts
    pet.daily_commit_count = 0
    pet.daily_issue_count  = 0
    pet.daily_pr_count     = 0
    pet.ci_failed_today    = False
    pet.daily_quest_done   = False

    # Build candidate list (filter contextual quests by repo state)
    candidates = []
    for q in TEAM_QUESTS:
        if not q["contextual"]:
            candidates.append(q)
            continue
        if context is None:
            continue  # skip contextual quests when we have no API data
        if q["id"] == "issues_3" and context.get("open_issues", 0) >= 3:
            candidates.append(q)
        elif q["id"] == "prs_2" and context.get("open_prs", 0) >= 2:
            candidates.append(q)
        elif q["id"] == "ci_fix" and context.get("ci_failing", False):
            candidates.append(q)

    if not candidates:
        candidates = [q for q in TEAM_QUESTS if not q["contextual"]]

    chosen = random.choice(candidates)
    pet.daily_quest_id        = chosen["id"]
    pet.daily_quest_text      = chosen["text"]
    pet.daily_quest_trigger   = chosen["trigger"]
    pet.daily_quest_threshold = chosen["threshold"]
    pet.daily_quest_date      = today
    pet.add_event(f"Team quest: {chosen['text']}")


def update_quest_progress(pet: PetState, trigger: str, count: int = 1) -> bool:
    """Advance quest progress counter. Returns True when quest is just completed.

    Called inside apply_github_event() on VPS for each relevant event.
    """
    today = date.today().isoformat()
    if (
        pet.daily_quest_done
        or not pet.daily_quest_trigger
        or pet.daily_quest_date != today
    ):
        return False

    if pet.daily_quest_trigger != trigger:
        return False

    # Update the relevant daily counter
    if trigger == "commit_count":
        pet.daily_commit_count += count
        current = pet.daily_commit_count
    elif trigger == "issue_count":
        pet.daily_issue_count += count
        current = pet.daily_issue_count
    elif trigger == "pr_count":
        pet.daily_pr_count += count
        current = pet.daily_pr_count
    elif trigger == "ci_fixed":
        # Quest "fix CI" completes only if CI was broken today and now passes
        current = 1 if pet.ci_failed_today else 0
    else:
        return False

    if current >= pet.daily_quest_threshold:
        pet.daily_quest_done = True
        pet.quests_completed += 1
        # Quest reward: significant boost to all three main stats
        pet.mood   = _clamp(pet.mood   + 25.0)
        pet.hunger = _clamp(pet.hunger + 15.0)
        pet.energy = _clamp(pet.energy + 10.0)
        pet.add_event(f"Team quest complete: {pet.daily_quest_text}! +Mood +Hunger +Energy")
        pet.check_achievements()
        return True

    pet.add_event(f"Quest progress: {current}/{pet.daily_quest_threshold} — {pet.daily_quest_text}")
    return False


# ── Local git scan (metadata only) ────────────────────────────────────────────

def apply_git_snapshot(pet: PetState, snapshot: GitSnapshot) -> list[str]:
    """Update git_repos metadata from a local repo scan.

    IMPORTANT: In team mode this function ONLY writes to pet.git_repos.
    It does NOT change hunger/energy/mood/streak — those are the webhook's job.
    The dirty_since timestamp stored here feeds the decay penalty in update_from_time().
    """
    if not snapshot.is_repo:
        return [snapshot.error or "Not inside a git repository"]

    repo_key  = snapshot.repo_root or "."
    prev      = pet.git_repos.get(repo_key, {})
    messages: list[str] = []
    now_iso   = datetime.now().isoformat()
    first_scan = "last_commit_hash" not in prev

    if first_scan:
        messages.append(f"Repo baseline saved: '{repo_key}'")
    elif snapshot.last_commit_hash and prev.get("last_commit_hash") != snapshot.last_commit_hash:
        messages.append(f"New commit detected on '{snapshot.branch}' (stat changes via webhook)")

    # Dirty tracking: store when the repo became dirty (for decay penalty)
    if snapshot.is_dirty:
        dirty_since = prev.get("dirty_since") or now_iso   # keep start time
        messages.append("Uncommitted changes detected")
    else:
        dirty_since = ""   # repo clean, reset the timer
        if prev.get("is_dirty"):
            messages.append("Repository cleaned")

    if snapshot.unpushed_commits > 0:
        messages.append(f"{snapshot.unpushed_commits} commit(s) not pushed yet")
    if snapshot.unpulled_commits > 0:
        messages.append(f"{snapshot.unpulled_commits} remote commit(s) not pulled")
    if not snapshot.upstream_available:
        messages.append("No upstream branch configured")
    if not messages:
        messages.append("Repository is clean")

    # Write metadata — this is the ONLY state change scan is allowed to make
    pet.git_repos[repo_key] = {
        "branch":           snapshot.branch,
        "last_commit_hash": snapshot.last_commit_hash,
        "last_commit_subj": snapshot.last_commit_subject or "",
        "last_scanned_at":  now_iso,
        "is_dirty":         snapshot.is_dirty,
        "dirty_since":      dirty_since,
        "unpushed":         snapshot.unpushed_commits or 0,
        "unpulled":         snapshot.unpulled_commits or 0,
    }
    return messages


# ── GitHub webhook events (VPS only) ──────────────────────────────────────────

def apply_github_event(pet: PetState, event: GitHubEvent) -> list[str]:
    """Apply a GitHub webhook event to pet state.

    This is the ONLY place that modifies hunger/energy/mood/health/streak/achievements.
    It runs inside the webhook server — never locally.
    """
    if event.ignored:
        pet.add_event(event.message)
        return [event.message]

    # Ghost mode: only track cooldown progress, no stat changes
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
            msgs.append("Cooldown complete — auto-init in progress")
        return msgs

    # Active pet: apply stat effects and quest progress
    now_iso = datetime.now().isoformat()

    if event.type == "push":
        count = max(1, event.count)
        pet.hunger = _clamp(pet.hunger + min(25.0, count * 5.0))
        pet.mood   = _clamp(pet.mood   + min(15.0, count * 3.0))
        update_streak(pet)
        update_quest_progress(pet, "commit_count", count)
        if event.contributor:
            pet.last_fed_by  = event.contributor
            pet.last_fed_at  = now_iso
            pet.last_activity_at = now_iso

    elif event.type == "pr_merged":
        pet.health = _clamp(pet.health + 15.0)
        pet.energy = _clamp(pet.energy + 10.0)
        pet.mood   = _clamp(pet.mood   + 10.0)
        update_quest_progress(pet, "pr_count", 1)
        if event.contributor:
            pet.last_fed_by = event.contributor
            pet.last_fed_at = now_iso
            pet.last_activity_at = now_iso

    elif event.type == "issue_closed":
        pet.mood   = _clamp(pet.mood   + 15.0)
        pet.hunger = _clamp(pet.hunger +  5.0)
        update_quest_progress(pet, "issue_count", 1)
        if event.contributor:
            pet.last_activity_at = now_iso

    elif event.type == "ci_success":
        pet.health = _clamp(pet.health + 10.0)
        pet.energy = _clamp(pet.energy +  5.0)
        update_quest_progress(pet, "ci_fixed", 1)   # only completes "fix CI" if ci_failed_today=True
        pet.last_activity_at = now_iso

    elif event.type == "ci_failed":
        pet.health = _clamp(pet.health - 20.0)
        pet.energy = _clamp(pet.energy - 10.0)
        pet.ci_failed_today = True   # enables the "fix CI" quest trigger for ci_success

    pet.add_event(event.message)
    pet.check_achievements()
    return [event.message]


def summarize_messages(messages: Iterable[str]) -> str:
    return "\n".join(f"  - {m}" for m in messages)
