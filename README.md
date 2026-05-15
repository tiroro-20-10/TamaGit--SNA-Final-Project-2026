# GitTama - Terminal Tamagotchi for Git and GitHub habits

GitTama is a small CLI pet that reacts to repository activity. It keeps a local
JSON state, changes mood over time, rewards useful actions, and can scan the
current git repository.

## Current MVP

- Pet state: hunger, energy, mood, health
- Persistent JSON state in `~/.gittama/state.json`
- Time-based decay between launches
- Basic CLI actions: `status`, `feed`, `play`, `sleep`, `clean`, `log`
- Local git scan: branch, dirty worktree, last commit, unpushed/unpulled commits
- Local FastAPI webhook server for GitHub-style payloads
- Docker and Docker Compose support

## Requirements

- Python 3.10+
- Git installed and available in `PATH` for `gittama scan`
- Docker Desktop or Docker Engine, optional

Do not commit a virtual environment. Create it locally on each machine.

## Local Setup

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .
gittama status
```

If `py` is not available, use the full path to your Python executable or install
Python from python.org.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
gittama status
```

## Commands

```bash
gittama status
gittama feed --amount 20
gittama play
gittama sleep
gittama clean
gittama log
gittama scan
gittama scan /path/to/repository
```

Use `gittama scan` to inspect the real local repository.

## Docker

```bash
docker compose build
docker compose run --rm gittama status
docker compose run --rm gittama scan
```

The Compose setup mounts the current project to `/workspace` and stores pet
state in `~/.gittama`.

For temporary runs or CI, override the state file:

```bash
GITTAMA_STATE_PATH=.tmp-gittama/state.json gittama status
```

PowerShell equivalent:

```powershell
$env:GITTAMA_STATE_PATH = ".tmp-gittama/state.json"
gittama status
```

## Local Webhook Server

Start the FastAPI webhook service:

```powershell
docker compose up --build webhook
```

In another terminal, check that the server is alive:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Send a local GitHub-style `push` payload:

```powershell
$payload = @{ commits = @(@{ id = "local-test" }) } | ConvertTo-Json -Depth 5
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/webhook/github `
  -Headers @{ "X-GitHub-Event" = "push" } `
  -ContentType "application/json" `
  -Body $payload
```

Then inspect the pet state:

```powershell
docker compose run --rm gittama status
docker compose run --rm gittama log
```

If `GITHUB_WEBHOOK_SECRET` is set, the server requires a valid
`X-Hub-Signature-256` header. Leave it empty for the first local smoke test.

This local server is enough to test the application logic. For real GitHub
deliveries, `/webhook/github` must be reachable from the internet through a
public server, domain, and HTTPS reverse proxy.


## Project Structure

```text
src/
  main.py                CLI entry point
  models.py              Pet state model
  pet_engine.py          Pet rules and reactions
  git_integration.py     Local git scanner
  github_integration.py  GitHub webhook payload mapper
  webhook_server.py      FastAPI webhook server
  storage.py             JSON persistence
  ui.py                  ASCII pet output
```

## Next Steps

- Add tests for `pet_engine`, `git_integration`, and CLI behavior
- Add daily quests
- Add real GitHub API sync via `GITHUB_TOKEN` and `GITHUB_REPO`
- Add GitHub Actions for linting and tests
