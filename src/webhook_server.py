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

app = FastAPI(title="TamaGit Webhook Server")

# Лок нужен на случай, если несколько webhook-ов придут одновременно
_state_lock = Lock()


@app.get("/health")
def health() -> dict[str, str]:
    """Простая проверка что сервер жив."""
    return {"status": "ok"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, Any]:
    """Основной endpoint для GitHub webhook-ов.

    Порядок работы:
    1. Проверяем HMAC-подпись (если задан секрет)
    2. Проверяем что событие от нужного репозитория
    3. Парсим событие и применяем к состоянию питомца
    4. Возвращаем JSON с результатом
    """
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)

    if not x_github_event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    _verify_repository(payload)
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
        "event_type":   event.type,
        "contributor":  event.contributor,
        "ignored":      event.ignored,
        "messages":     messages,
        "pet": {
            "name":   pet.name,
            "alive":  pet.alive,
            "hunger": int(pet.hunger),
            "energy": int(pet.energy),
            "mood":   int(pet.mood),
            "health": int(pet.health),
            "streak": pet.streak_days,
        },
        "cooldown_done": pet.cooldown_done if not pet.alive else None,
    }


def _verify_signature(body: bytes, signature: str | None) -> None:
    """Проверяем HMAC-SHA256 подпись от GitHub.
    Если GITHUB_WEBHOOK_SECRET не задан — пропускаем (для разработки).
    """
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        return
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256")
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _verify_repository(payload: dict[str, Any]) -> None:
    """Проверяем что событие пришло от нужного репозитория.
    Если GITHUB_REPO не задан — пропускаем (принимаем всё).
    """
    expected = os.environ.get("GITHUB_REPO")
    if not expected:
        return
    repo = (payload.get("repository") or {}).get("full_name")
    if repo != expected:
        raise HTTPException(
            status_code=403,
            detail=f"Unexpected repository: {repo or 'unknown'}",
        )
