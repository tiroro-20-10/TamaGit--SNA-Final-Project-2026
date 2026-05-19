<div align="center">
  <img src="docs/img/logo.svg" alt="TamaGit Logo" width="180" />

  # TamaGit 🐱

  **A terminal Tamagotchi for your development team.**  
  Your shared pet lives and dies by the team's GitHub activity.

  [![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com)
  [![Textual](https://img.shields.io/badge/Textual-TUI-7c3aed)](https://textual.textualize.io)
  [![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://docker.com)
  [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

  *SNA Course Project · Innopolis University · Spring 2026*
</div>

---

<details>
  <summary>📋 Table of Contents</summary>
  <ol>
    <li><a href="#-what-is-tamagit">What is TamaGit?</a></li>
    <li><a href="#-how-it-works">How it works</a></li>
    <li><a href="#-features">Features</a></li>
    <li><a href="#-architecture">Architecture</a></li>
    <li><a href="#-tech-stack">Tech Stack</a></li>
    <li><a href="#-project-structure">Project Structure</a></li>
    <li><a href="#-installation">Installation</a>
      <ul>
        <li><a href="#server-setup-one-time-admin-only">Server Setup</a></li>
        <li><a href="#local-developer-setup">Local Developer Setup</a></li>
      </ul>
    </li>
    <li><a href="#-commands-reference">Commands Reference</a></li>
    <li><a href="#-configuration">Configuration</a></li>
    <li><a href="#-pet-mechanics">Pet Mechanics</a></li>
    <li><a href="#-team-workflow">Team Workflow</a></li>
    <li><a href="#-uninstall--cleanup">Uninstall & Cleanup</a></li>
    <li><a href="#-running-tests">Running Tests</a></li>
    <li><a href="#-team">Team</a></li>
  </ol>
</details>

---

## 🌟 What is TamaGit?

TamaGit is a **shared team Tamagotchi** that lives inside your terminal and reacts to your team's GitHub activity in real time. One pet per project repository. The whole team watches it together.

Push code regularly → the pet is happy and healthy.  
Break CI, ignore issues, stop committing → the pet gets sick and eventually dies.

It is a **social coding experiment**: a tiny game layered on top of your normal git workflow that makes team health visible and gives everyone a reason to care about CI pipelines, open issues, and commit streaks.

```
    /\_/\        ╔══════════════ TamaGit ═══════════════╗
   ( ^.^ )       ║  Name  :  Committy
    > ~ <    →   ║  State :  happy  📅 5d streak
   /|   |\       ║  Repo  :  tiroro-20-10/my-project
  (_|   |_)      ╚═══════════════════════════════════════╝

  Hunger     [█████████████████░░░░░]  79%
  Energy     [████████████████████░░]  88%
  Mood       [████████████████░░░░░░]  74%
  Health     [████████████████████░░]  91%

  🎯 Team Quest:  Make 5 commits as a team today  [3/5]
```

[---{ back to top }---](#tamagit-)

---

## ⚙️ How it works

GitHub sends webhook events to a FastAPI server running on your VPS. The server updates the pet's stats and saves them to a state file. Every developer on the team can see the same pet by syncing from the VPS.

| GitHub Event | Pet Effect |
|---|---|
| `git push` / commit | Hunger ↑ · Mood ↑ · Streak +1 |
| PR merged | Health +15 · Energy +10 · Mood +10 |
| Issue closed | Mood +15 · Hunger +5 |
| CI pipeline passes | Health +10 · Energy +5 |
| CI pipeline fails | Health −20 · Energy −10 |
| No activity (days) | All stats decay → Health drops → **death** |

Stats run from **0** (critical) to **100** (excellent). Health is derived from the average of the other three. When Health reaches zero the pet dies and the team enters **cooldown mode**.

[---{ back to top }---](#tamagit-)

---

## ✨ Features

### 🐱 Shared Team Pet
- One pet per repository, one state file on the VPS — every teammate sees the same pet
- Pet name chosen randomly from a custom pool on every resurrection
- 8 mood states with matching ASCII art, emoji, and terminal colors

### 📊 Live Animated TUI
```
tamagit live
```
- Pet walks left and right, speed reflects mood
- Reacts with animations when GitHub events arrive (eating, celebrating, stressed)
- Reads VPS state directly every 5 s — no daemon needed
- Press `T` to toggle dark / monochrome theme

### 🎯 Team Daily Quests
Generated on the VPS every morning based on actual repo state:
- "Make 5 commits as a team today"
- "Close 3 open issues" *(only if 3+ issues exist)*
- "Fix the broken CI pipeline" *(only if CI is currently failing)*
- "Merge 2 pull requests" *(only if 2+ PRs are open)*

### 🏆 Team Achievements
13 achievements unlocked server-side: First Push, PR Factory, Daily Team (7-day streak), Weekly Warriors (30-day streak), Quest Champion, and more.

### 💀 Death & Auto-Resurrection
When the pet dies it is immediately laid to rest in the **graveyard**. The team must then complete a cooldown:
- Make 3 commits
- Close 1 issue
- Get CI green once

After all three, the **next GitHub event automatically hatches a new pet** and creates a GitHub issue to notify the team.

### 🔧 Full Local Customisation
Each developer can set a personal display name, ASCII style, prompt format, color theme, and sync intervals — all stored locally, never overwritten by server syncs.

### 🖥️ Bash Prompt Integration
```
[Committy(^.^) H:79 E:88 M:74 ❤:91] user@host:~$
```
The face icon uses the **mood state color** (cyan for happy, blue for sleeping, orange when on fire). Stats use a performance color. Name and brackets are neutral.

[---{ back to top }---](#tamagit-)

---

## 🏗️ Architecture

```
GitHub repository
       │
       │  push / PR / issue / CI event
       ▼
 ┌─────────────────────────────────────┐
 │  VPS  (e.g. 72.56.239.253)          │
 │                                     │
 │  FastAPI webhook server  :8000      │
 │  ├── POST /webhook/github           │
 │  │     • verify HMAC signature      │
 │  │     • update pet stats           │
 │  │     • refresh daily quest        │
 │  │     • award achievements         │
 │  │     • bury pet on death          │
 │  │     • auto-resurrect on cooldown │
 │  │                                  │
 │  ├── GET  /state      ← sync/live  │
 │  └── GET  /graveyard  ← sync       │
 │                                     │
 │  ~/.tamagit/state.json  (source of truth)
 └─────────────────────────────────────┘
          │  GET /state every 5 s
          │  (daemon every 10 min, or live directly)
          ▼
 ┌─────────────────────────────────────┐
 │  Developer machine (each teammate) │
 │                                     │
 │  ~/.tamagit/state.json  (local copy)│
 │  ~/.tamagit/config.json (personal)  │
 │                                     │
 │  tamagit status  → shows fresh VPS state
 │  tamagit live    → polls VPS every 5 s
 │  tamagit prompt  → reads local file (fast)
 │  tamagit daemon  → auto-syncs in background
 └─────────────────────────────────────┘
```

**Architectural rules:**
- VPS **owns**: stats, streak, quest, achievements, graveyard
- Local **owns**: display preferences (name alias, theme, ascii style)
- `tamagit react` — visual feedback **only**, never writes state
- `tamagit scan` — updates **only** git metadata (dirty/unpushed), never game stats

[---{ back to top }---](#tamagit-)

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Webhook server | Python · FastAPI · Uvicorn |
| Live TUI | Textual |
| Test suite | pytest |
| Container | Docker + Docker Compose |
| GitHub integration | Webhooks + REST API (stdlib `urllib` only) |
| Storage | JSON files in `~/.tamagit/` |
| CLI | argparse + ANSI escape codes |

Zero heavy dependencies on the client side — plain Python + one ANSI library.

[---{ back to top }---](#tamagit-)

---

## 📁 Project Structure

```
TamaGit/
├── install.sh              # VPS installer (creates venv + symlink)
├── docker-compose.yml      # Webhook server container
├── Dockerfile
├── pyproject.toml
├── .env.example            # Environment variable template
│
├── src/
│   ├── main.py             # CLI entry point (all commands)
│   ├── models.py           # PetState, GraveyardEntry, TEAM_ACHIEVEMENTS, TEAM_QUESTS
│   ├── pet_engine.py       # Decay, GitHub event effects, quest tracking, streak
│   ├── webhook_server.py   # FastAPI: /health /state /graveyard /webhook/github
│   ├── storage.py          # JSON persistence (~/.tamagit/)
│   ├── storage_helpers.py  # Death achievement computation
│   ├── config_manager.py   # Local config (~/.tamagit/config.json)
│   ├── github_api.py       # GitHub REST API wrapper (urllib only)
│   ├── github_integration.py  # Parse webhook payloads → GitHubEvent
│   ├── git_integration.py  # Local git subprocess scanning
│   ├── daemon.py           # Background sync + scan process
│   ├── ui.py               # ANSI terminal output (status, prompt, graveyard)
│   ├── tui.py              # Textual live TUI (tamagit live)
│   ├── demo.py             # Preview all animations and states
│   └── config.py           # Legacy shim (kept for compatibility)
│
├── tests/
│   └── test_tamagit.py     # 57 functional tests
│
└── docs/
    └── img/
        └── logo.svg
```

[---{ back to top }---](#tamagit-)

---

## 🚀 Installation

### Server Setup *(one-time, admin only)*

> **Prerequisites:** VPS with a public IP, Docker + Docker Compose installed, a GitHub repository for your project.

#### Step 1 — Clone and install

```bash
ssh root@<your-vps-ip>

git clone https://github.com/tiroro-20-10/TamaGit--SNA-Final-Project-2026.git /opt/TamaGit
cd /opt/TamaGit

# Creates /opt/tamagit-venv + /usr/local/bin/tamagit
bash install.sh

tamagit help     # verify installation
```

#### Step 2 — Create a GitHub token

1. **github.com → your avatar → Settings**
2. **Developer settings → Personal access tokens → Tokens (classic)**
3. **Generate new token (classic)**
   - Note: `TamaGit`
   - Expiration: 90 days
   - Scopes: **☑ repo** + **☑ admin:repo_hook**
4. Copy the token immediately — it is shown only once.

#### Step 3 — Run the server wizard

```bash
tamagit server-setup
```

Enter when prompted:
| Field | Example |
|---|---|
| GitHub repo | `tiroro-20-10/my-project` |
| GitHub token | `ghp_...` |
| Server public IP | `72.56.239.253` |
| Port | `8000` *(Enter for default)* |

The wizard automatically:
- Writes `/opt/TamaGit/.env`
- Runs `docker compose up -d --build webhook`
- Tests the `/health` endpoint
- Creates the GitHub webhook via API

Verify:
```bash
curl http://<vps-ip>:8000/health   # → {"status":"ok"}
docker compose ps                   # webhook should be Up
# GitHub → repo → Settings → Webhooks → webhook with ✓
```

#### Step 4 — Hatch the team pet

```bash
tamagit init
```

The wizard:
- Reads repo + token from `.env` automatically
- Calls GitHub API to compute **realistic initial stats** (hunger ← days since last push, mood ← open issues count, energy ← CI status)
- Plays an egg-hatching animation
- Creates the pet with a random name from the custom pool

```bash
tamagit status   # welcome, new pet!
```

> **Setup order is enforced:**
> `server-setup` → `init` → *(share VPS URL with team)* → each developer runs `setup`

---

### Local Developer Setup

```bash
# Install TamaGit
pip install git+https://github.com/tiroro-20-10/TamaGit--SNA-Final-Project-2026.git

# First-time wizard — asks for VPS URL, syncs state, installs prompt, starts daemon
tamagit setup
```

Or manual:
```bash
tamagit config set vps_url http://<vps-ip>:8000
tamagit sync
tamagit install-prompt && source ~/.bashrc
tamagit daemon start
```

[---{ back to top }---](#tamagit-)

---

## 📖 Commands Reference

| Command | Description |
|---|---|
| `tamagit server-setup` | VPS wizard: .env · Docker · GitHub webhook |
| `tamagit init` | Hatch the team pet *(run on server after server-setup)* |
| `tamagit setup` | Local wizard: VPS URL · sync · prompt · daemon |
| `tamagit status` | Full status panel — always shows fresh VPS data |
| `tamagit log` | Full event history |
| `tamagit scan [PATH]` | Scan local git repo (updates dirty/unpushed metadata) |
| `tamagit achievements` | All 13 team achievements |
| `tamagit graveyard` | Hall of fallen pets |
| `tamagit rename <name>` | Set a personal display name for the pet |
| `tamagit live` | Live animated TUI (polls VPS every 5 s) |
| `tamagit sync` | Fetch state + graveyard from VPS |
| `tamagit daemon start` | Start background sync daemon |
| `tamagit daemon stop/status/restart/logs` | Manage daemon |
| `tamagit config` | Interactive local settings editor |
| `tamagit config set key val` | Scriptable config |
| `tamagit install-prompt` | Add pet to bash prompt |
| `tamagit uninstall-prompt` | Remove pet from bash prompt |
| `tamagit demo status` | Preview all ASCII states |
| `tamagit demo live` | Preview all TUI animations |
| `tamagit demo prompt` | Preview all prompt formats |
| `tamagit test` | Run the test suite |
| `tamagit docs [topic]` | Built-in documentation |
| `tamagit uninstall` | Remove all TamaGit data |
| `tamagit help` | Command overview |

[---{ back to top }---](#tamagit-)

---

## ⚙️ Configuration

All personal settings are stored in `~/.tamagit/config.json` and are **never overwritten** by server syncs.

```bash
tamagit config                         # interactive menu
tamagit config list                    # show all settings with defaults
tamagit config set local_name Pixel    # personal pet name alias
tamagit config set ascii_style minimal # compact 3-line ASCII
tamagit config set ascii_style emoji   # emoji art with animations
tamagit config set prompt_format compact  # [Pixel(^.^) 80%]
tamagit config set prompt_format minimal  # [^.^]
tamagit config set theme monochrome    # no colors (works in live too)
tamagit config set sync_interval 5    # daemon syncs every 5 min
tamagit config reset                   # restore all defaults
```

| Key | Options | Default |
|---|---|---|
| `local_name` | any string | *(official name from server)* |
| `ascii_style` | `standard` · `minimal` · `emoji` | `standard` |
| `prompt_format` | `full` · `compact` · `minimal` | `full` |
| `theme` | `dark` · `monochrome` | `dark` |
| `show_stats` | `true` · `false` | `true` |
| `show_repos` | `true` · `false` | `true` |
| `show_quest` | `true` · `false` | `true` |
| `show_achievements` | `true` · `false` | `true` |
| `show_events` | `true` · `false` | `true` |
| `sync_interval` | minutes | `10` |
| `scan_interval` | minutes | `30` |

[---{ back to top }---](#tamagit-)

---

## 🎮 Pet Mechanics

### Stats

```
Hunger  — 0 (starving) → 100 (full)       fed by: commits / pushes
Energy  — 0 (exhausted) → 100 (energised) fed by: CI success
Mood    — 0 (sad) → 100 (happy)           fed by: closed issues / PRs
Health  — derived from average; CI failures damage it directly
```

### Mood States

| State | Trigger | Color |
|---|---|---|
| 😸 ecstatic | avg ≥ 80 | 🟢 green |
| 😺 happy | avg ≥ 60 | 🔵 cyan |
| 😼 okay | avg ≥ 40 | 🟡 yellow |
| 😿 sad | avg ≥ 20 | 🟣 magenta |
| 🙀 miserable | avg < 20 | 🔴 red |
| 😴 sleeping | no activity for 12 h | 🔵 blue |
| 🔥 on fire | streak ≥ 7 days + avg ≥ 70 | 🟠 orange |
| 👻 ghost | pet has died | ⬜ grey |

### Death & Cooldown

When Health reaches 0 the pet dies and is **immediately added to the graveyard**. The team must then complete three cooldown tasks via GitHub:

```
☐  Make 3 commits
☐  Close 1 issue
☐  Get CI green once
```

After all three, the **next GitHub event automatically hatches a new pet**. Starting stats reflect the quality of the cooldown work. The server creates a GitHub issue to announce the new pet.

[---{ back to top }---](#tamagit-)

---

## 👥 Team Workflow

```
Server admin (once):          Every developer (once):
  1. bash install.sh            pip install git+https://github.com/...
  2. tamagit server-setup       tamagit setup
  3. tamagit init

Daily workflow (everyone):
  git push → pet reacts automatically via webhook
  tamagit live → watch the pet in real time
  tamagit status → quick health check
```

**The pet updates automatically** — no extra commands needed during normal development. Just push code, close issues, and keep CI green.

[---{ back to top }---](#tamagit-)

---

## 🗑️ Uninstall & Cleanup

### Remove from a local machine

```bash
tamagit uninstall        # removes ~/.tamagit/ and .bashrc block
source ~/.bashrc         # restore original prompt in current session
pip uninstall tamagit    # remove the package
```

### Full removal from VPS

```bash
ssh root@<vps-ip>

# 1. Stop and remove Docker containers
cd /opt/TamaGit && docker compose down

# 2. Remove pet data
rm -rf ~/.tamagit/

# 3. Remove .env (credentials)
rm /opt/TamaGit/.env

# 4. Remove the package, venv, and symlink
/opt/tamagit-venv/bin/pip uninstall tamagit -y
rm -rf /opt/tamagit-venv
rm /usr/local/bin/tamagit

# 5. Remove the project folder
rm -rf /opt/TamaGit

# 6. Remove GitHub webhook (optional)
#    GitHub → repo → Settings → Webhooks → Delete
```

### Clean slate (keep installation, restart pet)

```bash
# On VPS — delete only the pet data
rm -rf ~/.tamagit/
docker compose restart webhook   # picks up fresh state
tamagit init                     # hatch a new pet
```

[---{ back to top }---](#tamagit-)

---

## 🧪 Running Tests

```bash
# From any machine with TamaGit installed
tamagit test

# Or directly with pytest
cd /opt/TamaGit
python -m pytest tests/test_tamagit.py -v
```

57 tests covering:
- All stat mechanics (push, PR, CI, issue events)
- Streak and sleeping detection
- Team quest generation, progress, and completion
- Scan metadata-only behavior (no stat side effects)
- Cooldown and auto-resurrection logic
- Graveyard and death achievements
- All 13 team achievements
- Config manager (set / get / reset / type coercion)
- All mood labels (parametrized for every state)

[---{ back to top }---](#tamagit-)

---

## 👨‍💻 Team

**Karim Khabibrakhmanov** — Product Owner + Development  
**Roman Titov** — Scrum Master + Development  
email → r.titov@innopolis.university · telegram → [@romyst](https://t.me/romyst)  
**Alina Khisamutdinova** — Development  
**Elizaveta Krasova** — Development  
**Dmitrii Vasiliev** — Development  
**Amir Valeev** — Development  

**Course:** Social Network Analysis · Innopolis University · Spring 2026

[---{ back to top }---](#tamagit-)

---

## 📄 License

Open Source — distributed under the MIT License. See [LICENSE](LICENSE) for details.

---

<div align="center">
  <sub>P.S. The pet is watching. Please commit.</sub>
</div>
