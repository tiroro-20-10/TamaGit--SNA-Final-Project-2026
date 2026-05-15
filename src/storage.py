import json
import os
from pathlib import Path
from .models import PetState


class Storage:
    def __init__(self, filepath: str | None = None):
        filepath = filepath or os.environ.get("GITTAMA_STATE_PATH", "~/.gittama/state.json")
        self.filepath = Path(filepath).expanduser()
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def save(self, pet: PetState) -> None:
        data = pet.to_dict()
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> PetState:
        if not self.filepath.exists():
            pet = PetState()
            self.save(pet)
            return pet

        with open(self.filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PetState.from_dict(data)
