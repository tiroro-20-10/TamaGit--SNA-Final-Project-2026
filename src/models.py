from __future__ import annotations

import random
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List

# ── Default pet name pool ──────────────────────────────────────────────────────
# Used when auto-init happens after cooldown (no human available to name the pet).
DEFAULT_PET_NAMES = [
    "Committy", "GitByte", "Mergekin", "Pixelcat", "Hashling",
    "Branchly", "Patchcat", "Rebaser", "Stageling", "Diffpaw",
    "Hookster", "Forklet", "Clonely", "Tagster", "Blobby",
]

# ── Team achievement definitions ───────────────────────────────────────────────
# All achievements are awarded on VPS side only (via webhook events).
# Keys are achievement names; values are display descriptions.
TEAM_ACHIEVEMENTS: Dict[str, str] = {
    "First Push":       "Team made their first push",
    "PR Merged":        "Team merged their first pull request",
    "Issue Solved":     "Team closed their first issue",
    "CI Passed":        "CI pipeline passed for the first time",
    "Zero Red CI":      "48 hours with no CI failures",
    "Issue Cleaners":   "Closed 10 issues total",
    "PR Factory":       "Merged 5 pull requests",
    "Always Green":     "7 days with CI passing every day",
    "Daily Team":       "7-day active commit streak",
    "Weekly Warriors":  "30-day active commit streak",
    "Quest Completers": "Completed first team quest",
    "Dedicated Team":   "Completed 10 team quests",
    "Resurrection":     "Completed full cooldown after pet death",
}
TOTAL_ACHIEVEMENTS = len(TEAM_ACHIEVEMENTS)

# ── Team daily quest definitions ───────────────────────────────────────────────
# All quests are generated and tracked on VPS only.
# "threshold" = how many events of "trigger" type are needed.
# "contextual" = True means the quest is only assigned when GitHub API confirms
#                the condition makes sense (e.g. open issues actually exist).
TEAM_QUESTS = [
    {
        "id":          "commits_5",
        "text":        "Make 5 commits as a team today",
        "trigger":     "commit_count",
        "threshold":   5,
        "contextual":  False,
    },
    {
        "id":          "issues_3",
        "text":        "Close 3 open issues today",
        "trigger":     "issue_count",
        "threshold":   3,
        "contextual":  True,   # only assigned when repo has 3+ open issues
    },
    {
        "id":          "prs_2",
        "text":        "Merge 2 pull requests today",
        "trigger":     "pr_count",
        "threshold":   2,
        "contextual":  True,   # only assigned when repo has 2+ open PRs
    },
    {
        "id":          "ci_fix",
        "text":        "Fix the broken CI pipeline",
        "trigger":     "ci_fixed",
        "threshold":   1,
        "contextual":  True,   # only assigned when CI is currently failing
    },
    {
        "id":          "pr_review",
        "text":        "Review and merge a pull request",
        "trigger":     "pr_count",
        "threshold":   1,
        "contextual":  False,
    },
    {
        "id":          "commits_10",
        "text":        "Make 10 commits as a team today",
        "trigger":     "commit_count",
        "threshold":   10,
        "contextual":  False,
    },
]


@dataclass
class PetState:
    # Identity
    name: str = "TamaGit"
    github_repo: str = ""          # owner/repo — one repo per pet
    born_at: str = ""
    last_updated: str = ""

    # Stats — float; 0 = worst, 100 = best
    hunger: float = 80.0   # 0 = starving,  100 = full
    energy: float = 80.0   # 0 = exhausted, 100 = energised
    mood:   float = 80.0   # 0 = sad,        100 = happy
    health: float = 100.0  # 0 = dying,      100 = healthy

    alive: bool = True

    # History (managed on VPS)
    achievements: List[str] = field(default_factory=list)
    events_log:   List[str] = field(default_factory=list)

    # Local-only repo metadata (NOT overwritten by sync merge logic)
    git_repos: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Team tracking (managed on VPS)
    last_fed_by: str = ""     # GitHub username of last pusher
    last_fed_at: str = ""

    # Streak (managed on VPS)
    streak_days:      int = 0
    last_streak_date: str = ""
    last_activity_at: str = ""

    # Daily quest (generated and tracked on VPS)
    daily_quest_id:        str = ""
    daily_quest_text:      str = ""
    daily_quest_trigger:   str = ""   # "commit_count" | "issue_count" | "pr_count" | "ci_fixed"
    daily_quest_threshold: int = 0
    daily_quest_date:      str = ""   # YYYY-MM-DD
    daily_quest_done:      bool = False
    quests_completed:      int = 0    # lifetime total

    # Daily counters (reset when quest refreshes each day)
    daily_commit_count: int = 0
    daily_issue_count:  int = 0
    daily_pr_count:     int = 0
    ci_failed_today:    bool = False  # for "fix CI" quest detection

    # Cooldown (after death)
    cooldown_commits: int = 0   # need 3
    cooldown_issues:  int = 0   # need 1
    cooldown_ci_ok:   int = 0   # need 1

    # Tracks whether the dead pet has been added to the graveyard already.
    # Prevents double-burying if the server was down at the moment of death.
    buried: bool = False

    # Custom name pool for auto-init (set during tamagit init)
    custom_pet_names: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        now = datetime.now().isoformat()
        if not self.born_at:      self.born_at      = now
        if not self.last_updated: self.last_updated  = now

    @property
    def age_days(self) -> int:
        try:
            return (datetime.now() - datetime.fromisoformat(self.born_at)).days
        except (ValueError, TypeError):
            return 0

    @property
    def cooldown_done(self) -> bool:
        return (
            self.cooldown_commits >= 3
            and self.cooldown_issues >= 1
            and self.cooldown_ci_ok >= 1
        )

    @property
    def is_sleeping(self) -> bool:
        if not self.alive or not self.last_activity_at:
            return False
        try:
            hrs = (datetime.now() - datetime.fromisoformat(self.last_activity_at)).total_seconds() / 3600
            return hrs >= 12
        except (ValueError, TypeError):
            return False

    @property
    def mood_label(self) -> str:
        if not self.alive:     return "ghost"
        if self.is_sleeping:   return "sleeping"
        avg = (self.hunger + self.energy + self.mood) / 3
        if self.streak_days >= 7 and avg >= 70: return "on_fire"
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

    def random_name(self) -> str:
        pool = self.custom_pet_names if self.custom_pet_names else DEFAULT_PET_NAMES
        return random.choice(pool)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PetState":
        _known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in _known}
        # Defaults for any fields missing in older state files
        filtered.setdefault("alive", True)
        filtered.setdefault("born_at", filtered.get("last_updated", datetime.now().isoformat()))
        filtered.setdefault("github_repo", "")
        filtered.setdefault("last_fed_by", "")
        filtered.setdefault("last_fed_at", "")
        filtered.setdefault("streak_days", 0)
        filtered.setdefault("last_streak_date", "")
        filtered.setdefault("last_activity_at", "")
        filtered.setdefault("daily_quest_id", "")
        filtered.setdefault("daily_quest_text", "")
        filtered.setdefault("daily_quest_trigger", "")
        filtered.setdefault("daily_quest_threshold", 0)
        filtered.setdefault("daily_quest_date", "")
        filtered.setdefault("daily_quest_done", False)
        filtered.setdefault("quests_completed", 0)
        filtered.setdefault("daily_commit_count", 0)
        filtered.setdefault("daily_issue_count", 0)
        filtered.setdefault("daily_pr_count", 0)
        filtered.setdefault("ci_failed_today", False)
        filtered.setdefault("cooldown_commits", 0)
        filtered.setdefault("cooldown_issues", 0)
        filtered.setdefault("cooldown_ci_ok", 0)
        filtered.setdefault("custom_pet_names", [])
        for stat in ("hunger", "energy", "mood", "health"):
            if stat in filtered:
                filtered[stat] = float(filtered[stat])
        return cls(**filtered)

    def add_event(self, message: str) -> None:
        ts = datetime.now().strftime("%d %b %H:%M")
        self.events_log.append(f"[{ts}] {message}")
        if len(self.events_log) > 30:
            self.events_log.pop(0)

    def check_achievements(self) -> None:
        """Award team achievements based on current pet state and event history.

        Called only on VPS (inside webhook handler) to keep achievements server-side.
        """
        if not self.alive:
            return
        logs = "\n".join(self.events_log).lower()

        conditions: Dict[str, bool] = {
            "First Push":       "pushed" in logs,
            "PR Merged":        "merged pr" in logs,
            "Issue Solved":     "closed issue" in logs,
            "CI Passed":        "ci" in logs and "passed" in logs,
            "Zero Red CI":      False,          # set externally after 48h tracking
            "Issue Cleaners":   self.daily_issue_count >= 10 or "closed issue" in logs,
            "PR Factory":       self.daily_pr_count >= 5,
            "Always Green":     False,          # tracked externally
            "Daily Team":       self.streak_days >= 7,
            "Weekly Warriors":  self.streak_days >= 30,
            "Quest Completers": self.quests_completed >= 1,
            "Dedicated Team":   self.quests_completed >= 10,
            "Resurrection":     self.cooldown_done,
        }
        for name, cond in conditions.items():
            if cond and name not in self.achievements:
                self.achievements.append(name)
                self.add_event(f"Team achievement unlocked: {name}")


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
