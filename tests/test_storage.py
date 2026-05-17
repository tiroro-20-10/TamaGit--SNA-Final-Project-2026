"""
Тесты для TamaGit v3.

Покрывают: Storage, PetState, pet_engine, ачивки, квесты, streak, смерть.
Запуск: pytest -q
"""
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from src.github_integration import GitHubEvent, parse_github_webhook
from src.models import GraveyardEntry, PetState
from src.pet_engine import (
    apply_github_event,
    get_or_refresh_daily_quest,
    try_complete_quest,
    update_from_time,
    update_streak,
)
from src.storage import Storage, _death_achievements


# ── Базовые тесты Storage ─────────────────────────────────────────────────────

def test_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "state.json"))
        pet = PetState(name="Pixel", hunger=60.0, energy=70.0, mood=80.0)
        s.save(pet)
        loaded = s.load()
        assert loaded.name == "Pixel"
        assert abs(loaded.hunger - 60.0) < 0.01
    print("save/load roundtrip: OK")


def test_default_created_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "sub" / "state.json"))
        assert not s.is_initialized()
        pet = s.load()
        assert pet.alive and pet.name == "TamaGit"
        assert s.is_initialized()
    print("default creation: OK")


# ── Семантика статов ──────────────────────────────────────────────────────────

def test_stats_higher_is_better():
    """100 = хорошо, 0 = плохо."""
    pet = PetState(hunger=100.0, energy=100.0, mood=100.0)
    assert pet.mood_label in ("ecstatic", "on_fire", "happy")
    print(f"stats semantics ({pet.mood_label}): OK")


def test_push_increases_hunger_mood():
    pet = PetState(hunger=50.0, mood=50.0)
    apply_github_event(pet, GitHubEvent(type="push", message="test", count=2, contributor="alice"))
    assert pet.hunger > 50 and pet.mood > 50
    assert pet.last_fed_by == "alice"
    print(f"push: hunger→{int(pet.hunger)}, fed_by={pet.last_fed_by}: OK")


def test_ci_fail_decreases_health_energy():
    pet = PetState(health=80.0, energy=80.0)
    apply_github_event(pet, GitHubEvent(type="ci_failed", message="CI failed", count=1))
    assert pet.health < 80 and pet.energy < 80
    print(f"ci_fail: health→{int(pet.health)}: OK")


# ── Contributor в webhook payload ─────────────────────────────────────────────

def test_contributor_from_webhook():
    payload = {
        "sender": {"login": "bob"},
        "commits": [{"id": "abc"}],
        "ref": "refs/heads/main",
    }
    event = parse_github_webhook("push", payload)
    assert event.contributor == "bob"
    assert "bob" in event.message
    print(f"contributor: {event.contributor}: OK")


# ── Streak ────────────────────────────────────────────────────────────────────

def test_streak_consecutive_days():
    pet = PetState()
    pet.last_streak_date = (date.today() - timedelta(days=1)).isoformat()
    pet.streak_days = 5
    update_streak(pet)
    assert pet.streak_days == 6
    assert pet.last_streak_date == date.today().isoformat()
    print(f"streak: {pet.streak_days} days: OK")


def test_streak_gap_resets():
    pet = PetState()
    pet.last_streak_date = (date.today() - timedelta(days=3)).isoformat()
    pet.streak_days = 10
    update_streak(pet)
    assert pet.streak_days == 1
    print("streak gap reset: OK")


# ── Daily quest ───────────────────────────────────────────────────────────────

def test_daily_quest_generated():
    pet = PetState()
    get_or_refresh_daily_quest(pet)
    assert pet.daily_quest_text != ""
    assert pet.daily_quest_date == date.today().isoformat()
    print(f"quest generated: '{pet.daily_quest_text}': OK")


def test_quest_completion_increments_counter():
    pet = PetState()
    get_or_refresh_daily_quest(pet)
    trigger = pet.daily_quest_trigger
    assert try_complete_quest(pet, trigger) is True
    assert pet.daily_quest_done is True
    assert pet.quests_completed == 1
    print(f"quest done, quests_completed={pet.quests_completed}: OK")


def test_quest_achievement_unlocked():
    pet = PetState()
    get_or_refresh_daily_quest(pet)
    try_complete_quest(pet, pet.daily_quest_trigger)
    assert "Quest Accepted" in pet.achievements
    print("Quest Accepted achievement: OK")


# ── Sleeping state ────────────────────────────────────────────────────────────

def test_sleeping_after_12h():
    pet = PetState()
    pet.last_activity_at = (datetime.now() - timedelta(hours=13)).isoformat()
    assert pet.is_sleeping is True
    assert pet.mood_label == "sleeping"
    print("sleeping state: OK")


# ── Cooldown ──────────────────────────────────────────────────────────────────

def test_cooldown_requires_all_tasks():
    pet = PetState(alive=False)
    assert not pet.cooldown_done
    pet.cooldown_commits = 3
    pet.cooldown_issues  = 1
    pet.cooldown_ci_ok   = 1
    assert pet.cooldown_done
    print("cooldown logic: OK")


# ── Кладбище и посмертные ачивки ──────────────────────────────────────────────

def test_bury_adds_to_graveyard():
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "state.json"))
        dead = PetState(name="Ghost", alive=False, hunger=0.0, health=0.0)
        s.bury(dead)
        entries = s.load_graveyard()
        assert entries[0].name == "Ghost"
    print("bury to graveyard: OK")


def test_first_death_achievement():
    """При первой смерти команды должна добавиться ачивка 'First Loss'."""
    pet = PetState(name="Test", alive=False, hunger=0.0)
    achs = _death_achievements(pet, [])   # пустое кладбище = первая смерть
    assert "💔 First Loss" in achs
    print("First Loss achievement: OK")


def test_short_life_achievement():
    pet = PetState(name="Baby")
    pet.born_at = datetime.now().isoformat()  # только что родился
    achs = _death_achievements(pet, [{"name": "old"}])
    assert "🌱 Short Life" in achs or "⚡ Gone in a Day" in achs
    print("Short Life achievement: OK")


def test_starved_achievement():
    pet = PetState(name="Hungry", alive=False, hunger=0.0, energy=70.0, mood=70.0, health=0.0)
    achs = _death_achievements(pet, [])
    assert "🍽️ Starved" in achs
    print("Starved achievement: OK")
