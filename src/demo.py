"""
TamaGit Demo — preview all visual states.

    tamagit demo status   cycle through all ASCII states
    tamagit demo live     Textual TUI cycling all animations
    tamagit demo prompt   show all prompt formats and moods
"""
from __future__ import annotations
import time
from datetime import datetime, timedelta

# Stats matching each mood for visual accuracy in demos
_MOOD_STATS = {
    "ecstatic":  (90, 90, 92, 100),
    "happy":     (70, 70, 70,  90),
    "okay":      (50, 50, 50,  70),
    "sad":       (30, 30, 30,  50),
    "miserable": (12, 12, 12,  25),
    "sleeping":  (60, 60, 60,  80),  # activity stale for 13h
    "on_fire":   (85, 85, 85,  95),  # streak≥7
    "ghost":     (0,  0,  0,   0),   # dead
    "rx_push":   (62, 72, 75,  85),
    "rx_pr":     (75, 80, 80,  90),
    "rx_fail":   (50, 35, 45,  50),
    "rx_quest":  (75, 75, 85,  88),
}


def _make_pet(mood: str):
    from .models import PetState
    h, e, m, hp = _MOOD_STATS.get(mood, (70, 70, 70, 90))
    pet = PetState(name="Pixel", hunger=float(h), energy=float(e),
                   mood=float(m), health=float(hp))
    if mood == "sleeping":
        pet.last_activity_at = (datetime.now() - timedelta(hours=13)).isoformat()
    elif mood == "on_fire":
        pet.streak_days = 8
        pet.last_activity_at = datetime.now().isoformat()
    elif mood == "ghost":
        pet.alive = False
    return pet


def run_demo(mode: str) -> None:
    if mode == "status":   _demo_status()
    elif mode == "live":   _demo_live()
    elif mode == "prompt": _demo_prompt()
    else:                  _demo_status()


_ALL_MOODS = ["ecstatic","happy","okay","sad","miserable","sleeping","on_fire","ghost"]


def _demo_status() -> None:
    from .ui import get_pet_ascii, stat_bar, BOLD, CYAN, DIM, GREEN, RESET
    from . import config_manager

    print(f"\n  {BOLD}TamaGit Demo — ASCII States{RESET}")
    print(f"  {DIM}Enter = next state  |  q = quit{RESET}\n")

    for i, mood in enumerate(_ALL_MOODS, 1):
        pet = _make_pet(mood)
        _clear()
        print(f"\n  {BOLD}State {i}/{len(_ALL_MOODS)}: {CYAN}{mood}{RESET}\n")

        for style in ("standard", "minimal", "emoji"):
            config_manager.set_("ascii_style", style)
            print(f"  {DIM}[{style}]{RESET}")
            print(get_pet_ascii(pet))

        config_manager.set_("ascii_style", "standard")
        print()
        print(stat_bar("Hunger", pet.hunger))
        print(stat_bar("Energy", pet.energy))
        print(stat_bar("Mood",   pet.mood))
        print(stat_bar("Health", pet.health))
        print()

        if input(f"  {DIM}Enter = next  |  q = quit:{RESET}  ").strip().lower() == "q":
            break

    _clear(); print(f"\n  {GREEN}Demo complete!{RESET}\n")


def _demo_prompt() -> None:
    from .ui import get_prompt_string, BOLD, CYAN, DIM, RESET
    from . import config_manager

    print(f"\n  {BOLD}TamaGit Demo — Prompt Formats{RESET}\n")
    original_fmt = config_manager.get("prompt_format")

    for fmt in ("full", "compact", "minimal"):
        config_manager.set_("prompt_format", fmt)
        print(f"  {BOLD}{fmt}:{RESET}")
        for mood in _ALL_MOODS:
            pet = _make_pet(mood)
            prompt = get_prompt_string(pet)
            print(f"    {DIM}{mood:<12}{RESET}  {prompt}")
        print()

    config_manager.set_("prompt_format", original_fmt or "full")
    print(f"  {DIM}Restored prompt_format = '{original_fmt or 'full'}'{RESET}\n")


def _demo_live() -> None:
    """Textual TUI that cycles through all states.  N = next, P = prev, Q = quit."""
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Static
    from .tui import (
        _WALK, _REACTIONS, _WALK_EMOJI, _REACTIONS_EMOJI,
        _WALK_MIN, _REACTIONS_MIN,
        _MOOD_COLOR, _get_frame, _get_rx_frame,
        _offset_frame, _sbar, MAX_WALK, _CSS_DARK, _CSS_MONO, _WALK_SPEED,
    )
    from .models import TOTAL_ACHIEVEMENTS
    from . import config_manager as _cfg

    _RX_STATES = {"rx_push", "rx_pr", "rx_fail", "rx_quest"}
    _DEMO_STATES = list(_ALL_MOODS) + list(_RX_STATES)
    _STATE_DURATION = 60   # ticks (~42 s) before auto-advance

    class DemoApp(App):
        CSS = _CSS_DARK
        BINDINGS = [
            ("q", "quit",  "Quit"),
            ("n", "next",  "Next state"),
            ("p", "prev",  "Prev state"),
            ("t", "theme", "Toggle theme"),
            ("ctrl+p", "noop", ""),
        ]

        def __init__(self):
            super().__init__()
            self._idx       = 0
            self._tick      = 0
            self._walk_pos  = 4.0
            self._walk_dir  = 1
            self._walk_phase= 0
            self._rx_tick   = 0
            self._mono      = (_cfg.get("theme") == "monochrome")
            self._style     = _cfg.get("ascii_style") or "standard"

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

        def _mood(self): return _DEMO_STATES[self._idx]

        def _tick_fn(self):
            self._tick += 1
            mood  = self._mood()
            is_rx = mood in _RX_STATES
            self._style = _cfg.get("ascii_style") or "standard"

            if not is_rx:
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
            if self._mono:
                self.query_one("#pet-art", Static).update(art)
            else:
                color = _MOOD_COLOR.get(mood, "white")
                self.query_one("#pet-art", Static).update(f"[{color}]{art}[/{color}]")

            if self._tick % _STATE_DURATION == 0:
                self._idx = (self._idx + 1) % len(_DEMO_STATES)
                self._rx_tick = 0; self._tick = 0; self._refresh()

        def _refresh(self):
            mood   = self._mood()
            total  = len(_DEMO_STATES)
            is_rx  = mood in _RX_STATES
            label  = f"REACTION: {mood}" if is_rx else f"mood: {mood}"
            self.query_one("#title-bar", Static).update(
                f"[bold][purple]TamaGit Demo[/purple][/bold]  •  "
                f"[cyan]{label}[/cyan]  •  "
                f"[dim]state {self._idx+1}/{total}  •  auto ~42s  •  N/P=manual  T=theme[/dim]"
            )
            # Stats matching the displayed mood (for visual accuracy)
            h, e, m, hp = _MOOD_STATS.get(mood, (70, 70, 70, 90))
            mono = self._mono
            bars = "\n".join([_sbar("Hunger",h,mono=mono), _sbar("Energy",e,mono=mono),
                              _sbar("Mood",  m,mono=mono), _sbar("Health",hp,mono=mono)])
            self.query_one("#stats", Static).update(bars)
            self.query_one("#quest", Static).update(
                "[yellow]🎯 Make 5 commits as a team today[/yellow] [dim](3/5)[/dim]"
            )
            self.query_one("#team-info", Static).update(
                "[dim]fed by[/dim] [cyan]alice[/cyan] [dim](5m ago)[/dim]  │  📅 [bold]3[/bold]d streak"
            )
            self.query_one("#achievements", Static).update(
                "[yellow]🏆 4/13[/yellow]  [dim][████░░░░░░░░░]  tamagit achievements[/dim]"
            )
            self.query_one("#log-panel", Static).update(
                "[bold bright_white][18 May 14:32] alice pushed 2 commits[/bold bright_white]\n"
                "[dim][18 May 14:30] CI 'tests' passed (triggered by alice)[/dim]\n"
                "[dim][18 May 13:15] bob closed issue: \"Fix login bug\"[/dim]\n"
                "[dim][18 May 12:00] Team quest: Make 5 commits today[/dim]"
            )

        def action_next(self):
            self._idx = (self._idx + 1) % len(_DEMO_STATES)
            self._rx_tick = 0; self._tick = 0; self._refresh()

        def action_prev(self):
            self._idx = (self._idx - 1) % len(_DEMO_STATES)
            self._rx_tick = 0; self._tick = 0; self._refresh()

        def action_theme(self):
            _cfg.set_("theme", "monochrome" if not self._mono else "dark")
            self._mono = not self._mono
            self.refresh_css()
            self.notify(f"Theme: {'monochrome' if self._mono else 'dark'}", timeout=2)

        def action_quit(self): self.exit()
        def action_noop(self): pass

    DemoApp().run()


def _clear() -> None:
    print("\033[2J\033[H", end="")
