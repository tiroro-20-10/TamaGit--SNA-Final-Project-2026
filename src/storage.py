from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List

from .models import GraveyardEntry, PetState


class Storage:
    """Читает/пишет state.json и graveyard.json.

    Файлы хранятся в ~/.tamagit/ (можно переопределить через TAMAGIT_STATE_PATH).
    """

    def __init__(self, filepath: str | None = None) -> None:
        filepath = filepath or os.environ.get("TAMAGIT_STATE_PATH", "~/.tamagit/state.json")
        self.filepath = Path(filepath).expanduser()
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.graveyard_path = self.filepath.parent / "graveyard.json"

    # ── Питомец ───────────────────────────────────────────────────────────────

    def is_initialized(self) -> bool:
        return self.filepath.exists()

    def save(self, pet: PetState) -> None:
        """Атомарная запись через .tmp файл — не теряем данные при прерывании."""
        tmp = self.filepath.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(pet.to_dict(), f, ensure_ascii=False, indent=2)
        tmp.replace(self.filepath)

    def load(self) -> PetState:
        if not self.filepath.exists():
            pet = PetState()
            self.save(pet)
            return pet
        with open(self.filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PetState.from_dict(data)

    def delete_state(self) -> None:
        if self.filepath.exists():
            self.filepath.unlink()

    # ── Кладбище ──────────────────────────────────────────────────────────────

    def load_graveyard(self) -> List[GraveyardEntry]:
        if not self.graveyard_path.exists():
            return []
        with open(self.graveyard_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [GraveyardEntry.from_dict(e) for e in data]

    def save_graveyard(self, entries: List[GraveyardEntry]) -> None:
        with open(self.graveyard_path, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in entries], f, ensure_ascii=False, indent=2)

    def bury(self, pet: PetState) -> GraveyardEntry:
        """Хороним питомца: добавляем посмертные ачивки и пишем в graveyard.json."""
        existing = self.load_graveyard()
        death_achs = _death_achievements(pet, existing)
        all_achs = list(pet.achievements) + death_achs

        entry = GraveyardEntry(
            name=pet.name,
            born_at=pet.born_at,
            died_at=datetime.now().isoformat(),
            age_days=pet.age_days,
            death_reason=pet.death_reason,
            achievements=all_achs,
        )
        existing.append(entry)
        self.save_graveyard(existing)
        return entry


def _death_achievements(pet: PetState, graveyard: List[GraveyardEntry]) -> List[str]:
    """Вычисляет ачивки которые получает питомец в момент смерти.

    Они добавляются к его уже заработанным ачивкам в записи кладбища.
    Это «грустные» ачивки — показывают как и почему умер питомец.
    """
    achs: List[str] = []

    # Смерти команды в целом
    if not graveyard:
        achs.append("💔 First Loss")          # первая смерть в команде
    if len(graveyard) == 2:
        achs.append("😬 Serial Offender")     # уже третья смерть
    if len(graveyard) >= 4:
        achs.append("💀 Graveyard Keeper")    # пять+ питомцев умерло

    # Продолжительность жизни
    if pet.age_days == 0:
        achs.append("⚡ Gone in a Day")       # не дожил и до суток
    elif pet.age_days < 3:
        achs.append("🌱 Short Life")
    elif pet.age_days >= 60:
        achs.append("🏛️ Legend")              # прожил 60+ дней
    elif pet.age_days >= 30:
        achs.append("🎖️ Veteran")             # прожил 30+ дней

    # Причина смерти
    reason = pet.death_reason
    if "no commits" in reason:
        achs.append("🍽️ Starved")             # умер от отсутствия коммитов
    if "CI was always red" in reason:
        achs.append("🔥 Burned Out")          # умер от постоянно красного CI
    if "abandoned issues" in reason:
        achs.append("😔 Left Unresolved")     # умер от брошенных issues
    if len(reason.split(",")) >= 3:
        achs.append("💫 Spectacular Failure") # умер сразу от трёх причин

    # Достижения при жизни
    if len(pet.achievements) >= 5:
        achs.append("🏆 Well Decorated")      # много ачивок — красивая смерть
    if pet.quests_completed >= 10:
        achs.append("🎯 Quest Champion")      # выполнил много квестов

    return achs
