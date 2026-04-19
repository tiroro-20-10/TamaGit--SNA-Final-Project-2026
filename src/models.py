from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, List
import random

@dataclass
class PetState:
    name: str = "GitTama"
    hunger: int = 50      # 0 = full, 100 = starving
    energy: int = 50      # 0 = energetic, 100 = exhausted
    mood: int = 50        # 0 = happy, 100 = sad
    health: int = 100     # 0 = critical, 100 = perfect
    last_updated: str = ""
    last_quest_date: str = ""
    achievements: List[str] = field(default_factory=list)
    events_log: List[str] = field(default_factory=list)
    current_quest: str = ""

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PetState":
        for key in ["last_quest_date", "current_quest"]:
            if key not in data:
                data[key] = ""
        if "achievements" not in data:
            data["achievements"] = []
        if "events_log" not in data:
            data["events_log"] = []
        return cls(**data)

    def update_from_time(self):
        now = datetime.now()
        last = datetime.fromisoformat(self.last_updated)
        minutes_passed = (now - last).total_seconds() / 60

        if minutes_passed < 1:
            return

        decay = int(minutes_passed * 0.8)
        self.hunger = min(100, self.hunger + decay)
        self.energy = min(100, self.energy + decay)
        self.mood = min(100, self.mood + decay // 2)
        self.health = max(0, self.health - decay // 3)

        self.last_updated = now.isoformat()

    def add_event(self, message: str):
        timestamp = datetime.now().strftime("%H:%M")
        entry = f"[{timestamp}] {message}"
        self.events_log.append(entry)
        if len(self.events_log) > 10:
            self.events_log.pop(0)

    def get_daily_quest(self) -> str:
        today = datetime.now().date().isoformat()
        if self.last_quest_date == today and self.current_quest:
            return self.current_quest

        quests = [
            "Make 1 commit today",
            "Close at least 1 issue",
            "Update README.md",
            "Check CI status",
            "Create a Pull Request"
        ]
        self.current_quest = random.choice(quests)
        self.last_quest_date = today
        return self.current_quest

    def complete_quest(self):
        if self.current_quest:
            self.mood = max(0, self.mood - 30)
            self.health = min(100, self.health + 15)
            self.add_event(f"Quest completed: {self.current_quest}")
            self.current_quest = ""
            self.check_achievements()

    def check_achievements(self):
        """6 достижений согласно брифа"""
        new_ach = []
        if "First Commit" not in self.achievements and any("commit" in log.lower() for log in self.events_log):
            new_ach.append("First Commit")
        if "Healthy Repo" not in self.achievements and self.health >= 90:
            new_ach.append("Healthy Repo")
        if "Happy Pet" not in self.achievements and self.mood <= 20:
            new_ach.append("Happy Pet")
        if "CI Hero" not in self.achievements and any("CI" in log for log in self.events_log):
            new_ach.append("CI Hero")
        if "7 Days Streak" not in self.achievements and len(self.events_log) >= 7:
            new_ach.append("7 Days Streak")
        if "Issue Closer" not in self.achievements and any("issue" in log.lower() for log in self.events_log):
            new_ach.append("Issue Closer")

        if new_ach:
            self.achievements.extend(new_ach)
            for a in new_ach:
                self.add_event(f"Achievement unlocked: {a}")
