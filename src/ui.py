from __future__ import annotations

import random
from datetime import datetime
from typing import List

from .models import GraveyardEntry, PetState

# ── ANSI коды ──────────────────────────────────────────────────────────────────
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
ORANGE  = "\033[38;5;208m"   # 256-цветный оранжевый


# ── 4-уровневая цветовая схема (0–100, больше = лучше) ───────────────────────
def stat_color(value: float) -> str:
    v = int(value)
    if v >= 75:
        return GREEN
    if v >= 50:
        return YELLOW
    if v >= 25:
        return ORANGE
    return RED


# ── Прогресс-бар ──────────────────────────────────────────────────────────────
def stat_bar(label: str, value: float, width: int = 22) -> str:
    v      = int(value)
    filled = v * width // 100
    empty  = width - filled
    color  = stat_color(value)
    bar    = "█" * filled + "░" * empty
    return f"  {BOLD}{label:<10}{RESET} {color}[{bar}] {v:3d}%{RESET}"


# ── ASCII арт по настроению ───────────────────────────────────────────────────
# Всего 8 состояний: ecstatic, happy, okay, sad, miserable,
#                    sleeping, on_fire (streak≥7), ghost (мёртв)

def get_pet_ascii(pet: PetState) -> str:
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


def _ascii_ecstatic() -> str:
    return (
        f"{GREEN}\n"
        "    /\\_/\\  \n"
        "   ( ^o^ )  ~*\n"
        "    > ~ <   *\n"
        "   /|   |\\\n"
        f"  (_|   |_){RESET}"
    )

def _ascii_happy() -> str:
    return (
        f"{CYAN}\n"
        "    /\\_/\\  \n"
        "   ( ^.^ ) \n"
        "    > ~ <  \n"
        "   /|   |\\\n"
        f"  (_|   |_){RESET}"
    )

def _ascii_okay() -> str:
    return (
        f"{YELLOW}\n"
        "    /\\_/\\  \n"
        "   ( -.- ) \n"
        "    > ~ <  \n"
        "   /|   |\\\n"
        f"  (_|   |_){RESET}"
    )

def _ascii_sad() -> str:
    return (
        f"{MAGENTA}\n"
        "    /\\_/\\  \n"
        "   ( T.T ) \n"
        "    > ~ <  \n"
        "   /|   |\\\n"
        f"  (_|   |_){RESET}"
    )

def _ascii_miserable() -> str:
    return (
        f"{RED}\n"
        "    /\\_/\\  \n"
        "   ( ;_; )  .\n"
        "    >   <   .\n"
        "   /|   |\\ .\n"
        f"  (_|   |_){RESET}"
    )

def _ascii_sleeping() -> str:
    # Питомец засыпает после 12+ часов без активности
    return (
        f"{BLUE}\n"
        "    /\\_/\\  \n"
        "   ( z.z )  z z\n"
        "    > ~ <    z\n"
        "   /|   |\\\n"
        f"  (_|   |_){RESET}"
    )

def _ascii_on_fire() -> str:
    # Особое состояние при streak ≥ 7 дней + хорошие статы
    return (
        f"{GREEN}\n"
        "    /\\_/\\  \n"
        "   (>^.^<)  🔥\n"
        "    > ~ <  🔥\n"
        "   /|   |\\\n"
        f"  (_|   |_){RESET}"
    )

def _ascii_ghost() -> str:
    # После смерти питомец становится призраком
    return (
        f"{DIM}{GRAY}\n"
        "    .--.    \n"
        "   (x.x)   \n"
        "    ~~~~   \n"
        "   /~~~~\\\n"
        f"  (~~~~~~){RESET}"
    )


# ── Кадры анимации вылупления из яйца (для tamagit init) ─────────────────────
def egg_hatch_frames() -> List[str]:
    return [
        f"{YELLOW}      _____  \n     /     \\ \n    |       |\n     \\_____/ {RESET}",
        f"{YELLOW}      _____  \n     / * * \\ \n    |   *   |\n     \\_ * _/ {RESET}",
        f"{YELLOW}      _____  \n     / ~~~ \\ \n    |  ~~~  |\n     \\ ~~~ / {RESET}",
        f"{YELLOW}     *  *  * \n      \\|/   \n      ---   {RESET}",
        f"{CYAN}    /\\_/\\   \n   ( ^.^ ) !!!\n    > ~ <  \n   /|   |\\ \n  (_|   |_){RESET}",
    ]


# ── Вспомогательная функция ───────────────────────────────────────────────────
def _mood_color(label: str) -> str:
    return {
        "ecstatic":  GREEN,
        "happy":     CYAN,
        "okay":      YELLOW,
        "sad":       MAGENTA,
        "miserable": RED,
        "sleeping":  BLUE,
        "on_fire":   ORANGE,
        "ghost":     GRAY,
    }.get(label, RESET)


def _time_ago(iso_str: str) -> str:
    """Конвертирует ISO timestamp в читаемый формат типа '2h ago'."""
    if not iso_str:
        return "never"
    try:
        delta = datetime.now() - datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return "?"
    minutes = int(delta.total_seconds() / 60)
    if minutes < 2:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


# ── Полная панель статуса ─────────────────────────────────────────────────────
def print_status(pet: PetState) -> None:
    is_dead = not pet.alive
    border  = GRAY if is_dead else WHITE

    # ── Шапка ─────────────────────────────────────────────────────────────────
    print()
    print(f"{BOLD}{border}  ╔══════════════ TamaGit ══════════════╗{RESET}")
    print(f"{BOLD}{border}  ║{RESET}  {BOLD}Name  :{RESET}  {pet.name}")
    print(f"{BOLD}{border}  ║{RESET}  {BOLD}Age   :{RESET}  {pet.age_days} day(s)")

    # Состояние с цветом
    mc = _mood_color(pet.mood_label)
    print(f"{BOLD}{border}  ║{RESET}  {BOLD}State :{RESET}  {mc}{pet.mood_label}{RESET}")

    # Streak — только если больше 0
    if pet.streak_days > 0:
        fire = "🔥" if pet.streak_days >= 7 else "📅"
        sc   = ORANGE if pet.streak_days >= 7 else CYAN
        print(f"{BOLD}{border}  ║{RESET}  {BOLD}Streak:{RESET}  {sc}{fire} {pet.streak_days} day(s) in a row{RESET}")

    # Кто последний кормил питомца (командная механика)
    if pet.last_fed_by:
        ago = _time_ago(pet.last_fed_at)
        print(f"{BOLD}{border}  ║{RESET}  {BOLD}Fed by:{RESET}  {DIM}{pet.last_fed_by} ({ago}){RESET}")

    if pet.github_repo:
        print(f"{BOLD}{border}  ║{RESET}  {BOLD}Repo  :{RESET}  {DIM}{pet.github_repo}{RESET}")

    print(f"{BOLD}{border}  ╚══════════════════════════════════════╝{RESET}")
    print()

    # ── ASCII арт ─────────────────────────────────────────────────────────────
    print(get_pet_ascii(pet))
    print()

    if is_dead:
        _print_death_panel(pet)
    else:
        _print_alive_panel(pet)


def _print_alive_panel(pet: PetState) -> None:
    # Прогресс-бары статов
    print(stat_bar("Hunger",  pet.hunger))
    print(stat_bar("Energy",  pet.energy))
    print(stat_bar("Mood",    pet.mood))
    print(stat_bar("Health",  pet.health))
    print()

    # Состояние отслеживаемых репозиториев
    if pet.git_repos:
        print(f"  {BOLD}Tracked Repos:{RESET}")
        for repo_key, info in pet.git_repos.items():
            branch   = info.get("branch", "?")
            dirty    = info.get("is_dirty", False)
            unpushed = info.get("unpushed", 0)
            scanned  = info.get("last_scanned_at", "")

            dirty_icon  = f"{ORANGE}⚠  dirty{RESET}"  if dirty    else f"{GREEN}✅ clean{RESET}"
            push_warn   = f"  {RED}↑{unpushed} unpushed{RESET}" if unpushed else ""
            scanned_str = _time_ago(scanned) if scanned else "never"

            # Показываем только имя папки, чтобы не обрезать длинные пути
            short_key = repo_key.split("/")[-1] if "/" in repo_key else repo_key
            print(f"    {DIM}{short_key}{RESET} ({branch})  {dirty_icon}{push_warn}  {DIM}scanned {scanned_str}{RESET}")
        print()

    # Ежедневное задание
    from datetime import date
    if pet.daily_quest_text and pet.daily_quest_date == date.today().isoformat():
        if pet.daily_quest_done:
            print(f"  {BOLD}🎯 Daily Quest:{RESET}  {GREEN}✅ {pet.daily_quest_text}{RESET}")
        else:
            print(f"  {BOLD}🎯 Daily Quest:{RESET}  {YELLOW}{pet.daily_quest_text}{RESET}  {DIM}[in progress]{RESET}")
        print()

    # Ачивки
    if pet.achievements:
        print(f"  {YELLOW}{BOLD}Achievements:{RESET}")
        for a in pet.achievements:
            print(f"    🏆  {a}")
        print()

    # Последние события
    if pet.events_log:
        print(f"  {BOLD}Recent events:{RESET}")
        for entry in pet.events_log[-5:]:
            print(f"    {DIM}{entry}{RESET}")
        print()

    print(f"  {DIM}Commands: status · log · scan · graveyard · help{RESET}")
    print()


def _print_death_panel(pet: PetState) -> None:
    print(f"  {RED}{BOLD}💀  Your team pet has died.{RESET}")
    print(f"  {DIM}Reason: {pet.death_reason}{RESET}")
    print()
    print(f"  {BOLD}Team must complete these tasks to adopt a new pet:{RESET}")

    def task_line(done: bool, label: str, progress: str) -> str:
        icon = f"{GREEN}✅{RESET}" if done else f"{GRAY}☐ {RESET}"
        return f"    {icon}  {label}  {DIM}[{progress}]{RESET}"

    print(task_line(pet.cooldown_commits >= 3, "Make 3 commits",  f"{pet.cooldown_commits}/3"))
    print(task_line(pet.cooldown_issues >= 1,  "Close 1 issue",   f"{pet.cooldown_issues}/1"))
    print(task_line(pet.cooldown_ci_ok >= 1,   "CI success once", f"{pet.cooldown_ci_ok}/1"))
    print()

    if pet.cooldown_done:
        print(f"  {GREEN}{BOLD}All tasks done!  Run: tamagit init{RESET}")
    else:
        remaining = []
        if pet.cooldown_commits < 3:
            remaining.append(f"{3 - pet.cooldown_commits} commit(s)")
        if pet.cooldown_issues < 1:
            remaining.append("1 issue to close")
        if pet.cooldown_ci_ok < 1:
            remaining.append("1 CI success")
        print(f"  {DIM}Still needed: {', '.join(remaining)}.{RESET}")
    print()
    print(f"  {DIM}Run 'tamagit graveyard' to see fallen pets.{RESET}")
    print()


# ── Кладбище ──────────────────────────────────────────────────────────────────
def print_graveyard(entries: List[GraveyardEntry]) -> None:
    print()
    print(f"{BOLD}{GRAY}  ══════════════ ⚰  Graveyard  ⚰ ══════════════{RESET}")
    print()
    if not entries:
        print(f"  {DIM}No pets have died yet. Keep committing!{RESET}")
        print()
        return

    tombstone = [
        "    .------.",
        "    | R.I.P |",
        "    |_______|",
        "   /         \\",
        "  |___________|",
    ]

    for i, e in enumerate(entries, 1):
        born = e.born_at[:10] if e.born_at else "?"
        died = e.died_at[:10] if e.died_at else "?"
        for line in tombstone:
            print(f"  {DIM}{GRAY}{line}{RESET}")
        print(f"  {BOLD}{e.name}{RESET}  {DIM}(lived {e.age_days} day(s)){RESET}")
        print(f"  {DIM}{born}  →  {died}{RESET}")
        print(f"  \"{RED}{e.death_reason}{RESET}\"")
        if e.achievements:
            print(f"  {YELLOW}🏆  {', '.join(e.achievements)}{RESET}")
        if i < len(entries):
            print()

    print()
    print(f"  {DIM}Total fallen: {len(entries)}{RESET}")
    print()


# ── Строка для bash prompt ─────────────────────────────────────────────────────
def get_prompt_string(pet: PetState) -> str:
    """Однострочная строка для встраивания в PS1."""
    # Иконки для каждого настроения
    icon_map = {
        "ecstatic":  "^o^",
        "happy":     "^.^",
        "okay":      "-.-",
        "sad":       "T.T",
        "miserable": ";_;",
        "sleeping":  "z.z",
        "on_fire":   ">^<",  # возбуждённая морда для streak-режима
        "ghost":     "x.x",
    }
    if not pet.alive:
        return f"{GRAY}[{pet.name}(x.x) DEAD]{RESET}"

    icon  = icon_map.get(pet.mood_label, "...")
    avg   = (pet.hunger + pet.energy + pet.mood) / 3
    color = stat_color(avg)
    h, e, m = int(pet.hunger), int(pet.energy), int(pet.mood)
    return f"{color}[{pet.name}({icon}) H:{h} E:{e} M:{m}]{RESET}"


# ── Сообщения призрака (30% при dead-состоянии) ───────────────────────────────
_GHOST_LINES = [
    "you abandoned me...",
    "the CI was always red...",
    "you never merged that PR...",
    "boo. make some commits.",
    "I haunt your git log.",
    "I just wanted clean issues...",
    "commit. at least once a week.",
    "even /dev/null got more attention.",
    "my issues are still open.",
    "the pipeline is still broken.",
]


def maybe_ghost_message(pet: PetState) -> str | None:
    if pet.alive or random.random() > 0.30:
        return None
    msg = random.choice(_GHOST_LINES)
    return f"\n  {DIM}{GRAY}~(*-*)~ {pet.name}: {msg}{RESET}\n"
