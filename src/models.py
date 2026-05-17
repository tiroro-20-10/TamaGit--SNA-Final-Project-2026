from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class PetState:
    # ── Идентификация ─────────────────────────────────────────────────────────
    name: str = "TamaGit"
    github_repo: str = ""
    born_at: str = ""
    last_updated: str = ""

    # ── Статы (float, 0 = плохо, 100 = хорошо) ───────────────────────────────
    hunger: float = 80.0
    energy: float = 80.0
    mood:   float = 80.0
    health: float = 100.0

    alive: bool = True

    # ── История ───────────────────────────────────────────────────────────────
    achievements: List[str] = field(default_factory=list)
    events_log:   List[str] = field(default_factory=list)
    git_repos:    Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # ── Командная механика ────────────────────────────────────────────────────
    last_fed_by: str = ""
    last_fed_at: str = ""

    # ── Streak ────────────────────────────────────────────────────────────────
    streak_days:      int = 0
    last_streak_date: str = ""

    # ── Сон ───────────────────────────────────────────────────────────────────
    last_activity_at: str = ""

    # ── Daily quest ───────────────────────────────────────────────────────────
    daily_quest_text:    str = ""
    daily_quest_trigger: str = ""
    daily_quest_date:    str = ""
    daily_quest_done:    bool = False
    quests_completed:    int = 0   # сколько квестов выполнено за жизнь питомца

    # ── Cooldown после смерти ─────────────────────────────────────────────────
    cooldown_commits: int = 0
    cooldown_issues:  int = 0
    cooldown_ci_ok:   int = 0

    def __post_init__(self) -> None:
        now = datetime.now().isoformat()
        if not self.born_at:
            self.born_at = now
        if not self.last_updated:
            self.last_updated = now

    # ── Свойства ──────────────────────────────────────────────────────────────

    @property
    def age_days(self) -> int:
        try:
            return (datetime.now() - datetime.fromisoformat(self.born_at)).days
        except (ValueError, TypeError):
            return 0

    @property
    def cooldown_done(self) -> bool:
        return self.cooldown_commits >= 3 and self.cooldown_issues >= 1 and self.cooldown_ci_ok >= 1

    @property
    def is_sleeping(self) -> bool:
        """Питомец считается спящим если 12+ часов без активности."""
        if not self.alive or not self.last_activity_at:
            return False
        try:
            hrs = (datetime.now() - datetime.fromisoformat(self.last_activity_at)).total_seconds() / 3600
            return hrs >= 12
        except (ValueError, TypeError):
            return False

    @property
    def mood_label(self) -> str:
        if not self.alive:
            return "ghost"
        if self.is_sleeping:
            return "sleeping"
        avg = (self.hunger + self.energy + self.mood) / 3
        if self.streak_days >= 7 and avg >= 70:
            return "on_fire"
        if avg >= 80: return "ecstatic"
        if avg >= 60: return "happy"
        if avg >= 40: return "okay"
        if avg >= 20: return "sad"
        return "miserable"

    @property
    def death_reason(self) -> str:
        reasons: List[str] = []
        if self.hunger <= 5:  reasons.append("no commits for too long")
        if self.energy <= 5:  reasons.append("CI was always red")
        if self.mood   <= 5:  reasons.append("too many abandoned issues")
        if self.health <= 5:  reasons.append("general neglect")
        return ", ".join(reasons) if reasons else "neglect"

    # ── Сериализация ──────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PetState":
        _known = {
            "name", "github_repo", "born_at", "last_updated",
            "hunger", "energy", "mood", "health",
            "alive", "achievements", "events_log", "git_repos",
            "last_fed_by", "last_fed_at",
            "streak_days", "last_streak_date", "last_activity_at",
            "daily_quest_text", "daily_quest_trigger",
            "daily_quest_date", "daily_quest_done", "quests_completed",
            "cooldown_commits", "cooldown_issues", "cooldown_ci_ok",
        }
        filtered = {k: v for k, v in data.items() if k in _known}
        filtered.setdefault("alive", True)
        filtered.setdefault("born_at", filtered.get("last_updated", datetime.now().isoformat()))
        filtered.setdefault("github_repo", "")
        filtered.setdefault("last_fed_by", "")
        filtered.setdefault("last_fed_at", "")
        filtered.setdefault("streak_days", 0)
        filtered.setdefault("last_streak_date", "")
        filtered.setdefault("last_activity_at", "")
        filtered.setdefault("daily_quest_text", "")
        filtered.setdefault("daily_quest_trigger", "")
        filtered.setdefault("daily_quest_date", "")
        filtered.setdefault("daily_quest_done", False)
        filtered.setdefault("quests_completed", 0)
        filtered.setdefault("cooldown_commits", 0)
        filtered.setdefault("cooldown_issues", 0)
        filtered.setdefault("cooldown_ci_ok", 0)
        for stat in ("hunger", "energy", "mood", "health"):
            if stat in filtered:
                filtered[stat] = float(filtered[stat])
        return cls(**filtered)

    # ── Лог ───────────────────────────────────────────────────────────────────

    def add_event(self, message: str) -> None:
        ts = datetime.now().strftime("%d %b %H:%M")
        self.events_log.append(f"[{ts}] {message}")
        if len(self.events_log) > 30:
            self.events_log.pop(0)

    # ── Ачивки ────────────────────────────────────────────────────────────────

    def check_achievements(self) -> None:
        if not self.alive:
            return
        logs = "\n".join(self.events_log).lower()
        candidates: Dict[str, bool] = {
            # Базовые git-ачивки
            "First Commit":   "commit" in logs,
            "CI Hero":        "ci" in logs and "passed" in logs,
            "Issue Closer":   "closed issue" in logs,
            "PR Master":      "merged pr" in logs,
            # Статы
            "Healthy Repo":   self.health >= 80,
            "Happy Pet":      self.mood >= 80,
            "Full Belly":     self.hunger >= 90,
            "Energised":      self.energy >= 90,
            # Streak
            "7-Day Streak":   self.streak_days >= 7,
            "30-Day Streak":  self.streak_days >= 30,
            # Daily quest
            "Quest Accepted": self.quests_completed >= 1,
            "Quest Master":   self.quests_completed >= 10,
            "Daily Devotion": self.quests_completed >= 30,
        }
        for ach, cond in candidates.items():
            if cond and ach not in self.achievements:
                self.achievements.append(ach)
                self.add_event(f"Achievement unlocked: {ach}")


# ── Запись о мёртвом питомце ──────────────────────────────────────────────────

@dataclass
class GraveyardEntry:
    name: str
    born_at: str
    died_at: str
    age_days: int
    death_reason: str
    achievements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraveyardEntry":
        _known = {"name", "born_at", "died_at", "age_days", "death_reason", "achievements"}
        return cls(**{k: v for k, v in data.items() if k in _known})
