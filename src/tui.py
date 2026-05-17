"""
TamaGit Live TUI
════════════════
Запуск:  tamagit live
Требует: pip install textual  (уже включено в зависимости)

Каждые 5 секунд читает ~/.tamagit/state.json.
При новом событии показывает реакцию питомца 3 секунды, потом
возвращается в idle-анимацию. Управление: Q = выход, R = обновить.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Static

from .models import PetState
from .storage import Storage
from .ui import _time_ago


# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
Screen {
    background: #0d0d0d;
}

#title-bar {
    background: #16213e;
    height: 3;
    content-align: center middle;
    border: solid #7c3aed;
}

#main-area {
    height: 1fr;
}

#left-panel {
    width: 40;
    border: solid #374151;
    background: #111111;
    align: center middle;
    padding: 1;
}

#right-panel {
    width: 1fr;
    border: solid #374151;
    background: #111111;
    padding: 1 2;
}

#log-panel {
    height: 9;
    border: solid #1f2937;
    background: #0a0a0a;
    padding: 0 2;
}

Footer {
    background: #16213e;
}
"""

# ── Анимационные кадры ────────────────────────────────────────────────────────
# Каждый список — набор поз для конкретного настроения или реакции.
# Кадры переключаются каждые 700 мс.

_FRAMES: dict[str, list[str]] = {
    "ecstatic": [
        "    /\\_/\\  \n   ( ^o^ )~*\n    > ~ <  *\n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\ *\n   ( ^o^ )  \n    > ~ < * \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( ^o^ ) ~\n    > ~ <   \n   /|   |\\\n  (_|   |_)",
    ],
    "happy": [
        "    /\\_/\\  \n   ( ^.^ ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( ^.^ ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( -.^ ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( ^.^ ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
    ],
    "okay": [
        "    /\\_/\\  \n   ( -.- ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( -.- ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( o.- ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( -.- ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
    ],
    "sad": [
        "    /\\_/\\  \n   ( T.T ) \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( T.T ). \n    > ~ <  .\n   /|   |\\\n  (_|   |_)",
    ],
    "miserable": [
        "    /\\_/\\  \n   ( ;_; )  .\n    >   <   .\n   /|   |\\ .\n  (_|   |_)",
        "    /\\_/\\  \n   ( ;.; )   \n    >   <   \n   /|   |\\\n  (_|   |_)",
    ],
    "sleeping": [
        "    /\\_/\\  \n   ( z.z )  z\n    > ~ <   \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( z.z )   \n    > ~ <   \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( z.z ) z z\n    > ~ <  \n   /|   |\\\n  (_|   |_)",
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
    # Реакции на события (3 секунды, потом возврат в idle)
    "rx_push": [
        "    /\\_/\\  \n   ( *o* ) !\n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( ^o^ )~*\n    > ~ < * \n   /|   |\\\n  (_|   |_)",
    ],
    "rx_pr": [
        "    /\\_/\\  \n   ( ^o^ ) ✓\n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   (>^.^<)  \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
    ],
    "rx_fail": [
        "    /\\_/\\  \n   ( ;_; ) !\n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( T.T )  \n    > ~ <  \n   /|   |\\\n  (_|   |_)",
    ],
    "rx_quest": [
        "    /\\_/\\  \n   ( ^o^ ) 🎯\n    > ~ <  \n   /|   |\\\n  (_|   |_)",
        "    /\\_/\\  \n   ( ^.^ ) ✓\n    > ~ <  \n   /|   |\\\n  (_|   |_)",
    ],
}

_MOOD_COLORS: dict[str, str] = {
    "ecstatic": "bright_green", "happy": "cyan",
    "okay": "yellow",           "sad": "magenta",
    "miserable": "red",         "sleeping": "blue",
    "on_fire": "orange1",       "ghost": "grey50",
    "rx_push": "bright_green",  "rx_pr": "bright_cyan",
    "rx_fail": "red",           "rx_quest": "yellow",
}


def _stat_bar(label: str, value: float, width: int = 18) -> str:
    """Прогресс-бар с Rich-разметкой для Textual Static."""
    v      = int(value)
    filled = v * width // 100
    bar    = "█" * filled + "░" * (width - filled)
    if v >= 75:   color = "bright_green"
    elif v >= 50: color = "yellow"
    elif v >= 25: color = "dark_orange"
    else:         color = "bright_red"
    return f"[bold]{label:<8}[/bold] [{color}][{bar}] {v:3d}%[/{color}]"


# ── Приложение ────────────────────────────────────────────────────────────────

class TamaGitApp(App):
    """Live TUI — анимированный питомец в реальном времени.

    Архитектура:
    - Опрос state.json каждые 5 секунд (_poll_state)
    - Анимация кадров каждые 700 мс (_tick)
    - При новом событии — 3 секунды реакции, потом возврат в idle
    - Уведомления через встроенный Textual notify()
    """

    CSS = _CSS
    BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh")]

    def __init__(self) -> None:
        super().__init__()
        self._storage    = Storage()
        self._pet:  Optional[PetState] = None
        self._frame: int = 0
        self._reaction: str = ""
        self._reaction_ticks: int = 0
        self._last_event_ts: str = ""

    # ── Интерфейс ─────────────────────────────────────────────────────────────

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
        self._load()
        self.set_interval(0.7, self._tick)
        self.set_interval(5.0, self._poll)

    # ── Логика обновления ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._storage.is_initialized():
            self.query_one("#title-bar", Static).update(
                "[bold red]No pet found.[/bold red]  Run [cyan]tamagit init[/cyan] first."
            )
            return
        self._pet = self._storage.load()
        self._last_event_ts = self._pet.last_updated
        self._refresh_all()

    def _poll(self) -> None:
        """Каждые 5 секунд проверяем, не изменился ли state.json."""
        if not self._storage.is_initialized():
            return
        pet = self._storage.load()

        # Определяем тип реакции по последнему событию
        if pet.last_updated != self._last_event_ts and pet.events_log:
            latest = pet.events_log[-1].lower()
            if any(w in latest for w in ("pushed", "commit")):
                self._react("rx_push", f"🍖 {pet.last_fed_by or 'Someone'} pushed! Nom nom!")
            elif "merged pr" in latest:
                self._react("rx_pr", "✨ PR merged! Health bonus!")
            elif "quest done" in latest:
                self._react("rx_quest", "🎯 Daily quest complete!")
            elif "failed" in latest or ("ci" in latest and "fail" in latest):
                self._react("rx_fail", "💔 CI failed... pet is stressed")
            elif "achievement" in latest:
                self._react("rx_quest", f"🏆 {pet.events_log[-1].split(':', 1)[-1].strip()}")

        self._pet = pet
        self._last_event_ts = pet.last_updated
        self._refresh_all()

    def _react(self, reaction: str, message: str) -> None:
        """Запускает 3-секундную реакцию питомца и показывает уведомление."""
        self._reaction = reaction
        self._reaction_ticks = 4   # 4 × 700мс ≈ 3 секунды
        self._frame = 0
        if message:
            severity = "warning" if reaction == "rx_fail" else "information"
            self.notify(message, severity=severity, timeout=4)

    def _tick(self) -> None:
        """Каждые 700 мс: переключаем кадр анимации."""
        if self._pet is None:
            return
        self._frame += 1
        if self._reaction_ticks > 0:
            self._reaction_ticks -= 1
            if self._reaction_ticks == 0:
                self._reaction = ""
                self._frame = 0
        self._update_art()

    def _refresh_all(self) -> None:
        if self._pet is None:
            return
        self._update_title()
        self._update_art()
        self._update_stats()
        self._update_quest()
        self._update_team()
        self._update_achievements()
        self._update_log()

    # ── Отдельные виджеты ─────────────────────────────────────────────────────

    def _update_title(self) -> None:
        pet = self._pet
        streak = f"  🔥 {pet.streak_days}d streak" if pet.streak_days >= 3 else ""
        fed    = f"  last: {pet.last_fed_by}" if pet.last_fed_by else ""
        title  = (
            f"[bold][purple]TamaGit[/purple][/bold]  •  "
            f"[cyan]{pet.name}[/cyan]  •  "
            f"day {pet.age_days}"
            f"[orange1]{streak}[/orange1]"
            f"[dim]{fed}[/dim]  •  "
            f"[italic]{pet.mood_label}[/italic]"
        )
        self.query_one("#title-bar", Static).update(title)

    def _update_art(self) -> None:
        if self._pet is None:
            return
        key    = self._reaction or self._pet.mood_label
        frames = _FRAMES.get(key, _FRAMES["happy"])
        frame  = frames[self._frame % len(frames)]
        color  = _MOOD_COLORS.get(key, "white")
        self.query_one("#pet-art", Static).update(f"[{color}]{frame}[/{color}]")

    def _update_stats(self) -> None:
        pet = self._pet
        lines = [
            _stat_bar("Hunger",  pet.hunger),
            _stat_bar("Energy",  pet.energy),
            _stat_bar("Mood",    pet.mood),
            _stat_bar("Health",  pet.health),
        ]
        # Если питомец мёртв — добавляем сводку cooldown
        if not pet.alive:
            lines += [
                "",
                f"[bold red]💀 Pet is dead[/bold red]",
                f"  Commits {pet.cooldown_commits}/3  "
                f"Issues {pet.cooldown_issues}/1  "
                f"CI {pet.cooldown_ci_ok}/1",
            ]
        self.query_one("#stats", Static).update("\n".join(lines))

    def _update_quest(self) -> None:
        pet = self._pet
        if not pet.daily_quest_text or pet.daily_quest_date != date.today().isoformat():
            self.query_one("#quest", Static).update("[dim]No quest yet today.[/dim]")
            return
        done = pet.daily_quest_done
        txt = (
            f"[green]🎯 ✅ {pet.daily_quest_text}[/green]"
            if done else
            f"[yellow]🎯 {pet.daily_quest_text}[/yellow] [dim](in progress)[/dim]"
        )
        self.query_one("#quest", Static).update(txt)

    def _update_team(self) -> None:
        pet   = self._pet
        parts = []
        if pet.last_fed_by:
            parts.append(f"[dim]Fed by[/dim] [cyan]{pet.last_fed_by}[/cyan] [dim]({_time_ago(pet.last_fed_at)})[/dim]")
        if pet.streak_days:
            icon = "🔥" if pet.streak_days >= 7 else "📅"
            parts.append(f"{icon} [bold]{pet.streak_days}[/bold] day streak")
        if pet.quests_completed:
            parts.append(f"[dim]{pet.quests_completed} quest(s) done[/dim]")
        self.query_one("#team-info", Static).update("   ".join(parts))

    def _update_achievements(self) -> None:
        pet = self._pet
        if not pet.achievements:
            self.query_one("#achievements", Static).update("")
            return
        recent = pet.achievements[-4:]   # последние 4
        line   = "  ".join(f"[yellow]🏆 {a}[/yellow]" for a in recent)
        self.query_one("#achievements", Static).update(line)

    def _update_log(self) -> None:
        pet = self._pet
        if not pet.events_log:
            self.query_one("#log-panel", Static).update("[dim]No events yet.[/dim]")
            return
        lines = []
        for i, entry in enumerate(reversed(pet.events_log[-7:])):
            style = "bold bright_green" if i == 0 else "dim"
            lines.append(f"[{style}]{entry}[/{style}]")
        self.query_one("#log-panel", Static).update("\n".join(lines))

    # ── Горячие клавиши ───────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._load()
        self.notify("Refreshed!", timeout=2)

    def action_quit(self) -> None:
        self.exit()
