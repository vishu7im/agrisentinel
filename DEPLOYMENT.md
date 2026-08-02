# Docker deployment on a new VPS

AgriSentinel runs as one self-contained Compose project with Caddy, the FastAPI backend, and
the static UI. Compose creates the private application network automatically. Only Caddy
publishes ports to the VPS.

## 1. Prepare DNS and the VPS

Point the `agri.vishu.dev` `A` record to the VPS public IP. Install Docker Engine and
the Docker Compose plugin, and allow inbound TCP ports 80 and 443 plus UDP port 443 in the VPS
firewall. Port 22 is only needed for SSH administration.

Clone the repository from the remote containing `agrisentinel/main`; the old `origin/main`
still points at the scaffold history.

## 2. Configure the app

Copy the environment template:

```bash
cp .env.example .env
```

`APP_DOMAIN` defaults to `agri.vishu.dev`. Keep `VITE_API_URL` empty so the browser uses the same
hostname for the UI and `/api`. Add `GEMINI_API_KEY` if desired; without it, the extractive
offline fallback remains available.

Validate the interpolated Compose configuration:

```bash
docker compose config --quiet
```

## 3. Build and start

```bash
docker compose up --detach --build --remove-orphans --wait
```

Check the service and follow logs:

```bash
curl -fsS https://agri.vishu.dev/api/health
docker compose ps
docker compose logs --follow --tail=100 caddy backend ui
```

The `agrisentinel_uploads` named volume contains uploaded images and `runs.db`. Include that
volume plus `caddy_data` in VPS backups. The backend intentionally runs one Uvicorn worker
because active run and SSE state is held in process memory.
