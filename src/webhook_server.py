"""
TamaGit Webhook Server — FastAPI app receiving GitHub events.

Endpoints:
    GET  /health        liveness check
    GET  /state         current pet state (404 if not yet initialized)
    GET  /graveyard     list of dead pets (404 if not yet initialized)
    PUT  /state/name    rename the pet (team admin action)
    POST /webhook/github  main GitHub webhook receiver

Architecture notes:
    - ALL game-logic changes happen here (stats, streak, quest, achievements).
    - Local CLI is read-only / display-only for game state.
    - update_from_time() is called before every read and write so decay
      accumulates correctly even if no events come in for hours.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
from threading import Lock
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from .github_integration import parse_github_webhook
from .models import PetState, DEFAULT_PET_NAMES
from .pet_engine import apply_github_event, refresh_daily_quest, update_from_time
from .storage import Storage

app = FastAPI(title="TamaGit Webhook Server")
_lock = Lock()


# ── Health & state ─────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/state")
def get_state() -> dict[str, Any]:
    """Return pet state as JSON.

    Returns 404 if tamagit init has not been run yet.
    Runs update_from_time() so decay is always up-to-date when clients sync.
    """
    with _lock:
        storage = Storage()
        if not storage.is_initialized():
            raise HTTPException(
                status_code=404,
                detail="No pet yet. Run 'tamagit init' on the server first.",
            )
        pet = storage.load()
        update_from_time(pet)   # apply time-based decay before serving
        storage.save(pet)
    return pet.to_dict()


@app.get("/graveyard")
def get_graveyard() -> list[dict]:
    """Return all graveyard entries. Returns 404 if not initialized."""
    storage = Storage()
    if not storage.is_initialized():
        raise HTTPException(status_code=404, detail="No pet yet.")
    return [e.to_dict() for e in storage.load_graveyard()]


@app.put("/state/name")
def set_name(body: dict[str, str]) -> dict[str, Any]:
    """Rename the team pet (intended for admin use from the server machine)."""
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    with _lock:
        storage = Storage()
        if not storage.is_initialized():
            raise HTTPException(status_code=404, detail="No pet yet.")
        pet = storage.load()
        old = pet.name
        pet.name = name
        pet.add_event(f"Pet renamed: {old} → {name}")
        storage.save(pet)
    return {"ok": True, "name": name}


# ── Main webhook ──────────────────────────────────────────────────────────────

@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event:      str | None = Header(default=None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, Any]:
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)

    if not x_github_event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event")

    try:
        payload = json.loads(body.decode() or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    _verify_repository(payload)
    event = parse_github_webhook(x_github_event, payload)

    with _lock:
        storage = Storage()

        # Don't process events if no pet has been initialized yet
        if not storage.is_initialized():
            return {"ok": True, "ignored": True, "reason": "no pet initialized"}

        pet = storage.load()
        update_from_time(pet)

        # Refresh quest on first event of the day (server-side generation)
        context = _build_quest_context()
        refresh_daily_quest(pet, context)

        messages = apply_github_event(pet, event)

        # Auto-resurrect after cooldown completes
        resurrected = False
        if not pet.alive and pet.cooldown_done:
            pet, _ = _auto_resurrect(pet, storage)
            resurrected = True

        storage.save(pet)

    return {
        "ok":          True,
        "event_type":  event.type,
        "contributor": event.contributor,
        "ignored":     event.ignored,
        "messages":    messages,
        "resurrected": resurrected,
        "pet": {
            "name":   pet.name,
            "alive":  pet.alive,
            "hunger": int(pet.hunger),
            "energy": int(pet.energy),
            "mood":   int(pet.mood),
            "health": int(pet.health),
            "streak": pet.streak_days,
        },
    }


# ── Auto-resurrection ──────────────────────────────────────────────────────────

def _auto_resurrect(dead_pet: PetState, storage: Storage) -> tuple[PetState, Any]:
    """Bury dead pet and hatch a new one with stats based on cooldown quality."""
    entry = storage.bury(dead_pet)
    new_name = dead_pet.random_name()

    # Better cooldown performance → better starting stats
    hunger = 40.0 + dead_pet.cooldown_commits * 10.0
    energy = 40.0 + dead_pet.cooldown_ci_ok    * 30.0
    mood   = 40.0 + dead_pet.cooldown_issues   * 20.0
    health = (hunger + energy + mood) / 3

    new_pet = PetState(
        name=new_name,
        github_repo=dead_pet.github_repo,
        hunger=hunger, energy=energy, mood=mood, health=health,
        git_repos=dead_pet.git_repos,
        custom_pet_names=dead_pet.custom_pet_names,
    )
    new_pet.add_event(f"New team pet hatched: {new_name}!")
    new_pet.add_event(
        f"Starting stats reflect cooldown work — "
        f"H:{int(hunger)} E:{int(energy)} M:{int(mood)}"
    )

    _notify_resurrection(new_name, dead_pet.name, dead_pet.github_repo)
    return new_pet, entry


def _notify_resurrection(new_name: str, old_name: str, github_repo: str) -> None:
    """Create a GitHub issue to notify the team (best-effort)."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token or "/" not in (github_repo or ""):
        return
    try:
        from .github_api import create_issue
        owner, repo = github_repo.split("/", 1)
        create_issue(
            owner, repo, token,
            title=f"🐣 New team pet: {new_name}!",
            body=(
                f"The previous pet **{old_name}** has passed away.\n\n"
                f"A new pet **{new_name}** has just hatched! 🥚\n\n"
                f"Run `tamagit sync` to meet your new team companion.\n\n"
                f"*To rename: SSH to the server and run `tamagit rename <name>`*"
            ),
            labels=["tamagit"],
        )
    except Exception:
        pass


def _build_quest_context() -> dict | None:
    """Fetch repo context for contextual quest generation via GitHub API."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo  = os.environ.get("GITHUB_REPO", "")
    if not token or "/" not in (repo or ""):
        return None
    try:
        from .github_api import get_open_issues, get_open_prs, get_latest_ci_run
        owner, repo_name = repo.split("/", 1)
        issues  = get_open_issues(owner, repo_name, token)
        prs     = get_open_prs(owner, repo_name, token)
        run     = get_latest_ci_run(owner, repo_name, token)
        ci_fail = bool(run and run.get("conclusion") == "failure")
        return {"open_issues": len(issues), "open_prs": len(prs), "ci_failing": ci_fail}
    except Exception:
        return None


# ── Security ──────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature: str | None) -> None:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


def _verify_repository(payload: dict) -> None:
    expected = os.environ.get("GITHUB_REPO", "")
    if not expected:
        return
    actual = (payload.get("repository") or {}).get("full_name", "")
    if actual != expected:
        raise HTTPException(status_code=403, detail=f"Unexpected repo: {actual}")
