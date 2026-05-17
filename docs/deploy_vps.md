# TamaGit — VPS & Webhook Setup Guide

## 1. Server Info

| Parameter | Value |
|---|---|
| Server IP | `72.56.239.253` |
| Project Path | `/opt/TamaGit` |
| Webhook URL | `http://72.56.239.253:8000/webhook/github` |
| Health URL | `http://72.56.239.253:8000/health` |

---

## 2. First-Time Setup

```bash
# Connect to VPS
ssh root@72.56.239.253

# Go to project directory
cd /opt/TamaGit

# Generate a webhook secret
openssl rand -hex 32
# Copy the output — you'll need it in .env and GitHub settings

# Create .env from template
cp .env.example .env
nano .env
# Fill in GITHUB_REPO and GITHUB_WEBHOOK_SECRET

# Start the webhook server
docker compose up -d --build webhook

# Verify it's running
docker compose ps
curl http://localhost:8000/health   # expected: {"status":"ok"}
curl http://72.56.239.253:8000/health
```

---

## 3. Configure GitHub Webhook

Open your repository:  
`https://github.com/tiroro-20-10/TamaGit--SNA-Final-Project-2026`

Go to: **Settings → Webhooks → Add webhook**

| Field | Value |
|---|---|
| Payload URL | `http://72.56.239.253:8000/webhook/github` |
| Content type | `application/json` |
| Secret | value of `GITHUB_WEBHOOK_SECRET` from `.env` |
| SSL verification | Disable (HTTP endpoint) |
| Events | Pushes, Pull requests, Issues, Workflow runs |
| Active | ✅ |

After saving, GitHub sends a **ping** — check Recent Deliveries for status 200.

---

## 4. Test the Webhook

```bash
# Watch logs in real time
cd /opt/TamaGit && docker compose logs -f webhook

# Test push event (from local machine with repo access)
git clone https://github.com/tiroro-20-10/TamaGit--SNA-Final-Project-2026.git
cd TamaGit--SNA-Final-Project-2026
echo "webhook test" >> webhook-test.txt
git add . && git commit -m "test: TamaGit webhook"
git push

# Check pet reaction on VPS
docker compose run --rm tamagit log
docker compose run --rm tamagit status
```

Expected log entry: `alice pushed 1 commit(s) to 'main'`

---

## 5. Useful Commands on VPS

```bash
# Check pet status
docker compose run --rm tamagit status

# See full event log
docker compose run --rm tamagit log

# View graveyard
docker compose run --rm tamagit graveyard

# Restart webhook after code changes
git pull && docker compose up -d --build webhook

# Firewall (if port 8000 is blocked)
ufw allow 8000/tcp
```
