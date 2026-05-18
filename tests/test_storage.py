"""
TamaGit tests — covers core mechanics, team quest system, config, and death achievements.
Run with: pytest -q
"""
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from src.config_manager import DEFAULTS, get, set_, reset, all_values
from src.github_integration import GitHubEvent, parse_github_webhook
from src.models import PetState, TOTAL_ACHIEVEMENTS, TEAM_ACHIEVEMENTS
from src.pet_engine import (
    apply_github_event, apply_git_snapshot,
    refresh_daily_quest, update_quest_progress,
    update_from_time, update_streak,
)
from src.storage import Storage
from src.storage_helpers import _death_achievements
from src.git_integration import GitSnapshot
import os


def test_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "state.json"))
        pet = PetState(name="X", hunger=60.0, energy=70.0, mood=80.0)
        s.save(pet)
        loaded = s.load()
        assert loaded.name == "X"
        assert abs(loaded.hunger - 60.0) < 0.01
    print("roundtrip: OK")


def test_stats_higher_is_better():
    pet = PetState(hunger=100.0, energy=100.0, mood=100.0)
    assert pet.mood_label in ("ecstatic", "on_fire", "happy")
    print(f"stats semantics ({pet.mood_label}): OK")


# ── Webhook events ─────────────────────────────────────────────────────────────

def test_push_increases_hunger_mood():
    pet = PetState(hunger=50.0, mood=50.0)
    apply_github_event(pet, GitHubEvent(type="push", message="bob pushed", count=2, contributor="bob"))
    assert pet.hunger > 50 and pet.mood > 50
    assert pet.last_fed_by == "bob"
    print(f"push: hunger→{int(pet.hunger)}, fed_by={pet.last_fed_by}: OK")


def test_ci_failed_decreases_health_energy():
    pet = PetState(health=80.0, energy=80.0)
    apply_github_event(pet, GitHubEvent(type="ci_failed", message="CI fail", count=1))
    assert pet.health < 80 and pet.energy < 80
    assert pet.ci_failed_today is True
    print("ci_failed: OK")


def test_contributor_in_webhook():
    payload = {"sender": {"login": "alice"}, "commits": [{}], "ref": "refs/heads/main"}
    event = parse_github_webhook("push", payload)
    assert event.contributor == "alice"
    assert "alice" in event.message
    print("contributor: OK")


# ── Scan: metadata only ────────────────────────────────────────────────────────

def test_scan_does_not_change_stats():
    """Scan must only update git_repos — no hunger/energy/mood/streak changes."""
    pet = PetState(hunger=70.0, mood=70.0, streak_days=5)
    snap = GitSnapshot(
        is_repo=True, repo_root="/tmp/r", branch="main",
        is_dirty=True, last_commit_hash="abc", last_commit_subject="fix",
        unpushed_commits=3, unpulled_commits=0, upstream_available=True, error=None,
    )
    apply_git_snapshot(pet, snap)
    assert abs(pet.hunger - 70.0) < 0.01, f"hunger changed: {pet.hunger}"
    assert abs(pet.mood   - 70.0) < 0.01, f"mood changed: {pet.mood}"
    assert pet.streak_days == 5,          "streak changed"
    assert pet.git_repos["/tmp/r"]["is_dirty"] is True
    print("scan metadata-only: OK")


# ── React: visual only ─────────────────────────────────────────────────────────

def test_react_does_not_save():
    """react must not write to state.json."""
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "state.json"))
        pet = PetState(hunger=70.0)
        s.save(pet)
        mtime_before = Path(tmp, "state.json").stat().st_mtime

        from src.main import _cmd_react_visual
        _cmd_react_visual(0, "git push", s)

        mtime_after = Path(tmp, "state.json").stat().st_mtime
        assert mtime_before == mtime_after, "react wrote to state.json!"
    print("react does not write state: OK")


# ── Team quest system ──────────────────────────────────────────────────────────

def test_quest_generated_server_side():
    pet = PetState()
    assert not pet.daily_quest_text
    refresh_daily_quest(pet, context=None)
    assert pet.daily_quest_text
    assert pet.daily_quest_date == date.today().isoformat()
    print(f"quest generated: '{pet.daily_quest_text}': OK")


def test_quest_not_regenerated_same_day():
    pet = PetState()
    refresh_daily_quest(pet, context=None)
    first_text = pet.daily_quest_text
    refresh_daily_quest(pet, context=None)
    assert pet.daily_quest_text == first_text, "quest regenerated on same day"
    print("quest stable same-day: OK")


def test_quest_progress_threshold():
    pet = PetState()
    pet.daily_quest_trigger   = "commit_count"
    pet.daily_quest_threshold = 5
    pet.daily_quest_text      = "Make 5 commits"
    pet.daily_quest_date      = date.today().isoformat()
    for _ in range(4):
        assert not update_quest_progress(pet, "commit_count", 1)
    assert update_quest_progress(pet, "commit_count", 1) is True
    assert pet.daily_quest_done
    assert pet.quests_completed == 1
    print("quest threshold: OK")


def test_ci_fix_quest():
    """ci_fixed trigger only completes when ci_failed_today is True."""
    pet = PetState()
    pet.daily_quest_trigger   = "ci_fixed"
    pet.daily_quest_threshold = 1
    pet.daily_quest_date      = date.today().isoformat()
    pet.ci_failed_today       = False
    assert not update_quest_progress(pet, "ci_fixed", 1)  # no prior failure
    pet.ci_failed_today = True
    assert update_quest_progress(pet, "ci_fixed", 1) is True
    print("ci_fix quest: OK")


# ── Streak ─────────────────────────────────────────────────────────────────────

def test_streak_consecutive():
    pet = PetState()
    pet.last_streak_date = (date.today() - timedelta(days=1)).isoformat()
    pet.streak_days = 5
    update_streak(pet)
    assert pet.streak_days == 6
    print("streak consecutive: OK")


def test_streak_gap_resets():
    pet = PetState()
    pet.last_streak_date = (date.today() - timedelta(days=3)).isoformat()
    pet.streak_days = 10
    update_streak(pet)
    assert pet.streak_days == 1
    print("streak gap reset: OK")


# ── Sleeping state ─────────────────────────────────────────────────────────────

def test_sleeping_after_12h():
    pet = PetState()
    pet.last_activity_at = (datetime.now() - timedelta(hours=13)).isoformat()
    assert pet.is_sleeping is True
    assert pet.mood_label == "sleeping"
    print("sleeping: OK")


# ── Cooldown ───────────────────────────────────────────────────────────────────

def test_cooldown_all_tasks():
    pet = PetState(alive=False)
    assert not pet.cooldown_done
    pet.cooldown_commits = 3
    pet.cooldown_issues  = 1
    pet.cooldown_ci_ok   = 1
    assert pet.cooldown_done
    print("cooldown: OK")


# ── Death achievements ─────────────────────────────────────────────────────────

def test_first_loss():
    pet = PetState(name="X", alive=False, hunger=0.0)
    achs = _death_achievements(pet, [])
    assert "💔 First Loss" in achs
    print("First Loss achievement: OK")


def test_starved():
    pet = PetState(name="X", alive=False, hunger=0.0, energy=70.0)
    achs = _death_achievements(pet, [])
    assert "🍽️ Starved" in achs
    print("Starved achievement: OK")


# ── Config manager ─────────────────────────────────────────────────────────────

def test_config_manager():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TAMAGIT_STATE_PATH"] = tmp + "/state.json"
        set_("local_name", "TestPet")
        assert get("local_name") == "TestPet"
        set_("sync_interval", "5")
        assert get("sync_interval") == 5
        reset()
        assert get("local_name") == ""
    print("config_manager: OK")


# ── Health in prompt ───────────────────────────────────────────────────────────

def test_health_in_prompt():
    from src.ui import get_prompt_string
    pet = PetState(name="P", hunger=80.0, energy=74.0, mood=82.0, health=91.0)
    p = get_prompt_string(pet)
    assert "❤:91" in p
    print("health in prompt: OK")


# ── Total achievements count ───────────────────────────────────────────────────

def test_total_achievements():
    assert TOTAL_ACHIEVEMENTS == len(TEAM_ACHIEVEMENTS)
    print(f"TOTAL_ACHIEVEMENTS={TOTAL_ACHIEVEMENTS}: OK")
