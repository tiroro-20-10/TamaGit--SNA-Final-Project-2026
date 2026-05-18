from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List

from .models import GraveyardEntry, PetState
from .storage_helpers import _death_achievements


class Storage:
    """Reads/writes state.json and graveyard.json.

    Both files live in ~/.tamagit/ (configurable via TAMAGIT_STATE_PATH).
    """

    def __init__(self, filepath: str | None = None) -> None:
        filepath = filepath or os.environ.get("TAMAGIT_STATE_PATH", "~/.tamagit/state.json")
        self.filepath = Path(filepath).expanduser()
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.graveyard_path = self.filepath.parent / "graveyard.json"

    def is_initialized(self) -> bool:
        return self.filepath.exists()

    def save(self, pet: PetState) -> None:
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
        """Add dead pet to graveyard with death achievements computed."""
        existing = self.load_graveyard()
        death_achs = _death_achievements(pet, existing)
        entry = GraveyardEntry(
            name=pet.name,
            born_at=pet.born_at,
            died_at=datetime.now().isoformat(),
            age_days=pet.age_days,
            death_reason=pet.death_reason,
            achievements=list(pet.achievements) + death_achs,
        )
        existing.append(entry)
        self.save_graveyard(existing)
        return entry
