"""
Sync router: manual trigger endpoints for Smartsheet sync jobs.
The APScheduler in main.py calls these same functions on schedule.
"""
import logging
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.auth import require_admin
from src.models import User, Poc, PocState, SyncLog
from src.smartsheet_service import sync_all_pocs_from_smartsheet, push_weekly_status
from src.config import SS_ALLOWED_STATUSES

router = APIRouter(prefix="/api/sync", tags=["sync"])
logger = logging.getLogger(__name__)

# Full week/group structure -- mirrors the frontend WEEK_STRUCTURE exactly
WEEK_STRUCTURE = [
    {"id": "week1", "label": "Week 1 – Installation & Setup", "groups": [
        {"name": "Pre-installation requirements", "count": 6},
        {"name": "Network and firewall verification", "count": 2},
        {"name": "Package download and installation", "count": 5},
        {"name": "Post-installation verification", "count": 3},
        {"name": "Initial appliance setup and license", "count": 5},
    ]},
    {"id": "week2", "label": "Week 2 – Add Clouds and Build Governance", "groups": [
        {"name": "POC license planning", "count": 1},
        {"name": "Add AWS cloud", "count": 4},
        {"name": "Add VMware vCenter cloud", "count": 3},
        {"name": "Tenants and groups", "count": 2},
        {"name": "Roles and users", "count": 2},
        {"name": "Policies", "count": 5},
        {"name": "Verify governance", "count": 3},
    ]},
    {"id": "week3", "label": "Week 3 – Provision Workloads and Golden Images", "groups": [
        {"name": "Provision on AWS", "count": 3},
        {"name": "Linux golden image on VMware", "count": 3},
        {"name": "Application automation and service catalog", "count": 4},
        {"name": "Windows golden image on VMware", "count": 1},
    ]},
    {"id": "week4", "label": "Week 4 – Blueprints, Multi-Cloud Catalog and FinOps", "groups": [
        {"name": "App blueprints", "count": 2},
        {"name": "Multi-cloud catalog item", "count": 3},
        {"name": "FinOps – cost visibility and governance", "count": 3},
    ]},
    {"id": "week5", "label": "Week 5 – Review, Validation and Sign-Off", "groups": [
        {"name": "End-to-end scenario run", "count": 1},
        {"name": "Appliance health and backup", "count": 2},
        {"name": "Analytics, guidance and reports", "count": 3},
        {"name": "Success criteria review and sign-off", "count": 2},
    ]},
]


def _build_progress_text(poc: Poc, db: Session) -> str:
    """
    Option D format: ▌ header bar, block progress bar, compact week table,
    group detail for in-progress weeks, SE notes at bottom.
    """
    states = db.query(PocState).filter(PocState.poc_id == poc.poc_id).all()
    state_map = {s.week_id: s for s in states}

    def _checked(chk):
        """Count True values from either dict or list checks."""
        if not chk:
            return 0
        if isinstance(chk, dict): return sum(1 for v in chk.values() if v)
        return sum(1 for c in chk if c)
    total_done = sum(_checked(s.checks) for s in states)
    total_items   = sum(sum(g["count"] for g in wk["groups"]) for wk in WEEK_STRUCTURE)
    pct           = round(total_done / total_items * 100) if total_items > 0 else 0
    signoff_count = sum(1 for s in states if s.signoff)

    from src.models import User
    se        = db.query(User).filter(User.id == poc.se_id).first()
    se_name   = se.name if se else "HPE SE"
    today     = date.today().strftime("%d %b %Y")
    end_date  = poc.smartsheet_end_date or poc.end_date
    days_left = max(0, (end_date - date.today()).days) if end_date else 0

    # 20-char block progress bar
    filled = round(pct * 20 / 100)
    bar    = "█" * filled + "░" * (20 - filled)

    # Short week names
    SHORT = {
        "week1": "Installation & Setup",
        "week2": "Add Clouds & Governance",
        "week3": "Provision Workloads",
        "week4": "Blueprints & FinOps",
        "week5": "Review & Sign-Off",
    }
    COL = 30   # label column width (Wx  Name)
    LINE_LIMIT = 70

    lines = [
        f"▌ HPE Morpheus POC — Weekly Status  {today}",
        f"▌ {poc.customer_name}  ·  {poc.poc_id}  ·  {days_left}d left",
        f"▌ SE: {se_name}" + (f"  ·  {poc.product_family}" if poc.product_family else ""),
        "",
        f"Overall: {pct}%  {bar}  ({total_done}/{total_items})  ·  {signoff_count}/5 weeks signed off",
        "",
    ]

    detail_weeks = []

    def flush_zeros(buf):
        if buf:
            lines.append("  " + "  ·  ".join(buf))
            buf.clear()

    for i, wk in enumerate(WEEK_STRUCTURE, 1):
        s       = state_map.get(wk["id"])
        name    = SHORT.get(wk["id"], f"Week {i}")
        label   = f"W{i}  {name}"
        w_total = sum(g["count"] for g in wk["groups"])

        if s and s.signoff:
            lines.append(f"W{i}  {name}  |  ✓ SIGNED OFF")
        elif s and s.checks and (any(s.checks.values() if isinstance(s.checks, dict) else s.checks)):
            w_done = _checked(s.checks)
            w_pct  = round(w_done / w_total * 100) if w_total > 0 else 0
            lines.append(f"W{i}  {name}  |  {w_pct}%  ({w_done}/{w_total}) ▶")
            detail_weeks.append((i, wk, s))
        else:
            lines.append(f"W{i}  {name}  |  not started")

    # Group detail for in-progress weeks
    # Import item IDs map from pocs router
    from src.routers.pocs import WEEK_GROUPS_ITEMS as _WGI
    for wk_num, wk, s in detail_weeks:
        lines.append("")
        lines.append(f"W{wk_num} detail:")
        chk_dict = s.checks if isinstance(s.checks, dict) else {}
        # Build item-id list from sync WEEK_STRUCTURE using pocs item map
        wk_items = _WGI.get(wk["id"], [])
        zero_buf = []
        item_offset = 0
        for g in wk["groups"]:
            g_count = g["count"]
            g_item_ids = wk_items[item_offset:item_offset + g_count]
            item_offset += g_count
            if isinstance(s.checks, dict):
                g_done = sum(1 for iid in g_item_ids if chk_dict.get(iid))
            else:
                g_done = sum(1 for c in (s.checks[item_offset-g_count:item_offset] if len(s.checks)>item_offset-g_count else []) if c)
            if g_done == g["count"]:
                flush_zeros(zero_buf)
                lines.append(f"  ✓ {g['name']}  {g_done}/{g['count']}")
            elif g_done > 0:
                flush_zeros(zero_buf)
                lines.append(f"  · {g['name']}  {g_done}/{g['count']}")
            else:
                entry     = f"○ {g['name']}  0/{g['count']}"
                projected = "  " + "  ·  ".join(zero_buf + [entry])
                if zero_buf and len(projected) > LINE_LIMIT:
                    flush_zeros(zero_buf)
                zero_buf.append(entry)
        flush_zeros(zero_buf)

    return "\n".join(lines)


# ── BI-DAILY SYNC: SMARTSHEET -> DB ──────────────────────────────────────────

def run_bidaily_sync(db: Session) -> dict:
    """
    Fetch all POC statuses from Smartsheet, update our DB.
    Auto-blocks rejected/blocked/completed, auto-expires past end-date, reactivates if fixed.
    """
    logger.info("Starting bi-daily Smartsheet -> DB sync")
    ss_data = sync_all_pocs_from_smartsheet()

    if not ss_data:
        msg = "Smartsheet returned no data (API key missing or network error)"
        logger.warning(msg)
        _log_sync(db, None, "bidaily", False, msg)
        return {"synced": 0, "blocked": 0, "expired": 0, "reactivated": 0, "error": msg}

    pocs = db.query(Poc).all()
    synced = blocked = expired = reactivated = 0

    for poc in pocs:
        ss = ss_data.get(poc.poc_id.upper())
        if not ss:
            continue

        ss_status   = ss["status"]
        ss_end_date = ss["end_date"]
        ss_row_id   = ss["row_id"]
        changed = False

        if poc.smartsheet_status != ss_status:
            poc.smartsheet_status = ss_status
            changed = True
        if ss_end_date and poc.smartsheet_end_date != ss_end_date:
            poc.smartsheet_end_date = ss_end_date
            changed = True
        if ss_row_id and poc.smartsheet_row_id != ss_row_id:
            poc.smartsheet_row_id = ss_row_id
            changed = True

        if not poc.force_blocked and not poc.admin_override:
            effective_end = poc.smartsheet_end_date or poc.end_date
            # Skip status changes for POCs already in a terminal/managed state
            _app_terminal = poc.status in ("completed", "completion_requested")
            if ss_status not in SS_ALLOWED_STATUSES:
                if not _app_terminal and poc.status != "blocked":
                    poc.status = "blocked"
                    blocked += 1
                    changed = True
            elif effective_end and date.today() > effective_end:
                if poc.status != "expired":
                    poc.status = "expired"
                    expired += 1
                    changed = True
            else:
                if poc.status in ("blocked", "expired"):
                    poc.status = "active"
                    reactivated += 1
                    changed = True
        # Record sync timestamp on every processed POC
        from datetime import datetime as _dt
        poc.last_synced_at = _dt.utcnow()
        changed = True

        if changed:
            synced += 1

    # Auto-complete POCs where all 5 weeks are signed off
    completed_auto = 0
    for poc in db.query(Poc).filter(Poc.status == "active").all():
        states = db.query(PocState).filter(PocState.poc_id == poc.poc_id).all()
        if len(states) == 5 and all(s.signoff for s in states):
            poc.status = "completed"
            completed_auto += 1

    db.commit()
    summary = f"Synced {synced} POCs. Blocked: {blocked}. Expired: {expired}. Reactivated: {reactivated}. Auto-completed: {completed_auto}."
    logger.info(summary)
    _log_sync(db, None, "bidaily", True, summary)
    return {"synced": synced, "blocked": blocked, "expired": expired, "reactivated": reactivated, "auto_completed": completed_auto}


# ── WEEKLY SYNC: DB -> SMARTSHEET ─────────────────────────────────────────────

def run_weekly_push(db: Session) -> dict:
    """
    For every active POC, prepend progress status to Smartsheet.
    If smartsheet_row_id is missing, attempt to resolve it first.
    """
    logger.info("Starting weekly DB -> Smartsheet progress push")
    # Broaden filter: include any non-completed/expired POC
    pocs = db.query(Poc).filter(
        Poc.status.notin_(["completed", "expired"]),
    ).all()

    pushed = failed = skipped = 0
    for poc in pocs:
        # Resolve row_id if missing
        if not poc.smartsheet_row_id:
            try:
                from src.smartsheet_service import lookup_poc
                ss = lookup_poc(poc.poc_id, is_admin=True)
                if ss.get("row_id"):
                    poc.smartsheet_row_id = ss["row_id"]
                    db.commit()
                    logger.info(f"Resolved smartsheet_row_id for {poc.poc_id}")
            except Exception as e:
                logger.warning(f"Could not resolve row_id for {poc.poc_id}: {e}")
        if not poc.smartsheet_row_id:
            logger.warning(f"Skipping {poc.poc_id} -- no Smartsheet row ID")
            skipped += 1
            continue
        progress_text = _build_progress_text(poc, db)
        ok = push_weekly_status(poc.smartsheet_row_id, poc.poc_id, poc.customer_name, progress_text, sa_notes=poc.sa_notes or "")
        if ok:
            pushed += 1
            from datetime import datetime as _dt
            poc.last_pushed_at = _dt.utcnow()
        else:
            failed += 1

    db.commit()
    summary = f"Weekly push: {pushed} pushed, {failed} failed."
    logger.info(summary)
    _log_sync(db, None, "weekly_push", failed == 0, summary)
    return {"pushed": pushed, "failed": failed}


# ── HELPER ───────────────────────────────────────────────────────────────────

def _log_sync(db: Session, poc_id, sync_type: str, success: bool, message: str):
    try:
        entry = SyncLog(poc_id=poc_id, sync_type=sync_type, success=success, payload={"message": message})
        db.add(entry)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to write sync log: {e}")


# ── MANUAL TRIGGER ENDPOINTS ──────────────────────────────────────────────────

@router.post("/smartsheet")
def trigger_bidaily_sync(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = run_bidaily_sync(db)
    return {"message": "Bi-daily sync complete", **result}


@router.post("/progress")
def trigger_weekly_push(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = run_weekly_push(db)
    return {"message": "Weekly progress push complete", **result}


@router.get("/logs")
def get_sync_logs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    logs = db.query(SyncLog).order_by(SyncLog.synced_at.desc()).limit(20).all()
    return [
        {
            "id":        l.id,
            "poc_id":    l.poc_id,
            "sync_type": l.sync_type,
            "success":   l.success,
            "message":   (l.payload or {}).get("message", ""),
            "synced_at": str(l.synced_at),
        }
        for l in logs
    ]
