from __future__ import annotations

import hashlib
import hmac
import json
import os
from threading import Lock
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from .github_integration import parse_github_webhook
from .pet_engine import apply_github_event, update_from_time
from .storage import Storage


app = FastAPI(title="GitTama Webhook Server")
_state_lock = Lock()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, Any]:
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)

    if not x_github_event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event = parse_github_webhook(x_github_event, payload)

    with _state_lock:
        storage = Storage()
        pet = storage.load()
        update_from_time(pet)
        messages = apply_github_event(pet, event)
        storage.save(pet)

    return {
        "ok": True,
        "github_event": x_github_event,
        "event_type": event.type,
        "ignored": event.ignored,
        "messages": messages,
        "pet": {
            "hunger": pet.hunger,
            "energy": pet.energy,
            "mood": pet.mood,
            "health": pet.health,
        },
    }


def _verify_signature(body: bytes, signature: str | None) -> None:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        return

    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
