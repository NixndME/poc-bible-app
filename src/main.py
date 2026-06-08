import time
import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from contextlib import asynccontextmanager
from sqlalchemy import text
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.database import engine, SessionLocal, Base
from src.models import User
from src.auth import hash_password
from src.config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME, SMARTSHEET_API_KEY, APP_CORS_ORIGINS
from src.routers import health, admin, pocs, public, auth_router
from src.routers.sync_router import router as sync_router, run_bidaily_sync, run_weekly_push
from src.routers.smartsheet_router import router as smartsheet_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")


def wait_for_db(max_retries=10, delay=2):
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[INIT] Database connected (attempt {i+1})")
            return True
        except Exception:
            print(f"[INIT] Waiting for database... (attempt {i+1}/{max_retries})")
            time.sleep(delay)
    raise Exception("Could not connect to database after retries")


def _bidaily_job():
    """Cron wrapper: bi-daily Smartsheet → DB sync (every 2 days at midnight IST = 18:30 UTC)."""
    db = SessionLocal()
    try:
        run_bidaily_sync(db)
    finally:
        db.close()


def _weekly_job():
    """Cron wrapper: weekly DB → Smartsheet progress push (Sunday 18:30 UTC = Monday midnight IST)."""
    db = SessionLocal()
    try:
        run_weekly_push(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    print("[INIT] Tables created")

    # ── Column migrations ─────────────────────────────────────────────────
    # Each ALTER TABLE uses its own engine.begin() = independent transaction.
    # One failure can never abort another — fixes the psycopg2 "aborted
    # transaction" issue where a single try/except block still leaves the
    # PostgreSQL connection in error state, causing conn.commit() to roll back
    # ALL columns including last_accessed_at.
    def _add_col(table: str, col: str, typ: str):
        try:
            with engine.begin() as _c:
                _c.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}"))
            logger.info(f"[INIT] column {table}.{col} OK")
        except Exception as exc:
            logger.warning(f"[INIT] column {table}.{col} skipped: {exc}")

    # pocs table
    for _col, _typ in [
        ("product_family",       "TEXT"),
        ("contact_name",         "TEXT"),
        ("contact_email",        "TEXT"),
        ("sub_region",           "TEXT"),
        ("on_prem_hypervisors",  "TEXT"),
        ("public_cloud_providers","TEXT"),
        ("use_case",             "TEXT"),
        ("morpheus_version",     "TEXT"),
        ("approved_sockets",     "TEXT"),
        ("using_hvm",            "TEXT"),
        ("using_k8s",            "TEXT"),
        ("last_pushed_at",       "TIMESTAMP"),
        ("last_synced_at",       "TIMESTAMP"),
        ("last_accessed_at",     "TIMESTAMP"),
        ("sa_notes",             "TEXT"),
    ]:
        _add_col("pocs", _col, _typ)

    # users table
    _add_col("users", "is_master", "BOOLEAN DEFAULT FALSE")

    # customer_notes table
    for _col, _typ in [
        ("section_id",     "TEXT"),
        ("section_title",  "TEXT"),
        ("item_id",        "TEXT"),
        ("item_title",     "TEXT"),
        ("acknowledged_at","TIMESTAMP"),   # SE note acknowledgment
        ("se_reply",       "TEXT"),         # one SE reply per customer note
        ("se_reply_at",    "TIMESTAMP"),    # when SE replied
    ]:
        _add_col("customer_notes", _col, _typ)

    print("[INIT] DB column migration complete")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not existing:
            admin_user = User(
                email=ADMIN_EMAIL,
                name=ADMIN_NAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
                is_master=True,
            )
            db.add(admin_user)
            db.commit()
            print(f"[INIT] Admin account created: {ADMIN_EMAIL}")
        else:
            # Always sync password, role, and flags from env on every startup.
            # This means updating ADMIN_PASSWORD in the secret + redeploying resets the password.
            existing.is_active = True
            existing.is_master = True
            existing.role = "admin"
            existing.password_hash = hash_password(ADMIN_PASSWORD)
            db.commit()
            print(f"[INIT] Admin account synced from secret: {ADMIN_EMAIL}")
    finally:
        db.close()

    # ── APScheduler ──────────────────────────────────────────────
    scheduler = BackgroundScheduler(timezone="UTC")

    if SMARTSHEET_API_KEY:
        # Bi-daily sync: every 2 days at 18:30 UTC (midnight IST)
        scheduler.add_job(
            _bidaily_job,
            CronTrigger(hour=18, minute=30, day="*/2"),
            id="bidaily_sync",
            replace_existing=True,
        )
        # Weekly push: every Sunday at 18:30 UTC (Monday midnight IST)
        scheduler.add_job(
            _weekly_job,
            CronTrigger(day_of_week="sun", hour=18, minute=30),
            id="weekly_push",
            replace_existing=True,
        )
        scheduler.start()
        print("[INIT] Smartsheet sync scheduler started (bi-daily + weekly)")
    else:
        print("[INIT] SMARTSHEET_API_KEY not set -- sync scheduler disabled")

    yield

    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[INIT] Scheduler stopped")


app = FastAPI(
    title="HPE Morpheus POC Bible",
    description="POC execution guide and tracking platform",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS origins come from config.py → set APP_CORS_ORIGINS in k8s/01-secret.yaml
_cors_origins = [o.strip() for o in APP_CORS_ORIGINS.split(",") if o.strip()]

# ── Custom error pages ────────────────────────────────────────────────────────
_error_page = lambda code, title, msg: f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} – POC Bible</title>
<style>*{{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif}}
body{{background:#F4F6F9;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#fff;border-radius:16px;padding:48px 40px;max-width:440px;width:90%;text-align:center;border:0.5px solid #DDE3EC}}
.hpe{{background:#01A982;color:#fff;font-size:12px;font-weight:700;padding:4px 10px;border-radius:6px;display:inline-block;margin-bottom:20px}}
.code{{font-size:64px;font-weight:700;color:#01A982;line-height:1}}
h1{{font-size:20px;font-weight:600;color:#111827;margin:12px 0 8px}}
p{{font-size:14px;color:#6B7280;line-height:1.6;margin-bottom:24px}}
a{{display:inline-block;padding:10px 24px;background:#01A982;color:#fff;text-decoration:none;border-radius:8px;font-size:14px;font-weight:600}}
</style></head>
<body><div class="card"><div class="hpe">HPE</div><div class="code">{code}</div>
<h1>{title}</h1><p>{msg}</p><a href="/login">← Back to login</a></div></body></html>"""

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return HTMLResponse(status_code=404, content=_error_page(404, "Page not found", "The page you're looking for doesn't exist or has been moved."))

@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return HTMLResponse(status_code=500, content=_error_page(500, "Something went wrong", "An unexpected error occurred. Please try again or contact your HPE admin."))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# API routers
app.include_router(health.router)
app.include_router(auth_router.router)
app.include_router(admin.router)
app.include_router(pocs.router)
app.include_router(public.router)
app.include_router(sync_router)
app.include_router(smartsheet_router)


# Page routes
@app.get("/")
async def root():
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@app.get("/admin")
async def admin_page():
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))


@app.get("/dashboard")
async def dashboard_page():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))


@app.get("/poc/{token}")
async def customer_poc_page(token: str):
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
