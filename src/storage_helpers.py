"""Death achievement computation — kept separate to avoid circular imports."""
from __future__ import annotations
from typing import List
from .models import PetState, GraveyardEntry


def _death_achievements(pet: PetState, graveyard: List[GraveyardEntry]) -> List[str]:
    """Compute post-mortem achievements added to the graveyard entry."""
    achs: List[str] = []
    if not graveyard:       achs.append("💔 First Loss")
    if len(graveyard) == 2: achs.append("😬 Serial Offender")
    if len(graveyard) >= 4: achs.append("💀 Graveyard Keeper")

    if pet.age_days == 0:               achs.append("⚡ Gone in a Day")
    elif pet.age_days < 3:              achs.append("🌱 Short Life")
    elif pet.age_days >= 60:            achs.append("🏛️ Legend")
    elif pet.age_days >= 30:            achs.append("🎖️ Veteran")

    if "no commits" in pet.death_reason:     achs.append("🍽️ Starved")
    if "CI was always red" in pet.death_reason: achs.append("🔥 Burned Out")
    if "abandoned issues" in pet.death_reason:  achs.append("😔 Left Unresolved")
    if len(pet.death_reason.split(",")) >= 3:    achs.append("💫 Spectacular Failure")
    if len(pet.achievements) >= 5:              achs.append("🏆 Well Decorated")
    if pet.quests_completed >= 10:              achs.append("🎯 Quest Champion")
    return achs
