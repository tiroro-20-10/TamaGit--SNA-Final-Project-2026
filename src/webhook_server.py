"""
TamaGit Webhook Server
======================
FastAPI server that receives GitHub webhook events and updates the team pet.

Key responsibilities (all VPS-side only):
  - Verify HMAC signatures and repository filter
  - Refresh daily quest on first event of each day
  - Apply event effects to pet stats
  - Award team achievements
  - Auto-resurrect the pet after cooldown is complete
  - Expose /state endpoint for client sync
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import string
from datetime import datetime
from threading import Lock
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from .github_integration import parse_github_webhook
from .models import PetState, DEFAULT_PET_NAMES
from .pet_engine import apply_github_event, refresh_daily_quest, update_from_time
from .storage import Storage

app = FastAPI(title="TamaGit Webhook Server")
_lock = Lock()


# ── Health & state endpoints ───────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/state")
def get_state() -> dict[str, Any]:
    """Return current pet state JSON — used by 'tamagit sync'."""
    with _lock:
        pet = Storage().load()
    return pet.to_dict()


@app.put("/state/name")
def set_name(body: dict[str, str]) -> dict[str, Any]:
    """Rename the team pet (called by 'tamagit rename' from admin machine)."""
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    with _lock:
        storage = Storage()
        pet = storage.load()
        old = pet.name
        pet.name = name
        pet.add_event(f"Pet renamed: {old} → {name}")
        storage.save(pet)
    return {"ok": True, "name": name}


# ── Main webhook endpoint ──────────────────────────────────────────────────────

@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event:       str | None = Header(default=None, alias="X-GitHub-Event"),
    x_hub_signature_256:  str | None = Header(default=None, alias="X-Hub-Signature-256"),
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
        pet     = storage.load()
        update_from_time(pet)

        # Refresh quest on first event of the day (server-side, so all clients agree)
        quest_context = _build_quest_context()
        refresh_daily_quest(pet, quest_context)

        messages = apply_github_event(pet, event)

        # Auto-resurrect after successful cooldown
        resurrected = False
        if not pet.alive and pet.cooldown_done:
            pet, entry = _auto_resurrect(pet, storage)
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


# ── Auto-resurrection ─────────────────────────────────────────────────────────

def _auto_resurrect(dead_pet: PetState, storage: Storage) -> tuple[PetState, Any]:
    """Bury the dead pet and create a new one automatically.

    Initial stats are influenced by cooldown performance:
      - 3 commits   → hunger starts healthy
      - 1 CI success → energy starts healthy
      - 1 issue closed → mood starts healthy
    This rewards a team that did REAL work during cooldown.
    """
    entry = storage.bury(dead_pet)

    new_name = dead_pet.random_name()

    # Stats based on what the team actually did during cooldown
    hunger = 40.0 + dead_pet.cooldown_commits * 10.0   # up to 70
    energy = 40.0 + dead_pet.cooldown_ci_ok * 30.0     # 40 or 70
    mood   = 40.0 + dead_pet.cooldown_issues * 20.0    # 40 or 60
    health = (hunger + energy + mood) / 3               # derived

    new_pet = PetState(
        name=new_name,
        github_repo=dead_pet.github_repo,
        hunger=hunger,
        energy=energy,
        mood=mood,
        health=health,
        git_repos=dead_pet.git_repos,      # preserve local repo metadata
        custom_pet_names=dead_pet.custom_pet_names,
    )
    new_pet.add_event(f"New team pet hatched: {new_name}!")
    new_pet.add_event(
        f"Starting stats reflect cooldown work — "
        f"H:{int(hunger)} E:{int(energy)} M:{int(mood)}"
    )

    # Try to notify the team via a GitHub issue (best-effort)
    _notify_resurrection(new_name, dead_pet.name, dead_pet.github_repo)

    return new_pet, entry


def _notify_resurrection(new_name: str, old_name: str, github_repo: str) -> None:
    """Create a GitHub issue to announce the new pet (best-effort, errors silenced)."""
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
                f"*If you'd like to rename the pet, run `tamagit rename <name>` "
                f"from a machine with VPS access.*"
            ),
            labels=["tamagit"],
        )
    except Exception:
        pass  # notification is best-effort


def _build_quest_context() -> dict | None:
    """Fetch GitHub repo context for contextual quest generation.

    Returns None if token/repo are not configured.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    repo  = os.environ.get("GITHUB_REPO", "")
    if not token or "/" not in (repo or ""):
        return None
    try:
        from .github_api import get_open_issues, get_open_prs, get_latest_ci_run
        owner, repo_name = repo.split("/", 1)
        issues   = get_open_issues(owner, repo_name, token)
        prs      = get_open_prs(owner, repo_name, token)
        run      = get_latest_ci_run(owner, repo_name, token)
        ci_fail  = run and run.get("conclusion") == "failure"
        return {
            "open_issues": len(issues),
            "open_prs":    len(prs),
            "ci_failing":  bool(ci_fail),
        }
    except Exception:
        return None


# ── Security helpers ──────────────────────────────────────────────────────────

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
