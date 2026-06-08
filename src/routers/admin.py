from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional, List
from src.database import get_db
from src.smartsheet_service import push_poc_status, push_weekly_status
from src.routers.sync_router import _build_progress_text
from src.auth import require_admin, require_master_admin, hash_password
from src.models import User, Poc, PocState, CustomerNote
from src.schemas import (
    CreateUserRequest, UserResponse, UpdateUserRequest,
    ResetPasswordRequest, PocResponse
)
from src.config import PARTNER_EXPIRY_DAYS, ALLOW_DB_CLEANUP

router = APIRouter(prefix="/api/admin", tags=["admin"])

WEEK_LABELS = {
    "week1": "Week 1 – Installation & Setup",
    "week2": "Week 2 – Add Clouds and Build Governance",
    "week3": "Week 3 – Provision Workloads and Golden Images",
    "week4": "Week 4 – Blueprints, Multi-Cloud Catalog and FinOps",
    "week5": "Week 5 – Review, Validation and Sign-Off",
}


# ── USERS ──────────────────────────────────────────────────────────────────

@router.post("/users", response_model=UserResponse)
def create_user(req: CreateUserRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    allowed_roles = ["se", "partner"]
    if admin.is_master:
        allowed_roles.append("admin")
    if req.role not in allowed_roles:
        raise HTTPException(400, f"Role must be one of: {', '.join(allowed_roles)}")
    if req.role == "partner" and not req.company:
        raise HTTPException(400, "Company is required for partner accounts")
    if not req.password or len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(409, "Email already exists")

    expires = None
    if req.role == "partner":
        expires = date.today() + timedelta(days=PARTNER_EXPIRY_DAYS)

    user = User(
        email=req.email,
        name=req.name,
        password_hash=hash_password(req.password),
        role=req.role,
        region=req.region,
        company=req.company,
        expires_at=expires,
        created_by=admin.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=List[UserResponse])
def list_users(
    role: Optional[str] = Query(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    # Non-master admins cannot see other admins
    if not admin.is_master:
        q = q.filter(User.role != "admin")
    return q.order_by(User.created_at.desc()).all()


@router.get("/me")
def get_me(admin: User = Depends(require_admin)):
    return {"id": admin.id, "email": admin.email, "name": admin.name,
            "role": admin.role, "is_master": admin.is_master}


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, req: UpdateUserRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.role == "admin" and not admin.is_master:
        raise HTTPException(403, "Only master admin can modify admin accounts")
    if req.name is not None: user.name = req.name
    if req.region is not None: user.region = req.region
    if req.company is not None: user.company = req.company
    if req.expires_at is not None: user.expires_at = req.expires_at
    if req.is_active is not None: user.is_active = req.is_active
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/reset-password")
def reset_password(user_id: int, req: ResetPasswordRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.role == "admin" and not admin.is_master:
        raise HTTPException(403, "Only master admin can reset admin passwords")
    if user.id == admin.id:
        raise HTTPException(400, "Use the change password flow to reset your own password")
    if not req.new_password or len(req.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": f"Password reset for {user.email}"}


@router.put("/users/{user_id}/revoke")
def revoke_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.is_master:
        raise HTTPException(403, "Master admin accounts cannot be deactivated.")
    if user.id == admin.id:
        raise HTTPException(403, "You cannot deactivate your own account.")
    if user.role == "admin" and not admin.is_master:
        raise HTTPException(403, "Only master admin can deactivate admin accounts.")
    user.is_active = False
    db.commit()
    return {"message": f"User {user.email} deactivated."}


@router.put("/users/{user_id}/reactivate")
def reactivate_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.role == "admin" and not admin.is_master:
        raise HTTPException(403, "Only master admin can reactivate admin accounts")
    user.is_active = True
    db.commit()
    return {"message": f"User {user.email} reactivated."}


# ── POCs ───────────────────────────────────────────────────────────────────

@router.get("/pocs")
def list_all_pocs(
    year: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(Poc, User).join(User, Poc.se_id == User.id)
    if year:
        q = q.filter(Poc.start_date >= date(year, 1, 1), Poc.start_date <= date(year, 12, 31))
    if status:
        q = q.filter(Poc.status == status)
    if role:
        q = q.filter(User.role == role)
    if region:
        q = q.filter(User.region == region)
    results = q.order_by(Poc.created_at.desc()).all()

    from src.routers.pocs import WEEK_GROUPS_ITEMS as _WGI, WEEK_GROUPS_TOTAL as _WGT
    pocs_out = []
    for poc, user in results:
        states = db.query(PocState).filter(PocState.poc_id == poc.poc_id).all()
        total = _WGT
        done = 0
        for s in states:
            chks = s.checks if isinstance(s.checks, dict) else {}
            for iid in _WGI.get(s.week_id, []):
                if chks.get(iid): done += 1
        pct = round(done / total * 100) if total > 0 else 0
        pocs_out.append({
            "poc_id": poc.poc_id,
            "access_token": poc.access_token,
            "customer_name": poc.customer_name,
            "se_id": poc.se_id,
            "se_name": user.name,
            "se_role": user.role,
            "se_email": user.email,
            "start_date": str(poc.start_date),
            "end_date": str(poc.end_date),
            "modules": poc.modules,
            "license_type": poc.license_type,
            "force_blocked": poc.force_blocked,
            "admin_override": poc.admin_override,
            "smartsheet_status": poc.smartsheet_status,
            "status": poc.status,
            "created_at": str(poc.created_at),
            "customer_url": f"/poc/{poc.access_token}",
            "progress_done": done,
            "progress_total": total,
            "progress_pct": pct,
            # Enriched Smartsheet fields
            "product_family":        poc.product_family,
            "contact_name":          poc.contact_name,
            "contact_email":         poc.contact_email,
            "sub_region":            poc.sub_region,
            "on_prem_hypervisors":   poc.on_prem_hypervisors,
            "public_cloud_providers": poc.public_cloud_providers,
            "use_case":              poc.use_case,
            "morpheus_version":      poc.morpheus_version,
            "approved_sockets":      poc.approved_sockets,
            "last_synced_at": poc.last_synced_at.isoformat() if poc.last_synced_at else None,
            "last_pushed_at": poc.last_pushed_at.isoformat() if poc.last_pushed_at else None,
            "last_accessed_at": poc.last_accessed_at.isoformat() if poc.last_accessed_at else None,
            "sa_notes": poc.sa_notes or "",
            "watermark_text": poc.watermark_text or "",
            "customer_note_count": db.query(CustomerNote).filter(CustomerNote.poc_id == poc.poc_id).count(),
        })
    return pocs_out





@router.get("/pocs/{poc_id}/state")
def admin_poc_state(poc_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    states = db.query(PocState).filter(PocState.poc_id == poc_id).all()
    return [{"week_id": s.week_id, "checks": s.checks, "signoff": s.signoff} for s in states]


@router.put("/pocs/{poc_id}/block")
def admin_block_poc(poc_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc: raise HTTPException(404, "POC not found")
    poc.force_blocked = True; poc.blocked_by = admin.id
    poc.blocked_at = datetime.utcnow(); poc.admin_override = False; poc.status = "blocked"
    db.commit()
    return {"message": f"POC {poc_id} blocked."}


@router.put("/pocs/{poc_id}/unblock")
def admin_unblock_poc(poc_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc: raise HTTPException(404, "POC not found")
    poc.force_blocked = False; poc.blocked_by = None
    poc.blocked_at = None; poc.status = "active"
    db.commit()
    return {"message": f"POC {poc_id} unblocked."}


@router.put("/pocs/{poc_id}/override")
def admin_override_poc(poc_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc: raise HTTPException(404, "POC not found")
    poc.admin_override = True; poc.override_by = admin.id
    poc.override_at = datetime.utcnow(); poc.force_blocked = False
    db.commit()
    return {"message": f"POC {poc_id} override active."}


@router.put("/pocs/{poc_id}/revoke-override")
def admin_revoke_override(poc_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc: raise HTTPException(404, "POC not found")
    poc.admin_override = False; poc.override_by = None; poc.override_at = None
    db.commit()
    return {"message": f"POC {poc_id} override removed."}


# ── DELETE POC (admin only, DB only -- Smartsheet untouched) ─────────────────

@router.delete("/pocs/{poc_id}")
def delete_poc(poc_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    # Cascade delete all related data (including customer notes)
    db.query(PocState).filter(PocState.poc_id == poc_id).delete(synchronize_session=False)
    db.query(CustomerNote).filter(CustomerNote.poc_id == poc_id).delete(synchronize_session=False)
    db.delete(poc)
    db.commit()
    return {
        "deleted": poc_id,
        "message": f"POC {poc_id} and all associated data permanently deleted from database. Smartsheet row is untouched."
    }




# ── ANALYTICS ────────────────────────────────────────────────────────────────
@router.get("/analytics")
def get_analytics(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from datetime import datetime, timedelta
    from src.routers.pocs import WEEK_GROUPS_ITEMS as WGI, WEEK_GROUPS_TOTAL as WGT
    pocs_users = db.query(Poc, User).join(User, Poc.se_id == User.id).all()
    total = len(pocs_users)
    by_status = {}
    progress_bands = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}
    avg_pct_sum = 0
    week_signoffs = {f"week{i}": 0 for i in range(1, 6)}
    se_map = {}
    now = datetime.utcnow()
    engaged_7d = 0
    poc_list = []
    for poc, user in pocs_users:
        s = poc.status or "active"
        by_status[s] = by_status.get(s, 0) + 1
        states = db.query(PocState).filter(PocState.poc_id == poc.poc_id).all()
        done = 0
        for st in states:
            chks = st.checks if isinstance(st.checks, dict) else {}
            for iid in WGI.get(st.week_id, []):
                if chks.get(iid): done += 1
            if st.signoff and st.week_id in week_signoffs:
                week_signoffs[st.week_id] += 1
        pct = round(done / WGT * 100) if WGT > 0 else 0
        avg_pct_sum += pct
        band = "75-100" if pct >= 75 else "50-75" if pct >= 50 else "25-50" if pct >= 25 else "0-25"
        progress_bands[band] += 1
        sid = str(poc.se_id)
        if sid not in se_map:
            se_map[sid] = {"name": user.name, "email": user.email, "total": 0, "completed": 0, "pct_sum": 0}
        se_map[sid]["total"] += 1
        se_map[sid]["pct_sum"] += pct
        if poc.status == "completed": se_map[sid]["completed"] += 1
        if poc.last_accessed_at and (now - poc.last_accessed_at).days <= 7:
            engaged_7d += 1
        nc = db.query(CustomerNote).filter(CustomerNote.poc_id == poc.poc_id).count()
        end = poc.smartsheet_end_date or poc.end_date
        days_left = max(0, (end - now.date()).days) if end else 0
        poc_list.append({
            "poc_id": poc.poc_id, "customer_name": poc.customer_name,
            "se_name": user.name, "se_email": user.email,
            "pct": pct, "done": done, "total": WGT, "status": poc.status or "active",
            "days_left": days_left, "customer_note_count": nc,
            "last_accessed_at": poc.last_accessed_at.isoformat() if poc.last_accessed_at else None,
            "signoff_count": sum(1 for st in states if st.signoff),
            "product_family": poc.product_family, "sub_region": poc.sub_region,
        })
    total_notes = db.query(CustomerNote).count()
    return {
        "total": total, "by_status": by_status,
        "progress_bands": progress_bands,
        "avg_progress": round(avg_pct_sum / total) if total > 0 else 0,
        "week_signoffs": week_signoffs,
        "engaged_7d": engaged_7d, "total_customer_notes": total_notes,
        "se_stats": list(se_map.values()),
        "pocs": poc_list,
    }


# ── CSV EXPORT ───────────────────────────────────────────────────────────────
@router.put("/pocs/{poc_id}/signoff/{week_id}")
def admin_signoff_week(poc_id: str, week_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin can sign off any week on behalf of the SE."""
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    state = db.query(PocState).filter(PocState.poc_id == poc_id, PocState.week_id == week_id).first()
    if not state:
        state = PocState(poc_id=poc_id, week_id=week_id, checks={}, signoff=True)
        db.add(state)
    else:
        state.signoff = True
    db.commit()
    return {"poc_id": poc_id, "week_id": week_id, "signoff": True}


@router.put("/pocs/{poc_id}/complete")
def complete_poc(poc_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    # Do all Smartsheet pushes BEFORE committing DB changes so we can
    # leave the DB unchanged if something unexpected raises.
    ss_warning = None
    if poc.smartsheet_row_id:
        try:
            final_text = _build_progress_text(poc, db)
            ok1 = push_weekly_status(poc.smartsheet_row_id, poc.poc_id, poc.customer_name or "", final_text, sa_notes=poc.sa_notes or "")
            ok2 = push_poc_status(poc.smartsheet_row_id, poc.poc_id, "completed")
            if not ok1 or not ok2:
                ss_warning = "Smartsheet update failed; POC marked complete in database only."
        except Exception as e:
            ss_warning = f"Smartsheet error ({e}); POC marked complete in database only."
    poc.status = "completed"
    poc.smartsheet_status = "Completed"
    db.commit()
    return {"status": "completed", "warning": ss_warning}

@router.put("/pocs/{poc_id}/reopen")
def reopen_poc(poc_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    # Reset week progress and signoffs only — customer notes are historical
    # context and must NOT be deleted on reopen.
    db.query(PocState).filter(PocState.poc_id == poc_id).delete()
    poc.status = "active"
    poc.smartsheet_status = "Extended"
    db.commit()
    # Push Extended status to Smartsheet (triggers +45 day formula)
    ss_warning = None
    if poc.smartsheet_row_id:
        try:
            ok = push_poc_status(poc.smartsheet_row_id, poc.poc_id, "extended")
            if not ok:
                ss_warning = "Smartsheet status update failed; POC reopened in database only."
        except Exception as e:
            ss_warning = f"Smartsheet error ({e}); POC reopened in database only."
    return {"status": "active", "reset": True, "warning": ss_warning}

@router.patch("/pocs/{poc_id}/reassign")
def reassign_poc(poc_id: str, body: dict, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    new_se_id = body.get("se_id")
    if not new_se_id:
        raise HTTPException(400, "se_id required")
    new_se = db.query(User).filter(User.id == int(new_se_id)).first()
    if not new_se:
        raise HTTPException(404, "User not found")
    poc.se_id = int(new_se_id)
    db.commit()
    return {"se_id": poc.se_id, "se_email": new_se.email, "se_name": new_se.name}

@router.patch("/pocs/{poc_id}/extend")
def extend_poc(poc_id: str, body: dict, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from datetime import timedelta
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    days = int(body.get("days", 0))
    if days < 1 or days > 365:
        raise HTTPException(400, "Days must be between 1 and 365")
    current_end = poc.smartsheet_end_date or poc.end_date
    poc.end_date = current_end + timedelta(days=days)
    poc.smartsheet_end_date = poc.end_date
    db.commit()
    return {"end_date": str(poc.end_date)}


@router.put("/pocs/{poc_id}/modules")
def update_poc_modules(poc_id: str, body: dict, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    poc.modules = body.get("modules", {})
    db.commit()
    return {"poc_id": poc_id, "modules": poc.modules}

# ── DB CLEANUP (master admin only, QA/testing use, REMOVE BEFORE PRODUCTION) ─

@router.get("/db/cleanup-preview")
def cleanup_preview(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Returns counts of what a full DB cleanup would delete. Read-only."""
    if not admin.is_master:
        raise HTTPException(403, "Only the master admin can access DB cleanup.")
    from src.models import SyncLog
    users_to_delete = db.query(User).filter(User.is_master == False).count()
    poc_count = db.query(Poc).count()
    state_count = db.query(PocState).count()
    note_count = 0  # SE private notes removed
    customer_note_count = db.query(CustomerNote).count()
    try:
        log_count = db.query(SyncLog).count()
    except Exception:
        log_count = 0
    return {
        "users": users_to_delete,
        "pocs": poc_count,
        "poc_states": state_count,
        "poc_notes": note_count,
        "customer_notes": customer_note_count,
        "sync_logs": log_count,
        "master_admin_preserved": admin.email,
        "smartsheet": "UNTOUCHED — this cleanup only affects the PostgreSQL database.",
    }


@router.post("/db/cleanup")
def execute_cleanup(body: dict, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    PERMANENTLY deletes all non-admin users, POCs, states, notes and sync logs.
    Master admin account is preserved. Smartsheet is NOT touched.
    Requires confirmation token 'CLEAN' in request body.
    FOR QA/TESTING USE ONLY. REMOVE THIS ENDPOINT BEFORE PRODUCTION.
    """
    if not ALLOW_DB_CLEANUP:
        raise HTTPException(403, "DB cleanup is disabled. Set ALLOW_DB_CLEANUP=true in k8s/01-secret.yaml to enable.")
    if not admin.is_master:
        raise HTTPException(403, "Only the master admin can execute DB cleanup.")
    if body.get("confirm") != "CLEAN":
        raise HTTPException(400, 'Send {"confirm": "CLEAN"} to execute cleanup.')
    from src.models import SyncLog
    # Delete in dependency order (CustomerNote first — FK dependency on Poc)
    customer_notes_deleted = db.query(CustomerNote).delete(synchronize_session=False)
    notes_deleted = 0  # SE private notes removed
    states_deleted = db.query(PocState).delete(synchronize_session=False)
    pocs_deleted = db.query(Poc).delete(synchronize_session=False)
    users_deleted = db.query(User).filter(User.is_master == False).delete(synchronize_session=False)
    try:
        logs_deleted = db.query(SyncLog).delete(synchronize_session=False)
    except Exception:
        logs_deleted = 0
    db.commit()
    return {
        "status": "cleanup_complete",
        "deleted": {
            "users": users_deleted,
            "pocs": pocs_deleted,
            "poc_states": states_deleted,
            "poc_notes": notes_deleted,
            "customer_notes": customer_notes_deleted,
            "sync_logs": logs_deleted,
        },
        "preserved": admin.email,
        "smartsheet": "UNTOUCHED",
    }


@router.get("/customer-notes")
def get_all_customer_notes(
    poc_id: Optional[str] = Query(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    q = db.query(CustomerNote, Poc).join(Poc, CustomerNote.poc_id == Poc.poc_id)
    if poc_id:
        q = q.filter(CustomerNote.poc_id == poc_id)
    rows = q.order_by(CustomerNote.created_at.asc()).limit(200).all()
    result = []
    for note, poc in rows:
        se = db.query(User).filter(User.id == poc.se_id).first()
        result.append({
            "id": note.id,
            "poc_id": note.poc_id,
            "customer_name": poc.customer_name,
            "se_email": se.email if se else "",
            "se_name": se.name if se else "",
            "week_id": note.week_id,
            "section_id": note.section_id,
            "section_title": note.section_title,
            "note": note.note,
            "acknowledged_at": note.acknowledged_at.isoformat() if note.acknowledged_at else None,
            "se_reply": note.se_reply,
            "se_reply_at": note.se_reply_at.isoformat() if note.se_reply_at else None,
            "created_at": str(note.created_at),
        })
    return result
