# Demo Scenarios

Use these commands during the project defense.

## 1. Launch the pet

```bash
gittama status
```

Show hunger, energy, mood, health, recent events, and achievements.

## 2. User actions

```bash
gittama feed
gittama play
gittama sleep
gittama clean
gittama status
```

Explain that these actions are local controls for the pet.

## 3. Local git scan

Run from inside a git repository:

```bash
gittama scan
gittama status
```

Show that GitTama reads branch, dirty worktree, upstream status, and latest
commit. The scan result is converted into pet reactions.

## 4. Persistence

Run:

```bash
gittama status
gittama feed
gittama status
```

Close the terminal, open it again, and run:

```bash
gittama status
```

The changed state should still be available because it is stored in
`~/.gittama/state.json`.

## 5. Docker run

```bash
docker compose build
docker compose run --rm gittama status
docker compose run --rm gittama scan
```

Use this to demonstrate that the project can run without committing a local
virtual environment.
