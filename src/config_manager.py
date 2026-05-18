"""
Local config manager — stores user preferences in ~/.tamagit/config.json.

The config is intentionally separate from state.json:
  - state.json  = game state (synced from VPS, overwritten by daemon)
  - config.json = personal preferences (never overwritten by sync)

This module is a simple key-value store with typed defaults.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# All supported keys with their default values and descriptions
DEFAULTS: dict[str, tuple[Any, str]] = {
    # Connection
    "vps_url":          ("",         "VPS webhook server URL (e.g. http://1.2.3.4:8000)"),
    # Display
    "local_name":       ("",         "Personal pet name override (only shown in your terminal)"),
    "ascii_style":      ("standard", "ASCII art style: standard | minimal | emoji"),
    "prompt_format":    ("full",     "Prompt format: full | compact | minimal"),
    "theme":            ("dark",     "Color theme: dark | monochrome"),
    # Status panel sections (show/hide)
    "show_stats":       (True,       "Show stat bars in 'tamagit status'"),
    "show_repos":       (True,       "Show tracked repos in 'tamagit status'"),
    "show_quest":       (True,       "Show daily quest in 'tamagit status'"),
    "show_achievements":(True,       "Show achievement count in 'tamagit status'"),
    "show_events":      (True,       "Show recent events in 'tamagit status'"),
    "show_ascii":       (True,       "Show ASCII art in 'tamagit status'"),
    # Daemon intervals
    "sync_interval":    (10,         "Daemon: minutes between VPS syncs"),
    "scan_interval":    (30,         "Daemon: minutes between git repo scans"),
}


def _config_path() -> Path:
    state_path = os.environ.get("TAMAGIT_STATE_PATH", "~/.tamagit/state.json")
    return Path(state_path).expanduser().parent / "config.json"


def _load_raw() -> dict:
    p = _config_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_raw(data: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────────────

def get(key: str) -> Any:
    """Return config value, falling back to default."""
    if key not in DEFAULTS:
        return None
    default, _ = DEFAULTS[key]
    return _load_raw().get(key, default)


def set_(key: str, value: Any) -> bool:
    """Set a config value. Returns False if key is unknown."""
    if key not in DEFAULTS:
        return False
    data = _load_raw()
    # Type coercion: keep booleans/ints correct when coming from CLI strings
    default_val, _ = DEFAULTS[key]
    if isinstance(default_val, bool):
        if isinstance(value, str):
            value = value.lower() not in ("0", "false", "no", "off")
        else:
            value = bool(value)
    elif isinstance(default_val, int):
        value = int(value)
    data[key] = value
    _save_raw(data)
    return True


def all_values() -> dict[str, Any]:
    """All config values merged with defaults."""
    raw = _load_raw()
    return {k: raw.get(k, default) for k, (default, _) in DEFAULTS.items()}


def reset() -> None:
    """Delete config file (restores all defaults)."""
    p = _config_path()
    if p.exists():
        p.unlink()


def effective_vps_url() -> str:
    """VPS URL: config file → TAMAGIT_VPS_URL env → empty."""
    url = get("vps_url")
    if not url:
        url = os.environ.get("TAMAGIT_VPS_URL", "")
    return url.rstrip("/")


def effective_name(official_name: str) -> str:
    """Pet name shown to the user: local_name override or official name."""
    return get("local_name") or official_name
