"""
TamaGit Demo — preview all visual states interactively.

Usage:
    tamagit demo status   — cycle through all ASCII states in the terminal
    tamagit demo live     — Textual app cycling through all TUI animations
    tamagit demo prompt   — show all prompt formats
"""
from __future__ import annotations

import time
from datetime import datetime


def run_demo(mode: str) -> None:
    if mode == "status":
        _demo_status()
    elif mode == "live":
        _demo_live()
    elif mode == "prompt":
        _demo_prompt()
    else:
        _demo_status()


# ── Status demo ────────────────────────────────────────────────────────────────

_ALL_MOODS = ["ecstatic", "happy", "okay", "sad", "miserable", "sleeping", "on_fire", "ghost"]


def _demo_status() -> None:
    """Cycle through all ASCII states. Press Enter for next, q to quit."""
    from .models import PetState
    from .ui import get_pet_ascii, stat_bar, BOLD, CYAN, DIM, GREEN, RESET, YELLOW

    print(f"\n  {BOLD}TamaGit Demo — ASCII States{RESET}")
    print(f"  {DIM}Press Enter for next state, 'q' to quit.{RESET}\n")

    # Build fake pets for each mood state
    mood_configs = {
        "ecstatic":  dict(hunger=90.0, energy=90.0, mood=92.0, health=100.0),
        "happy":     dict(hunger=70.0, energy=70.0, mood=70.0, health=90.0),
        "okay":      dict(hunger=50.0, energy=50.0, mood=50.0, health=70.0),
        "sad":       dict(hunger=30.0, energy=30.0, mood=30.0, health=50.0),
        "miserable": dict(hunger=15.0, energy=15.0, mood=15.0, health=30.0),
        "sleeping":  dict(hunger=60.0, energy=60.0, mood=60.0, health=80.0),
        "on_fire":   dict(hunger=80.0, energy=80.0, mood=80.0, health=90.0),
        "ghost":     dict(hunger=0.0,  energy=0.0,  mood=0.0,  health=0.0),
    }

    for i, mood in enumerate(_ALL_MOODS, 1):
        pet = PetState(name="Pixel", **mood_configs[mood])

        # Force sleeping / on_fire state via last_activity_at / streak
        if mood == "sleeping":
            from datetime import timedelta
            pet.last_activity_at = (datetime.now() - timedelta(hours=13)).isoformat()
        elif mood == "on_fire":
            pet.streak_days = 8
        elif mood == "ghost":
            pet.alive = False

        _clear()
        print(f"\n  {BOLD}State {i}/{len(_ALL_MOODS)}: {CYAN}{mood}{RESET}\n")
        print(get_pet_ascii(pet))
        print()
        print(stat_bar("Hunger", pet.hunger))
        print(stat_bar("Energy", pet.energy))
        print(stat_bar("Mood",   pet.mood))
        print(stat_bar("Health", pet.health))
        print()

        # Also show minimal and emoji styles
        from . import config_manager
        original_style = config_manager.get("ascii_style")

        print(f"  {DIM}[minimal style]{RESET}")
        config_manager.set_("ascii_style", "minimal")
        print(get_pet_ascii(pet))

        print(f"\n  {DIM}[emoji style]{RESET}")
        config_manager.set_("ascii_style", "emoji")
        print(get_pet_ascii(pet))

        config_manager.set_("ascii_style", original_style or "standard")

        ans = input(f"\n  {DIM}Enter = next  |  q = quit:{RESET}  ").strip().lower()
        if ans == "q":
            break

    _clear()
    print(f"\n  {GREEN}Demo complete!{RESET}\n")


# ── Prompt demo ────────────────────────────────────────────────────────────────

def _demo_prompt() -> None:
    from .models import PetState
    from .ui import get_prompt_string, BOLD, CYAN, DIM, RESET
    from . import config_manager

    print(f"\n  {BOLD}TamaGit Demo — Prompt Formats{RESET}\n")

    moods = ["ecstatic", "happy", "okay", "sad", "miserable", "sleeping", "on_fire", "ghost"]
    formats = ["full", "compact", "minimal"]
    original_fmt = config_manager.get("prompt_format")

    for fmt in formats:
        config_manager.set_("prompt_format", fmt)
        print(f"  {BOLD}{fmt}:{RESET}")
        for mood in moods:
            pet = PetState(name="Pixel", hunger=80.0, energy=74.0, mood=82.0, health=91.0)
            if mood == "sleeping":
                from datetime import timedelta
                pet.last_activity_at = (datetime.now() - timedelta(hours=13)).isoformat()
            elif mood == "on_fire":
                pet.streak_days = 8
            elif mood == "ghost":
                pet.alive = False
            else:
                # Force the mood by tweaking stats
                avg_targets = {
                    "ecstatic": 85, "happy": 65, "okay": 45,
                    "sad": 25, "miserable": 10,
                }
                v = float(avg_targets.get(mood, 70))
                pet.hunger = pet.energy = pet.mood = v

            s = get_prompt_string(pet)
            print(f"    {DIM}{mood:<12}{RESET}  {s}")
        print()

    config_manager.set_("prompt_format", original_fmt or "full")
    print(f"  {DIM}Prompt format restored to '{original_fmt or 'full'}'{RESET}\n")


# ── Live TUI demo ──────────────────────────────────────────────────────────────

def _demo_live() -> None:
    """Textual-based demo that cycles through all TUI states automatically."""
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Static
    from .tui import (
        _WALK, _REACTIONS, _MOOD_COLOR, _get_frame, _get_rx_frame,
        _offset_frame, _sbar, MAX_WALK, _CSS,
    )
    from .models import PetState
    from . import config_manager

    _DEMO_STATES = [
        # (mood_label,     streak, alive, activity_offset_hours)
        ("ecstatic",   0, True,  0),
        ("happy",      0, True,  0),
        ("okay",       0, True,  0),
        ("sad",        0, True,  0),
        ("miserable",  0, True,  0),
        ("sleeping",   0, True,  13),   # 13h of inactivity → sleeping
        ("on_fire",    8, True,  0),    # streak 8 → on_fire
        ("ghost",      0, False, 0),    # dead
        # Reaction animations
        ("rx_push",   0, True,  0),
        ("rx_pr",     0, True,  0),
        ("rx_fail",   0, True,  0),
        ("rx_quest",  0, True,  0),
    ]
    _RX_STATES = {"rx_push", "rx_pr", "rx_fail", "rx_quest"}
    _STATE_DURATION = 60   # ticks (~42 seconds) per state before auto-advancing

    class DemoApp(App):
        CSS = _CSS
        BINDINGS = [
            ("q", "quit",     "Quit"),
            ("n", "next",     "Next state"),
            ("p", "prev",     "Prev state"),
        ]

        def __init__(self):
            super().__init__()
            self._idx       = 0
            self._tick      = 0
            self._walk_pos  = 4.0
            self._walk_dir  = 1
            self._walk_phase= 0
            self._rx_tick   = 0
            self._style     = config_manager.get("ascii_style") or "standard"

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

        def on_mount(self):
            self._refresh(); self.set_interval(0.7, self._tick_fn)

        def _mood(self):
            return _DEMO_STATES[self._idx][0]

        def _tick_fn(self):
            self._tick += 1
            mood  = self._mood()
            is_rx = mood in _RX_STATES

            if not is_rx:
                from .tui import _WALK_SPEED
                speed = _WALK_SPEED.get(mood, 0.3)
                self._walk_pos += speed * self._walk_dir
                if self._walk_pos >= MAX_WALK:
                    self._walk_pos = MAX_WALK; self._walk_dir = -1; self._walk_phase = 1
                elif self._walk_pos <= 0.0:
                    self._walk_pos = 0.0; self._walk_dir = 1; self._walk_phase = 1
                if self._tick % 2 == 0:
                    self._walk_phase = 1 - self._walk_phase
                frame = _get_frame(mood, self._walk_dir, self._walk_phase, self._tick, self._style)
            else:
                self._rx_tick = (self._rx_tick + 1) % 6
                frame = _get_rx_frame(mood, self._rx_tick, self._style)

            offset = int(self._walk_pos)
            art    = frame if self._style == "emoji" else _offset_frame(frame, offset)
            color  = _MOOD_COLOR.get(mood, "white")
            self.query_one("#pet-art", Static).update(f"[{color}]{art}[/{color}]")

            # Auto-advance after _STATE_DURATION ticks
            if self._tick % _STATE_DURATION == 0:
                self._idx = (self._idx + 1) % len(_DEMO_STATES)
                self._rx_tick = 0
                self._refresh()

        def _refresh(self):
            mood, streak, alive, inactivity_h = _DEMO_STATES[self._idx]
            total = len(_DEMO_STATES)
            is_rx = mood in _RX_STATES
            label = f"REACTION: {mood}" if is_rx else f"mood: {mood}"
            self.query_one("#title-bar", Static).update(
                f"[bold][purple]TamaGit Demo[/purple][/bold]  •  "
                f"[cyan]{label}[/cyan]  •  "
                f"[dim]state {self._idx+1}/{total}  •  auto-advances every ~42s[/dim]  •  "
                f"[dim]N=next  P=prev[/dim]"
            )
            # Stat bars
            bars = "\n".join([_sbar("Hunger",75), _sbar("Energy",70),
                              _sbar("Mood",  80), _sbar("Health",90)])
            self.query_one("#stats", Static).update(bars)
            self.query_one("#quest",  Static).update(
                "[yellow]🎯 Make 5 commits as a team today[/yellow] [dim](3/5)[/dim]"
            )
            self.query_one("#team-info", Static).update(
                "[dim]repo[/dim] [blue]owner/repo[/blue]  │  "
                "[dim]fed by[/dim] [cyan]alice[/cyan] [dim](5m ago)[/dim]  │  "
                "📅 [bold]3[/bold]d streak"
            )
            self.query_one("#achievements", Static).update(
                "[yellow]🏆 4/13[/yellow]  [dim][████░░░░░░░░░]  tamagit achievements[/dim]"
            )
            self.query_one("#log-panel", Static).update(
                "[bold bright_white][18 May 14:32] alice pushed 2 commits to 'main'[/bold bright_white]\n"
                "[dim][18 May 14:30] CI 'tests' passed (triggered by alice)[/dim]\n"
                "[dim][18 May 13:15] bob closed issue: \"Fix login bug\"[/dim]\n"
                "[dim][18 May 12:00] New daily quest: Make 5 commits as a team today[/dim]"
            )

        def action_next(self):
            self._idx = (self._idx + 1) % len(_DEMO_STATES)
            self._rx_tick = 0; self._tick = 0; self._refresh()

        def action_prev(self):
            self._idx = (self._idx - 1) % len(_DEMO_STATES)
            self._rx_tick = 0; self._tick = 0; self._refresh()

        def action_quit(self):
            self.exit()

    DemoApp().run()


def _clear() -> None:
    print("\033[2J\033[H", end="")
