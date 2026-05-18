"""
TamaGit functional tests.
Tests cover actual pet mechanics, not implementation details.
Run with: python -m pytest tests/ -v
"""
import tempfile, os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from src.models import PetState, TOTAL_ACHIEVEMENTS, TEAM_ACHIEVEMENTS, GraveyardEntry
from src.pet_engine import (
    apply_github_event, apply_git_snapshot,
    refresh_daily_quest, update_quest_progress,
    update_from_time, update_streak,
)
from src.github_integration import GitHubEvent, parse_github_webhook
from src.git_integration import GitSnapshot
from src.storage import Storage
from src.storage_helpers import _death_achievements
from src import config_manager


# ── State persistence ──────────────────────────────────────────────────────────

def test_state_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "state.json"))
        pet = PetState(name="X", hunger=60.0, energy=70.0, mood=80.0)
        s.save(pet); loaded = s.load()
        assert loaded.name == "X"
        assert abs(loaded.hunger - 60.0) < 0.01
        assert abs(loaded.mood - 80.0) < 0.01


def test_default_created_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "sub" / "state.json"))
        assert not s.is_initialized()
        pet = s.load()
        assert pet.alive and pet.name == "TamaGit"
        assert s.is_initialized()


def test_from_dict_handles_missing_fields():
    """Deserialising old state.json (missing new fields) must not crash."""
    partial = {"name": "Old", "hunger": 70.0, "energy": 60.0, "mood": 50.0}
    pet = PetState.from_dict(partial)
    assert pet.name == "Old"
    assert pet.quests_completed == 0   # new field defaulted


# ── Stat mechanics (higher = better) ──────────────────────────────────────────

def test_push_increases_hunger_and_mood():
    pet = PetState(hunger=50.0, mood=50.0)
    apply_github_event(pet, GitHubEvent("push","bob pushed",count=2,contributor="bob"))
    assert pet.hunger > 50 and pet.mood > 50
    assert pet.last_fed_by == "bob"


def test_multi_commit_push_capped():
    pet = PetState(hunger=60.0)
    apply_github_event(pet, GitHubEvent("push","big push",count=100,contributor="alice"))
    assert pet.hunger <= 100.0


def test_pr_merged_boosts_health_energy_mood():
    pet = PetState(health=60.0, energy=60.0, mood=60.0)
    apply_github_event(pet, GitHubEvent("pr_merged","merged",count=1,contributor="bob"))
    assert pet.health > 60 and pet.energy > 60 and pet.mood > 60


def test_issue_closed_boosts_mood():
    pet = PetState(mood=50.0, hunger=50.0)
    apply_github_event(pet, GitHubEvent("issue_closed","closed",count=1,contributor="carol"))
    assert pet.mood > 50 and pet.hunger > 50


def test_ci_success_boosts_health_energy():
    pet = PetState(health=60.0, energy=60.0)
    apply_github_event(pet, GitHubEvent("ci_success","CI passed",count=1))
    assert pet.health > 60 and pet.energy > 60


def test_ci_failure_hurts_health_energy():
    pet = PetState(health=80.0, energy=80.0)
    apply_github_event(pet, GitHubEvent("ci_failed","CI failed",count=1))
    assert pet.health < 80 and pet.energy < 80
    assert pet.ci_failed_today is True


def test_stats_clamped_0_to_100():
    pet = PetState(hunger=5.0, mood=5.0)
    apply_github_event(pet, GitHubEvent("push","push",count=1000,contributor="x"))
    assert pet.hunger <= 100.0 and pet.mood <= 100.0


# ── Time decay ─────────────────────────────────────────────────────────────────

def test_decay_reduces_stats_over_time():
    pet = PetState(hunger=80.0, energy=80.0, mood=80.0)
    # Simulate last_updated 2 days ago
    pet.last_updated = (datetime.now() - timedelta(days=2)).isoformat()
    update_from_time(pet)
    assert pet.hunger < 80 and pet.energy < 80 and pet.mood < 80


def test_decay_kills_pet_eventually():
    pet = PetState(hunger=0.0, energy=0.0, mood=0.0, health=1.0)
    pet.last_updated = (datetime.now() - timedelta(days=5)).isoformat()
    update_from_time(pet)
    assert not pet.alive


def test_no_decay_if_updated_recently():
    pet = PetState(hunger=80.0)
    pet.last_updated = datetime.now().isoformat()
    update_from_time(pet)
    assert abs(pet.hunger - 80.0) < 0.1


# ── Webhook parsing ────────────────────────────────────────────────────────────

def test_webhook_extracts_contributor():
    payload = {"sender":{"login":"alice"}, "commits":[{}], "ref":"refs/heads/main"}
    ev = parse_github_webhook("push", payload)
    assert ev.contributor == "alice"
    assert "alice" in ev.message


def test_webhook_pr_merged():
    payload = {
        "sender":{"login":"bob"},
        "action":"closed",
        "pull_request":{"title":"Fix bug","merged":True},
    }
    ev = parse_github_webhook("pull_request", payload)
    assert ev.type == "pr_merged"
    assert "bob" in ev.message


def test_webhook_pr_not_merged_is_ignored():
    payload = {
        "sender":{"login":"bob"},
        "action":"closed",
        "pull_request":{"title":"Fix bug","merged":False},
    }
    ev = parse_github_webhook("pull_request", payload)
    assert ev.ignored


def test_webhook_ping_ignored():
    ev = parse_github_webhook("ping", {})
    assert ev.ignored


# ── Streak ─────────────────────────────────────────────────────────────────────

def test_streak_increments_consecutive_days():
    pet = PetState()
    pet.last_streak_date = (date.today() - timedelta(days=1)).isoformat()
    pet.streak_days = 5
    update_streak(pet)
    assert pet.streak_days == 6
    assert pet.last_streak_date == date.today().isoformat()


def test_streak_resets_after_gap():
    pet = PetState()
    pet.last_streak_date = (date.today() - timedelta(days=3)).isoformat()
    pet.streak_days = 10
    update_streak(pet)
    assert pet.streak_days == 1


def test_streak_not_doubled_same_day():
    pet = PetState()
    pet.last_streak_date = date.today().isoformat()
    pet.streak_days = 5
    update_streak(pet)
    assert pet.streak_days == 5   # unchanged


def test_on_fire_state_at_7_day_streak():
    pet = PetState(hunger=80.0, energy=80.0, mood=80.0)
    pet.streak_days = 7
    pet.last_activity_at = datetime.now().isoformat()
    assert pet.mood_label == "on_fire"


# ── Sleeping ───────────────────────────────────────────────────────────────────

def test_sleeping_after_12h_inactivity():
    pet = PetState(hunger=70.0, energy=70.0, mood=70.0)
    pet.last_activity_at = (datetime.now() - timedelta(hours=13)).isoformat()
    assert pet.is_sleeping
    assert pet.mood_label == "sleeping"


def test_not_sleeping_if_recently_active():
    pet = PetState(hunger=70.0, energy=70.0, mood=70.0)
    pet.last_activity_at = datetime.now().isoformat()
    assert not pet.is_sleeping


# ── Team quests ────────────────────────────────────────────────────────────────

def test_quest_generated_server_side():
    pet = PetState()
    assert not pet.daily_quest_text
    refresh_daily_quest(pet, context=None)
    assert pet.daily_quest_text
    assert pet.daily_quest_date == date.today().isoformat()


def test_quest_not_regenerated_same_day():
    pet = PetState()
    refresh_daily_quest(pet, context=None)
    first_text = pet.daily_quest_text
    refresh_daily_quest(pet, context=None)
    assert pet.daily_quest_text == first_text


def test_quest_resets_counters_on_new_day():
    pet = PetState()
    pet.daily_commit_count = 5
    pet.daily_issue_count  = 3
    # Simulate yesterday's quest
    pet.daily_quest_date = (date.today() - timedelta(days=1)).isoformat()
    pet.daily_quest_done = True
    refresh_daily_quest(pet, context=None)
    assert pet.daily_commit_count == 0
    assert pet.daily_issue_count == 0
    assert not pet.daily_quest_done


def test_quest_completes_at_threshold():
    pet = PetState()
    pet.daily_quest_trigger   = "commit_count"
    pet.daily_quest_threshold = 5
    pet.daily_quest_text      = "5 commits"
    pet.daily_quest_date      = date.today().isoformat()
    for _ in range(4):
        assert not update_quest_progress(pet, "commit_count", 1)
    assert update_quest_progress(pet, "commit_count", 1)
    assert pet.daily_quest_done
    assert pet.quests_completed == 1


def test_ci_fix_quest_requires_prior_failure():
    pet = PetState()
    pet.daily_quest_trigger   = "ci_fixed"
    pet.daily_quest_threshold = 1
    pet.daily_quest_date      = date.today().isoformat()
    pet.ci_failed_today       = False
    assert not update_quest_progress(pet, "ci_fixed", 1)
    pet.ci_failed_today = True
    assert update_quest_progress(pet, "ci_fixed", 1)


def test_contextual_quest_with_context():
    """Context-aware quests only appear when conditions are met."""
    pet = PetState()
    context = {"open_issues": 5, "open_prs": 3, "ci_failing": True}
    refresh_daily_quest(pet, context=context)
    # Should pick one of the available quests
    assert pet.daily_quest_text


# ── Scan (metadata only) ───────────────────────────────────────────────────────

def test_scan_updates_only_git_repos():
    pet = PetState(hunger=70.0, mood=70.0, streak_days=5)
    snap = GitSnapshot(
        is_repo=True, repo_root="/tmp/r", branch="main",
        is_dirty=True, last_commit_hash="abc", last_commit_subject="fix",
        unpushed_commits=3, unpulled_commits=0, upstream_available=True, error=None,
    )
    apply_git_snapshot(pet, snap)
    # Stats must not change
    assert abs(pet.hunger - 70.0) < 0.01
    assert abs(pet.mood   - 70.0) < 0.01
    assert pet.streak_days == 5
    # But metadata must be recorded
    assert pet.git_repos["/tmp/r"]["is_dirty"] is True
    assert pet.git_repos["/tmp/r"]["unpushed"] == 3


def test_scan_records_dirty_since():
    pet = PetState()
    snap = GitSnapshot(
        is_repo=True, repo_root="/tmp/r", branch="main",
        is_dirty=True, last_commit_hash="abc", last_commit_subject="",
        unpushed_commits=0, unpulled_commits=0, upstream_available=True, error=None,
    )
    apply_git_snapshot(pet, snap)
    assert pet.git_repos["/tmp/r"]["dirty_since"] != ""


def test_scan_clears_dirty_since_when_clean():
    pet = PetState()
    pet.git_repos["/tmp/r"] = {"last_commit_hash":"abc","is_dirty":True,"dirty_since":"2020-01-01"}
    snap = GitSnapshot(
        is_repo=True, repo_root="/tmp/r", branch="main",
        is_dirty=False, last_commit_hash="def", last_commit_subject="",
        unpushed_commits=0, unpulled_commits=0, upstream_available=True, error=None,
    )
    apply_git_snapshot(pet, snap)
    assert pet.git_repos["/tmp/r"]["dirty_since"] == ""


# ── Cooldown ───────────────────────────────────────────────────────────────────

def test_cooldown_requires_all_three_tasks():
    pet = PetState(alive=False)
    assert not pet.cooldown_done
    pet.cooldown_commits = 3; pet.cooldown_issues = 1; pet.cooldown_ci_ok = 1
    assert pet.cooldown_done


def test_cooldown_partial_not_done():
    pet = PetState(alive=False, cooldown_commits=3, cooldown_issues=1, cooldown_ci_ok=0)
    assert not pet.cooldown_done


def test_ghost_mode_tracks_cooldown():
    pet = PetState(alive=False, cooldown_commits=0)
    apply_github_event(pet, GitHubEvent("push","pushed",count=2,contributor="x"))
    assert pet.cooldown_commits == 2


# ── Graveyard & death achievements ────────────────────────────────────────────

def test_bury_adds_to_graveyard():
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "state.json"))
        dead = PetState(name="Ghost", alive=False, hunger=0.0)
        s.bury(dead)
        entries = s.load_graveyard()
        assert entries[0].name == "Ghost"


def test_graveyard_grows():
    with tempfile.TemporaryDirectory() as tmp:
        s = Storage(str(Path(tmp) / "state.json"))
        for name in ["Pet1", "Pet2", "Pet3"]:
            s.bury(PetState(name=name, alive=False))
        assert len(s.load_graveyard()) == 3


def test_first_loss_achievement():
    pet = PetState(name="X", alive=False, hunger=0.0)
    achs = _death_achievements(pet, [])
    assert "💔 First Loss" in achs


def test_starved_achievement():
    pet = PetState(name="X", alive=False, hunger=0.0, energy=70.0)
    achs = _death_achievements(pet, [])
    assert "🍽️ Starved" in achs


def test_burned_out_achievement():
    pet = PetState(name="X", alive=False, energy=0.0)
    pet.hunger = 50.0; pet.mood = 50.0   # energy caused death
    achs = _death_achievements(pet, [])
    assert "🔥 Burned Out" in achs


def test_veteran_achievement():
    pet = PetState(name="X", alive=False)
    pet.born_at = (datetime.now() - timedelta(days=35)).isoformat()
    achs = _death_achievements(pet, [{"x":1}])   # non-empty graveyard
    assert "🎖️ Veteran" in achs


def test_serial_offender_achievement():
    pet = PetState(name="X", alive=False)
    # Two existing entries → third death → Serial Offender
    existing = [object(), object()]   # two stubs
    achs = _death_achievements(pet, existing)
    assert "😬 Serial Offender" in achs


# ── Achievements ───────────────────────────────────────────────────────────────

def test_achievement_first_push():
    pet = PetState()
    apply_github_event(pet, GitHubEvent("push","alice pushed",count=1,contributor="alice"))
    assert "First Push" in pet.achievements


def test_achievement_daily_team_streak():
    pet = PetState(hunger=80.0, energy=80.0, mood=80.0)
    pet.last_streak_date = (date.today() - timedelta(days=1)).isoformat()
    pet.streak_days = 6
    update_streak(pet)   # reaches 7
    pet.check_achievements()
    assert "Daily Team" in pet.achievements


def test_achievement_quest_completers():
    pet = PetState()
    pet.quests_completed = 1
    pet.check_achievements()
    assert "Quest Completers" in pet.achievements


def test_total_achievements_count():
    assert TOTAL_ACHIEVEMENTS == len(TEAM_ACHIEVEMENTS) == 13


# ── Config manager ─────────────────────────────────────────────────────────────

def test_config_set_get():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TAMAGIT_STATE_PATH"] = tmp + "/state.json"
        config_manager.set_("local_name", "TestPet")
        assert config_manager.get("local_name") == "TestPet"
        config_manager.reset()
        assert config_manager.get("local_name") == ""


def test_config_int_coercion():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TAMAGIT_STATE_PATH"] = tmp + "/state.json"
        config_manager.set_("sync_interval", "3")
        assert config_manager.get("sync_interval") == 3


def test_config_bool_coercion():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TAMAGIT_STATE_PATH"] = tmp + "/state.json"
        config_manager.set_("show_stats", "false")
        assert config_manager.get("show_stats") is False


def test_config_effective_name_override():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TAMAGIT_STATE_PATH"] = tmp + "/state.json"
        config_manager.set_("local_name", "Custom")
        assert config_manager.effective_name("Official") == "Custom"
        config_manager.reset()
        assert config_manager.effective_name("Official") == "Official"


# ── Mood labels ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hunger,energy,mood,expected", [
    (90, 90, 90, "ecstatic"),
    (70, 70, 70, "happy"),
    (50, 50, 50, "okay"),
    (25, 25, 25, "sad"),
    (10, 10, 10, "miserable"),
])
def test_mood_labels(hunger, energy, mood, expected):
    pet = PetState(hunger=float(hunger), energy=float(energy), mood=float(mood))
    pet.last_activity_at = datetime.now().isoformat()   # not sleeping
    assert pet.mood_label == expected


def test_ghost_mood():
    pet = PetState(alive=False)
    assert pet.mood_label == "ghost"
