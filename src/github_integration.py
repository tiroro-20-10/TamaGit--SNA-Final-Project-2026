from .models import PetState


class GitHubEvents:
    """Имитация GitHub-событий (для MVP)"""

    @staticmethod
    def apply_event(pet: PetState, event_type: str) -> str:
        """Применяем событие и возвращаем сообщение"""
        if event_type == "commit":
            pet.hunger = max(0, pet.hunger - 20)
            pet.mood = max(0, pet.mood - 10)
            return "📨 Новый коммит! +20 к сытости"

        elif event_type == "pr":
            pet.health = min(100, pet.health + 15)
            pet.energy = max(0, pet.energy - 8)
            return "🔀 Pull Request merged! +15 к здоровью"

        elif event_type in ["issue", "issue_closed"]:   # ← исправлено
            pet.mood = max(0, pet.mood - 25)
            pet.hunger = max(0, pet.hunger - 10)
            return "✅ Issue закрыт! +25 к настроению"

        elif event_type == "ci_success":
            pet.health = min(100, pet.health + 10)
            return "✅ CI прошёл успешно! +10 к здоровью"

        else:
            return f"Неизвестное событие: {event_type}"
