"""
Terminal UI — ANSI output for tamagit status, prompt, graveyard.

All display functions respect the local config (theme, show_* flags,
ascii_style, prompt_format). Import config_manager here to read prefs.
"""
from __future__ import annotations

import random
from datetime import datetime
from typing import List

from .models import GraveyardEntry, PetState, TOTAL_ACHIEVEMENTS, TEAM_ACHIEVEMENTS

# ── ANSI codes ─────────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[97m"
GRAY    = "\033[90m"
ORANGE  = "\033[38;5;208m"


def _cfg(key: str):
    """Read local config value (lazy import to avoid circular deps)."""
    try:
        from . import config_manager
        return config_manager.get(key)
    except Exception:
        from .config_manager import DEFAULTS
        return DEFAULTS[key][0]


def _is_mono() -> bool:
    return _cfg("theme") == "monochrome"


def _c(*codes: str) -> str:
    """Return ANSI codes or empty string in monochrome mode."""
    return "" if _is_mono() else "".join(codes)


def stat_color(value: float) -> str:
    if _is_mono():
        return ""
    v = int(value)
    if v >= 75: return GREEN
    if v >= 50: return YELLOW
    if v >= 25: return ORANGE
    return RED


def stat_bar(label: str, value: float, width: int = 22) -> str:
    v      = int(value)
    filled = v * width // 100
    color  = stat_color(value)
    bar    = "█" * filled + "░" * (width - filled)
    reset  = _c(RESET)
    bold   = _c(BOLD)
    return f"  {bold}{label:<10}{reset} {color}[{bar}] {v:3d}%{reset}"


# ── ASCII art (config-aware) ───────────────────────────────────────────────────

def get_pet_ascii(pet: PetState) -> str:
    style = _cfg("ascii_style")
    if style == "emoji":
        icon = {
            "ecstatic": "😸", "happy": "😺", "okay": "😼", "sad": "😿",
            "miserable": "🙀", "sleeping": "😴", "on_fire": "🔥😺", "ghost": "👻",
        }.get(pet.mood_label, "🐱")
        return f"\n   {icon}\n"
    if style == "minimal":
        return _ascii_minimal(pet.mood_label)
    # standard (default)
    return {
        "ecstatic":  _ascii_ecstatic,
        "happy":     _ascii_happy,
        "okay":      _ascii_okay,
        "sad":       _ascii_sad,
        "miserable": _ascii_miserable,
        "sleeping":  _ascii_sleeping,
        "on_fire":   _ascii_on_fire,
        "ghost":     _ascii_ghost,
    }.get(pet.mood_label, _ascii_okay)()


def _ascii_minimal(label: str) -> str:
    faces = {
        "ecstatic": "^o^", "happy": "^.^", "okay": "-.-",
        "sad": "T.T", "miserable": ";_;", "sleeping": "z.z",
        "on_fire": ">^<", "ghost": "x.x",
    }
    return f"\n  /\\_/\\\n ({faces.get(label, '...')})\n   ~\n"


def _ascii_ecstatic() -> str:
    return f"{_c(GREEN)}\n    /\\_/\\  \n   ( ^o^ )~*\n    > ~ <  *\n   /|   |\\\n  (_|   |_){_c(RESET)}"
def _ascii_happy() -> str:
    return f"{_c(CYAN)}\n    /\\_/\\  \n   ( ^.^ ) \n    > ~ <  \n   /|   |\\\n  (_|   |_){_c(RESET)}"
def _ascii_okay() -> str:
    return f"{_c(YELLOW)}\n    /\\_/\\  \n   ( -.- ) \n    > ~ <  \n   /|   |\\\n  (_|   |_){_c(RESET)}"
def _ascii_sad() -> str:
    return f"{_c(MAGENTA)}\n    /\\_/\\  \n   ( T.T ) \n    > ~ <  \n   /|   |\\\n  (_|   |_){_c(RESET)}"
def _ascii_miserable() -> str:
    return f"{_c(RED)}\n    /\\_/\\  \n   ( ;_; )  .\n    >   <   .\n   /|   |\\ .\n  (_|   |_){_c(RESET)}"
def _ascii_sleeping() -> str:
    return f"{_c(BLUE)}\n    /\\_/\\  \n   ( z.z )  z\n    > ~ <   \n   /|   |\\\n  (_|   |_){_c(RESET)}"
def _ascii_on_fire() -> str:
    return f"{_c(ORANGE)}\n    /\\_/\\  \n   (>^.^<) 🔥\n    > ~ <  🔥\n   /|   |\\\n  (_|   |_){_c(RESET)}"
def _ascii_ghost() -> str:
    return f"{_c(DIM)}{_c(GRAY)}\n    .--.    \n   (x.x)   \n    ~~~~   \n   /~~~~\\\n  (~~~~~~){_c(RESET)}"


def egg_hatch_frames() -> List[str]:
    return [
        f"{_c(YELLOW)}      _____  \n     /     \\ \n    |       |\n     \\_____/ {_c(RESET)}",
        f"{_c(YELLOW)}      _____  \n     / * * \\ \n    |   *   |\n     \\_ * _/ {_c(RESET)}",
        f"{_c(YELLOW)}      _____  \n     / ~~~ \\ \n    |  ~~~  |\n     \\ ~~~ / {_c(RESET)}",
        f"{_c(YELLOW)}     *  *  * \n      \\|/   \n      ---   {_c(RESET)}",
        f"{_c(CYAN)}    /\\_/\\   \n   ( ^.^ ) !!!\n    > ~ <  \n   /|   |\\ \n  (_|   |_){_c(RESET)}",
    ]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mood_color(label: str) -> str:
    if _is_mono(): return ""
    return {
        "ecstatic": GREEN,  "happy":     CYAN,
        "okay":     YELLOW, "sad":       MAGENTA,
        "miserable":RED,    "sleeping":  BLUE,
        "on_fire":  ORANGE, "ghost":     GRAY,
    }.get(label, RESET)


def _time_ago(iso_str: str) -> str:
    if not iso_str: return "never"
    try:
        delta   = datetime.now() - datetime.fromisoformat(iso_str)
        minutes = int(delta.total_seconds() / 60)
    except (ValueError, TypeError):
        return "?"
    if minutes < 2:   return "just now"
    if minutes < 60:  return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:    return f"{hours}h ago"
    return f"{hours // 24}d ago"


# ── Full status panel ──────────────────────────────────────────────────────────

def print_status(pet: PetState) -> None:
    is_dead = not pet.alive
    border  = _c(GRAY) if is_dead else _c(WHITE)
    reset   = _c(RESET)
    bold    = _c(BOLD)
    dim     = _c(DIM)

    # Effective display name (local override or official)
    try:
        from . import config_manager
        display_name = config_manager.effective_name(pet.name)
    except Exception:
        display_name = pet.name

    print()
    print(f"{bold}{border}  ╔══════════════ TamaGit ══════════════╗{reset}")
    print(f"{bold}{border}  ║{reset}  {bold}Name  :{reset}  {display_name}")
    if display_name != pet.name:
        print(f"{bold}{border}  ║{reset}  {bold}(official):{reset}  {dim}{pet.name}{reset}")
    print(f"{bold}{border}  ║{reset}  {bold}Age   :{reset}  {pet.age_days} day(s)")
    mc = _mood_color(pet.mood_label)
    print(f"{bold}{border}  ║{reset}  {bold}State :{reset}  {mc}{pet.mood_label}{reset}")
    if pet.streak_days > 0:
        fire = "🔥" if pet.streak_days >= 7 else "📅"
        sc   = _c(ORANGE) if pet.streak_days >= 7 else _c(CYAN)
        print(f"{bold}{border}  ║{reset}  {bold}Streak:{reset}  {sc}{fire} {pet.streak_days} day(s){reset}")
    if pet.last_fed_by:
        print(f"{bold}{border}  ║{reset}  {bold}Fed by:{reset}  {dim}{pet.last_fed_by} ({_time_ago(pet.last_fed_at)}){reset}")
    if pet.github_repo:
        print(f"{bold}{border}  ║{reset}  {bold}Repo  :{reset}  {dim}{pet.github_repo}{reset}")
    print(f"{bold}{border}  ╚══════════════════════════════════════╝{reset}")
    print()

    if _cfg("show_ascii"):
        print(get_pet_ascii(pet))
        print()

    if is_dead:
        _print_death_panel(pet)
    else:
        _print_alive_panel(pet)


def _print_alive_panel(pet: PetState) -> None:
    reset = _c(RESET)
    bold  = _c(BOLD)
    dim   = _c(DIM)

    if _cfg("show_stats"):
        print(stat_bar("Hunger",  pet.hunger))
        print(stat_bar("Energy",  pet.energy))
        print(stat_bar("Mood",    pet.mood))
        print(stat_bar("Health",  pet.health))
        print()

    if _cfg("show_repos") and pet.git_repos:
        print(f"  {bold}Tracked Repos:{reset}")
        for key, info in pet.git_repos.items():
            branch   = info.get("branch", "?")
            dirty    = info.get("is_dirty", False)
            unpushed = info.get("unpushed", 0)
            unpulled = info.get("unpulled", 0)
            scanned  = info.get("last_scanned_at", "")
            dirty_s  = f"{_c(ORANGE)}⚠  dirty{reset}" if dirty else f"{_c(GREEN)}✅ clean{reset}"
            push_s   = f"  {_c(RED)}↑{unpushed} unpushed{reset}" if unpushed else ""
            pull_s   = f"  {_c(YELLOW)}↓{unpulled} behind{reset}" if unpulled else ""
            short    = key.split("/")[-1] if "/" in key else key
            print(f"    {dim}{short}{reset} ({branch})  {dirty_s}{push_s}{pull_s}  {dim}scanned {_time_ago(scanned)}{reset}")
        print()

    if _cfg("show_quest") and pet.daily_quest_text:
        from datetime import date
        if pet.daily_quest_date == date.today().isoformat():
            progress = f"{pet.daily_commit_count if pet.daily_quest_trigger=='commit_count' else pet.daily_issue_count if pet.daily_quest_trigger=='issue_count' else pet.daily_pr_count}/{pet.daily_quest_threshold}"
            if pet.daily_quest_done:
                print(f"  {bold}🎯 Team Quest:{reset}  {_c(GREEN)}✅ {pet.daily_quest_text}{reset}")
            else:
                print(f"  {bold}🎯 Team Quest:{reset}  {_c(YELLOW)}{pet.daily_quest_text}{reset}  {dim}[{progress}]{reset}")
            print()

    if _cfg("show_achievements"):
        cnt = len(pet.achievements)
        if cnt > 0:
            pct_bar = "█" * (cnt * 10 // TOTAL_ACHIEVEMENTS) + "░" * (10 - cnt * 10 // TOTAL_ACHIEVEMENTS)
            print(f"  🏆 {_c(YELLOW)}{cnt}/{TOTAL_ACHIEVEMENTS}{reset} achievements  {dim}[{pct_bar}]  tamagit achievements{reset}")
            print()

    if _cfg("show_events") and pet.events_log:
        print(f"  {bold}Recent events:{reset}")
        for entry in pet.events_log[-5:]:
            print(f"    {dim}{entry}{reset}")
        print()

    print(f"  {dim}status · log · scan · achievements · graveyard · live · help{reset}")
    print()


def _print_death_panel(pet: PetState) -> None:
    reset = _c(RESET)
    bold  = _c(BOLD)
    dim   = _c(DIM)
    red   = _c(RED)
    green = _c(GREEN)
    gray  = _c(GRAY)

    print(f"  {red}{bold}💀  Your team pet has died.{reset}")
    print(f"  {dim}Reason: {pet.death_reason}{reset}")
    print()
    print(f"  {bold}The team must complete these tasks before a new pet hatches:{reset}")

    def task_line(done: bool, label: str, progress: str) -> str:
        icon = f"{green}✅{reset}" if done else f"{gray}☐ {reset}"
        return f"    {icon}  {label}  {dim}[{progress}]{reset}"

    print(task_line(pet.cooldown_commits >= 3, "Make 3 commits",  f"{pet.cooldown_commits}/3"))
    print(task_line(pet.cooldown_issues >= 1,  "Close 1 issue",   f"{pet.cooldown_issues}/1"))
    print(task_line(pet.cooldown_ci_ok >= 1,   "CI success once", f"{pet.cooldown_ci_ok}/1"))
    print()
    if pet.cooldown_done:
        print(f"  {green}{bold}All tasks done — new pet will hatch on next GitHub event!{reset}")
    else:
        remaining = []
        if pet.cooldown_commits < 3: remaining.append(f"{3 - pet.cooldown_commits} commit(s)")
        if pet.cooldown_issues < 1:  remaining.append("close 1 issue")
        if pet.cooldown_ci_ok < 1:   remaining.append("1 CI success")
        print(f"  {dim}Still needed: {', '.join(remaining)}.{reset}")
    print()
    print(f"  {dim}When done, the server auto-creates a new pet. Run 'tamagit sync'.{reset}")
    print(f"  {dim}Run 'tamagit graveyard' to see all fallen pets.{reset}")
    print()


def print_graveyard(entries: List[GraveyardEntry]) -> None:
    reset = _c(RESET)
    bold  = _c(BOLD)
    dim   = _c(DIM)
    gray  = _c(GRAY)
    red   = _c(RED)
    yellow= _c(YELLOW)

    print()
    print(f"{bold}{gray}  ══════════════ ⚰  Graveyard  ⚰ ══════════════{reset}")
    print()
    if not entries:
        print(f"  {dim}No pets have died yet. Keep committing!{reset}")
        print()
        return
    tombstone = ["    .------.", "    | R.I.P |", "    |_______|", "   /         \\", "  |___________|"]
    for i, e in enumerate(entries, 1):
        for line in tombstone:
            print(f"  {dim}{gray}{line}{reset}")
        born = e.born_at[:10] if e.born_at else "?"
        died = e.died_at[:10] if e.died_at else "?"
        print(f"  {bold}{e.name}{reset}  {dim}(lived {e.age_days} day(s)){reset}")
        print(f"  {dim}{born}  →  {died}{reset}")
        print(f"  \"{red}{e.death_reason}{reset}\"")
        if e.achievements:
            print(f"  {yellow}{', '.join(e.achievements[:4])}{reset}")
        if i < len(entries): print()
    print()
    print(f"  {dim}Total fallen: {len(entries)}{reset}")
    print()


def get_prompt_string(pet: PetState) -> str:
    """One-line string for embedding in PS1. Respects prompt_format config."""
    try:
        from . import config_manager
        display_name = config_manager.effective_name(pet.name)
        fmt = config_manager.get("prompt_format")
    except Exception:
        display_name = pet.name
        fmt = "full"

    if not pet.alive:
        return f"{_c(GRAY)}[{display_name}(x.x) DEAD]{_c(RESET)}"

    icon_map = {
        "ecstatic": "^o^", "happy": "^.^", "okay": "-.-",
        "sad": "T.T", "miserable": ";_;", "sleeping": "z.z",
        "on_fire": ">^<", "ghost": "x.x",
    }
    icon  = icon_map.get(pet.mood_label, "...")
    avg   = (pet.hunger + pet.energy + pet.mood) / 3
    color = stat_color(avg)
    reset = _c(RESET)

    h, e, m, hp = int(pet.hunger), int(pet.energy), int(pet.mood), int(pet.health)

    if fmt == "minimal":
        return f"{color}{icon}{reset}"
    if fmt == "compact":
        return f"{color}[{display_name}({icon}) {int(avg)}%]{reset}"
    # full (default): show all four stats including health
    return f"{color}[{display_name}({icon}) H:{h} E:{e} M:{m} ❤:{hp}]{reset}"


# ── Ghost messages ─────────────────────────────────────────────────────────────
_GHOST_LINES = [
    "you abandoned me...", "the CI was always red...",
    "you never merged that PR...", "boo. make some commits.",
    "I haunt your git log.", "I just wanted clean issues...",
    "commit. at least once a week.", "even /dev/null got more attention.",
    "my issues are still open.", "the pipeline is still broken.",
]


def maybe_ghost_message(pet: PetState) -> str | None:
    if pet.alive or random.random() > 0.30:
        return None
    msg = random.choice(_GHOST_LINES)
    return f"\n  {_c(DIM)}{_c(GRAY)}~(*-*)~ {pet.name}: {msg}{_c(RESET)}\n"
