"""
TamaGit Live TUI  (tamagit live)
════════════════════════════════
Требует: textual (уже в зависимостях)
Управление: Q — выход, R — принудительное обновление

Каждые 5 секунд читает ~/.tamagit/state.json.
При новом событии в event_log — питомец останавливается, проигрывает
реакцию (~4 секунды), потом возобновляет ходьбу.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static

from .models import PetState
from .storage import Storage
from .ui import _time_ago

# ── Константы анимации ────────────────────────────────────────────────────────
MAX_WALK_OFFSET = 9   # максимальный сдвиг питомца влево в ячейках
TOTAL_ACHIEVEMENTS = 13

# Скорость ходьбы (ячеек за тик ~700 мс) — разная для каждого настроения
_WALK_SPEED: dict[str, float] = {
    "ecstatic":  0.55,
    "happy":     0.35,
    "okay":      0.22,
    "sad":       0.12,
    "miserable": 0.06,
    "sleeping":  0.0,    # не ходит, только ZZZ
    "on_fire":   0.65,
    "ghost":     0.09,
}

_MOOD_COLOR: dict[str, str] = {
    "ecstatic": "bright_green", "happy":     "cyan",
    "okay":     "yellow",       "sad":       "magenta",
    "miserable":"red",          "sleeping":  "blue",
    "on_fire":  "orange1",      "ghost":     "grey50",
    "rx_push":  "bright_green", "rx_pr":     "bright_cyan",
    "rx_fail":  "red",          "rx_quest":  "yellow",
}

# ── Конструктор кадра ─────────────────────────────────────────────────────────
def _cat(face: str, sfx: str = "") -> str:
    """Собирает стандартный 5-строчный ASCII-кадр кошки."""
    return (
        f"    /\\_/\\  \n"
        f"   {face}\n"
        f"    > ~ <  {sfx}\n"
        f"   /|   |\\\n"
        f"  (_|   |_)"
    )

# ── Кадры ходьбы ──────────────────────────────────────────────────────────────
# Каждый список: [нейтральный, смотрит_вправо, смотрит_влево]
# При движении вправо — правый глаз ">" (смотрит куда идёт)
# При движении влево  — левый глаз "<"

_WALK: dict[str, list[str]] = {
    "ecstatic": [
        _cat("( ^o^ )", "~"),
        _cat("( >o^ )", "*"),
        _cat("( ^o< )", "*"),
    ],
    "happy": [
        _cat("( ^.^ )"),
        _cat("( >.^ )"),
        _cat("( ^.< )"),
    ],
    "okay": [
        _cat("( -.- )"),
        _cat("( >.- )"),
        _cat("( -.< )"),
    ],
    "sad": [
        _cat("( T.T )"),
        _cat("( T.- )"),
        _cat("( -.T )"),
    ],
    "miserable": [
        _cat("( ;_; )", " ."),
        _cat("( ;_. )", "."),
        _cat("( ._; )", " ."),
    ],
    # Ниже — mood'ы с особым движением (фаза = простой цикл, не направление)
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

# Фреймы реакций — играются на месте (ходьба приостановлена)
_REACTIONS: dict[str, list[str]] = {
    "rx_push": [
        _cat("( *o* )", "nom"),   # ест/доволен
        _cat("( ^o^ )", "!  "),
        _cat("( ^.^ )", "~  "),
    ],
    "rx_pr": [
        _cat("( ^o^ )", "✓  "),
        _cat("(>^.^<)", "!  "),
        _cat("( ^.^ )", "   "),
    ],
    "rx_fail": [
        _cat("( ;_; )", "!  "),   # расстроен
        _cat("( T.T )", "   "),
        _cat("( T.T )", ".  "),
    ],
    "rx_quest": [
        _cat("( ^o^ )", "🎯"),
        _cat("( ^.^ )", "✓ "),
        _cat("( ^.^ )", "  "),
    ],
}

_SIMPLE_CYCLE = {"sleeping", "on_fire", "ghost"}


def _walk_frame(mood: str, direction: int, phase: int, tick: int) -> str:
    """Выбирает кадр для текущего состояния ходьбы.

    Для sleeping/on_fire/ghost — простой цикл по тикам.
    Для остальных — направленные кадры (нейтральный / вправо / влево).
    """
    frames = _WALK.get(mood, _WALK["happy"])
    if mood in _SIMPLE_CYCLE:
        return frames[(tick // 2) % len(frames)]
    if phase == 0:
        return frames[0]  # нейтральный
    return frames[1] if direction >= 0 else frames[2]


def _apply_offset(frame: str, offset: int) -> str:
    """Добавляет отступ к каждой строке — эффект движения по горизонтали."""
    pad = " " * max(0, offset)
    return "\n".join(pad + line for line in frame.split("\n"))


# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
Screen { background: #0d0d0d; }

#title-bar {
    background: #16213e;
    height: 3;
    content-align: center middle;
    border: solid #7c3aed;
}

#main-area { height: 1fr; }

#left-panel {
    width: 44;
    border: solid #374151;
    background: #111111;
    padding: 1 0;
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

Footer { background: #16213e; }
"""


# ── Приложение ────────────────────────────────────────────────────────────────

class TamaGitApp(App):
    """Live TUI — питомец ходит по экрану в реальном времени.

    Архитектура:
    - _tick() каждые 700 мс: обновляет позицию и кадр анимации
    - _poll() каждые 5 с: читает state.json, при новом событии запускает реакцию
    - Реакция: питомец останавливается, проигрывает 3 кадра (~4 с), продолжает ходить
    - Событие обнаруживается по изменению ПОСЛЕДНЕЙ строки events_log
    """

    CSS = _CSS
    BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh")]

    def __init__(self) -> None:
        super().__init__()
        self._storage = Storage()
        self._vps_url = os.environ.get("TAMAGIT_VPS_URL", "").rstrip("/")
        self._pet: Optional[PetState] = None

        # Состояние ходьбы
        self._tick_n: int = 0
        self._walk_pos: float = 4.0     # 0 … MAX_WALK_OFFSET
        self._walk_dir: int = 1          # +1 вправо, -1 влево
        self._walk_phase: int = 0        # 0 нейтральный, 1 шаг

        # Состояние реакции
        self._reaction: str = ""
        self._rx_tick: int = 0           # индекс тика внутри реакции
        self._rx_total: int = 6          # сколько тиков длится реакция

        # Детектор новых событий
        self._last_event: str = ""

    # ── Инициализация ─────────────────────────────────────────────────────────

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

    # ── Анимационный тик ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        """700 мс тик: движение/кадр реакции → обновление ASCII."""
        self._tick_n += 1
        if self._pet is None:
            return

        if self._reaction:
            # Реакция активна — шагаем по кадрам, позиция не меняется
            self._rx_tick += 1
            if self._rx_tick >= self._rx_total:
                self._reaction = ""
                self._rx_tick = 0
        else:
            # Нормальная ходьба
            mood = self._pet.mood_label
            speed = _WALK_SPEED.get(mood, 0.3)
            self._walk_pos += speed * self._walk_dir

            if self._walk_pos >= MAX_WALK_OFFSET:
                self._walk_pos = MAX_WALK_OFFSET
                self._walk_dir = -1
                self._walk_phase = 1  # начать шаг в новом направлении
            elif self._walk_pos <= 0.0:
                self._walk_pos = 0.0
                self._walk_dir = 1
                self._walk_phase = 1

            # Чередование нейтральный / шаговый кадр каждые 2 тика
            if self._tick_n % 2 == 0:
                self._walk_phase = 1 - self._walk_phase

        self._render_art()

    def _render_art(self) -> None:
        if self._pet is None:
            return
        mood = self._pet.mood_label
        offset = int(self._walk_pos)

        if self._reaction:
            # Реакция — специальный кадр, позиция фиксирована
            frames = _REACTIONS.get(self._reaction, [_cat("( ^.^ )")])
            frame = frames[(self._rx_tick // 2) % len(frames)]
            color = _MOOD_COLOR.get(self._reaction, "white")
        else:
            frame = _walk_frame(mood, self._walk_dir, self._walk_phase, self._tick_n)
            color = _MOOD_COLOR.get(mood, "white")

        art = _apply_offset(frame, offset)
        self.query_one("#pet-art", Static).update(f"[{color}]{art}[/{color}]")

    # ── Опрос state.json ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._storage.is_initialized():
            self.query_one("#title-bar", Static).update(
                "[bold red]No pet.[/bold red]  Run [cyan]tamagit init[/cyan] first."
            )
            return
        self._pet = self._storage.load()
        self._last_event = self._pet.events_log[-1] if self._pet.events_log else ""
        self._refresh_ui()

    def _poll(self) -> None:
        """Каждые 5 с: читаем state — либо с VPS напрямую, либо из локального файла.

        Если TAMAGIT_VPS_URL задан — опрашиваем GET /state на VPS.
        Это даёт по-настоящему реальное время без ручного sync.
        Если VPS недоступен — тихо переключаемся на локальный файл.
        """
        if self._vps_url:
            try:
                resp = urllib.request.urlopen(f"{self._vps_url}/state", timeout=3)
                data = json.loads(resp.read().decode())
                pet  = PetState.from_dict(data)
            except Exception:
                # VPS недоступен — fallback на локальный файл без сообщения об ошибке
                if not self._storage.is_initialized():
                    return
                pet = self._storage.load()
        elif not self._storage.is_initialized():
            return
        else:
            pet = self._storage.load()

        # Сравниваем последнее событие — НЕ last_updated (тот меняется при любом decay)
        current = pet.events_log[-1] if pet.events_log else ""
        if current and current != self._last_event:
            self._last_event = current
            self._trigger_reaction(current)

        self._pet = pet
        self._refresh_ui()

    def _trigger_reaction(self, event_text: str) -> None:
        """Определяет тип реакции по тексту события и запускает её."""
        evt = event_text.lower()
        if any(w in evt for w in ("pushed", "commit", "nom nom")):
            self._start_reaction("rx_push", f"🍖 Nom nom! Team pushed!")
        elif "merged pr" in evt:
            self._start_reaction("rx_pr",   "✨ PR merged! Health bonus!")
        elif "quest done" in evt:
            self._start_reaction("rx_quest", "🎯 Daily quest complete!")
        elif "achievement" in evt:
            label = event_text.split(":")[-1].strip()[:40]
            self._start_reaction("rx_quest", f"🏆 {label}")
        elif "failed" in evt or ("ci" in evt and "fail" in evt):
            self._start_reaction("rx_fail", "💔 CI failed... pet is stressed")

    def _start_reaction(self, key: str, message: str, ticks: int = 6) -> None:
        """Останавливает ходьбу и запускает реакцию на N тиков."""
        self._reaction  = key
        self._rx_tick   = 0
        self._rx_total  = ticks
        # _walk_pos не меняется → после реакции ходьба возобновится с той же точки
        if message:
            sev = "warning" if key == "rx_fail" else "information"
            self.notify(message, severity=sev, timeout=4)

    # ── Обновление виджетов ───────────────────────────────────────────────────

    def _refresh_ui(self) -> None:
        if self._pet is None:
            return
        self._update_title()
        self._update_stats()
        self._update_quest()
        self._update_team()
        self._update_achievements()
        self._update_log()
        # ASCII-арт обновляется в _render_art (вызывается из _tick)

    def _update_title(self) -> None:
        p = self._pet
        streak = f"  🔥 {p.streak_days}d" if p.streak_days >= 3 else ""
        repo   = f"  [dim]{p.github_repo}[/dim]" if p.github_repo else ""
        src_tag = f"  [dim][VPS ↻5s][/dim]" if self._vps_url else "  [dim][local][/dim]"
        self.query_one("#title-bar", Static).update(
            f"[bold][purple]TamaGit[/purple][/bold]  •  "
            f"[cyan]{p.name}[/cyan]  •  day {p.age_days}"
            f"[orange1]{streak}[/orange1]"
            f"[italic]  {p.mood_label}[/italic]"
            f"{repo}"
            f"{src_tag}"
        )

    def _update_stats(self) -> None:
        p = self._pet
        lines = [
            _sbar("Hunger",  p.hunger),
            _sbar("Energy",  p.energy),
            _sbar("Mood",    p.mood),
            _sbar("Health",  p.health),
        ]
        if not p.alive:
            lines += [
                "",
                "[bold red]💀 Pet is dead[/bold red]",
                f"  commits {p.cooldown_commits}/3 "
                f"• issues {p.cooldown_issues}/1 "
                f"• CI {p.cooldown_ci_ok}/1",
            ]
        self.query_one("#stats", Static).update("\n".join(lines))

    def _update_quest(self) -> None:
        p = self._pet
        if not p.daily_quest_text or p.daily_quest_date != date.today().isoformat():
            self.query_one("#quest", Static).update("[dim]No quest yet today.[/dim]")
            return
        if p.daily_quest_done:
            txt = f"[green]🎯 ✅ {p.daily_quest_text}[/green]"
        else:
            txt = f"[yellow]🎯 {p.daily_quest_text}[/yellow] [dim](in progress)[/dim]"
        self.query_one("#quest", Static).update(txt)

    def _update_team(self) -> None:
        p     = self._pet
        parts = []
        if p.github_repo:
            parts.append(f"[dim]repo[/dim] [blue]{p.github_repo}[/blue]")
        if p.last_fed_by:
            parts.append(f"[dim]fed by[/dim] [cyan]{p.last_fed_by}[/cyan] [dim]({_time_ago(p.last_fed_at)})[/dim]")
        if p.streak_days:
            icon = "🔥" if p.streak_days >= 7 else "📅"
            parts.append(f"{icon} [bold]{p.streak_days}[/bold]d streak")
        self.query_one("#team-info", Static).update("  │  ".join(parts))

    def _update_achievements(self) -> None:
        p   = self._pet
        cnt = len(p.achievements)
        if cnt:
            pct = cnt * 100 // TOTAL_ACHIEVEMENTS
            bar = "█" * (cnt * 13 // TOTAL_ACHIEVEMENTS) + "░" * (13 - cnt * 13 // TOTAL_ACHIEVEMENTS)
            self.query_one("#achievements", Static).update(
                f"[yellow]🏆 {cnt}/{TOTAL_ACHIEVEMENTS}[/yellow]  "
                f"[dim][{bar}] {pct}%  "
                f"(tamagit achievements)[/dim]"
            )
        else:
            self.query_one("#achievements", Static).update(
                "[dim]No achievements yet.[/dim]"
            )

    def _update_log(self) -> None:
        p = self._pet
        if not p.events_log:
            self.query_one("#log-panel", Static).update("[dim]No events yet.[/dim]")
            return
        lines = []
        for i, entry in enumerate(reversed(p.events_log[-7:])):
            style = "bold bright_green" if i == 0 else "dim"
            lines.append(f"[{style}]{entry}[/{style}]")
        self.query_one("#log-panel", Static).update("\n".join(lines))

    # ── Горячие клавиши ───────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._load()
        self.notify("Refreshed!", timeout=2)

    def action_quit(self) -> None:
        self.exit()


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _sbar(label: str, value: float, width: int = 18) -> str:
    """Прогресс-бар с Rich-разметкой."""
    v      = int(value)
    filled = v * width // 100
    bar    = "█" * filled + "░" * (width - filled)
    if v >= 75:   color = "bright_green"
    elif v >= 50: color = "yellow"
    elif v >= 25: color = "dark_orange"
    else:         color = "bright_red"
    return f"[bold]{label:<8}[/bold] [{color}][{bar}] {v:3d}%[/{color}]"
