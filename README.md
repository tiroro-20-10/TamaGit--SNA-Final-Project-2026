# TamaGit 🐱

**A terminal Tamagotchi for your development team.**  
Your pet lives and dies by the team's GitHub activity — commits, pull requests, CI pipelines and issue hygiene.

---

## Concept

TamaGit is a **shared team pet** that reacts to real GitHub events:

| Event | Effect |
|---|---|
| `git push` / commit | Hunger ↑, Mood ↑ |
| PR merged | Health ↑, Energy ↑, Mood ↑ |
| Issue closed | Mood ↑, Hunger ↑ |
| CI passes | Health ↑, Energy ↑ |
| CI fails | Health ↓, Energy ↓ |
| No activity (days) | All stats decay → death |

Stats range **0–100** (higher = better). The pet dies when Health reaches 0.

---

## Quick Start (local)

```bash
# Install
pip install -e .

# Hatch your team pet (egg animation + name + repo setup)
tamagit init

# Check status
tamagit status

# Scan a local git repo
tamagit scan .

# See event history
tamagit log

# Add pet to your bash prompt
tamagit install-prompt && source ~/.bashrc
```

---

## Webhook Setup (VPS)

The pet reacts to GitHub events in real time via webhook. `tamagit status` also refreshes from the VPS when configured, while `tamagit prompt` stays local for speed.

```bash
# Copy project to VPS
scp -r . root@<your-ip>:/opt/TamaGit

# On the VPS
cp .env.example .env
# Edit .env: set GITHUB_REPO and GITHUB_WEBHOOK_SECRET

# Start the webhook server
docker compose up -d webhook

# Verify
curl http://localhost:8000/health
```

Then in GitHub → Settings → Webhooks → Add webhook:
- **Payload URL**: `http://<your-ip>:8000/webhook/github`
- **Content type**: `application/json`
- **Secret**: value of `GITHUB_WEBHOOK_SECRET` from `.env`
- **Events**: Pushes, Pull requests, Issues, Workflow runs

See `docs/deploy_vps.md` for the full guide.

---

## Commands

```
tamagit init              Hatch a new pet (or adopt after death cooldown)
tamagit status            Full status panel
tamagit log               Event history
tamagit scan [PATH]       Scan a local git repository
tamagit graveyard         See all fallen pets
tamagit install-prompt    Add TamaGit to bash prompt (local cache for speed)
tamagit uninstall-prompt  Remove from bash prompt
tamagit help              Show help
```

---

## Pet States

| State | Condition |
|---|---|
| 🟢 ecstatic | avg stats ≥ 80 |
| 🔵 happy | avg stats ≥ 60 |
| 🟡 okay | avg stats ≥ 40 |
| 🟣 sad | avg stats ≥ 20 |
| 🔴 miserable | avg stats < 20 |
| 💤 sleeping | no activity for 12+ hours |
| 🔥 on fire | streak ≥ 7 days + stats ≥ 70 |
| 👻 ghost | dead (awaiting cooldown) |

---

## Death & Graveyard

When the pet dies, the team must complete a **cooldown** before adopting a new one:

- ☐ Make 3 commits
- ☐ Close 1 issue
- ☐ Get CI green once

After cooldown: `tamagit init` to hatch a new pet.  
All dead pets are preserved in `tamagit graveyard`.

---

## Tech Stack

Python · FastAPI · Docker · GitHub Webhooks · GitHub Actions · SQLite/JSON · Optional daemon

---

## Project Structure

```
src/
  models.py           PetState and GraveyardEntry data classes
  storage.py          JSON persistence (~/.tamagit/)
  pet_engine.py       Core logic: decay, events, streak, quests
  github_integration.py  Parse GitHub webhook payloads
  git_integration.py  Local git repository scanning
  webhook_server.py   FastAPI webhook endpoint
  ui.py               ANSI terminal display, ASCII art, progress bars
  main.py             CLI entry point (argparse)
tests/
  test_storage.py     Unit tests
docs/
  deploy_vps.md       Full VPS + webhook setup guide
```
