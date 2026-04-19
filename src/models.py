from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import Dict, Any, List


@dataclass
class PetState:
    name: str = "GitTama"
    hunger: int = 50
    energy: int = 50
    mood: int = 50
    health: int = 100
    last_updated: str = ""
    achievements: List[str] = field(default_factory=list)
    events_log: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PetState":
        if "last_updated" not in data:
            data["last_updated"] = datetime.now().isoformat()
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

    def check_achievements(self):
        new_ach = []
        if "First Commit" not in self.achievements and any("коммит" in log.lower() for log in self.events_log):
            new_ach.append("First Commit")
        if "Healthy Repo" not in self.achievements and self.health >= 80:
            new_ach.append("Healthy Repo")
        if "Happy Pet" not in self.achievements and self.mood <= 30:
            new_ach.append("Happy Pet")
        if "CI Hero" not in self.achievements and any("CI" in log for log in self.events_log):
            new_ach.append("CI Hero")

        if new_ach:
            self.achievements.extend(new_ach)
            for a in new_ach:
                self.add_event(f"Get achievement: {a}")
