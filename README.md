# HPE Morpheus POC Bible

A guided POC execution platform for HPE Morpheus — gives customers a week-by-week checklist, lets Sales Engineers track progress, and syncs status bi-directionally with Smartsheet.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick start — Docker Compose](#quick-start--docker-compose)
- [Running locally or air-gapped](#running-locally-or-air-gapped)
- [Environment variables](#environment-variables)
- [Kubernetes deployment](#kubernetes-deployment)
- [Project structure](#project-structure)
- [How the Smartsheet sync works](#how-the-smartsheet-sync-works)
- [Security notes](#security-notes)

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | Latest | Container runtime |
| Docker Compose | Latest | Local multi-container setup |
| PostgreSQL | 16 | Database (provided automatically via compose) |
| Python | 3.11+ | Only needed if running without containers |

---

## Quick start — Docker Compose

The fastest way to run the full app locally. One command starts both the database and the app.

### 1. Clone the repo

```bash
git clone https://github.com/your-org/poc-bible-app.git
cd poc-bible-app
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in your values. At minimum you need:

```env
# Use 'db' as the hostname — that's the compose service name, not localhost
DATABASE_URL=postgresql://postgres:localdev123@db:5432/pocbible

# Generate with: openssl rand -hex 32
JWT_SECRET=your-generated-secret-here

ADMIN_EMAIL=you@yourcompany.com
ADMIN_PASSWORD=your-strong-password
ADMIN_NAME=Your Name

# Optional — leave blank to disable Smartsheet sync
SMARTSHEET_API_KEY=your-api-key
SMARTSHEET_SHEET_ID=your-sheet-id

APP_CORS_ORIGINS=*
```

### 3. Start the app

```bash
docker compose up --build
```

The app will be available at **http://localhost:8000**

| Page | URL |
|------|-----|
| Login | http://localhost:8000/login |
| SE Dashboard | http://localhost:8000/dashboard |
| Admin panel | http://localhost:8000/admin |
| API docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/health |

### 4. First login

On first startup the master admin account is seeded automatically from `ADMIN_EMAIL` / `ADMIN_PASSWORD`. Log in at `/login` with those credentials.

If you ever get locked out, restart the container — the app auto-heals the master admin account on startup.

### 5. Stop the app

```bash
# Stop containers (keeps the database volume)
docker compose down

# Full reset — also deletes the database
docker compose down -v
```

---

## Running locally or air-gapped

The app runs in two modes depending on whether `SMARTSHEET_API_KEY` is set. The same Docker image is used in both modes.

| Mode | When | Smartsheet |
|------|------|-----------|
| **SaaS / connected** | `SMARTSHEET_API_KEY` is set | Full sync, validation, push |
| **Local / air-gapped** | `SMARTSHEET_API_KEY` is blank | All Smartsheet features disabled |

### Feature comparison by persona

| Feature | SaaS (connected) | Local / air-gapped |
|---------|:---:|:---:|
| **Customer** | | |
| 5-week POC checklist at `/poc/<token>` | ✓ | ✓ |
| Week-by-week task tracking | ✓ | ✓ |
| Progress auto-save to database | ✓ | ✓ |
| Submit notes to SE | ✓ | ✓ |
| Read SE replies | ✓ | ✓ |
| Week sign-off | ✓ | ✓ |
| **SE / Partner** | | |
| Login at `/login` | ✓ | ✓ |
| SE dashboard at `/dashboard` | ✓ | ✓ |
| Create POC links | ✓ With Smartsheet validation | ✓ No validation (any ID accepted) |
| View customer progress | ✓ | ✓ |
| Block / unblock / override POC | ✓ | ✓ |
| Reply to customer notes | ✓ | ✓ |
| PDF export | ✓ | ✓ |
| Smartsheet POC ID validation | ✓ | ✗ Skipped |
| Bi-daily status sync | ✓ Auto | ✗ Not available |
| Weekly progress push to Smartsheet | ✓ Auto | ✗ Not available |
| Manual sync / push buttons | ✓ | ✗ Return "no data" |
| **Admin** | | |
| Admin panel at `/admin` | ✓ | ✓ |
| User management | ✓ | ✓ |
| POC controls (block, reassign, extend, delete) | ✓ | ✓ |
| Analytics (based on local DB) | ✓ | ✓ |
| Smartsheet sync triggers | ✓ | ✗ Return "no data" |

**The customer checklist is identical in both modes.** The customer never knows or cares whether Smartsheet is connected. All customer-facing features — task tracking, notes, sign-off — work exactly the same.

---

### Scenario A — Customer (air-gapped or DMZ)

The customer never logs in. They only need one URL. The SE runs the app locally, seeds the POC once, and hands the customer a single link. The customer opens it in any browser — no login, no dashboard, no Smartsheet.

**Step 1 — Build and save images (SE does this while still connected)**

```bash
docker build -t poc-bible:latest .
docker save poc-bible:latest -o poc-bible.tar
docker save postgres:16-alpine -o postgres.tar
```

Copy `poc-bible.tar`, `postgres.tar`, and the project folder to the target machine.

**Step 2 — Load and start (on the target machine)**

```bash
docker load -i poc-bible.tar
docker load -i postgres.tar

# Create your local secrets file (never committed to git)
cp .env.airgapped.example .env.airgapped
# Edit .env.airgapped — set POSTGRES_PASSWORD, JWT_SECRET, ADMIN_PASSWORD

docker compose -f docker-compose.airgapped.yml up -d
```

**Step 3 — Seed the POC (one time per customer)**

```bash
docker compose -f docker-compose.airgapped.yml run --rm app python scripts/seed_poc.py
```

The script asks for customer name, POC ID, start date, and duration, then prints the URL:

```
  ✓ POC record created  (POC-202506-001)

  ┌──────────────────────────────────────────────────────────┐
  │  Customer URL  →  http://localhost:8000/poc/a3f9c2e1b4d6  │
  └──────────────────────────────────────────────────────────┘

  Customer:  Acme Corp
  Period:    2026-06-01 → 2026-07-16  (45 days)
```

**Step 4 — Share the URL**

The customer opens `http://<machine-ip>:8000/poc/<token>` in any browser on the same LAN. That is the only URL they ever need.

Find the machine IP: `ip addr` (Linux) or `ipconfig getifaddr en0` (macOS) or `ipconfig` (Windows).

**Stop / reset:**

```bash
docker compose -f docker-compose.airgapped.yml down      # stop, keep data
docker compose -f docker-compose.airgapped.yml down -v   # stop + wipe all POC data
```

---

### Scenario B — SE or Partner (local laptop or server, no Smartsheet)

The SE wants to run the full app locally — create POC links, track progress, reply to customer notes — without connecting to Smartsheet.

Use the standard `docker-compose.yml`. In your `.env`, leave the Smartsheet keys blank:

```env
DATABASE_URL=postgresql://postgres:localdev123@db:5432/pocbible
JWT_SECRET=<generate with: openssl rand -hex 32>
ADMIN_EMAIL=se@yourcompany.com
ADMIN_PASSWORD=yourpassword
ADMIN_NAME=Your Name
SMARTSHEET_API_KEY=
SMARTSHEET_SHEET_ID=
APP_CORS_ORIGINS=*
```

```bash
docker compose up --build
```

Log in at `http://localhost:8000/login`. The SE dashboard works in full. When creating a POC, the Smartsheet validation step is silently skipped — any POC ID is accepted and the link is created immediately in the local database.

Hand the customer URL (`http://<machine-ip>:8000/poc/<token>`) to the customer. They open it in any browser on the same network.

**What the SE loses in this mode:**
- POC ID is not validated against Smartsheet (no approval check — any ID is accepted)
- POC status does not auto-update from Smartsheet (remains whatever was set at creation)
- Progress is not pushed to the Smartsheet weekly status column
- The Sync buttons in the dashboard are present but return "no data" silently

---

### Scenario C — Admin (local server or DMZ)

Admin gets the full panel. Run the same way as Scenario B. Smartsheet-dependent features (sync triggers) will silently return "no data" — no errors, no crashes.

**What the admin loses:** Smartsheet sync triggers only. All user management, POC controls, analytics, and DB cleanup work exactly as in SaaS mode.

---

## Environment variables

All configuration is read from environment variables defined in a single place — `src/config.py`. For local dev use `.env`. For Kubernetes use `k8s/01-secret.yaml`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `JWT_SECRET` | Yes | — | Secret key for signing JWTs. Generate with `openssl rand -hex 32` |
| `JWT_EXPIRY_HOURS` | No | `8` | How long login tokens last (hours) |
| `ADMIN_EMAIL` | Yes | — | Master admin email — seeded on first startup |
| `ADMIN_PASSWORD` | Yes | — | Master admin password — seeded on first startup |
| `ADMIN_NAME` | No | `Admin` | Master admin display name |
| `SMARTSHEET_API_KEY` | No | — | Smartsheet personal access token. If blank, sync is disabled |
| `SMARTSHEET_SHEET_ID` | No | — | ID of your HPE Morpheus POC Tracker sheet |
| `APP_CORS_ORIGINS` | No | `*` | Comma-separated allowed origins. Use `*` for dev only |
| `PARTNER_EXPIRY_DAYS` | No | `183` | Default partner account expiry in days |
| `ALLOW_DB_CLEANUP` | No | `false` | Enables a full DB wipe endpoint — QA/testing only, never production |

---

## Kubernetes deployment

### 1. Fill in your secrets

Edit `k8s/01-secret.yaml` with your real values. This file is git-ignored — never commit it with real credentials.

```bash
# Generate a strong JWT secret
openssl rand -hex 32
```

### 2. Build and push the image

```bash
docker build -t your-registry/poc-bible:latest .
docker login your-registry
docker push your-registry/poc-bible:latest
```

Update the `image:` field in `k8s/02-deployment.yaml` to match your registry path.

### 3. Load image into local Kubernetes (without a remote registry)

**kind:**
```bash
docker save poc-bible:latest -o poc-bible.tar
kind load image-archive poc-bible.tar --name <your-cluster-name>
```

Then set `imagePullPolicy: IfNotPresent` in `k8s/02-deployment.yaml` so it uses the local image.

**k3s:**
```bash
docker save poc-bible:latest | sudo k3s ctr images import -
```

### 4. Apply the manifests

```bash
# Apply everything in order (kubectl respects the numeric prefix)
kubectl apply -f k8s/

# Watch the pod come up
kubectl get pods -n poc-bible -w

# Check logs
kubectl logs -n poc-bible -l app=poc-bible --tail=50
```

### 5. Verify

```bash
kubectl get all -n poc-bible
kubectl get ingress -n poc-bible
```

The health endpoint returns `200 {"status": "healthy"}` when the app and database are both up.

### Ingress

The default ingress (`k8s/04-ingress.yaml`) uses the `traefik` ingress class (built into k3s). If your cluster uses nginx, change `ingressClassName: traefik` to `ingressClassName: nginx`.

---

## Project structure

```
poc-bible-app/
├── src/
│   ├── main.py                  # App entry point, scheduler, DB migrations
│   ├── config.py                # All env vars — single source of truth
│   ├── database.py              # SQLAlchemy engine and session
│   ├── models.py                # ORM models (User, Poc, PocState, CustomerNote)
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── auth.py                  # JWT auth, password hashing, role guards
│   ├── smartsheet_service.py    # Smartsheet API integration
│   └── routers/
│       ├── auth_router.py       # POST /api/auth/login, /me
│       ├── pocs.py              # SE/partner POC CRUD, state, notes
│       ├── admin.py             # Admin user management, analytics, POC controls
│       ├── public.py            # Customer-facing endpoints (token-based, rate-limited)
│       ├── sync_router.py       # Smartsheet sync jobs
│       ├── smartsheet_router.py # POC lookup from Smartsheet
│       └── health.py            # GET /api/health
├── static/
│   ├── index.html               # Customer POC page  →  /poc/<token>
│   ├── dashboard.html           # SE / partner dashboard  →  /dashboard
│   ├── admin.html               # Admin panel  →  /admin
│   └── login.html               # Login page  →  /login
├── scripts/
│   └── seed_poc.py              # Air-gapped POC seeder — creates a POC without the dashboard
├── k8s/
│   ├── 00-namespace.yaml        # Namespace: poc-bible
│   ├── 01-secret.yaml           # All secrets — fill in before applying (git-ignored)
│   ├── 02-deployment.yaml       # App deployment
│   ├── 03-service.yaml          # ClusterIP service on port 8000
│   └── 04-ingress.yaml          # Traefik ingress
├── Dockerfile                   # python:3.11-slim, uvicorn on port 8000
├── docker-compose.yml           # Full stack: app + postgres (SaaS / connected mode)
├── docker-compose.airgapped.yml # Minimal stack for air-gapped / local customer POC view
├── .env.example                 # Template — copy to .env and fill in values
├── .env.airgapped.example       # Template for air-gapped mode — copy to .env.airgapped
├── .gitignore                   # Ignores .env, .env.airgapped, and k8s/01-secret.yaml
└── requirements.txt             # Python dependencies
```

---

## How the Smartsheet sync works

- **Bi-daily sync (Smartsheet → DB):** runs every 2 days at 18:30 UTC. Pulls POC status and end dates from Smartsheet, auto-blocks rejected/expired POCs, and reactivates them if the status is fixed.
- **Weekly push (DB → Smartsheet):** runs every Sunday at 18:30 UTC. Pushes a formatted progress report for every active POC into the Smartsheet weekly status column.
- Both jobs can be triggered manually from the admin panel under Sync.
- If `SMARTSHEET_API_KEY` is not set, the scheduler is disabled and the app runs in standalone mode.

---

## Security notes

- `k8s/01-secret.yaml` and `.env` are both git-ignored. Never remove them from `.gitignore`.
- `JWT_SECRET` must be a strong random value in production. Use `openssl rand -hex 32`.
- `ALLOW_DB_CLEANUP` must be `false` in production — it enables a full database wipe endpoint.
- Customer access URLs (`/poc/<token>`) are rate-limited to 60 requests/minute per IP.
