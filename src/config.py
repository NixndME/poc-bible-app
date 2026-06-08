import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pocbible:changeme@localhost:5432/pocbible")

# ── JWT ───────────────────────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
JWT_ALGORITHM = "HS256"

# ── Master admin bootstrap ────────────────────────────────────────────────────
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@yourcompany.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
ADMIN_NAME = os.getenv("ADMIN_NAME", "Admin")

# ── Smartsheet integration ────────────────────────────────────────────────────
SMARTSHEET_API_KEY = os.getenv("SMARTSHEET_API_KEY", "")
SMARTSHEET_SHEET_ID = os.getenv("SMARTSHEET_SHEET_ID", "")

# ── Access control ────────────────────────────────────────────────────────────
PARTNER_EXPIRY_DAYS = int(os.getenv("PARTNER_EXPIRY_DAYS", "183"))

# ── CORS ──────────────────────────────────────────────────────────────────────
# Use * for local dev only. Set to your domain(s) in production.
APP_CORS_ORIGINS = os.getenv("APP_CORS_ORIGINS", "*")

# ── Feature flags ─────────────────────────────────────────────────────────────
# Set to "true" only in QA/testing environments — never in production.
ALLOW_DB_CLEANUP = os.getenv("ALLOW_DB_CLEANUP", "false").lower() in ("true", "1", "yes")

# ── Smartsheet column IDs (HPE Morpheus POC Tracker) ──────────────
SS_COL_POC_ID          = 6467914468462468
SS_COL_STATUS          = 2154971325042564
SS_COL_PRODUCT_FAMILY  = 6023268130918276   # was incorrectly labelled SS_COL_LICENSE before
SS_COL_LICENSE_TYPE    = 6007920331624324   # correct License Type column
SS_COL_CUSTOMER        = 5578351243988868
SS_COL_SE_NAME         = 6141301197410180
SS_COL_SE_EMAIL        = 3889501383724932
SS_COL_REGION          = 7830151057674116
SS_COL_SUB_REGION      = 4488368468823940
SS_COL_CONTACT_NAME    = 2200651523460996
SS_COL_CONTACT_EMAIL   = 6704251150831492
SS_COL_START_DATE      = 1815644212596612
SS_COL_END_DATE        = 6319243839967108
SS_COL_USE_CASE        = 689744305753988
SS_COL_MORPHEUS_VER    = 2941544119439236
SS_COL_ON_PREM_HV      = 6391143739985796
SS_COL_PUBLIC_CLOUD    = 8642943553671044
SS_COL_USING_HVM       = 8358270235611012
SS_COL_USING_K8S       = 3854670608240516
SS_COL_APPROVED_SOCKETS= 341270454374276
SS_COL_WEEKLY_STATUS      = 4720129889046404
SS_COL_LAST_UPDATE        = 8803990952513412
SS_COL_SE_PARTNER_NOTES   = 7488035519500164   # New: SE / Partner Notes (app-written, locked)

# Statuses that allow Bible POC creation
SS_ALLOWED_STATUSES = {"Approved", "Extended"}
