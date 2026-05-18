"""
TamaGit CLI — entry point for all user-facing commands.

Architecture reminder:
  VPS webhook server   owns: stats, streak, quest, achievements, auto-init
  Local CLI            owns: display, config prefs, git_repos metadata (scan)

tamagit react  — visual feedback ONLY, never writes state.json
tamagit scan   — updates git_repos metadata ONLY, no stat changes
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
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
    egg_hatch_frames, get_prompt_string,
    maybe_ghost_message, print_graveyard, print_status, stat_bar,
)


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()
    cmd    = args.command or "status"
    storage = Storage()

    # Commands that always work regardless of pet state
    if cmd == "help":           _cmd_help();            return
    if cmd == "graveyard":      print_graveyard(storage.load_graveyard()); return
    if cmd == "docs":           _cmd_docs(getattr(args,"topic",None)); return
    if cmd == "config":
        _cmd_config(
            getattr(args,"config_cmd",None) or "interactive",
            getattr(args,"key",""), getattr(args,"value",""),
        ); return
    if cmd == "install-prompt":   _cmd_install_prompt();   return
    if cmd == "uninstall-prompt": _cmd_uninstall_prompt(); return
    if cmd == "prompt":           _cmd_prompt(storage);    return
    if cmd == "server-setup":     _cmd_server_setup();     return
    if cmd == "setup":            _cmd_setup(storage);     return
    if cmd == "uninstall":        _cmd_uninstall();        return
    if cmd == "react":
        _cmd_react_visual(
            getattr(args,"exit_code",0),
            getattr(args,"full_cmd","") or "",
            storage,
        ); return
    if cmd == "daemon":
        _cmd_daemon(getattr(args,"daemon_cmd",None) or "status"); return
    if cmd == "rename":
        _cmd_rename(getattr(args,"new_name",""), storage); return
    if cmd == "sync":   _cmd_sync(storage); return
    if cmd == "live":
        try:
            from .tui import TamaGitApp
        except ImportError:
            print(f"\n  {RED}Textual not installed.{RESET}  Run: pip install textual\n")
            return
        TamaGitApp().run(); return
    if cmd == "init":   _cmd_init(storage); return
    if cmd == "demo":
        _cmd_demo(getattr(args,"demo_mode","status")); return

    # Commands that need pet state
    if not storage.is_initialized():
        _print_no_pet_hint(cmd); return

    pet = storage.load()
    was_alive = pet.alive
    update_from_time(pet)

    if not pet.alive:
        ghost = maybe_ghost_message(pet)
        if ghost: print(ghost)

    if cmd == "status":     print_status(pet)
    elif cmd == "log":      _cmd_log(pet)
    elif cmd == "scan":     _cmd_scan(pet, getattr(args,"path","."))
    elif cmd == "achievements": _cmd_achievements(pet)

    if was_alive and not pet.alive:
        _print_death_notification(pet)
    storage.save(pet)


# ── No-pet helper ─────────────────────────────────────────────────────────────

def _print_no_pet_hint(cmd: str) -> None:
    """Show helpful message when local state doesn't exist yet."""
    vps_url = config_manager.effective_vps_url()
    if vps_url:
        # Check if VPS has a pet
        try:
            urllib.request.urlopen(f"{vps_url}/state", timeout=3)
            # VPS has pet but local doesn't — just need to sync
            print(f"\n  {YELLOW}No local pet data.{RESET}  Run: {BOLD}tamagit sync{RESET}\n")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"\n  {RED}No pet on the server yet.{RESET}")
                print(f"  SSH to the server and run: {BOLD}tamagit init{RESET}\n")
            else:
                print(f"\n  {YELLOW}No local pet.{RESET}  Run: {BOLD}tamagit sync{RESET}\n")
        except Exception:
            print(f"\n  {YELLOW}No local pet data.{RESET}  Run: {BOLD}tamagit sync{RESET}\n")
    else:
        print(f"\n  {YELLOW}No pet found.{RESET}  Run: {BOLD}tamagit setup{RESET} or {BOLD}tamagit init{RESET}\n")


# ── Core commands ──────────────────────────────────────────────────────────────

def _cmd_prompt(storage: Storage) -> None:
    """Lightweight PS1 helper — reads state, no decay, no save."""
    if not storage.is_initialized():
        print(f"\033[90m[TamaGit(?) sync needed]\033[0m", end="")
        return
    pet = storage.load()
    print(get_prompt_string(pet), end="")


def _cmd_react_visual(exit_code: int, full_cmd: str, storage: Storage) -> None:
    """Show face + comment based on terminal command result.

    Pure display function — never reads or writes state.json.
    All game-state changes come from the VPS webhook handler.
    """
    full_cmd = full_cmd.strip()
    if not full_cmd:
        return
    parts   = full_cmd.split()
    first   = parts[0]
    git_sub = parts[1] if first == "git" and len(parts) > 1 else ""

    _BORING = {
        "ls","ll","la","l","cd","pwd","echo","cat","clear","history","man",
        "tamagit","which","whoami","exit","source","export","alias",
        "true","false","","code","nano","vim","vi","less","more",
    }
    if first in _BORING:
        return

    face_label = "happy"
    if storage.is_initialized():
        pet = storage.load()
        if not pet.alive:
            ghost = maybe_ghost_message(pet)
            if ghost: print(ghost)
            return
        face_label = pet.mood_label

    face = _mood_face(face_label)
    if exit_code == 0 and random.random() < 0.35:
        msg = _pick_praise(first, git_sub)
        if msg: print(f"\n  {CYAN}{face}{RESET}  {DIM}{msg}{RESET}")
    elif exit_code != 0 and random.random() < 0.55:
        msg = _pick_roast(first, git_sub)
        if msg: print(f"\n  {MAGENTA}{face}{RESET}  {DIM}{msg}{RESET}")


def _cmd_init(storage: Storage) -> None:
    """Hatch the team pet on the server.

    Reads GITHUB_REPO and GITHUB_TOKEN from the .env file (set by server-setup).
    Does not ask for them again — server-setup is the right place.
    """
    if storage.is_initialized():
        pet = storage.load()
        if pet.alive:
            print(f"\n  {YELLOW}Team already has a living pet!{RESET}")
            print(f"  Run {BOLD}tamagit status{RESET}\n")
            return
        if not pet.cooldown_done:
            print(f"\n  {RED}{BOLD}Pet is dead. Complete cooldown tasks first:{RESET}\n")
            print_status(pet)
            return
        entry = storage.bury(pet)
        storage.delete_state()
        print(f"\n  {GRAY}{DIM}{entry.name} laid to rest in the graveyard.{RESET}")
        time.sleep(1.2)

    # Read from .env (server-setup already configured these)
    github_repo  = os.environ.get("GITHUB_REPO",  "")
    github_token = os.environ.get("GITHUB_TOKEN", "")

    # Optional: custom name pool
    print(f"\n  {BOLD}TamaGit — Hatch a New Team Pet{RESET}")
    raw = input(
        f"\n  Custom name pool (comma-separated, or Enter for defaults):\n  > "
    ).strip()
    custom_names = [n.strip() for n in raw.split(",") if n.strip()] if raw else []

    # Hatch animation
    hatch_msgs = ["...", "Something is moving...", "The shell is cracking!", "It's hatching!!!", ""]
    for frame, msg in zip(egg_hatch_frames(), hatch_msgs):
        _clear()
        print(f"\n  {BOLD}TamaGit — Team Pet{RESET}\n"); print(frame)
        if msg: print(f"\n  {DIM}{msg}{RESET}")
        time.sleep(0.9)

    # Initial stats from GitHub API (reflects real repo health)
    initial = {"hunger": 80.0, "energy": 80.0, "mood": 80.0, "health": 100.0}
    if github_token and github_repo and "/" in github_repo:
        print(f"\n  {DIM}Checking repo health via GitHub API...{RESET}")
        try:
            from .github_api import compute_initial_stats
            owner, rname = github_repo.split("/", 1)
            initial = compute_initial_stats(owner, rname, github_token)
            avg = (initial["hunger"] + initial["energy"] + initial["mood"]) / 3
            if avg < 20:
                print(f"  {RED}⚠  Repo is severely neglected — pet starts very weak!{RESET}")
            elif avg < 40:
                print(f"  {YELLOW}⚠  Repo needs attention — pet starts in poor shape.{RESET}")
            else:
                print(f"  {GREEN}Repo looks healthy — pet starts in good shape.{RESET}")
        except Exception as exc:
            print(f"  {DIM}API check failed ({exc}) — using defaults.{RESET}")

    pool = custom_names if custom_names else DEFAULT_PET_NAMES
    name = random.choice(pool)
    pet  = PetState(name=name, github_repo=github_repo,
                    custom_pet_names=custom_names, **{k: v for k, v in initial.items()})
    storage.save(pet)

    _clear()
    print(f"\n  {GREEN}{BOLD}Welcome, {name}!{RESET}")
    print(f"  Repo: {github_repo or '(not set)'}")
    avg = (pet.hunger + pet.energy + pet.mood) / 3
    if avg < 30:
        print(f"  {RED}⚠  The repo is in rough shape — fix things fast!{RESET}")
    print()
    print_status(pet)


def _cmd_log(pet: PetState) -> None:
    print(f"\n{BOLD}  Event history:{RESET}")
    if not pet.events_log:
        print(f"  {DIM}Nothing yet...{RESET}\n"); return
    for entry in pet.events_log:
        print(f"  {DIM}{entry}{RESET}")
    print()


def _cmd_scan(pet: PetState, path: str) -> None:
    """Scan local git repo — only updates git_repos metadata."""
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

    print(f"\n  {BOLD}Results:{RESET}")
    print(summarize_messages(messages))
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
    """Set a local display name for the pet (stored in config.json).

    This is the LOCAL alias — only visible in your terminal.
    The official name lives on the server and syncs to everyone via 'tamagit sync'.
    If local_name is empty, the server's official name is shown.
    """
    new_name = new_name.strip()
    if not new_name:
        print(f"\n  {YELLOW}Usage: tamagit rename <name>{RESET}\n"); return
    config_manager.set_("local_name", new_name)
    print(f"\n  {GREEN}Name set to '{new_name}'{RESET}")
    print(f"  {DIM}Visible only in your terminal. To clear: tamagit config set local_name ''{RESET}\n")


def _cmd_sync(storage: Storage) -> None:
    """Fetch state + graveyard from VPS, merge with local git_repos."""
    vps_url = config_manager.effective_vps_url()
    if not vps_url:
        print(f"\n  {YELLOW}VPS URL not configured.{RESET}")
        print(f"  Run: {BOLD}tamagit config set vps_url http://...:8000{RESET}\n"); return
    try:
        # Fetch state
        resp    = urllib.request.urlopen(f"{vps_url}/state", timeout=8)
        data    = json.loads(resp.read().decode())
        vps_pet = PetState.from_dict(data)

        # Merge: VPS game stats + local git_repos metadata
        if storage.is_initialized():
            local_pet = storage.load()
            vps_pet.git_repos = local_pet.git_repos
            # VPS events are authoritative; append any local-only events
            vps_set = set(vps_pet.events_log)
            local_only = [e for e in local_pet.events_log if e not in vps_set]
            vps_pet.events_log = (vps_pet.events_log + local_only)[-30:]

            # Sync name: if no local override, use server's official name
            if not config_manager.get("local_name"):
                pass  # display_name = vps_pet.name already

        storage.save(vps_pet)

        # Fetch graveyard
        try:
            from .models import GraveyardEntry
            resp2   = urllib.request.urlopen(f"{vps_url}/graveyard", timeout=8)
            gdata   = json.loads(resp2.read().decode())
            entries = [GraveyardEntry.from_dict(e) for e in gdata]
            storage.save_graveyard(entries)
        except Exception:
            pass  # graveyard sync is best-effort

        print(f"{GREEN}Synced!{RESET}  {vps_pet.name}  alive={vps_pet.alive}  "
              f"H={int(vps_pet.hunger)} E={int(vps_pet.energy)} M={int(vps_pet.mood)}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"\n  {RED}No pet on server yet.{RESET}  Run 'tamagit init' on the server.\n")
        else:
            print(f"{RED}Sync failed:{RESET} HTTP {exc.code}")
    except Exception as exc:
        print(f"{RED}Sync failed:{RESET} {exc}")


def _print_death_notification(pet: PetState) -> None:
    print(f"\n  {RED}{BOLD}{'─'*42}{RESET}")
    print(f"  {RED}{BOLD}💀  {pet.name} has just died.{RESET}")
    print(f"  {DIM}Reason: {pet.death_reason}{RESET}")
    print(f"  {DIM}Complete the cooldown tasks — server auto-hatches a new pet.{RESET}")
    print(f"  {RED}{BOLD}{'─'*42}{RESET}\n")


# ── Setup wizards ──────────────────────────────────────────────────────────────

def _cmd_setup(storage: Storage) -> None:
    """First-time wizard for LOCAL developer setup."""
    print(f"\n  {BOLD}{WHITE}TamaGit — Local Setup{RESET}")
    print(f"  {'─'*38}\n")

    existing = config_manager.effective_vps_url()
    prompt   = f"  VPS URL [{existing}]: " if existing else "  VPS URL: "
    vps_url  = input(prompt).strip() or existing

    if vps_url:
        vps_url = vps_url.rstrip("/")
        print(f"  Testing connection... ", end="", flush=True)
        try:
            resp = urllib.request.urlopen(f"{vps_url}/health", timeout=5)
            data = json.loads(resp.read())
            if data.get("status") == "ok":
                print(f"{GREEN}✅ Connected{RESET}")
            config_manager.set_("vps_url", vps_url)
        except Exception as exc:
            print(f"{RED}❌ {exc}{RESET}")
            print(f"  {DIM}Continuing — set later with: tamagit config set vps_url{RESET}")

        # Check if pet exists on VPS before syncing
        try:
            urllib.request.urlopen(f"{vps_url}/state", timeout=5)
            _cmd_sync(storage)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"  {YELLOW}⚠  No pet on server yet.{RESET}")
                print(f"  {DIM}SSH to server and run: tamagit init{RESET}")
                print(f"  Continuing setup anyway...\n")
        except Exception:
            pass
    else:
        print(f"  {DIM}No VPS URL — skipping sync.{RESET}")

    ans = input(f"\n  Add TamaGit to bash prompt? [Y/n]: ").strip().lower()
    if ans != "n": _cmd_install_prompt()

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
    """One-time wizard run ON the VPS to configure the webhook server."""
    print(f"\n  {BOLD}{WHITE}TamaGit — Server Setup{RESET}")
    print(f"  {'─'*38}\n")
    print(f"  {DIM}Run this once on your VPS after cloning the repo.{RESET}\n")

    github_repo  = input("  GitHub repo (owner/name): ").strip()
    github_token = input("  GitHub token (for webhook creation + API): ").strip()
    server_ip    = input("  This server's public IP or domain: ").strip()
    port         = input("  Port [8000]: ").strip() or "8000"

    webhook_url    = f"http://{server_ip}:{port}/webhook/github"
    webhook_secret = _generate_secret()

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

    # Start Docker — show output directly (no capture_output) for reliability
    print(f"  Starting webhook server (docker output below):")
    import subprocess
    result = subprocess.run(
        ["docker", "compose", "up", "-d", "--build", "webhook"],
        cwd="/opt/TamaGit",
    )
    if result.returncode == 0:
        print(f"  {GREEN}✅ Docker started{RESET}")
    else:
        print(f"  {YELLOW}⚠  Docker returned non-zero. Check output above.{RESET}")

    # Verify
    time.sleep(2)
    print(f"  Testing /health... ", end="", flush=True)
    try:
        resp = urllib.request.urlopen(f"http://localhost:{port}/health", timeout=5)
        print(f"{GREEN}✅ OK{RESET}")
    except Exception:
        print(f"{YELLOW}⚠  Server may still be starting. Try 'curl http://localhost:{port}/health'{RESET}")

    # Create GitHub webhook via API
    if github_token and "/" in github_repo:
        print(f"  Creating GitHub webhook... ", end="", flush=True)
        try:
            from .github_api import create_webhook
            owner, rname = github_repo.split("/", 1)
            create_webhook(owner, rname, github_token, webhook_url, webhook_secret)
            print(f"{GREEN}✅ Webhook created{RESET}")
        except Exception as exc:
            print(f"{YELLOW}⚠  {exc}{RESET}")
            print(f"  {DIM}Create manually: GitHub → repo → Settings → Webhooks{RESET}")
            print(f"  URL: {webhook_url}  |  Secret: {webhook_secret}")
    else:
        print(f"\n  {YELLOW}No token — create webhook manually:{RESET}")
        print(f"  URL:    {webhook_url}\n  Secret: {webhook_secret}")

    print(f"\n  {GREEN}{BOLD}Server ready!{RESET}")
    print(f"  Share with team: {BOLD}TAMAGIT_VPS_URL=http://{server_ip}:{port}{RESET}")
    print(f"\n  Next: {BOLD}tamagit init{RESET}  (hatch the team pet)\n")


def _cmd_uninstall() -> None:
    print(f"\n  {BOLD}TamaGit Uninstall{RESET}")
    state_dir = Path("~/.tamagit").expanduser()
    print(f"\n  Will delete: {state_dir}/  •  .bashrc block  •  daemon")
    confirm = input(f"\n  Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print(f"\n  {YELLOW}Cancelled.{RESET}\n"); return

    try:
        from . import daemon as _d
        print(f"  {GREEN}{_d.stop()}{RESET}")
    except Exception:
        pass

    import shutil
    if state_dir.exists():
        shutil.rmtree(state_dir)
        print(f"  {GREEN}Removed {state_dir}/{RESET}")

    _cmd_uninstall_prompt()
    print(f"\n  {GREEN}Done!{RESET}")
    print(f"  Finish with: {BOLD}pip uninstall tamagit{RESET}  +  {BOLD}source ~/.bashrc{RESET}\n")


# ── Config ─────────────────────────────────────────────────────────────────────

def _cmd_config(subcommand: str, key: str = "", value: str = "") -> None:
    if subcommand == "set":
        if not key:
            print(f"\n  {YELLOW}Usage: tamagit config set <key> <value>{RESET}\n"); return
        ok = config_manager.set_(key, value)
        print(f"  {GREEN if ok else YELLOW}{'Set' if ok else 'Unknown key'}: {key}{' = '+value if ok else ''}{RESET}")
        if not ok: print(f"  Run {BOLD}tamagit config list{RESET}")
    elif subcommand == "get":
        print(f"  {key} = {config_manager.get(key)}")
    elif subcommand == "list":
        print(f"\n  {BOLD}Local Config (~/.tamagit/config.json):{RESET}\n")
        vals = config_manager.all_values()
        for k, (default, desc) in config_manager.DEFAULTS.items():
            cur = vals[k]
            marker = f" {YELLOW}(modified){RESET}" if cur != default else ""
            print(f"  {CYAN}{k:<24}{RESET}  {str(cur):<14}  {DIM}{desc}{RESET}{marker}")
        print()
    elif subcommand == "reset":
        config_manager.reset()
        print(f"  {GREEN}Config reset to defaults.{RESET}")
    else:
        _cmd_config_interactive()


def _cmd_config_interactive() -> None:
    keys = list(config_manager.DEFAULTS.keys())
    while True:
        print(f"\n  {BOLD}TamaGit — Local Settings{RESET}")
        print(f"  {'─'*38}")
        vals = config_manager.all_values()
        for i, k in enumerate(keys, 1):
            default, _ = config_manager.DEFAULTS[k]
            cur = vals[k]
            m = f" {YELLOW}*{RESET}" if cur != default else ""
            print(f"  {i:2}. {CYAN}{k:<24}{RESET}  {str(cur):<14}{m}")
        print(f"\n  r = reset  |  q = quit")
        choice = input("  Number to change: ").strip().lower()
        if choice == "q": break
        if choice == "r":
            config_manager.reset(); print(f"  {GREEN}Reset.{RESET}"); continue
        try:
            idx = int(choice) - 1
            k   = keys[idx]
            default, desc = config_manager.DEFAULTS[k]
            print(f"\n  {k}: {desc}")
            print(f"  Current: {vals[k]}  |  Default: {default}")
            new_val = input(f"  New value (Enter to keep): ").strip()
            if new_val:
                config_manager.set_(k, new_val); print(f"  {GREEN}Saved.{RESET}")
        except (ValueError, IndexError):
            print(f"  {YELLOW}Invalid.{RESET}")


# ── Daemon ─────────────────────────────────────────────────────────────────────

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
            print(f"\n  {DIM}No logs yet.{RESET}\n"); return
        print(f"\n{BOLD}  Daemon logs:{RESET}")
        for line in lines:
            c = RED if "ERROR" in line else (GREEN if any(w in line for w in ("OK","Done","started")) else "")
            print(f"  {c}{DIM}{line}{RESET}")
        print()
    else:  # status
        s = _d.get_status()
        if s["running"]:
            si = config_manager.get("sync_interval")
            sc = config_manager.get("scan_interval")
            print(f"\n  {GREEN}{BOLD}Daemon is running{RESET} (PID {s['pid']})")
            print(f"  {DIM}sync every {si} min  •  scan every {sc} min{RESET}\n")
        else:
            print(f"\n  {YELLOW}Daemon is not running.{RESET}")
            print(f"  Start: {BOLD}tamagit daemon start{RESET}\n")


# ── Prompt ─────────────────────────────────────────────────────────────────────

def _cmd_install_prompt() -> None:
    bashrc = Path.home() / ".bashrc"
    marker = "# TAMAGIT-PROMPT"
    if bashrc.exists() and marker in bashrc.read_text(encoding="utf-8"):
        print(f"{YELLOW}TamaGit prompt already installed.{RESET}"); return

    snippet = """
# TAMAGIT-PROMPT — TamaGit team pet in bash prompt
if command -v tamagit &> /dev/null; then
    if [[ -z "${__TAMAGIT_ORIG_PS1+x}" ]]; then
        export __TAMAGIT_ORIG_PS1="$PS1"
        export __TAMAGIT_ORIG_PC="$PROMPT_COMMAND"
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


def _cmd_uninstall_prompt() -> None:
    bashrc = Path.home() / ".bashrc"
    start, end = "# TAMAGIT-PROMPT", "# END-TAMAGIT-PROMPT"
    if not bashrc.exists() or start not in bashrc.read_text(encoding="utf-8"):
        print(f"{YELLOW}TamaGit prompt not installed.{RESET}"); return

    lines  = bashrc.read_text(encoding="utf-8").splitlines(keepends=True)
    result, skip = [], False
    for line in lines:
        if start in line:  skip = True
        if not skip:       result.append(line)
        if end   in line:  skip = False

    # Append a self-deleting cleanup block that fires on next 'source ~/.bashrc'
    cleanup = """
# TAMAGIT-CLEANUP — one-time cleanup after uninstall (self-removes)
PROMPT_COMMAND="${PROMPT_COMMAND//; __tamagit_prompt/}"
PROMPT_COMMAND="${PROMPT_COMMAND//__tamagit_prompt; /}"
PROMPT_COMMAND="${PROMPT_COMMAND//__tamagit_prompt/}"
if [[ -n "${__TAMAGIT_ORIG_PS1+x}" ]]; then
    PS1="${__TAMAGIT_ORIG_PS1}"
    unset __TAMAGIT_ORIG_PS1 __TAMAGIT_ORIG_PC
fi
unset -f __tamagit_prompt 2>/dev/null
sed -i '/# TAMAGIT-CLEANUP/,/# END-TAMAGIT-CLEANUP/d' ~/.bashrc 2>/dev/null
# END-TAMAGIT-CLEANUP
"""
    result.append(cleanup)
    bashrc.write_text("".join(result), encoding="utf-8")
    print(f"{GREEN}Prompt removed.{RESET}  Run: {BOLD}source ~/.bashrc{RESET}  (or open a new terminal)")


# ── Help & docs ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    print(f"\n  {BOLD}{WHITE}TamaGit — Terminal Team Tamagotchi for GitHub{RESET}")
    print(f"  {DIM}Your pet lives through the team's GitHub activity.{RESET}\n")
    cmds = [
        ("setup",            "First-time wizard for local developer"),
        ("server-setup",     "First-time wizard for VPS (run on server)"),
        ("init",             "Hatch the team pet (run on server after server-setup)"),
        ("status",           "Show full status panel"),
        ("log",              "Show full event history"),
        ("scan [PATH]",      "Scan local git repo (updates dirty/unpushed metadata)"),
        ("achievements",     "Show all team achievements"),
        ("graveyard",        "View all fallen pets"),
        ("rename <name>",    "Set local display name"),
        ("live",             "Live animated TUI in a separate terminal"),
        ("sync",             "Sync state + graveyard from VPS"),
        ("daemon start",     "Start background daemon (auto-sync + scan)"),
        ("daemon stop/status/restart/logs", "Manage daemon"),
        ("config",           "Interactive local config editor"),
        ("config set k v",   "Set config value"),
        ("config list",      "List all config values"),
        ("install-prompt",   "Add pet to bash prompt"),
        ("uninstall-prompt", "Remove pet from bash prompt"),
        ("uninstall",        "Remove all TamaGit data"),
        ("demo status",      "Preview all ASCII states"),
        ("demo live",        "Preview all TUI animations"),
        ("docs [TOPIC]",     "Built-in documentation"),
        ("help",             "This help"),
    ]
    print(f"  {BOLD}Commands:{RESET}")
    for c, d in cmds:
        print(f"    {CYAN}{c:<35}{RESET}  {d}")

    print(f"\n  {BOLD}Team pet mechanics:{RESET}")
    events = [
        (GREEN, "✅", "git push / commit",    "Hunger ↑  Mood ↑  Streak +1"),
        (GREEN, "✅", "PR merged",            "Health +15  Energy +10  Mood +10"),
        (GREEN, "✅", "Issue closed",         "Mood +15  Hunger +5"),
        (GREEN, "✅", "CI passes",            "Health +10  Energy +5"),
        (RED,   "❌", "CI fails",             "Health −20  Energy −10"),
        (RED,   "❌", "No activity (days)",   "All stats decay → pet dies"),
        (ORANGE,"⚠ ", "Dirty local repo",    "Mood penalty after 2h (local only)"),
    ]
    for color, icon, trigger, effect in events:
        print(f"    {icon}  {color}{trigger:<26}{RESET}  {DIM}{effect}{RESET}")

    print(f"\n  {BOLD}Health:{RESET}")
    print(f"    Rises: avg(H,E,M) ≥ 60   Falls fast: avg < 30")
    print(f"    {GREEN}CI pass +10{RESET}  {GREEN}PR merge +15{RESET}  {RED}CI fail −20{RESET}")
    print(f"\n  {BOLD}Stats (0 = critical, 100 = excellent):{RESET}")
    print(f"    {GREEN}75–100{RESET} Excellent  {YELLOW}50–74{RESET} Good  {ORANGE}25–49{RESET} Warning  {RED}0–24{RESET} Critical\n")


_DOCS: dict[str, str] = {
"server-setup": f"""
{BOLD}TamaGit Server Setup — complete guide{RESET}

{BOLD}Requirements:{RESET}
  • VPS with public IP (e.g. 72.56.239.253)
  • Docker + Docker Compose installed
  • GitHub repository for your project

{BOLD}Step 1 — Install TamaGit on VPS:{RESET}
  ssh root@<vps-ip>
  git clone https://github.com/tiroro-20-10/TamaGit--SNA-Final-Project-2026.git /opt/TamaGit
  cd /opt/TamaGit
  bash install.sh           # creates venv + global symlink
  tamagit help              # verify installation

{BOLD}Step 2 — Create GitHub token:{RESET}
  1. github.com → your avatar → Settings
  2. Developer settings → Personal access tokens → Tokens (classic)
  3. Generate new token (classic)
     • Note: "TamaGit"
     • Expiration: 90 days or No expiration
     • Scopes: ☑ repo   ☑ admin:repo_hook
  4. Copy the token immediately (shown only once)

{BOLD}Step 3 — Run server setup wizard:{RESET}
  tamagit server-setup
  # Enter: GitHub repo, token, server IP, port

  What it does automatically:
    • Writes /opt/TamaGit/.env
    • Runs docker compose up -d --build webhook
    • Creates GitHub webhook via API
    • Tests /health endpoint

{BOLD}Step 4 — Hatch the team pet:{RESET}
  tamagit init
  # Optional: custom name pool
  # Uses GitHub API to set realistic initial stats

{BOLD}Step 5 — Share with team:{RESET}
  Tell teammates: TAMAGIT_VPS_URL=http://<vps-ip>:8000
  They run: pip install git+https://github.com/... && tamagit setup
""",

"setup": f"""
{BOLD}TamaGit Local Setup — developer guide{RESET}

{BOLD}Install:{RESET}
  pip install git+https://github.com/tiroro-20-10/TamaGit--SNA-Final-Project-2026.git
  # or from local clone:  bash install.sh

{BOLD}First-time setup wizard:{RESET}
  tamagit setup
  # Enter VPS URL → tests connection → syncs pet → installs prompt → starts daemon

{BOLD}Manual setup:{RESET}
  tamagit config set vps_url http://72.56.239.253:8000
  tamagit sync
  tamagit install-prompt && source ~/.bashrc
  tamagit daemon start

{BOLD}What syncs from server:{RESET}
  • Pet stats (hunger, energy, mood, health)
  • Streak, achievements, daily quest
  • Event history
  • Graveyard

{BOLD}What stays local:{RESET}
  • local_name, ascii_style, theme, prompt_format (config.json)
  • git_repos metadata (dirty/unpushed status)
""",

"scan": f"""
{BOLD}tamagit scan — how it works{RESET}

Scans a local git repository and updates ONLY metadata
stored in the local git_repos section of state.json.

{BOLD}What it records:{RESET}
  is_dirty      — uncommitted changes exist
  dirty_since   — when the repo became dirty (for penalty timing)
  unpushed      — commits not yet pushed to remote
  unpulled      — remote commits not yet pulled
  last_commit   — hash and subject of last commit
  last_scanned  — timestamp

{BOLD}Dirty repo — visual indicator only:{RESET}
  The ⚠ dirty flag in status and scan is informational only.
  It does NOT affect pet stats — dirty repos are a normal part
  of development. The pet reacts to actual GitHub events instead
  (pushes, CI, PRs, issues).

{BOLD}Auto-scan via daemon:{RESET}
  tamagit daemon start
  The daemon rescans all registered repos every 30 min (configurable).
  Register a repo: tamagit scan /path/to/repo  (once is enough)
""",

"quest": f"""
{BOLD}Team Daily Quest{RESET}

Generated on the VPS on the first GitHub event of each day.
All teammates see the same quest after 'tamagit sync'.

{BOLD}Quest types:{RESET}
  Make 5 commits as a team today            (always available)
  Make 10 commits as a team today           (always available)
  Review and merge a pull request           (always available)
  Close 3 open issues today                 (only if 3+ issues exist)
  Merge 2 pull requests today               (only if 2+ open PRs)
  Fix the broken CI pipeline                (only if CI is failing)

{BOLD}Reward on completion:{RESET}
  Mood +25  Hunger +15  Energy +10

{BOLD}Achievements from quests:{RESET}
  Quest Completers  — 1 quest done
  Dedicated Team    — 10 quests done
""",

"death": f"""
{BOLD}Death & Auto-Resurrection{RESET}

When health → 0 the pet dies. Ghost mode begins.
The VPS still receives events but only tracks cooldown progress.

{BOLD}Cooldown tasks (via GitHub events):{RESET}
  ☐  Make 3 commits
  ☐  Close 1 issue
  ☐  Get CI green once

After all three: the NEXT GitHub event automatically:
  1. Buries the old pet (added to graveyard)
  2. Hatches a new pet with a random name
  3. Sets starting stats based on cooldown quality
  4. Creates a GitHub issue to notify the team
  5. Run 'tamagit sync' to see the new pet

{BOLD}Starting stats after resurrection:{RESET}
  Hunger = 40 + (commits_done × 10)   max 70
  Energy = 40 + (ci_ok × 30)          40 or 70
  Mood   = 40 + (issues_done × 20)    40 or 60
""",

"webhook": f"""
{BOLD}GitHub Webhook — setup & troubleshooting{RESET}

{BOLD}Automatic (via tamagit server-setup):{RESET}
  Requires: GitHub token with admin:repo_hook scope.
  The wizard creates the webhook automatically.

{BOLD}Manual setup if automatic fails:{RESET}
  GitHub → repo → Settings → Webhooks → Add webhook
  • Payload URL:   http://<vps>:8000/webhook/github
  • Content type:  application/json
  • Secret:        value of GITHUB_WEBHOOK_SECRET from .env
  • Events:        Pushes, Pull requests, Issues, Workflow runs
  • Active:        ✅

{BOLD}Verify it works:{RESET}
  curl http://<vps>:8000/health      → {{"status":"ok"}}
  docker compose logs -f webhook     → live logs
  GitHub → Webhooks → Recent Deliveries → ping should be 200

{BOLD}Events that affect the pet:{RESET}
  PushEvent          → hunger ↑, mood ↑, streak
  PullRequestEvent   → health ↑ (on merge)
  IssuesEvent        → mood ↑ (on close)
  WorkflowRunEvent   → health ↑ or ↓ (CI result)
""",

"daemon": f"""
{BOLD}tamagit daemon — background auto-sync{RESET}

  tamagit daemon start    start in background (detached)
  tamagit daemon stop     stop
  tamagit daemon status   check PID and intervals
  tamagit daemon restart  restart (picks up config changes)
  tamagit daemon logs     last 40 lines of ~/.tamagit/daemon.log

{BOLD}What it does:{RESET}
  Every N minutes: GET /state + GET /graveyard from VPS
  Every M minutes: 'tamagit scan' on all registered repos

{BOLD}Config (tamagit config set key value):{RESET}
  vps_url          VPS server URL
  sync_interval    minutes between VPS syncs  (default 10, min 1)
  scan_interval    minutes between scans       (default 30)

{BOLD}Note:{RESET}
  Config is re-read every loop iteration.
  Changes via 'tamagit config set' take effect within 1 minute
  without restarting the daemon.
""",

"config": f"""
{BOLD}tamagit config — local personalisation{RESET}

Stored in ~/.tamagit/config.json.
Never overwritten by sync — these are personal preferences.

  tamagit config              interactive menu
  tamagit config set k v      set a value  
  tamagit config get k        read a value
  tamagit config list         show all with defaults
  tamagit config reset        restore all defaults

{BOLD}Available settings:{RESET}
  local_name       personal pet name (overrides server name locally)
  vps_url          VPS server URL
  ascii_style      standard | minimal | emoji  (affects status, live, prompt)
  prompt_format    full | compact | minimal
  theme            dark | monochrome
  show_stats       true/false
  show_repos       true/false
  show_quest       true/false
  show_achievements true/false
  show_events      true/false
  show_ascii       true/false
  sync_interval    daemon sync minutes
  scan_interval    daemon scan minutes
""",
}


def _cmd_docs(topic: str | None) -> None:
    if not topic:
        print(f"\n  {BOLD}TamaGit built-in documentation{RESET}\n")
        topics = [
            ("server-setup", "Full VPS + webhook setup guide"),
            ("setup",        "Local developer setup guide"),
            ("scan",         "How scan works, dirty repo mechanics"),
            ("quest",        "Team daily quests"),
            ("death",        "Death, cooldown, auto-resurrection"),
            ("webhook",      "Webhook setup and troubleshooting"),
            ("daemon",       "Background daemon"),
            ("config",       "Local config system"),
        ]
        for t, d in topics:
            print(f"    {CYAN}tamagit docs {t:<14}{RESET}  {d}")
        print()
        return
    doc = _DOCS.get(topic)
    if not doc:
        print(f"\n  {YELLOW}Unknown topic: {topic}{RESET}  —  run: tamagit docs\n"); return
    print(doc)


# ── Demo command ───────────────────────────────────────────────────────────────

def _cmd_demo(mode: str) -> None:
    """Preview all visual states (for testing and demonstration)."""
    try:
        from .demo import run_demo
        run_demo(mode)
    except ImportError as exc:
        print(f"\n  {YELLOW}Demo requires textual: pip install textual{RESET}\n")


# ── React helpers ──────────────────────────────────────────────────────────────

def _mood_face(label: str) -> str:
    return {
        "ecstatic": "( ^o^ )", "happy":     "( ^.^ )",
        "okay":     "( -.- )", "sad":       "( T.T )",
        "miserable":"( ;_; )", "sleeping":  "( z.z )",
        "on_fire":  "(>^.^<)", "ghost":     "( x.x )",
    }.get(label, "( ... )")


_PRAISE: dict[tuple, list] = {
    ("git","push"):   ["pushed! team pet is fed ✓", "remote updated, nom nom!", "commits delivered!"],
    ("git","commit"): ["new commit! pet noticed ✓", "saved to history!"],
    ("git","pull"):   ["synced with remote!", "pulled! good habit"],
    ("git","merge"):  ["merged! health bonus incoming"],
    ("docker",""):    ["container running! 🐋"],
    ("pytest",""):    ["tests green! 🧪", "all tests passed!"],
}
_ROAST: dict[tuple, list] = {
    ("git","push"):   ["push rejected... fix and retry", "nothing made it to remote"],
    ("git","commit"): ["nothing to commit? stage something first"],
    ("git","pull"):   ["pull failed... conflicts?"],
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
    import secrets; return secrets.token_hex(length)

def _clear() -> None:
    print("\033[2J\033[H", end="")


# ── Parser ─────────────────────────────────────────────────────────────────────

def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="tamagit",
        description=(
            "TamaGit — Terminal Team Tamagotchi for GitHub\n\n"
            "First time on server:  tamagit server-setup && tamagit init\n"
            "First time locally:    tamagit setup\n"
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for sc in ["setup","server-setup","init","status","log","achievements",
               "graveyard","live","sync","install-prompt","uninstall-prompt",
               "uninstall","help","prompt"]:
        sub.add_parser(sc)

    rename_p = sub.add_parser("rename"); rename_p.add_argument("new_name", nargs="?", default="")
    scan_p   = sub.add_parser("scan");   scan_p.add_argument("path", nargs="?", default=".")
    docs_p   = sub.add_parser("docs");   docs_p.add_argument("topic", nargs="?", default=None)
    demo_p   = sub.add_parser("demo");   demo_p.add_argument("demo_mode", nargs="?", default="status",
                                                              choices=["status","live","prompt"])

    cfg_p = sub.add_parser("config")
    cfg_p.add_argument("config_cmd", nargs="?", default=None, choices=["set","get","list","reset"])
    cfg_p.add_argument("key",   nargs="?", default="")
    cfg_p.add_argument("value", nargs="?", default="")

    daemon_p   = sub.add_parser("daemon")
    daemon_sub = daemon_p.add_subparsers(dest="daemon_cmd")
    for sc in ["start","stop","status","restart","logs"]:
        daemon_sub.add_parser(sc)

    react_p = sub.add_parser("react")
    react_p.add_argument("exit_code", type=int)
    react_p.add_argument("full_cmd",  nargs="?", default="")

    return parser


if __name__ == "__main__":
    main()
