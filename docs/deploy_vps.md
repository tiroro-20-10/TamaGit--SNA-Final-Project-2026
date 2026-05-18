# Deploy to VPS

This is the simple deployment path for the current MVP. It uses one
`docker-compose.yml` file and exposes the FastAPI webhook server directly on
port `8000`.

## 1. What Runs Where

Run these commands on your local Windows machine:

```powershell
git add .
git commit -m "Prepare webhook deployment"
git push
```

Run server setup commands in the VPS terminal over SSH:

```bash
ssh root@YOUR_SERVER_IP
```

## 2. Server Requirements

- Ubuntu 24.04 LTS or Ubuntu 22.04 LTS
- Public IPv4 address
- Open TCP ports: `22` and `8000`
- Docker Engine with Docker Compose plugin

For this simple MVP setup, a domain is not required.

## 3. Install Base Tools

On the server:

```bash
apt update && apt upgrade -y
apt install -y git curl ca-certificates openssl
```

Install Docker Engine using the official Docker instructions for Ubuntu:

```text
https://docs.docker.com/engine/install/ubuntu/
```

Check:

```bash
docker --version
docker compose version
```

## 4. Clone Project

On the server:

```bash
cd /opt
git clone YOUR_REPOSITORY_URL GitTama
cd GitTama
```

## 5. Configure Environment

Create `.env`:

```bash
cp .env.example .env
nano .env
```

Set:

```env
GITHUB_REPO=your_username/your_repo
GITHUB_WEBHOOK_SECRET=replace_with_generated_secret
GITTAMA_STATE_PATH=~/.gittama/state.json
```

Generate secret:

```bash
openssl rand -hex 32
```

## 6. Start Webhook Server

On the server:

```bash
docker compose up -d --build webhook
```

Check:

```bash
docker compose ps
curl http://localhost:8000/health
curl http://YOUR_SERVER_IP:8000/health
```

Expected:

```json
{"status":"ok"}
```

## 7. Configure GitHub Webhook

In the GitHub repository:

```text
Settings -> Webhooks -> Add webhook
```

Use:

```text
Payload URL: http://YOUR_SERVER_IP:8000/webhook/github
Content type: application/json
Secret: same value as GITHUB_WEBHOOK_SECRET
Events: push, pull_request, issues, workflow_run
Active: yes
```

After saving, check `Recent Deliveries` on the webhook page.

## 8. Useful Commands

Logs:

```bash
docker compose logs -f webhook
```

Restart:

```bash
docker compose restart webhook
```

Update after local push:

```bash
git pull
docker compose up -d --build webhook
```

Check pet state on the server:

```bash
docker compose run --rm gittama status
docker compose run --rm gittama log
```

## 9. Notes

This setup uses plain HTTP. It is simpler and good enough for an MVP/demo, but a
real production setup should use HTTPS with a domain and a reverse proxy such as
Caddy.
