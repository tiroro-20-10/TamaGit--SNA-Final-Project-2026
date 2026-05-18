"""
TamaGit Daemon — background process for automatic sync and repo scanning.

Commands:
    tamagit daemon start    start in background
    tamagit daemon stop     stop
    tamagit daemon status   check status
    tamagit daemon restart  restart
    tamagit daemon logs     show last 40 log lines

Config (config.json or env vars, re-read every loop iteration):
    vps_url / TAMAGIT_VPS_URL        VPS server URL
    sync_interval / TAMAGIT_SYNC_INTERVAL   minutes between syncs  (default 10)
    scan_interval / TAMAGIT_SCAN_INTERVAL   minutes between scans  (default 30)

What the daemon does:
    1. Sync: GET /state and GET /graveyard from VPS, merge with local git_repos,
       save to ~/.tamagit/state.json and ~/.tamagit/graveyard.json.
    2. Scan: run git_integration on every path in pet.git_repos (previously
       scanned paths), update dirty/unpushed metadata.

Both tasks run on their own intervals, checked every 60 seconds.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path


def _state_dir() -> Path:
    path = os.environ.get("TAMAGIT_STATE_PATH", "~/.tamagit/state.json")
    return Path(path).expanduser().parent


def _pid_file()  -> Path: return _state_dir() / "daemon.pid"
def _log_file()  -> Path: return _state_dir() / "daemon.log"


# ── Public API ────────────────────────────────────────────────────────────────

def start() -> str:
    if _is_running():
        pid = int(_pid_file().read_text().strip())
        return f"Daemon already running (PID {pid})"
    try:
        child_pid = _daemonize_unix()
        return f"Daemon started (PID {child_pid})"
    except AttributeError:
        return _start_windows()


def stop() -> str:
    pid_file = _pid_file()
    if not pid_file.exists():
        return "Daemon is not running"
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        return f"Daemon stopped (PID {pid})"
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return "Daemon was not running (stale PID file removed)"
    except PermissionError:
        return "Cannot stop daemon: permission denied"


def get_status() -> dict:
    pid_file = _pid_file()
    if not pid_file.exists():
        return {"running": False}
    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, TypeError):
        pid_file.unlink(missing_ok=True)
        return {"running": False}

    try:
        if os.name == "nt":   # Windows
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True,
            )
            alive = str(pid) in result.stdout
        else:                 # Unix
            os.kill(pid, 0)
            alive = True
    except (ProcessLookupError, OSError):
        alive = False

    if not alive:
        pid_file.unlink(missing_ok=True)
        return {"running": False}
    return {"running": True, "pid": pid}


def tail_logs(n: int = 40) -> list[str]:
    log = _log_file()
    if not log.exists():
        return []
    lines = log.read_text(encoding="utf-8").splitlines()
    return lines[-n:]


def _is_running() -> bool:
    return get_status()["running"]


# ── Daemonization ─────────────────────────────────────────────────────────────

def _daemonize_unix() -> int:
    """Standard double-fork daemonization. Returns child PID."""
    pid = os.fork()
    if pid > 0:
        time.sleep(0.4)
        try:
            return int(_pid_file().read_text().strip())
        except Exception:
            return pid

    os.setsid()
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Inside daemon process
    for fd, mode in [(0, "r"), (1, "w"), (2, "w")]:
        with open(os.devnull, mode) as devnull:
            os.dup2(devnull.fileno(), fd)

    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _pid_file().write_text(str(os.getpid()))

    def _on_sigterm(signum, frame):
        _log("SIGTERM — shutting down")
        _pid_file().unlink(missing_ok=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, _on_sigterm)

    _main_loop()
    sys.exit(0)


def _start_windows() -> str:
    import subprocess
    script = (
        "import sys, os; sys.path.insert(0, os.getcwd());"
        "from src.daemon import _main_loop; _main_loop()"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    _state_dir().mkdir(parents=True, exist_ok=True)
    _pid_file().write_text(str(proc.pid))
    return f"Daemon started in Windows mode (PID {proc.pid})"


# ── Main loop ─────────────────────────────────────────────────────────────────

def _main_loop() -> None:
    """Run sync and scan tasks on their respective intervals.

    Config is re-read every iteration so changes take effect without restart.
    The loop sleeps 60 seconds between checks, so minimum effective interval is 1 min.
    """
    _log("Daemon loop started")
    last_sync = 0.0
    last_scan = 0.0

    while True:
        # Re-read config every iteration — picks up changes made via tamagit config
        try:
            from .config_manager import get as _cfg, effective_vps_url
            vps_url    = effective_vps_url()
            sync_every = int(os.environ.get("TAMAGIT_SYNC_INTERVAL") or _cfg("sync_interval") or 10)
            scan_every = int(os.environ.get("TAMAGIT_SCAN_INTERVAL") or _cfg("scan_interval") or 30)
        except Exception:
            vps_url    = os.environ.get("TAMAGIT_VPS_URL", "").rstrip("/")
            sync_every = int(os.environ.get("TAMAGIT_SYNC_INTERVAL", "10"))
            scan_every = int(os.environ.get("TAMAGIT_SCAN_INTERVAL", "30"))

        now = time.time()

        if vps_url and (now - last_sync) >= sync_every * 60:
            try:
                _do_sync(vps_url)
                last_sync = now
            except Exception as exc:
                _log(f"[sync] ERROR: {exc}")

        if (now - last_scan) >= scan_every * 60:
            try:
                _do_scan_all()
                last_scan = now
            except Exception as exc:
                _log(f"[scan] ERROR: {exc}")

        time.sleep(60)


# ── Tasks ─────────────────────────────────────────────────────────────────────

def _do_sync(vps_url: str) -> None:
    """Fetch state + graveyard from VPS and merge with local git_repos.

    VPS is the source of truth for game stats.
    Local git_repos (dirty/unpushed metadata) are preserved because the VPS
    has no visibility into the developer's local worktree.
    """
    import urllib.request
    from .models import PetState, GraveyardEntry
    from .storage import Storage

    storage = Storage()

    # Fetch state
    resp     = urllib.request.urlopen(f"{vps_url}/state", timeout=10)
    vps_data = json.loads(resp.read().decode())
    vps_pet  = PetState.from_dict(vps_data)

    # Preserve local git_repos; merge events (no exact duplicates)
    if storage.is_initialized():
        local_pet = storage.load()
        vps_pet.git_repos  = local_pet.git_repos
        all_events = list(dict.fromkeys(vps_pet.events_log + local_pet.events_log))
        vps_pet.events_log = all_events[-30:]
    storage.save(vps_pet)

    # Fetch and overwrite graveyard
    try:
        resp2     = urllib.request.urlopen(f"{vps_url}/graveyard", timeout=10)
        gdata     = json.loads(resp2.read().decode())
        entries   = [GraveyardEntry.from_dict(e) for e in gdata]
        storage.save_graveyard(entries)
    except Exception:
        pass  # graveyard endpoint might not exist on older servers

    _log(
        f"[sync] {vps_pet.name} alive={vps_pet.alive} "
        f"H={int(vps_pet.hunger)} E={int(vps_pet.energy)} "
        f"M={int(vps_pet.mood)} health={int(vps_pet.health)}"
    )


def _do_scan_all() -> None:
    """Scan all previously registered local git repos.

    'Registered' means they appear as keys in pet.git_repos — which happens
    the first time the user runs 'tamagit scan /path/to/repo'.
    Only updates git_repos metadata; never changes game stats directly.
    """
    from .pet_engine import apply_git_snapshot, update_from_time
    from .git_integration import collect_git_snapshot
    from .storage import Storage

    storage = Storage()
    if not storage.is_initialized():
        _log("[scan] No state file — skipping")
        return

    pet = storage.load()
    update_from_time(pet)

    repos = list(pet.git_repos.keys())
    if not repos:
        _log("[scan] No repos registered. Run 'tamagit scan /path' once to register.")
        storage.save(pet)
        return

    _log(f"[scan] Scanning {len(repos)} repo(s): {', '.join(Path(r).name for r in repos)}")
    for repo_path in repos:
        p = Path(repo_path)
        if not p.exists():
            _log(f"[scan] {repo_path}: not found — skipping")
            continue
        try:
            snapshot = collect_git_snapshot(p)
            messages = apply_git_snapshot(pet, snapshot)
            for msg in messages:
                _log(f"[scan] {p.name}: {msg}")
        except Exception as exc:
            _log(f"[scan] {repo_path}: ERROR — {exc}")

    storage.save(pet)
    _log("[scan] Done")


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log = _log_file()
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
        _rotate_log(500)
    except Exception:
        pass


def _rotate_log(max_lines: int) -> None:
    log = _log_file()
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_lines:
            log.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    except Exception:
        pass
