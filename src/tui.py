"""
TamaGit Live TUI  (tamagit live)
════════════════════════════════
Controls:  Q = quit  R = refresh  T = toggle dark/monochrome theme

Polls VPS every 5 s (direct) or reads local state.json.
Detects new events, plays reaction animation (walking pauses), then resumes.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static

from .models import PetState
from .storage import Storage
from .ui import _time_ago

MAX_WALK = 9

_WALK_SPEED = {
    "ecstatic": 0.55, "happy": 0.35, "okay": 0.22, "sad": 0.12,
    "miserable": 0.06, "sleeping": 0.0, "on_fire": 0.65, "ghost": 0.09,
}

# Mood colors — IDENTICAL to ui.py _mood_color() for consistency
_MOOD_COLOR = {
    "ecstatic": "green",   "happy":     "cyan",
    "okay":     "yellow",  "sad":       "magenta",
    "miserable":"red",     "sleeping":  "blue",
    "on_fire":  "orange1", "ghost":     "grey50",
    "rx_push":  "green",   "rx_pr":     "cyan",
    "rx_fail":  "red",     "rx_quest":  "yellow",
}

_CSS_DARK = """
Screen { background: #0d0d0d; }
#title-bar { background: #16213e; height: 3; content-align: center middle; border: solid #7c3aed; }
#main-area { height: 1fr; }
#left-panel { width: 46; border: solid #374151; background: #111111; padding: 1 0; }
#right-panel { width: 1fr; border: solid #374151; background: #111111; padding: 1 2; }
#log-panel { height: 9; border: solid #1f2937; background: #0a0a0a; padding: 0 2; }
Footer { background: #16213e; }
"""
_CSS_MONO = """
Screen { background: #000000; }
#title-bar { background: #111111; height: 3; content-align: center middle; border: solid #555555; }
#main-area { height: 1fr; }
#left-panel { width: 46; border: solid #555555; background: #0a0a0a; padding: 1 0; }
#right-panel { width: 1fr; border: solid #555555; background: #0a0a0a; padding: 1 2; }
#log-panel { height: 9; border: solid #333333; background: #000000; padding: 0 2; }
Footer { background: #111111; }
"""

# ── Frame builders ─────────────────────────────────────────────────────────────

def _cat(face: str, sfx: str = "") -> str:
    return (
        f"    /\\_/\\  \n"
        f"   {face}\n"
        f"    > ~ <  {sfx}\n"
        f"   /|   |\\\n"
        f"  (_|   |_)"
    )

def _cat_min(face: str) -> str:
    return f" /\\_/\\\n({face})\n  ~  "

_WALK = {
    "ecstatic": [_cat("( ^o^ )", "~"), _cat("( >o^ )", "*"), _cat("( ^o< )", "*")],
    "happy":    [_cat("( ^.^ )"),      _cat("( >.^ )"),       _cat("( ^.< )")],
    "okay":     [_cat("( -.- )"),      _cat("( >.- )"),       _cat("( -.< )")],
    "sad":      [_cat("( T.T )"),      _cat("( T.- )"),       _cat("( -.T )")],
    "miserable":[_cat("( ;_; )", " ."),_cat("( ;_. )", "."),  _cat("( ._; )", " .")],
    "sleeping": [
        "    /\\_/\\  \n   ( z.z )  z\n    > ~ <   \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( z.z )   \n    > ~ <   \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( z.z ) z z\n    > ~ <   \n   /|   |\\\n  (_|   |_)",
    ],
    "on_fire": [
        "    /\\_/\\  \n   (>^.^<) 🔥\n    > ~ <  🔥\n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   (>^o^<) 🔥\n    > ~ <  🔥\n   /|   |\\\n  (_|   |_)",
    ],
    "ghost": [
        "    .--.    \n   (x.x)  ~ \n    ~~~~    \n   /~~~~\\  \n  (~~~~~~) ",
        "    .--.    \n   (x.x) ~ ~\n    ~~~~    \n   /~~~~\\  \n  (~~~~~~) ",
        "    .--.    \n   (x.x)    \n    ~~~~  ~ \n   /~~~~\\  \n  (~~~~~~) ",
    ],
}
_WALK_MIN = {
    "ecstatic": ["^o^", ">o^", "^o<"], "happy":    ["^.^", ">.^", "^.<"],
    "okay":     ["-.-", ">.-", "-.<"], "sad":      ["T.T", "T.-", "-.T"],
    "miserable":["?_?", ";_.", "._?"], "sleeping": ["z.z", "z.z", "z.z"],
    "on_fire":  [">^<", ">>^", "^<<"], "ghost":    ["x.x", "x.x", "x.x"],
}
_WALK_EMOJI = {
    "ecstatic": ["😸", "😺", "😸", "🎉"],
    "happy":    ["😺", "😺", "😸", "😺"],
    "okay":     ["😼", "😼", "😺", "😼"],
    "sad":      ["😿", "😿", "😿", "😿"],
    "miserable":["🙀", "😿", "🙀", "😿"],
    "sleeping": ["😴", "😴", "💤",  "😴"],
    "on_fire":  ["🔥😺", "😺🔥", "🔥😺", "✨😺"],
    "ghost":    ["👻", "👻 ~", "~ 👻", "👻"],
}
_REACTIONS = {
    "rx_push":  [_cat("( *o* )", "nom"), _cat("( ^o^ )", "!  "), _cat("( ^.^ )", "~  ")],
    "rx_pr":    [_cat("( ^o^ )", "✓  "), _cat("(>^.^<)", "!  "), _cat("( ^.^ )", "   ")],
    "rx_fail":  [_cat("( ;_; )", "!  "), _cat("( T.T )", "   "), _cat("( T.T )", ".  ")],
    "rx_quest": [_cat("( ^o^ )", "🎯"), _cat("( ^.^ )", "✓ "), _cat("( ^.^ )", "  ")],
}
_REACTIONS_MIN = {
    "rx_push":  ["*o*", "^o^", "^.^"], "rx_pr":   ["^o^", ">^<", "^.^"],
    "rx_fail":  [";_;", "T.T", "T.T"], "rx_quest":["^o^", "^.^", "^.^"],
}
_REACTIONS_EMOJI = {
    "rx_push":  ["😋", "🍖😺", "😺", "😸"],
    "rx_pr":    ["🎉", "😸",   "🎉", "✨"],
    "rx_fail":  ["😱", "😿",   "😱", "😿"],
    "rx_quest": ["🎯😺", "😸", "🎉", "😸"],
}
_SIMPLE_CYCLE = {"sleeping", "on_fire", "ghost"}


def _get_frame(mood: str, direction: int, phase: int, tick: int, style: str) -> str:
    if style == "emoji":
        frames = _WALK_EMOJI.get(mood, _WALK_EMOJI["happy"])
        return frames[tick // 2 % len(frames)]
    if style == "minimal":
        frames = _WALK_MIN.get(mood, _WALK_MIN["happy"])
        if mood in _SIMPLE_CYCLE:
            return _cat_min(frames[tick // 2 % len(frames)])
        return _cat_min(frames[0] if phase == 0 else (frames[1] if direction >= 0 else frames[2]))
    frames = _WALK.get(mood, _WALK["happy"])
    if mood in _SIMPLE_CYCLE:
        return frames[(tick // 2) % len(frames)]
    return frames[0] if phase == 0 else (frames[1] if direction >= 0 else frames[2])


def _get_rx_frame(key: str, tick: int, style: str) -> str:
    if style == "emoji":
        frames = _REACTIONS_EMOJI.get(key, _REACTIONS_EMOJI["rx_push"])
        return frames[(tick // 2) % len(frames)]
    if style == "minimal":
        frames = _REACTIONS_MIN.get(key, _REACTIONS_MIN["rx_push"])
        return _cat_min(frames[(tick // 2) % len(frames)])
    frames = _REACTIONS.get(key, _REACTIONS["rx_push"])
    return frames[(tick // 2) % len(frames)]


def _offset_frame(frame: str, offset: int) -> str:
    pad = " " * max(0, offset)
    return "\n".join(pad + line for line in frame.split("\n"))


def _sbar(label: str, value: float, width: int = 18, mono: bool = False) -> str:
    v      = int(value)
    filled = v * width // 100
    bar    = "█" * filled + "░" * (width - filled)
    if mono:
        return f"[bold]{label:<8}[/bold] [{bar}] {v:3d}%"
    if v >= 75:   color = "green"
    elif v >= 50: color = "yellow"
    elif v >= 25: color = "orange1"
    else:         color = "red"
    return f"[bold]{label:<8}[/bold] [{color}][{bar}] {v:3d}%[/{color}]"


# ── App ────────────────────────────────────────────────────────────────────────

class TamaGitApp(App):
    """Live TUI — animated team pet.

    Reads directly from the VPS every 5 s when TAMAGIT_VPS_URL is set,
    or falls back to the local state.json cache. Press T to toggle dark/monochrome theme.
    """
    BINDINGS = [
        ("q", "quit",         "Quit"),
        ("r", "refresh",      "Refresh"),
        ("t", "toggle_theme", "Toggle theme"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._storage = Storage()
        self._reload_config()

        self._pet: Optional[PetState] = None
        self._tick    = 0
        self._walk_pos: float = 4.0
        self._walk_dir: int   = 1
        self._walk_phase: int = 0
        self._reaction:   str = ""
        self._rx_tick:    int = 0
        self._rx_total:   int = 6
        self._last_event: str = ""

    def _reload_config(self) -> None:
        from . import config_manager as _cfg
        self._vps_url = _cfg.effective_vps_url()
        self._style   = _cfg.get("ascii_style") or "standard"
        self._mono    = (_cfg.get("theme") == "monochrome")

    @property
    def CSS(self) -> str:  # type: ignore[override]
        return _CSS_MONO if self._mono else _CSS_DARK

    def compose(self) -> ComposeResult:
        yield Static("", id="title-bar")
        with Horizontal(id="main-area"):
            with Vertical(id="left-panel"):
                yield Static("", id="pet-art")
            with Vertical(id="right-panel"):
                yield Static("", id="stats")
                yield Static("", id="quest")
                yield Static("", id="team-info")
                yield Static("", id="achievements")
        yield Static("", id="log-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._load(); self.set_interval(0.7, self._tick_fn); self.set_interval(5.0, self._poll)

    # ── Animation ──────────────────────────────────────────────────────────────

    def _tick_fn(self) -> None:
        self._tick += 1
        if self._pet is None:
            return
        if self._reaction:
            self._rx_tick += 1
            if self._rx_tick >= self._rx_total:
                self._reaction = ""; self._rx_tick = 0
        else:
            mood  = self._pet.mood_label
            speed = _WALK_SPEED.get(mood, 0.3)
            self._walk_pos += speed * self._walk_dir
            if self._walk_pos >= MAX_WALK:
                self._walk_pos = MAX_WALK; self._walk_dir = -1; self._walk_phase = 1
            elif self._walk_pos <= 0.0:
                self._walk_pos = 0.0; self._walk_dir = 1; self._walk_phase = 1
            if self._tick % 2 == 0:
                self._walk_phase = 1 - self._walk_phase
        self._render_art()

    def _render_art(self) -> None:
        if self._pet is None:
            return
        mood   = self._pet.mood_label
        offset = int(self._walk_pos)

        if self._reaction:
            frame = _get_rx_frame(self._reaction, self._rx_tick, self._style)
            color_key = self._reaction
        else:
            frame = _get_frame(mood, self._walk_dir, self._walk_phase, self._tick, self._style)
            color_key = mood

        if self._mono:
            art = frame if self._style == "emoji" else _offset_frame(frame, offset)
            self.query_one("#pet-art", Static).update(art)
        else:
            color = _MOOD_COLOR.get(color_key, "white")
            art   = frame if self._style == "emoji" else _offset_frame(frame, offset)
            self.query_one("#pet-art", Static).update(f"[{color}]{art}[/{color}]")

    # ── Polling ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        self._reload_config()
        pet = self._fetch_pet()
        if pet:
            self._pet = pet
            self._last_event = pet.events_log[-1] if pet.events_log else ""
            self._refresh_ui()
        else:
            self.query_one("#title-bar", Static).update(
                "[bold red]No pet.[/bold red]  Run [cyan]tamagit init[/cyan] on the server."
            )

    def _fetch_pet(self) -> Optional[PetState]:
        if self._vps_url:
            try:
                resp = urllib.request.urlopen(f"{self._vps_url}/state", timeout=3)
                return PetState.from_dict(json.loads(resp.read().decode()))
            except Exception:
                pass  # fall through to local
        if self._storage.is_initialized():
            return self._storage.load()
        return None

    def _poll(self) -> None:
        self._reload_config()
        pet = self._fetch_pet()
        if pet is None:
            return
        current = pet.events_log[-1] if pet.events_log else ""
        if current and current != self._last_event:
            self._last_event = current
            self._trigger(current)
        self._pet = pet
        self._refresh_ui()

    def _trigger(self, event_text: str) -> None:
        evt = event_text.lower()
        if any(w in evt for w in ("pushed", "commit", "nom nom")):
            self._react("rx_push", "🍖 Team pushed! Nom nom!")
        elif "merged pr" in evt:
            self._react("rx_pr",    "✨ PR merged! Health bonus!")
        elif "quest complete" in evt:
            self._react("rx_quest", "🎯 Team quest complete!")
        elif "achievement" in evt:
            self._react("rx_quest", f"🏆 {event_text.split(':')[-1].strip()[:40]}")
        elif "failed" in evt or ("ci" in evt and "fail" in evt):
            self._react("rx_fail",  "💔 CI failed... pet is stressed")

    def _react(self, key: str, msg: str, ticks: int = 6) -> None:
        self._reaction = key; self._rx_tick = 0; self._rx_total = ticks
        if msg:
            sev = "warning" if key == "rx_fail" else "information"
            self.notify(msg, severity=sev, timeout=4)

    # ── Widgets ────────────────────────────────────────────────────────────────

    def _refresh_ui(self) -> None:
        if self._pet is None: return
        self._update_title(); self._update_stats(); self._update_quest()
        self._update_team(); self._update_achievements(); self._update_log()

    def _update_title(self) -> None:
        p      = self._pet
        from . import config_manager as _cfg
        name   = _cfg.effective_name(p.name)
        streak = f"  🔥 {p.streak_days}d" if p.streak_days >= 3 else ""
        # Show data source clearly
        src = "VPS  5s" if self._vps_url else "local"
        src_tag = f"[dim][{src}][/dim]"
        repo_tag = f"  [dim]{p.github_repo}[/dim]" if p.github_repo else ""
        self.query_one("#title-bar", Static).update(
            f"[bold][purple]TamaGit[/purple][/bold]  •  "
            f"[cyan]{name}[/cyan]  •  day {p.age_days}"
            f"[orange1]{streak}[/orange1]  •  "
            f"[italic]{p.mood_label}[/italic]{repo_tag}  •  {src_tag}"
        )

    def _update_stats(self) -> None:
        from . import config_manager as _cfg
        if not _cfg.get("show_stats"):
            self.query_one("#stats", Static).update(""); return
        p     = self._pet
        lines = [_sbar("Hunger",p.hunger,mono=self._mono), _sbar("Energy",p.energy,mono=self._mono),
                 _sbar("Mood",  p.mood,  mono=self._mono), _sbar("Health",p.health,mono=self._mono)]
        if not p.alive:
            lines += ["", "[bold red]💀 Pet is dead[/bold red]",
                      f"  commits {p.cooldown_commits}/3 • "
                      f"issues {p.cooldown_issues}/1 • CI {p.cooldown_ci_ok}/1"]
        self.query_one("#stats", Static).update("\n".join(lines))

    def _update_quest(self) -> None:
        from . import config_manager as _cfg
        if not _cfg.get("show_quest"):
            self.query_one("#quest", Static).update(""); return
        p = self._pet
        if not p.daily_quest_text or p.daily_quest_date != date.today().isoformat():
            self.query_one("#quest", Static).update("[dim]No quest yet today.[/dim]"); return
        if p.daily_quest_done:
            txt = f"[green]🎯 ✅ {p.daily_quest_text}[/green]"
        else:
            c = p.daily_commit_count if p.daily_quest_trigger == "commit_count" else \
                p.daily_issue_count  if p.daily_quest_trigger == "issue_count"  else \
                p.daily_pr_count
            txt = f"[yellow]🎯 {p.daily_quest_text}[/yellow] [dim]({c}/{p.daily_quest_threshold})[/dim]"
        self.query_one("#quest", Static).update(txt)

    def _update_team(self) -> None:
        p     = self._pet
        from . import config_manager as _cfg
        parts = []
        if p.last_fed_by:
            parts.append(f"[dim]fed by[/dim] [cyan]{p.last_fed_by}[/cyan] [dim]({_time_ago(p.last_fed_at)})[/dim]")
        if p.streak_days:
            icon = "🔥" if p.streak_days >= 7 else "📅"
            parts.append(f"{icon} [bold]{p.streak_days}[/bold]d streak")
        self.query_one("#team-info", Static).update("  │  ".join(parts))

    def _update_achievements(self) -> None:
        from . import config_manager as _cfg
        if not _cfg.get("show_achievements"):
            self.query_one("#achievements", Static).update(""); return
        p   = self._pet
        cnt = len(p.achievements)
        if cnt:
            from .models import TOTAL_ACHIEVEMENTS
            bar = "█"*(cnt*13//TOTAL_ACHIEVEMENTS) + "░"*(13-cnt*13//TOTAL_ACHIEVEMENTS)
            self.query_one("#achievements", Static).update(
                f"[yellow]🏆 {cnt}/{TOTAL_ACHIEVEMENTS}[/yellow]  "
                f"[dim][{bar}]  tamagit achievements[/dim]"
            )
        else:
            self.query_one("#achievements", Static).update("[dim]No achievements yet.[/dim]")

    def _update_log(self) -> None:
        from . import config_manager as _cfg
        if not _cfg.get("show_events"):
            self.query_one("#log-panel", Static).update(""); return
        p = self._pet
        if not p.events_log:
            self.query_one("#log-panel", Static).update("[dim]No events yet.[/dim]"); return
        lines = []
        for i, entry in enumerate(reversed(p.events_log[-7:])):
            style = "bold bright_white" if i == 0 else "dim"
            lines.append(f"[{style}]{entry}[/{style}]")
        self.query_one("#log-panel", Static).update("\n".join(lines))

    # ── Actions ────────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._load(); self.notify("Refreshed!", timeout=2)

    def action_quit(self) -> None:
        self.exit()

    def action_toggle_theme(self) -> None:
        """Toggle between dark and monochrome theme."""
        from . import config_manager as _cfg
        current   = _cfg.get("theme")
        new_theme = "monochrome" if current == "dark" else "dark"
        _cfg.set_("theme", new_theme)
        self._mono = (new_theme == "monochrome")
        # Force CSS reload
        self.refresh_css()
        self.notify(f"Theme: {new_theme}", timeout=2)

