from __future__ import annotations

import random
import sys
import time
from argparse import ArgumentParser
from pathlib import Path

from .git_integration import collect_git_snapshot
from .models import PetState
from .pet_engine import (
    apply_git_snapshot, get_or_refresh_daily_quest,
    summarize_messages, try_complete_quest, update_from_time, update_streak,
)
from .storage import Storage
from .ui import (
    BOLD, CYAN, DIM, GRAY, GREEN, MAGENTA, ORANGE, RED, RESET,
    WHITE, YELLOW,
    egg_hatch_frames, get_pet_ascii, get_prompt_string,
    maybe_ghost_message, print_graveyard, print_status, stat_bar,
)


# ── Точка входа ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    command = args.command or "status"

    storage = Storage()

    # Команды, которые не требуют состояния питомца или очень лёгкие
    if command == "prompt":
        _cmd_prompt(storage)
        return

    if command == "help":
        _cmd_help()
        return

    if command == "graveyard":
        print_graveyard(storage.load_graveyard())
        return

    if command == "install-prompt":
        _cmd_install_prompt()
        return

    if command == "uninstall-prompt":
        _cmd_uninstall_prompt()
        return

    if command == "init":
        _cmd_init(storage)
        return

    # react — лёгкая команда без decay, вызывается из bash PROMPT_COMMAND
    if command == "react":
        exit_code = getattr(args, "exit_code", 0)
        full_cmd  = getattr(args, "full_cmd", "") or ""
        _cmd_react(storage, exit_code, full_cmd)
        return

    # live — запускает Textual TUI в текущем терминале
    if command == "live":
        _cmd_live()
        return

    # Все остальные команды требуют живого (или мёртвого) питомца
    if not storage.is_initialized():
        print(f"\n  {YELLOW}No pet yet.  Run:{RESET} {BOLD}tamagit init{RESET}\n")
        return

    pet = storage.load()
    was_alive = pet.alive
    update_from_time(pet)

    # Если питомец мёртв — показываем призрака случайно
    if not pet.alive:
        ghost = maybe_ghost_message(pet)
        if ghost:
            print(ghost)

    # Для команд отображения — обновляем квест на сегодня
    if command in ("status",) and pet.alive:
        get_or_refresh_daily_quest(pet)

    if command == "status":
        print_status(pet)
    elif command == "log":
        _cmd_log(pet)
    elif command == "scan":
        _cmd_scan(pet, getattr(args, "path", "."))

    # Объявляем о смерти, если это только что произошло
    if was_alive and not pet.alive:
        _print_death_notification(pet)

    storage.save(pet)


# ── Реализации команд ─────────────────────────────────────────────────────────

def _cmd_live() -> None:
    """Запускает Textual live TUI — анимированный питомец в реальном времени.

    Требует textual (уже в зависимостях).
    Нажми Q для выхода, R для принудительного обновления.
    """
    try:
        from .tui import TamaGitApp
    except ImportError:
        print(f"\n  {RED}Textual не установлен.{RESET}")
        print(f"  Установи: {BOLD}pip install textual{RESET}\n")
        return
    TamaGitApp().run()


def _cmd_prompt(storage: Storage) -> None:
    """Лёгкий режим: только читаем state, не запускаем decay, не сохраняем.

    Вызывается каждый раз при отображении bash prompt, поэтому должен быть быстрым.
    """
    if not storage.is_initialized():
        print(f"{GRAY}[TamaGit(?)]{RESET}", end="")
        return
    pet = storage.load()
    print(get_prompt_string(pet), end="")


def _cmd_react(storage: Storage, exit_code: int, full_cmd: str) -> None:
    """Реагирует на команду в терминале (вызывается из bash PROMPT_COMMAND).

    Логика:
    - Не реагирует на скучные команды (ls, cd, tamagit и т.д.)
    - С вероятностью 35% хвалит при успехе, 55% подкалывает при ошибке
    - При git push/commit обновляет streak и проверяет квест
    - Сохраняет state только если что-то изменилось (не при каждом промпте)
    """
    if not storage.is_initialized():
        return

    full_cmd = full_cmd.strip()
    if not full_cmd:
        return

    parts   = full_cmd.split()
    first   = parts[0]
    git_sub = parts[1] if first == "git" and len(parts) > 1 else ""

    # Игнорируем неинтересные команды
    _BORING = {
        "ls", "ll", "la", "l", "cd", "pwd", "echo", "cat", "clear",
        "history", "man", "tamagit", "which", "whoami", "exit",
        "source", "export", "alias", "true", "false", "", "code",
        "nano", "vim", "vi", "less", "more",
    }
    if first in _BORING:
        return

    pet = storage.load()

    # Ghost — показываем призрака вместо обычной реакции
    if not pet.alive:
        ghost = maybe_ghost_message(pet)
        if ghost:
            print(ghost)
        return

    # ── Реакция питомца ───────────────────────────────────────────────────────
    if exit_code == 0 and random.random() < 0.35:
        msg = _pick_praise(first, git_sub)
        if msg:
            face = _mood_face(pet.mood_label)
            print(f"\n  {CYAN}{face}{RESET}  {DIM}{msg}{RESET}")

    elif exit_code != 0 and random.random() < 0.55:
        msg = _pick_roast(first, git_sub)
        if msg:
            face = _mood_face("sad")
            print(f"\n  {MAGENTA}{face}{RESET}  {DIM}{msg}{RESET}")

    # ── Обновление streak и квеста при успешных git командах ─────────────────
    changed = False
    if exit_code == 0:
        trigger = _cmd_to_trigger(first, git_sub)

        # Streak считаем только за push и commit
        if trigger in ("git_push", "git_commit"):
            update_streak(pet)
            pet.last_activity_at = __import__("datetime").datetime.now().isoformat()
            changed = True

        # Проверяем квест
        if trigger:
            get_or_refresh_daily_quest(pet)
            if try_complete_quest(pet, trigger):
                changed = True
                print(f"\n  {GREEN}🎯 Daily quest complete! Mood and Hunger boosted!{RESET}")

    if changed:
        storage.save(pet)


def _cmd_init(storage: Storage) -> None:
    """Вылупляет нового питомца или усыновляет после cooldown."""
    if storage.is_initialized():
        pet = storage.load()

        if pet.alive:
            print(f"\n  {YELLOW}Your team already has a living pet!{RESET}")
            print(f"  Run {BOLD}tamagit status{RESET} to see them.\n")
            return

        if not pet.cooldown_done:
            print(f"\n  {RED}{BOLD}The pet is dead. Complete the team tasks first:{RESET}\n")
            print_status(pet)
            return

        # Cooldown пройден — хороним и начинаем заново
        entry = storage.bury(pet)
        storage.delete_state()
        print(f"\n  {GRAY}{DIM}{entry.name} has been laid to rest in the graveyard.{RESET}")
        time.sleep(1.2)

    # ── Анимация вылупления ───────────────────────────────────────────────────
    hatch_msgs = [
        "...",
        "Something is moving inside...",
        "The shell is cracking!",
        "It's hatching!!!",
        "",
    ]
    for frame, msg in zip(egg_hatch_frames(), hatch_msgs):
        _clear()
        print(f"\n  {BOLD}TamaGit — New Team Pet{RESET}\n")
        print(frame)
        print()
        if msg:
            print(f"  {DIM}{msg}{RESET}")
        time.sleep(0.9)

    # ── Настройка ─────────────────────────────────────────────────────────────
    print()
    name = input(f"  {BOLD}Give your team pet a name:{RESET} ").strip() or "TamaGit"
    repo = input(f"  {BOLD}GitHub repo to watch (owner/name):{RESET} ").strip()

    pet = PetState(name=name, github_repo=repo)
    storage.save(pet)

    _clear()
    print(f"\n  {GREEN}{BOLD}Welcome, {name}!{RESET}")
    print(f"  Watching: {repo or '(no repo configured)'}")
    print(f"\n  {DIM}Configure the GitHub webhook so {name} reacts to team commits.{RESET}")
    print(f"  {DIM}See docs/deploy_vps.md for instructions.{RESET}\n")
    print_status(pet)


def _cmd_log(pet: PetState) -> None:
    print(f"\n{BOLD}  Full event history:{RESET}")
    if not pet.events_log:
        print(f"  {DIM}Nothing has happened yet...{RESET}\n")
        return
    for entry in pet.events_log:
        print(f"  {DIM}{entry}{RESET}")
    print()


def _cmd_scan(pet: PetState, path: str) -> None:
    snapshot = collect_git_snapshot(Path(path))
    messages = apply_git_snapshot(pet, snapshot)

    print()
    if snapshot.is_repo:
        dirty_str = f"{ORANGE}⚠  dirty{RESET}" if snapshot.is_dirty else f"{GREEN}✅ clean{RESET}"
        print(f"  {BOLD}Git scan:{RESET}  {snapshot.repo_root}")
        print(f"  Branch:   {snapshot.branch}   {dirty_str}")
        if snapshot.last_commit_hash:
            short = snapshot.last_commit_hash[:8]
            subj  = snapshot.last_commit_subject or ""
            print(f"  Last commit: {short}  {DIM}{subj}{RESET}")
        if snapshot.upstream_available:
            print(f"  Unpushed: {snapshot.unpushed_commits}  Unpulled: {snapshot.unpulled_commits}")
        else:
            print(f"  Upstream: not configured")
    else:
        print(f"  {YELLOW}Not a git repository:{RESET}  {snapshot.error}")

    print(f"\n  {BOLD}Pet reactions:{RESET}")
    print(summarize_messages(messages))
    print()
    print(stat_bar("Hunger",  pet.hunger))
    print(stat_bar("Energy",  pet.energy))
    print(stat_bar("Mood",    pet.mood))
    print(stat_bar("Health",  pet.health))
    print()


def _print_death_notification(pet: PetState) -> None:
    print(f"\n  {RED}{BOLD}{'─' * 42}{RESET}")
    print(f"  {RED}{BOLD}💀  {pet.name} has just died.{RESET}")
    print(f"  {DIM}Reason: {pet.death_reason}{RESET}")
    print(f"  {DIM}Team must complete cooldown tasks, then: tamagit init{RESET}")
    print(f"  {RED}{BOLD}{'─' * 42}{RESET}\n")


def _cmd_help() -> None:
    print(f"\n  {BOLD}{WHITE}TamaGit — Terminal Team Tamagotchi for GitHub{RESET}")
    print(f"  {DIM}Your team pet lives through shared git activity.{RESET}\n")

    cmds = [
        ("init",             "Hatch a new pet, or adopt after death cooldown"),
        ("status",           "Show full status panel"),
        ("log",              "Show all event history"),
        ("scan [PATH]",      "Scan a local git repository (default: .)"),
        ("graveyard",        "View all fallen pets"),
        ("prompt",           "One-line status for bash prompt (for PS1)"),
        ("install-prompt",   "Add TamaGit to your bash prompt"),
        ("uninstall-prompt", "Remove TamaGit from bash prompt"),
        ("help",             "Show this help"),
    ]
    print(f"  {BOLD}Commands:{RESET}")
    for cmd, desc in cmds:
        print(f"    {CYAN}{cmd:<22}{RESET}  {desc}")

    print(f"\n  {BOLD}How the team pet stays alive:{RESET}")
    events = [
        (GREEN,  "✅", "git push / commit",  "Hunger ↑  Mood ↑"),
        (GREEN,  "✅", "Merge PR",           "Health ↑  Energy ↑  Mood ↑"),
        (GREEN,  "✅", "Close issue",        "Mood   ↑  Hunger ↑"),
        (GREEN,  "✅", "CI passes",          "Health ↑  Energy ↑"),
        (RED,    "❌", "CI fails",           "Health ↓  Energy ↓"),
        (RED,    "❌", "No team activity",   "All stats slowly decay → death"),
    ]
    for color, icon, trigger, effect in events:
        print(f"    {icon}  {color}{trigger:<26}{RESET}  {DIM}{effect}{RESET}")

    print(f"\n  {BOLD}Stats (0 = critical, 100 = excellent):{RESET}")
    print(
        f"    {GREEN}75–100{RESET}  Excellent   "
        f"{YELLOW}50–74{RESET}  Good   "
        f"{ORANGE}25–49{RESET}  Warning   "
        f"{RED}0–24{RESET}  Critical\n"
    )


def _cmd_install_prompt() -> None:
    bashrc  = Path.home() / ".bashrc"
    marker  = "# TAMAGIT-PROMPT"

    if bashrc.exists() and marker in bashrc.read_text(encoding="utf-8"):
        print(f"{YELLOW}TamaGit prompt already installed in ~/.bashrc{RESET}")
        return

    # Скрипт добавляет реакцию питомца на каждую команду + статус в PS1
    snippet = """
# TAMAGIT-PROMPT — TamaGit team pet in your bash prompt
if command -v tamagit &> /dev/null; then
    __tamagit_prompt() {
        local _exit=$?
        local _last_cmd
        # Читаем последнюю команду из истории
        _last_cmd=$(HISTTIMEFORMAT= history 1 2>/dev/null | sed 's/^[[:space:]]*[0-9]*[[:space:]]*//')
        # Реакция питомца на команду (streak, квест, ASCII-реакция)
        if [[ -n "$_last_cmd" ]]; then
            tamagit react "$_exit" "$_last_cmd" 2>/dev/null
        fi
        # Отображаем питомца в строке промпта
        local _status
        _status=$(tamagit prompt 2>/dev/null)
        if [[ -n "$_status" ]]; then
            PS1="${_status} \\[\\033[1;32m\\]\\u@\\h\\[\\033[0m\\]:\\[\\033[1;34m\\]\\w\\[\\033[0m\\]\\$ "
        else
            PS1="\\[\\033[1;32m\\]\\u@\\h\\[\\033[0m\\]:\\[\\033[1;34m\\]\\w\\[\\033[0m\\]\\$ "
        fi
    }
    PROMPT_COMMAND="__tamagit_prompt"
fi
# END-TAMAGIT-PROMPT
"""
    with open(bashrc, "a", encoding="utf-8") as f:
        f.write(snippet)

    print(f"{GREEN}TamaGit prompt installed!{RESET}")
    print(f"  Run: {BOLD}source ~/.bashrc{RESET}")
    print(f"  {DIM}Your prompt: [PetName(^.^) H:80 E:75 M:90] user@host:~${RESET}")


def _cmd_uninstall_prompt() -> None:
    bashrc = Path.home() / ".bashrc"
    start  = "# TAMAGIT-PROMPT"
    end    = "# END-TAMAGIT-PROMPT"

    if not bashrc.exists() or start not in bashrc.read_text(encoding="utf-8"):
        print(f"{YELLOW}TamaGit prompt is not installed.{RESET}")
        return

    lines  = bashrc.read_text(encoding="utf-8").splitlines(keepends=True)
    result, skip = [], False
    for line in lines:
        if start in line:
            skip = True
        if not skip:
            result.append(line)
        if end in line:
            skip = False

    bashrc.write_text("".join(result), encoding="utf-8")
    print(f"{GREEN}TamaGit prompt removed.{RESET}  Run: {BOLD}source ~/.bashrc{RESET}")


# ── Вспомогательные функции для react ────────────────────────────────────────

def _mood_face(label: str) -> str:
    """Маленькая морда для inline-реакций (не полный ASCII арт)."""
    return {
        "ecstatic":  "( ^o^ )",
        "happy":     "( ^.^ )",
        "okay":      "( -.- )",
        "sad":       "( T.T )",
        "miserable": "( ;_; )",
        "sleeping":  "( z.z )",
        "on_fire":   "(>^.^<)",
        "ghost":     "( x.x )",
    }.get(label, "( ... )")


def _cmd_to_trigger(first: str, git_sub: str) -> str:
    """Маппинг команды терминала → trigger для проверки квеста."""
    if first == "git":
        return {
            "commit": "git_commit",
            "push":   "git_push",
            "pull":   "git_pull",
        }.get(git_sub, "")
    if first in ("pytest", "python") and "test" in git_sub:
        return "ci_success"
    return ""


# Пулы фраз для реакций: (первая команда, git subcommand) → список фраз
_PRAISE: dict[tuple[str, str], list[str]] = {
    ("git", "push"):   [
        "pushed! team pet is fed ✓",
        "remote updated, nom nom!",
        "commits delivered! streak alive",
        "team repo synced — nice work",
    ],
    ("git", "commit"): [
        "new commit! pet is pleased",
        "saved to history! good developer",
        "commit done — pet noticed",
    ],
    ("git", "pull"):   [
        "synced! team keeps moving",
        "pulled! good habit",
        "up to date with remote",
    ],
    ("git", "merge"):  [
        "merged! pet is thriving",
        "branch united! health bonus incoming",
    ],
    ("git", "rebase"): ["rebased! clean history — pet approves"],
    ("git", "clone"):  ["cloned! new repo, new opportunities"],
    ("docker", ""):    ["container running! 🐋 pet impressed"],
    ("pytest", ""):    [
        "tests green! pet loves clean code 🧪",
        "all tests passed! pet is ecstatic",
    ],
}

_ROAST: dict[tuple[str, str], list[str]] = {
    ("git", "push"):   [
        "push rejected... fix and retry",
        "nothing made it to remote",
        "push failed. check the logs",
    ],
    ("git", "commit"): [
        "nothing to commit? stage something first",
        "commit failed. pet frowns",
    ],
    ("git", "pull"):   [
        "pull failed... conflicts? 😿",
        "sync failed. team is diverging",
    ],
    ("git", "merge"):  [
        "merge conflict... pet is stressed",
        "merge failed. resolve conflicts first",
    ],
    ("docker", ""):    ["docker error. pet is worried 🐋"],
    ("pytest", ""):    [
        "tests failed. fix before committing 😿",
        "red tests... pet is sad",
    ],
}

_GENERIC_PRAISE = [
    "clean exit! pet purrs",
    "good work! pet noticed",
    "pet approves ✓",
]

_GENERIC_ROAST = [
    "error... pet felt that",
    "non-zero exit. what happened?",
    "command failed. pet is watching",
]


def _pick_praise(first: str, git_sub: str) -> str:
    pool = _PRAISE.get((first, git_sub)) or _PRAISE.get((first, ""))
    return random.choice(pool) if pool else random.choice(_GENERIC_PRAISE)


def _pick_roast(first: str, git_sub: str) -> str:
    pool = _ROAST.get((first, git_sub)) or _ROAST.get((first, ""))
    return random.choice(pool) if pool else random.choice(_GENERIC_ROAST)


# ── Разное ────────────────────────────────────────────────────────────────────

def _clear() -> None:
    print("\033[2J\033[H", end="")


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="tamagit",
        description="TamaGit — Terminal Team Tamagotchi for GitHub",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init",             help="Hatch or adopt a new pet")
    sub.add_parser("status",           help="Show pet status panel")
    sub.add_parser("log",              help="Show event history")
    sub.add_parser("graveyard",        help="View fallen pets")
    sub.add_parser("prompt",           help="One-line status (for PS1)")
    sub.add_parser("install-prompt",   help="Add TamaGit to bash prompt")
    sub.add_parser("uninstall-prompt", help="Remove TamaGit from bash prompt")
    sub.add_parser("help",             help="Show help")

    sub.add_parser("live", help="Open live TUI (animated, real-time)")
    scan_p = sub.add_parser("scan", help="Scan a git repository")
    scan_p.add_argument("path", nargs="?", default=".", help="Path (default: .)")

    # react вызывается из bash PROMPT_COMMAND после каждой команды
    react_p = sub.add_parser("react", help="React to a terminal command (internal)")
    react_p.add_argument("exit_code", type=int, help="Exit code of previous command")
    react_p.add_argument("full_cmd",  nargs="?", default="", help="Full command string")

    return parser


if __name__ == "__main__":
    main()
