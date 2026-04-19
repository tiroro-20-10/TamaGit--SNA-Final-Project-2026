from models import PetState


class GitHubEvents:

    @staticmethod
    def apply_event(pet: PetState, event_type: str) -> str:
        if event_type == "commit":
            pet.hunger = max(0, pet.hunger - 20)
            pet.mood = max(0, pet.mood - 10)
            return "📨 New commit! +20 to satiety"

        elif event_type == "pr":
            pet.health = min(100, pet.health + 15)
            pet.energy = max(0, pet.energy - 8)
            return "🔀 Pull Request merged! +15 to health"

        elif event_type in ["issue", "issue_closed"]: 
            pet.mood = max(0, pet.mood - 25)
            pet.hunger = max(0, pet.hunger - 10)
            return "✅ Issue is closed! +25 to the mood"

        elif event_type == "ci_success":
            pet.health = min(100, pet.health + 10)
            return "✅ CI was successful! +10 to health"

        else:
            return f"Unknown event: {event_type}"
