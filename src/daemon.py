"""
TamaGit Daemon — фоновый процесс автоматической синхронизации и сканирования.

Управление:
  tamagit daemon start    — запустить
  tamagit daemon stop     — остановить
  tamagit daemon status   — проверить
  tamagit daemon restart  — перезапустить
  tamagit daemon logs     — последние 30 строк лога

Конфигурация через .env / переменные окружения:
  TAMAGIT_VPS_URL          URL webhook-сервера на VPS
  TAMAGIT_SYNC_INTERVAL    синхронизация, минут (default 10)
  TAMAGIT_SCAN_INTERVAL    сканирование, минут  (default 30)

Как работает:
  1. Демон запускается через double-fork (Unix) или subprocess (Windows).
  2. Каждую минуту проверяет расписание и запускает задачи:
     а) sync  — GET /state на VPS, мерджит с локальным state.json
     б) scan  — tamagit scan для всех путей в pet.git_repos
  3. Логи пишутся в ~/.tamagit/daemon.log (ротация на 500 строк).
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path


# ── Утилиты путей ─────────────────────────────────────────────────────────────

def _state_dir() -> Path:
    path = os.environ.get("TAMAGIT_STATE_PATH", "~/.tamagit/state.json")
    return Path(path).expanduser().parent


def _pid_file()  -> Path: return _state_dir() / "daemon.pid"
def _log_file()  -> Path: return _state_dir() / "daemon.log"


# ── Публичный API ─────────────────────────────────────────────────────────────

def start() -> str:
    """Запускает демон в фоне. Возвращает строку со статусом."""
    if _is_running():
        pid = int(_pid_file().read_text().strip())
        return f"Daemon already running (PID {pid})"
    try:
        child_pid = _daemonize_unix()
        return f"Daemon started (PID {child_pid})"
    except AttributeError:
        # os.fork() отсутствует (Windows) — запускаем через subprocess
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
        os.kill(pid, 0)          # signal 0 = просто проверяем что процесс жив
        return {"running": True, "pid": pid}
    except (ProcessLookupError, ValueError):
        pid_file.unlink(missing_ok=True)
        return {"running": False}


def tail_logs(n: int = 30) -> list[str]:
    log = _log_file()
    if not log.exists():
        return []
    lines = log.read_text(encoding="utf-8").splitlines()
    return lines[-n:]


def _is_running() -> bool:
    return get_status()["running"]


# ── Демонизация (Unix) ────────────────────────────────────────────────────────

def _daemonize_unix() -> int:
    """Стандартный double-fork. Возвращает PID дочернего процесса.

    Первый форк: отвязываемся от терминала.
    os.setsid(): создаём новую сессию → демон больше не зависит от терминала.
    Второй форк: гарантируем что демон не сможет случайно захватить tty.
    """
    pid = os.fork()
    if pid > 0:
        # Родитель: ждём, пока ребёнок запишет PID-файл, потом возвращаем PID
        time.sleep(0.4)
        try:
            return int(_pid_file().read_text().strip())
        except Exception:
            return pid

    os.setsid()

    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # ── Мы внутри демона ──────────────────────────────────────────────────────
    _redirect_fds()
    _write_pid()
    _setup_signals()
    _log("Daemon process started")
    _main_loop()
    sys.exit(0)


def _redirect_fds() -> None:
    """Перенаправляем stdin/stdout/stderr в /dev/null."""
    devnull = os.devnull
    with open(devnull, 'r') as f:
        os.dup2(f.fileno(), 0)
    with open(devnull, 'w') as f:
        os.dup2(f.fileno(), 1)
        os.dup2(f.fileno(), 2)


def _write_pid() -> None:
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _pid_file().write_text(str(os.getpid()))


def _setup_signals() -> None:
    def _on_sigterm(signum, frame):
        _log("SIGTERM received — shutting down")
        _pid_file().unlink(missing_ok=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, _on_sigterm)


def _start_windows() -> str:
    """Fallback для Windows через subprocess."""
    import subprocess
    script = (
        "import sys, os\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from src.daemon import _main_loop\n"
        "_main_loop()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    _state_dir().mkdir(parents=True, exist_ok=True)
    _pid_file().write_text(str(proc.pid))
    return f"Daemon started in Windows mode (PID {proc.pid})"


# ── Главный цикл ──────────────────────────────────────────────────────────────

def _main_loop() -> None:
    """Бесконечный цикл демона. Проверяет расписание каждые 60 секунд."""
    vps_url    = os.environ.get("TAMAGIT_VPS_URL", "").rstrip("/")
    sync_every = int(os.environ.get("TAMAGIT_SYNC_INTERVAL", "10"))   # мин
    scan_every = int(os.environ.get("TAMAGIT_SCAN_INTERVAL", "30"))   # мин

    _log(
        f"Loop started | sync={sync_every}min | scan={scan_every}min | "
        f"vps={'yes' if vps_url else 'none'}"
    )

    last_sync = 0.0
    last_scan = 0.0

    while True:
        now = time.time()

        # Шаг 1: синхронизация с VPS
        if vps_url and (now - last_sync) >= sync_every * 60:
            try:
                _do_sync(vps_url)
                last_sync = now
            except Exception as exc:
                _log(f"[sync] ERROR: {exc}")

        # Шаг 2: сканирование локальных репозиториев
        if (now - last_scan) >= scan_every * 60:
            try:
                _do_scan_all()
                last_scan = now
            except Exception as exc:
                _log(f"[scan] ERROR: {exc}")

        time.sleep(60)


# ── Задачи ────────────────────────────────────────────────────────────────────

def _do_sync(vps_url: str) -> None:
    """Получает state.json с VPS и мерджит с локальным.

    Что берётся с VPS:
      • Статы питомца (hunger, energy, mood, health)
      • Streak, ачивки, события от webhook

    Что сохраняется с локальной машины:
      • git_repos — пути и состояния локальных репозиториев
        (dirty_since, unpushed и т.д. имеют смысл только локально)

    Почему мерджим, а не перезаписываем:
      Если просто перезаписать, то scan-данные (dirty_since, unpushed)
      затираются на каждом sync-цикле, и демон теряет контекст.
    """
    import urllib.request

    resp     = urllib.request.urlopen(f"{vps_url}/state", timeout=10)
    vps_data = json.loads(resp.read().decode())

    from .models import PetState
    from .storage import Storage

    storage   = Storage()
    local_pet = storage.load() if storage.is_initialized() else PetState()
    vps_pet   = PetState.from_dict(vps_data)

    # Берём пути репозиториев из локального state —
    # на VPS этих путей нет (там другая файловая система)
    vps_pet.git_repos = local_pet.git_repos

    # Объединяем логи событий (без дублей, последние 30)
    all_events = list(dict.fromkeys(vps_pet.events_log + local_pet.events_log))
    vps_pet.events_log = all_events[-30:]

    storage.save(vps_pet)
    _log(
        f"[sync] {vps_pet.name} alive={vps_pet.alive} "
        f"H={int(vps_pet.hunger)} E={int(vps_pet.energy)} "
        f"M={int(vps_pet.mood)} health={int(vps_pet.health)}"
    )


def _do_scan_all() -> None:
    """Сканирует все пути из pet.git_repos.

    'Сохранённые репозитории' — это ключи git_repos в state.json.
    Они добавляются при каждом ручном вызове 'tamagit scan /path'.
    Демон просто переиспользует этот список и не требует отдельной конфигурации.
    """
    from .models import PetState
    from .pet_engine import apply_git_snapshot, update_from_time
    from .git_integration import collect_git_snapshot
    from .storage import Storage

    storage = Storage()
    if not storage.is_initialized():
        _log("[scan] No state.json yet — skipping")
        return

    pet = storage.load()
    update_from_time(pet)

    repos = list(pet.git_repos.keys())
    if not repos:
        _log("[scan] No repos registered. Run 'tamagit scan /path' once to add a repo.")
        storage.save(pet)
        return

    _log(f"[scan] Scanning {len(repos)} repo(s): {', '.join(Path(r).name for r in repos)}")

    for repo_path in repos:
        p = Path(repo_path)
        if not p.exists():
            _log(f"[scan] {repo_path}: directory not found — skipping")
            continue
        try:
            snapshot = collect_git_snapshot(p)
            messages = apply_git_snapshot(pet, snapshot)
            for msg in messages:
                _log(f"[scan] {p.name}: {msg}")
        except Exception as exc:
            _log(f"[scan] {repo_path}: ERROR — {exc}")

    storage.save(pet)
    _log(f"[scan] Done")


# ── Лог ───────────────────────────────────────────────────────────────────────

def _log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log_path = _log_file()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
        _rotate_log(500)
    except Exception:
        pass  # демон не должен падать из-за проблем с логами


def _rotate_log(max_lines: int) -> None:
    """Обрезает лог до max_lines строк (простая ротация)."""
    log = _log_file()
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_lines:
            log.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    except Exception:
        pass
