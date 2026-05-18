# Demo Scenarios

Use these commands during the project defense.

## 1. Launch the pet

```bash
tamagit status
```

Show hunger, energy, mood, health, recent events, and achievements.

## 2. User actions

```bash
tamagit feed
tamagit play
tamagit sleep
tamagit clean
tamagit status
```

Explain that these actions are local controls for the pet.

## 3. Local git scan

Run from inside a git repository:

```bash
tamagit scan
tamagit status
```

Show that TamaGit reads branch, dirty worktree, upstream status, and latest
commit. The scan result is converted into pet reactions.

## 4. Persistence

Run:

```bash
tamagit status
tamagit feed
tamagit status
```

Close the terminal, open it again, and run:

```bash
tamagit status
```

The changed state should still be available because it is stored in
`~/.tamagit/state.json`.

## 5. Docker run

```bash
docker compose build
docker compose run --rm tamagit status
docker compose run --rm tamagit scan
```

Use this to demonstrate that the project can run without committing a local
virtual environment.

## 6. Local webhook server

Start the server:

```bash
docker compose up --build webhook
```

In another terminal, send a local GitHub-style payload:

```powershell
$payload = @{ commits = @(@{ id = "local-test" }) } | ConvertTo-Json -Depth 5
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/webhook/github `
  -Headers @{ "X-GitHub-Event" = "push" } `
  -ContentType "application/json" `
  -Body $payload
```

Then show the updated state:

```bash
docker compose run --rm tamagit status
docker compose run --rm tamagit log
```

Explain that this validates webhook processing locally. Real GitHub delivery
requires a public HTTPS URL on a server.
