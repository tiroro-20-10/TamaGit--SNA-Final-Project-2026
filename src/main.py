"""
TamaGit CLI entry point.

Architecture reminder (what runs WHERE):
  VPS webhook server:  apply_github_event, refresh_daily_quest, achievements, auto-init
  Local CLI:           display, config, git_repos metadata (scan), daemon sync

tamagit react  — visual reaction only (no state changes)
tamagit scan   — git_repos metadata only (no stat changes)
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.request
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

from . import config_manager
from .git_integration import collect_git_snapshot
from .models import PetState, TEAM_ACHIEVEMENTS, TOTAL_ACHIEVEMENTS, DEFAULT_PET_NAMES
from .pet_engine import apply_git_snapshot, summarize_messages, update_from_time
from .storage import Storage
from .ui import (
    BOLD, CYAN, DIM, GRAY, GREEN, MAGENTA, ORANGE, RED, RESET,
    WHITE, YELLOW,
    egg_hatch_frames, get_pet_ascii, get_prompt_string,
    maybe_ghost_message, print_graveyard, print_status, stat_bar,
)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()
    cmd    = args.command or "status"
    storage = Storage()

    # ── Commands that never need pet state ────────────────────────────────────
    if cmd == "help":      _cmd_help();                                    return
    if cmd == "setup":     _cmd_setup(storage);                            return
    if cmd == "uninstall": _cmd_uninstall();                               return
    if cmd == "server-setup": _cmd_server_setup();                         return

    if cmd == "graveyard":
        print_graveyard(storage.load_graveyard())
        return

    if cmd in ("install-prompt",):   _cmd_install_prompt();               return
    if cmd in ("uninstall-prompt",): _cmd_uninstall_prompt();             return

    if cmd == "prompt":
        _cmd_prompt(storage)
        return

    if cmd == "react":
        # Visual-only reaction to a terminal command — no state changes at all
        exit_code = getattr(args, "exit_code", 0)
        full_cmd  = getattr(args, "full_cmd",  "") or ""
        _cmd_react_visual(exit_code, full_cmd, storage)
        return

    if cmd == "config":
        subcommand = getattr(args, "config_cmd", None) or "interactive"
        _cmd_config(subcommand, getattr(args, "key", ""), getattr(args, "value", ""))
        return

    if cmd == "daemon":
        _cmd_daemon(getattr(args, "daemon_cmd", None) or "status")
        return

    if cmd == "docs":
        _cmd_docs(getattr(args, "topic", None))
        return

    if cmd == "sync":
        _cmd_sync(storage)
        return

    if cmd == "rename":
        _cmd_rename(getattr(args, "new_name", ""), storage)
        return

    if cmd == "live":
        try:
            from .tui import TamaGitApp
        except ImportError:
            print(f"\n  {RED}Textual not installed.{RESET}  Run: {BOLD}pip install textual{RESET}\n")
            return
        TamaGitApp().run()
        return

    if cmd == "init":
        _cmd_init(storage)
        return

    # ── Commands that need the pet ────────────────────────────────────────────
    if not storage.is_initialized():
        print(f"\n  {YELLOW}No pet found.  Run:{RESET} {BOLD}tamagit init{RESET}\n")
        return

    pet = storage.load()
    was_alive = pet.alive
    update_from_time(pet)

    if not pet.alive:
        ghost = maybe_ghost_message(pet)
        if ghost:
            print(ghost)

    if cmd == "status":
        print_status(pet)
    elif cmd == "log":
        _cmd_log(pet)
    elif cmd == "scan":
        _cmd_scan(pet, getattr(args, "path", "."))
    elif cmd == "achievements":
        _cmd_achievements(pet)

    if was_alive and not pet.alive:
        _print_death_notification(pet)

    storage.save(pet)


# ── Command implementations ───────────────────────────────────────────────────

def _cmd_prompt(storage: Storage) -> None:
    """Lightweight — only reads state, no decay, no save. Called from PS1."""
    if not storage.is_initialized():
        print(f"{GRAY}[TamaGit(?) run setup]{RESET}", end="")
        return
    pet = storage.load()
    print(get_prompt_string(pet), end="")


def _cmd_react_visual(exit_code: int, full_cmd: str, storage: Storage) -> None:
    """Show a face + comment reaction to a terminal command.

    IMPORTANT: This function does NOT modify any pet state.
    State changes come only from webhook events (VPS side).
    The only purpose here is visual feedback for the developer.
    """
    full_cmd = full_cmd.strip()
    if not full_cmd:
        return

    parts   = full_cmd.split()
    first   = parts[0]
    git_sub = parts[1] if first == "git" and len(parts) > 1 else ""

    _BORING = {
        "ls","ll","la","l","cd","pwd","echo","cat","clear","history","man",
        "tamagit","which","whoami","exit","source","export","alias","true",
        "false","","code","nano","vim","vi","less","more",
    }
    if first in _BORING:
        return

    # Read pet for the face icon — but never write anything back
    if storage.is_initialized():
        pet = storage.load()
        if not pet.alive:
            ghost = maybe_ghost_message(pet)
            if ghost:
                print(ghost)
            return
        face_label = pet.mood_label
    else:
        face_label = "happy"

    face = _mood_face(face_label)

    if exit_code == 0 and random.random() < 0.35:
        msg = _pick_praise(first, git_sub)
        if msg:
            print(f"\n  {CYAN}{face}{RESET}  {DIM}{msg}{RESET}")
    elif exit_code != 0 and random.random() < 0.55:
        msg = _pick_roast(first, git_sub)
        if msg:
            print(f"\n  {MAGENTA}{face}{RESET}  {DIM}{msg}{RESET}")


def _cmd_init(storage: Storage) -> None:
    """Hatch a new team pet. Can only be run on the VPS (or by the admin)."""
    if storage.is_initialized():
        pet = storage.load()
        if pet.alive:
            print(f"\n  {YELLOW}Team already has a living pet!{RESET}")
            print(f"  Run {BOLD}tamagit status{RESET} to see them.\n")
            return
        if not pet.cooldown_done:
            print(f"\n  {RED}{BOLD}Pet is dead. Team must complete cooldown first:{RESET}\n")
            print_status(pet)
            return
        # Cooldown done — bury and continue
        entry = storage.bury(pet)
        storage.delete_state()
        print(f"\n  {GRAY}{DIM}{entry.name} laid to rest in the graveyard.{RESET}")
        time.sleep(1.2)

    # Ask for custom name pool (optional)
    print(f"\n  {BOLD}TamaGit — New Team Pet{RESET}")
    print(f"  {DIM}The pet will be automatically named after death/resurrection.{RESET}")
    raw = input(
        f"\n  Enter custom name pool for auto-naming (comma-separated, or Enter for defaults):\n  > "
    ).strip()
    custom_names = [n.strip() for n in raw.split(",") if n.strip()] if raw else []

    # Ask for GitHub token (for contextual features + webhook auto-creation)
    token = input(
        f"\n  GitHub token (for initial stats + auto-webhook creation, or Enter to skip):\n  > "
    ).strip()

    repo = input(f"\n  GitHub repo to watch (owner/name):\n  > ").strip()

    # Hatch animation
    hatch_msgs = ["...", "Something is moving inside...", "The shell is cracking!", "It's hatching!!!", ""]
    for frame, msg in zip(egg_hatch_frames(), hatch_msgs):
        _clear()
        print(f"\n  {BOLD}TamaGit — Team Pet{RESET}\n")
        print(frame)
        if msg: print(f"\n  {DIM}{msg}{RESET}")
        time.sleep(0.9)

    # Compute realistic initial stats via GitHub API
    initial_stats = {"hunger": 80.0, "energy": 80.0, "mood": 80.0, "health": 100.0}
    if token and repo and "/" in repo:
        print(f"\n  {DIM}Checking repo health via GitHub API...{RESET}")
        try:
            from .github_api import compute_initial_stats
            owner, repo_name = repo.split("/", 1)
            initial_stats = compute_initial_stats(owner, repo_name, token)
            _show_initial_stat_warning(initial_stats)
        except Exception as exc:
            print(f"  {YELLOW}API error ({exc}) — using default stats{RESET}")

    # Choose a name
    pool = custom_names if custom_names else DEFAULT_PET_NAMES
    name = random.choice(pool)

    pet = PetState(
        name=name,
        github_repo=repo,
        custom_pet_names=custom_names,
        **{k: v for k, v in initial_stats.items()},
    )
    storage.save(pet)

    _clear()
    print(f"\n  {GREEN}{BOLD}Welcome, {name}!{RESET}")
    print(f"  Repo: {repo or '(not set)'}")
    avg = (pet.hunger + pet.energy + pet.mood) / 3
    if avg < 30:
        print(f"  {RED}⚠  The repo is in rough shape — pet starts weak. Fix things fast!{RESET}")
    print(f"\n  {DIM}Set up the GitHub webhook so {name} reacts to the team's commits.{RESET}")
    print(f"  {DIM}Run: tamagit docs webhook{RESET}\n")
    print_status(pet)


def _show_initial_stat_warning(stats: dict) -> None:
    avg = (stats["hunger"] + stats["energy"] + stats["mood"]) / 3
    if avg < 20:
        print(f"  {RED}⚠  Repo is severely neglected — pet will start very weak!{RESET}")
    elif avg < 40:
        print(f"  {YELLOW}⚠  Repo needs attention — pet starts in poor shape.{RESET}")
    else:
        print(f"  {GREEN}Repo looks healthy — pet starts in good shape.{RESET}")


def _cmd_setup(storage: Storage) -> None:
    """First-time wizard for local developer setup."""
    print(f"\n  {BOLD}{WHITE}TamaGit — Local Setup Wizard{RESET}")
    print(f"  {'─' * 38}\n")

    # Step 1: VPS URL
    existing = config_manager.effective_vps_url()
    prompt   = f"  Team VPS URL [{existing or 'none'}]: " if existing else "  Team VPS URL: "
    vps_url  = input(prompt).strip() or existing
    if not vps_url:
        print(f"  {YELLOW}No VPS URL provided. You can set it later: tamagit config set vps_url <url>{RESET}\n")
    else:
        vps_url = vps_url.rstrip("/")
        print(f"  Testing connection... ", end="", flush=True)
        try:
            resp = urllib.request.urlopen(f"{vps_url}/health", timeout=5)
            data = json.loads(resp.read())
            if data.get("status") == "ok":
                print(f"{GREEN}✅ Connected{RESET}")
                config_manager.set_("vps_url", vps_url)
                _cmd_sync(storage)
            else:
                print(f"{RED}❌ Unexpected response{RESET}")
        except Exception as exc:
            print(f"{RED}❌ Cannot connect ({exc}){RESET}")
            print(f"  {DIM}Continuing without connection — set later with: tamagit config set vps_url{RESET}")

    # Step 2: Prompt
    ans = input(f"\n  Add TamaGit to bash prompt? [Y/n]: ").strip().lower()
    if ans != "n":
        _cmd_install_prompt()

    # Step 3: Daemon
    ans = input(f"\n  Start background sync daemon? [Y/n]: ").strip().lower()
    if ans != "n":
        try:
            from . import daemon as _d
            print(f"  {GREEN}{_d.start()}{RESET}")
        except Exception as exc:
            print(f"  {YELLOW}Could not start daemon: {exc}{RESET}")

    print(f"\n  {GREEN}{BOLD}Setup complete!{RESET}")
    print(f"  Try: tamagit status  |  tamagit live  |  tamagit help\n")


def _cmd_server_setup() -> None:
    """Server-side setup wizard. Run on the VPS after cloning."""
    print(f"\n  {BOLD}{WHITE}TamaGit — Server Setup Wizard{RESET}")
    print(f"  {'─' * 38}\n")
    print(f"  {DIM}Run this once on your VPS to configure the webhook server.{RESET}\n")

    github_repo  = input("  GitHub repo (owner/name): ").strip()
    github_token = input("  GitHub token (for webhook creation + API features): ").strip()
    server_ip    = input("  This server's public IP or domain: ").strip()
    port         = input("  Port [8000]: ").strip() or "8000"

    webhook_url    = f"http://{server_ip}:{port}/webhook/github"
    webhook_secret = _generate_secret()

    # Write .env
    env_path = Path("/opt/TamaGit/.env")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        f"GITHUB_REPO={github_repo}\n"
        f"GITHUB_TOKEN={github_token}\n"
        f"GITHUB_WEBHOOK_SECRET={webhook_secret}\n"
        f"TAMAGIT_VPS_URL=http://{server_ip}:{port}\n"
        f"TAMAGIT_SYNC_INTERVAL=10\n"
        f"TAMAGIT_SCAN_INTERVAL=30\n",
        encoding="utf-8",
    )
    print(f"\n  {GREEN}✅ .env written{RESET}")

    # Start docker compose
    print(f"  Starting webhook server...", end="", flush=True)
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "up", "-d", "--build", "webhook"],
            capture_output=True, text=True, cwd="/opt/TamaGit",
        )
        if result.returncode == 0:
            print(f" {GREEN}✅ Started{RESET}")
        else:
            print(f" {YELLOW}⚠  {result.stderr.strip()[:80]}{RESET}")
    except Exception as exc:
        print(f" {YELLOW}⚠  {exc}{RESET}")

    # Test health endpoint
    time.sleep(2)
    print(f"  Testing /health...", end="", flush=True)
    try:
        resp = urllib.request.urlopen(f"http://localhost:{port}/health", timeout=5)
        print(f" {GREEN}✅ OK{RESET}")
    except Exception:
        print(f" {YELLOW}⚠  Server might still be starting{RESET}")

    # Create GitHub webhook via API
    if github_token and "/" in github_repo:
        print(f"  Creating GitHub webhook...", end="", flush=True)
        try:
            from .github_api import create_webhook, GithubAPIError
            owner, repo_name = github_repo.split("/", 1)
            create_webhook(owner, repo_name, github_token, webhook_url, webhook_secret)
            print(f" {GREEN}✅ Webhook created{RESET}")
        except Exception as exc:
            print(f" {YELLOW}⚠  {exc}{RESET}")
            print(f"  {DIM}Create manually: GitHub → repo → Settings → Webhooks{RESET}")
            print(f"  {DIM}URL: {webhook_url}  |  Secret: {webhook_secret}{RESET}")
    else:
        print(f"\n  {YELLOW}No token — create webhook manually:{RESET}")
        print(f"  URL:    {webhook_url}")
        print(f"  Secret: {webhook_secret}")

    print(f"\n  {GREEN}{BOLD}Server ready!{RESET}")
    print(f"  Share with team: {BOLD}TAMAGIT_VPS_URL=http://{server_ip}:{port}{RESET}")
    print(f"\n  Next: {BOLD}tamagit init{RESET}  (hatch your team pet)\n")


def _cmd_uninstall() -> None:
    """Remove all TamaGit data, daemon, and .bashrc modifications."""
    print(f"\n  {BOLD}TamaGit Uninstall{RESET}")
    state_dir = Path("~/.tamagit").expanduser()
    print(f"\n  This will permanently delete:")
    print(f"    • {state_dir}/ (state, graveyard, logs, config)")
    print(f"    • TamaGit block from ~/.bashrc")
    print(f"    • Background daemon (if running)")
    confirm = input(f"\n  Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print(f"\n  {YELLOW}Cancelled.{RESET}\n")
        return

    # Stop daemon
    try:
        from . import daemon as _d
        msg = _d.stop()
        print(f"  {GREEN}{msg}{RESET}")
    except Exception:
        pass

    # Remove ~/.tamagit/
    import shutil
    if state_dir.exists():
        shutil.rmtree(state_dir)
        print(f"  {GREEN}Removed {state_dir}/{RESET}")

    # Remove .bashrc block
    _cmd_uninstall_prompt()

    print(f"\n  {GREEN}Done!{RESET}")
    print(f"  To finish: {BOLD}pip uninstall tamagit{RESET}  then  {BOLD}source ~/.bashrc{RESET}\n")


def _cmd_log(pet: PetState) -> None:
    print(f"\n{BOLD}  Full event history:{RESET}")
    if not pet.events_log:
        print(f"  {DIM}Nothing yet...{RESET}\n")
        return
    for entry in pet.events_log:
        print(f"  {DIM}{entry}{RESET}")
    print()


def _cmd_scan(pet: PetState, path: str) -> None:
    """Scan local git repo — updates ONLY git_repos metadata, no stat changes."""
    snapshot = collect_git_snapshot(Path(path))
    messages = apply_git_snapshot(pet, snapshot)

    print()
    if snapshot.is_repo:
        dirty_str = f"{ORANGE}⚠  dirty{RESET}" if snapshot.is_dirty else f"{GREEN}✅ clean{RESET}"
        print(f"  {BOLD}Scan:{RESET}  {snapshot.repo_root}")
        print(f"  Branch: {snapshot.branch}   {dirty_str}")
        if snapshot.last_commit_hash:
            print(f"  Last commit: {snapshot.last_commit_hash[:8]}  {DIM}{snapshot.last_commit_subject or ''}{RESET}")
        if snapshot.upstream_available and (snapshot.unpushed_commits or snapshot.unpulled_commits):
            print(f"  {YELLOW}Unpushed: {snapshot.unpushed_commits}  Unpulled: {snapshot.unpulled_commits}{RESET}")
        elif not snapshot.upstream_available:
            print(f"  {DIM}Upstream: not configured{RESET}")
    else:
        print(f"  {YELLOW}Not a git repository:{RESET}  {snapshot.error}")

    print(f"\n  {BOLD}Scan results (metadata only):{RESET}")
    print(summarize_messages(messages))
    print(f"  {DIM}Note: stat changes happen via GitHub webhook, not locally.{RESET}")
    print()


def _cmd_achievements(pet: PetState) -> None:
    cnt = len(pet.achievements)
    print(f"\n  {BOLD}Team Achievements  {YELLOW}{cnt}/{TOTAL_ACHIEVEMENTS}{RESET}\n")
    for name, desc in TEAM_ACHIEVEMENTS.items():
        done = name in pet.achievements
        icon = f"{GREEN}✅{RESET}" if done else f"{GRAY}☐ {RESET}"
        print(f"    {icon}  {BOLD}{name}{RESET}  {DIM}{desc}{RESET}")
    if pet.quests_completed:
        print(f"\n  {DIM}Team quests completed: {pet.quests_completed}{RESET}")
    print()


def _cmd_rename(new_name: str, storage: Storage) -> None:
    """Rename the pet — local alias only (in ~/.tamagit/config.json).

    If you want to rename the official pet name on the VPS, SSH there
    and run 'tamagit rename <name>' which updates the server's local_name,
    or use the PUT /state/name endpoint directly.
    """
    new_name = new_name.strip()
    if not new_name:
        print(f"\n  {YELLOW}Usage: tamagit rename <name>{RESET}\n")
        return
    config_manager.set_("local_name", new_name)
    print(f"\n  {GREEN}Local name set to '{new_name}'{RESET}")
    print(f"  {DIM}This name is only visible in your terminal.{RESET}")
    print(f"  {DIM}Official name on the server is unchanged.{RESET}\n")


def _cmd_sync(storage: Storage) -> None:
    vps_url = config_manager.effective_vps_url()
    if not vps_url:
        print(f"\n  {YELLOW}TAMAGIT_VPS_URL not configured.{RESET}")
        print(f"  Run: {BOLD}tamagit config set vps_url http://...:8000{RESET}\n")
        return
    try:
        resp    = urllib.request.urlopen(f"{vps_url}/state", timeout=5)
        data    = json.loads(resp.read().decode())
        vps_pet = PetState.from_dict(data)

        # Merge: VPS stats + local git_repos metadata
        if storage.is_initialized():
            local_pet = storage.load()
            vps_pet.git_repos   = local_pet.git_repos
            all_events = list(dict.fromkeys(vps_pet.events_log + local_pet.events_log))
            vps_pet.events_log  = all_events[-30:]

        storage.save(vps_pet)
        print(f"{GREEN}Synced!{RESET} {vps_pet.name} alive={vps_pet.alive} H={int(vps_pet.hunger)}")
    except Exception as exc:
        print(f"{RED}Sync failed:{RESET} {exc}")


def _print_death_notification(pet: PetState) -> None:
    print(f"\n  {RED}{BOLD}{'─' * 42}{RESET}")
    print(f"  {RED}{BOLD}💀  {pet.name} has just died.{RESET}")
    print(f"  {DIM}Reason: {pet.death_reason}{RESET}")
    print(f"  {DIM}Team must complete cooldown. Server will auto-hatch a new pet.{RESET}")
    print(f"  {RED}{BOLD}{'─' * 42}{RESET}\n")


# ── Config command ─────────────────────────────────────────────────────────────

def _cmd_config(subcommand: str, key: str = "", value: str = "") -> None:
    if subcommand == "set":
        if not key:
            print(f"\n  {YELLOW}Usage: tamagit config set <key> <value>{RESET}\n")
            return
        ok = config_manager.set_(key, value)
        if ok:
            print(f"  {GREEN}Set {key} = {value}{RESET}")
        else:
            print(f"  {YELLOW}Unknown key: {key}{RESET}")
            print(f"  Run {BOLD}tamagit config list{RESET} to see valid keys.")

    elif subcommand == "get":
        val = config_manager.get(key)
        print(f"  {key} = {val}")

    elif subcommand == "list":
        print(f"\n  {BOLD}Local Config (~/.tamagit/config.json):{RESET}\n")
        vals = config_manager.all_values()
        for k, (default, desc) in config_manager.DEFAULTS.items():
            cur = vals[k]
            marker = "" if cur == default else f" {YELLOW}(modified){RESET}"
            print(f"  {CYAN}{k:<22}{RESET}  {cur!s:<12}  {DIM}{desc}{RESET}{marker}")
        print()

    elif subcommand == "reset":
        config_manager.reset()
        print(f"  {GREEN}Config reset to defaults.{RESET}")

    else:
        # Interactive menu
        _cmd_config_interactive()


def _cmd_config_interactive() -> None:
    """Simple text-based interactive config menu (no Textual dependency)."""
    keys_ordered = list(config_manager.DEFAULTS.keys())
    while True:
        print(f"\n  {BOLD}TamaGit — Local Settings{RESET}")
        print(f"  {'─' * 38}")
        vals = config_manager.all_values()
        for i, k in enumerate(keys_ordered, 1):
            default, desc = config_manager.DEFAULTS[k]
            cur = vals[k]
            modified = f" {YELLOW}*{RESET}" if cur != default else ""
            print(f"  {i:2}. {CYAN}{k:<22}{RESET}  {cur!s:<12}{modified}")
        print()
        print(f"  r = reset all  |  q = quit")
        choice = input("  Number to change: ").strip().lower()
        if choice == "q":
            break
        if choice == "r":
            config_manager.reset()
            print(f"  {GREEN}Reset to defaults.{RESET}")
            continue
        try:
            idx = int(choice) - 1
            k   = keys_ordered[idx]
            default, desc = config_manager.DEFAULTS[k]
            print(f"\n  {k}: {desc}")
            print(f"  Current: {vals[k]}  |  Default: {default}")
            new_val = input(f"  New value (Enter to keep): ").strip()
            if new_val:
                config_manager.set_(k, new_val)
                print(f"  {GREEN}Saved.{RESET}")
        except (ValueError, IndexError):
            print(f"  {YELLOW}Invalid choice.{RESET}")


# ── Daemon command ─────────────────────────────────────────────────────────────

def _cmd_daemon(subcommand: str) -> None:
    from . import daemon as _d
    if subcommand == "start":
        print(f"\n  {GREEN}{_d.start()}{RESET}\n")
    elif subcommand == "stop":
        print(f"\n  {YELLOW}{_d.stop()}{RESET}\n")
    elif subcommand == "restart":
        print(f"\n  {YELLOW}{_d.stop()}{RESET}")
        time.sleep(0.5)
        print(f"  {GREEN}{_d.start()}{RESET}\n")
    elif subcommand == "logs":
        lines = _d.tail_logs(40)
        if not lines:
            print(f"\n  {DIM}No logs yet.{RESET}\n")
            return
        print(f"\n{BOLD}  Daemon logs:{RESET}")
        for line in lines:
            if "ERROR" in line:    color = RED
            elif "OK" in line or "Done" in line: color = GREEN
            else:                   color = ""
            print(f"  {color}{DIM}{line}{RESET}")
        print()
    else:  # status
        s = _d.get_status()
        if s["running"]:
            print(f"\n  {GREEN}{BOLD}Daemon is running{RESET} (PID {s['pid']})")
            print(f"  {DIM}sync every {config_manager.get('sync_interval')} min  "
                  f"• scan every {config_manager.get('scan_interval')} min{RESET}\n")
        else:
            print(f"\n  {YELLOW}Daemon is not running.{RESET}")
            print(f"  Start with: {BOLD}tamagit daemon start{RESET}\n")


# ── Help & docs ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    print(f"\n  {BOLD}{WHITE}TamaGit — Terminal Team Tamagotchi for GitHub{RESET}")
    print(f"  {DIM}Your pet lives through the team's git activity.{RESET}\n")

    cmds = [
        ("setup",            "First-time wizard for local users"),
        ("server-setup",     "First-time wizard for VPS (run on server)"),
        ("init",             "Hatch a new team pet (run on server)"),
        ("status",           "Show full status panel"),
        ("log",              "Show all event history"),
        ("scan [PATH]",      "Scan local git repo (metadata only, no stat changes)"),
        ("achievements",     "Show all team achievements"),
        ("graveyard",        "View all fallen pets"),
        ("rename <name>",    "Set local name alias for the pet"),
        ("live",             "Live animated TUI in a separate terminal"),
        ("sync",             "Fetch pet state from VPS"),
        ("daemon start",     "Start background daemon (auto-sync + auto-scan)"),
        ("daemon stop/status/logs", "Manage daemon"),
        ("config",           "Interactive local config editor"),
        ("config set k v",   "Set config value (scriptable)"),
        ("config list",      "List all config values"),
        ("install-prompt",   "Add pet to bash prompt"),
        ("uninstall-prompt", "Remove pet from bash prompt"),
        ("uninstall",        "Remove all TamaGit data and config"),
        ("docs [TOPIC]",     "Built-in documentation"),
        ("help",             "This help"),
    ]
    print(f"  {BOLD}Commands:{RESET}")
    for c, d in cmds:
        print(f"    {CYAN}{c:<32}{RESET}  {d}")

    print(f"\n  {BOLD}Team pet mechanics:{RESET}")
    events = [
        (GREEN, "✅", "git push/commit",     "Hunger ↑  Mood ↑  Streak +1"),
        (GREEN, "✅", "PR merged",           "Health +15  Energy +10  Mood +10"),
        (GREEN, "✅", "Issue closed",        "Mood +15  Hunger +5"),
        (GREEN, "✅", "CI passes",           "Health +10  Energy +5"),
        (RED,   "❌", "CI fails",            "Health −20  Energy −10  (ci_failed flag set)"),
        (RED,   "❌", "No activity (days)",  "All stats decay → Health drops → death"),
    ]
    for color, icon, trigger, effect in events:
        print(f"    {icon}  {color}{trigger:<24}{RESET}  {DIM}{effect}{RESET}")

    print(f"\n  {BOLD}Health:{RESET}")
    print(f"    Rises when avg(H,E,M) ≥ 60   Falls fast when avg < 30")
    print(f"    {GREEN}CI pass +10{RESET}  {GREEN}PR merge +15{RESET}  {RED}CI fail −20{RESET}")

    print(f"\n  {BOLD}Stats (0 = critical, 100 = excellent):{RESET}")
    print(f"    {GREEN}75–100{RESET} Excellent  {YELLOW}50–74{RESET} Good  {ORANGE}25–49{RESET} Warning  {RED}0–24{RESET} Critical\n")


_DOCS: dict[str, str] = {
    "mechanics": f"""
{BOLD}TamaGit — Pet Mechanics{RESET}

Pet lives on VPS, reacts to GitHub events via webhook.
Local machine shows state via sync/daemon.

{BOLD}VPS side (webhook handler):{RESET}
  - Stat changes (hunger, energy, mood, health)
  - Streak, achievements, daily quest
  - Auto-resurrect after cooldown

{BOLD}Local side (CLI):{RESET}
  - Display (tamagit status, live, prompt)
  - Git repo metadata scan (dirty/unpushed)
  - Config preferences (name alias, theme, etc.)
""",
    "scan": f"""
{BOLD}tamagit scan — what it does{RESET}

Updates ONLY git_repos metadata in state.json:
  is_dirty, dirty_since, unpushed, unpulled, last_commit_hash

Does NOT change hunger/energy/mood/streak — that's the webhook's job.

{BOLD}Dirty repo penalty:{RESET}
  - First 2 hours: no penalty
  - After 2 hours: mood falls 0.5 per hour
  - On commit: dirty_since resets, penalty stops

{BOLD}Auto-scan via daemon:{RESET}
  tamagit daemon start    (default: every 30 min)
""",
    "quest": f"""
{BOLD}Team Daily Quest{RESET}

Generated on VPS on the first GitHub event of each day.
All team members see the same quest (via sync).

{BOLD}Available quests:{RESET}
  Make 5 commits as a team today
  Close 3 open issues today        (only if 3+ exist)
  Merge 2 pull requests today      (only if 2+ open)
  Fix the broken CI pipeline       (only if CI failing)
  Review and merge a pull request
  Make 10 commits as a team today

{BOLD}Reward on completion:{RESET}  Mood +25, Hunger +15, Energy +10
""",
    "death": f"""
{BOLD}Death & Resurrection{RESET}

When health → 0, pet dies. Ghost mode begins.

{BOLD}Cooldown tasks (tracked via webhook on VPS):{RESET}
  ☐  Make 3 commits
  ☐  Close 1 issue
  ☐  Get CI green once

After all three: {BOLD}server auto-creates a new pet{RESET} on the next event.
  - Name: randomly chosen from pool
  - Stats: based on cooldown performance
  - GitHub issue created to notify the team

Run 'tamagit sync' to see the new pet locally.
""",
    "webhook": f"""
{BOLD}GitHub Webhook Setup{RESET}

{BOLD}Automatic (recommended):{RESET}
  ssh root@<vps>
  cd /opt/TamaGit
  tamagit server-setup

{BOLD}Manual:{RESET}
  GitHub → repo → Settings → Webhooks → Add webhook
  Payload URL:  http://<vps>:8000/webhook/github
  Content type: application/json
  Secret:       value of GITHUB_WEBHOOK_SECRET from .env
  Events:       Pushes, Pull requests, Issues, Workflow runs

{BOLD}Verify:{RESET}
  curl http://<vps>:8000/health   → {{\"status\":\"ok\"}}
  docker compose logs -f webhook
""",
    "daemon": f"""
{BOLD}tamagit daemon{RESET}

Background process on the LOCAL machine.
Auto-syncs from VPS and auto-scans local repos.

  tamagit daemon start    start in background
  tamagit daemon stop     stop
  tamagit daemon status   check PID and intervals
  tamagit daemon restart  restart
  tamagit daemon logs     last 40 lines of log

{BOLD}Config (.env or tamagit config set):{RESET}
  TAMAGIT_SYNC_INTERVAL  minutes between VPS syncs  (default 10)
  TAMAGIT_SCAN_INTERVAL  minutes between repo scans (default 30)
  TAMAGIT_VPS_URL        VPS server URL
""",
    "config": f"""
{BOLD}tamagit config — local settings{RESET}

Stored in ~/.tamagit/config.json.
Never overwritten by daemon sync (server state is separate).

  tamagit config              interactive menu
  tamagit config set k v      set a value
  tamagit config get k        get a value
  tamagit config list         show all values
  tamagit config reset        restore defaults

{BOLD}Key settings:{RESET}
  local_name      personal pet alias (only in your terminal)
  vps_url         VPS server URL
  ascii_style     standard | minimal | emoji
  prompt_format   full | compact | minimal
  theme           dark | monochrome
  show_*          true/false (toggle status sections)
  sync_interval   daemon sync interval (min)
  scan_interval   daemon scan interval (min)
""",
}


def _cmd_docs(topic: str | None) -> None:
    if not topic:
        print(f"\n  {BOLD}TamaGit docs — built-in documentation{RESET}\n")
        topics = [
            ("mechanics", "How the pet works, decay, events"),
            ("scan",      "What tamagit scan does, dirty repo mechanics"),
            ("quest",     "Team daily quests — generation and tracking"),
            ("death",     "Death, cooldown, auto-resurrection"),
            ("webhook",   "GitHub webhook setup guide"),
            ("daemon",    "Background daemon for auto-sync and scan"),
            ("config",    "Local config system"),
        ]
        for t, d in topics:
            print(f"    {CYAN}tamagit docs {t:<12}{RESET}  {d}")
        print()
        return
    doc = _DOCS.get(topic)
    if not doc:
        print(f"\n  {YELLOW}Unknown topic: {topic}{RESET}  Run: tamagit docs\n")
        return
    print(doc)


# ── Prompt helpers ─────────────────────────────────────────────────────────────

def _cmd_install_prompt() -> None:
    bashrc = Path.home() / ".bashrc"
    marker = "# TAMAGIT-PROMPT"
    if bashrc.exists() and marker in bashrc.read_text(encoding="utf-8"):
        print(f"{YELLOW}TamaGit prompt already installed.{RESET}")
        return
    snippet = """
# TAMAGIT-PROMPT — TamaGit team pet in bash prompt
if command -v tamagit &> /dev/null; then
    if [[ -z "${__TAMAGIT_ORIG_PS1+x}" ]]; then
        export __TAMAGIT_ORIG_PS1="$PS1"
    fi
    __tamagit_prompt() {
        local _exit=$?
        local _last_cmd
        _last_cmd=$(HISTTIMEFORMAT= history 1 2>/dev/null | sed 's/^[[:space:]]*[0-9]*[[:space:]]*//')
        if [[ -n "$_last_cmd" ]]; then
            tamagit react "$_exit" "$_last_cmd" 2>/dev/null
        fi
        local _pet
        _pet=$(tamagit prompt 2>/dev/null)
        if [[ -n "$_pet" ]]; then
            PS1="${_pet} ${__TAMAGIT_ORIG_PS1:-\\$ }"
        else
            PS1="${__TAMAGIT_ORIG_PS1:-\\$ }"
        fi
    }
    case "$PROMPT_COMMAND" in
        *__tamagit_prompt*) ;;
        *) PROMPT_COMMAND="${PROMPT_COMMAND:+${PROMPT_COMMAND}; }__tamagit_prompt" ;;
    esac
fi
# END-TAMAGIT-PROMPT
"""
    with open(bashrc, "a", encoding="utf-8") as f:
        f.write(snippet)
    print(f"{GREEN}Prompt installed!{RESET}  Run: {BOLD}source ~/.bashrc{RESET}")
    print(f"  {DIM}Pet added before your existing prompt (not replacing it).{RESET}")


def _cmd_uninstall_prompt() -> None:
    bashrc = Path.home() / ".bashrc"
    start, end = "# TAMAGIT-PROMPT", "# END-TAMAGIT-PROMPT"
    if not bashrc.exists() or start not in bashrc.read_text(encoding="utf-8"):
        print(f"{YELLOW}TamaGit prompt not installed.{RESET}")
        return
    lines  = bashrc.read_text(encoding="utf-8").splitlines(keepends=True)
    result, skip = [], False
    for line in lines:
        if start in line:  skip = True
        if not skip:       result.append(line)
        if end   in line:  skip = False
    bashrc.write_text("".join(result), encoding="utf-8")
    print(f"{GREEN}Prompt removed.{RESET}  Run: {BOLD}source ~/.bashrc{RESET}")


# ── React helpers (visual only) ────────────────────────────────────────────────

def _mood_face(label: str) -> str:
    return {
        "ecstatic": "( ^o^ )", "happy":     "( ^.^ )",
        "okay":     "( -.- )", "sad":       "( T.T )",
        "miserable":"( ;_; )", "sleeping":  "( z.z )",
        "on_fire":  "(>^.^<)", "ghost":     "( x.x )",
    }.get(label, "( ... )")


_PRAISE: dict[tuple, list] = {
    ("git","push"):   ["pushed! team pet is fed ✓", "remote updated, nom nom!", "commits delivered!"],
    ("git","commit"): ["new commit! pet noticed ✓", "saved to history!", "pet is pleased"],
    ("git","pull"):   ["synced! team keeps moving", "pulled! good habit"],
    ("git","merge"):  ["merged! health bonus incoming"],
    ("docker",""):    ["container running! 🐋"],
    ("pytest",""):    ["tests green! pet loves clean code 🧪", "all tests passed!"],
}
_ROAST: dict[tuple, list] = {
    ("git","push"):   ["push rejected... fix and retry", "nothing made it to remote"],
    ("git","commit"): ["nothing to commit? stage something first"],
    ("git","pull"):   ["pull failed... conflicts? 😿"],
    ("git","merge"):  ["merge conflict... pet is stressed"],
    ("docker",""):    ["docker error. pet is worried 🐋"],
    ("pytest",""):    ["tests failed. fix before committing 😿"],
}
_GP = ["clean exit! pet approves", "good work noted", "pet purrs ✓"]
_GR = ["error... pet felt that", "non-zero exit", "command failed"]


def _pick_praise(first: str, git_sub: str) -> str:
    pool = _PRAISE.get((first, git_sub)) or _PRAISE.get((first, ""))
    return random.choice(pool) if pool else random.choice(_GP)


def _pick_roast(first: str, git_sub: str) -> str:
    pool = _ROAST.get((first, git_sub)) or _ROAST.get((first, ""))
    return random.choice(pool) if pool else random.choice(_GR)


def _generate_secret(length: int = 32) -> str:
    import secrets
    return secrets.token_hex(length)


def _clear() -> None:
    print("\033[2J\033[H", end="")


# ── Argument parser ────────────────────────────────────────────────────────────

def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="tamagit",
        description=(
            "TamaGit — Terminal Team Tamagotchi for GitHub\n\n"
            "Quick start (local user):\n"
            "  tamagit setup\n\n"
            "Quick start (server admin):\n"
            "  tamagit server-setup\n"
            "  tamagit init\n"
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("setup",            help="First-time local setup wizard")
    sub.add_parser("server-setup",     help="First-time server setup wizard")
    sub.add_parser("init",             help="Hatch new team pet (run on server)")
    sub.add_parser("status",           help="Show status panel")
    sub.add_parser("log",              help="Show event history")
    sub.add_parser("achievements",     help="Show all achievements")
    sub.add_parser("graveyard",        help="View fallen pets")
    sub.add_parser("live",             help="Open live animated TUI")
    sub.add_parser("sync",             help="Fetch state from VPS")
    sub.add_parser("install-prompt",   help="Add pet to bash prompt")
    sub.add_parser("uninstall-prompt", help="Remove pet from bash prompt")
    sub.add_parser("uninstall",        help="Remove all TamaGit data and config")
    sub.add_parser("help",             help="Show help")
    sub.add_parser("prompt",           help="One-line status for PS1 (internal)")

    rename_p = sub.add_parser("rename", help="Set local name alias")
    rename_p.add_argument("new_name", nargs="?", default="")

    scan_p = sub.add_parser("scan", help="Scan local git repo (metadata only)")
    scan_p.add_argument("path", nargs="?", default=".")

    docs_p = sub.add_parser("docs", help="Built-in docs (tamagit docs [topic])")
    docs_p.add_argument("topic", nargs="?", default=None)

    cfg_p = sub.add_parser("config", help="Local config (interactive or scripted)")
    cfg_p.add_argument("config_cmd", nargs="?", default=None,
                       choices=["set","get","list","reset"])
    cfg_p.add_argument("key",   nargs="?", default="")
    cfg_p.add_argument("value", nargs="?", default="")

    daemon_p   = sub.add_parser("daemon", help="Background daemon")
    daemon_sub = daemon_p.add_subparsers(dest="daemon_cmd")
    for sc in ("start","stop","status","restart","logs"):
        daemon_sub.add_parser(sc)

    react_p = sub.add_parser("react", help="Visual reaction to a terminal command (internal)")
    react_p.add_argument("exit_code", type=int)
    react_p.add_argument("full_cmd",  nargs="?", default="")

    return parser


if __name__ == "__main__":
    main()
