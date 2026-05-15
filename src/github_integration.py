from .models import PetState
from .pet_engine import apply_mock_github_event


class GitHubEvents:

    @staticmethod
    def apply_mock_event(pet: PetState, event_type: str) -> str:
        return apply_mock_github_event(pet, event_type)
