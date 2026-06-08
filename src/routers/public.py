from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
_limiter = Limiter(key_func=get_remote_address)
from sqlalchemy.orm import Session
from datetime import date
from src.database import get_db
from src.models import User, Poc, PocState, CustomerNote
from src.schemas import SaveStateRequest
from pydantic import BaseModel

class CustomerNoteRequest(BaseModel):
    week_id: str
    note: str
    section_id: str = ""
    section_title: str = ""
    item_id: str = ""
    item_title: str = ""

router = APIRouter(prefix="/api/public", tags=["public"])


def check_access(poc: Poc, db: Session) -> tuple:
    """Returns (allowed: bool, reason: str)"""
    # Admin override bypasses everything
    if poc.admin_override:
        return True, "ok"

    # Manual block by admin/SE/partner
    if poc.force_blocked:
        return False, "Access has been restricted by your HPE Solutions Engineer."

    # Smartsheet status check (from last daily sync)
    if poc.smartsheet_status and poc.smartsheet_status not in ("Approved", "Extended"):
        status_messages = {
            "Completed": "This POC has been completed. Contact your HPE SE for next steps.",
            "Blocked": "This POC is currently blocked. Contact your HPE SE.",
            "Rejected": "This POC is not available.",
            "New Submission": "This POC has not been approved yet.",
        }
        return False, status_messages.get(poc.smartsheet_status, "This POC is not currently active.")

    # Date expiry check
    end = poc.smartsheet_end_date or poc.end_date
    if end and date.today() > end:
        return False, "This POC period has expired. Contact your HPE SE."

    # Owner account check
    owner = db.query(User).filter(User.id == poc.se_id).first()
    if owner and not owner.is_active:
        return False, "This POC is not currently available."
    if owner and owner.expires_at and date.today() > owner.expires_at:
        return False, "This POC is not currently available."

    return True, "ok"


@router.get("/{token}")
@_limiter.limit("60/minute")
def get_public_poc(request: Request,token: str, db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.access_token == token).first()
    if not poc:
        raise HTTPException(404, "POC not found. Check your URL with your HPE SE.")

    allowed, reason = check_access(poc, db)
    if not allowed:
        return {"allowed": False, "reason": reason}

    end = poc.smartsheet_end_date or poc.end_date
    days_left = max(0, (end - date.today()).days) if end else 0
    owner = db.query(User).filter(User.id == poc.se_id).first()

    # Record customer last access time
    from datetime import datetime as _dt
    try:
        poc.last_accessed_at = _dt.utcnow()
        db.commit()
    except Exception:
        pass

    return {
        "allowed": True,
        "poc_id": poc.poc_id,
        "customer_name": poc.customer_name,
        "se_name": owner.name if owner else "Your HPE Solutions Engineer",
        "se_email": owner.email if owner else "",
        "start_date": str(poc.start_date),
        "end_date": str(end),
        "days_remaining": days_left,
        "modules": poc.modules,
        "watermark_text": poc.watermark_text,
        "status": poc.status,
    }


@router.get("/{token}/state")
@_limiter.limit("60/minute")
def get_public_state(request: Request,token: str, db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.access_token == token).first()
    if not poc:
        raise HTTPException(404, "POC not found")

    allowed, reason = check_access(poc, db)
    if not allowed:
        raise HTTPException(403, reason)

    states = db.query(PocState).filter(PocState.poc_id == poc.poc_id).all()
    return [
        {
            "poc_id":  s.poc_id,
            "week_id": s.week_id,
            "checks":  s.checks or [],
            "signoff": bool(s.signoff),
        }
        for s in states
    ]


@router.put("/{token}/state")
@_limiter.limit("60/minute")
def save_public_state(request: Request,token: str, req: SaveStateRequest, db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.access_token == token).first()
    if not poc:
        raise HTTPException(404, "POC not found")

    allowed, reason = check_access(poc, db)
    if not allowed:
        raise HTTPException(403, reason)

    state = db.query(PocState).filter(
        PocState.poc_id == poc.poc_id, PocState.week_id == req.week_id
    ).first()
    if state:
        state.checks = req.checks
        state.signoff = req.signoff
    else:
        state = PocState(
            poc_id=poc.poc_id, week_id=req.week_id,
            checks=req.checks, signoff=req.signoff,
        )
        db.add(state)
    db.commit()
    return {"message": "Progress saved"}


@router.post("/{token}/customer-notes")
@_limiter.limit("20/minute")
def add_customer_note(request: Request, token: str, req: CustomerNoteRequest, db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.access_token == token).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    allowed, reason = check_access(poc, db)
    if not allowed:
        raise HTTPException(403, reason)
    if not req.note.strip():
        raise HTTPException(400, "Note cannot be empty")
    if len(req.note) > 2000:
        raise HTTPException(400, "Note too long (max 2000 characters)")
    note = CustomerNote(poc_id=poc.poc_id, week_id=req.week_id, section_id=req.section_id or None, section_title=req.section_title or None, item_id=req.item_id or None, item_title=req.item_title or None, note=req.note.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "week_id": note.week_id, "note": note.note, "acknowledged_at": note.acknowledged_at.isoformat() if note.acknowledged_at else None, "se_reply": note.se_reply, "se_reply_at": note.se_reply_at.isoformat() if note.se_reply_at else None, "created_at": str(note.created_at)}


@router.get("/{token}/customer-notes")
@_limiter.limit("60/minute")
def get_customer_notes(request: Request, token: str, db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.access_token == token).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    allowed, reason = check_access(poc, db)
    if not allowed:
        raise HTTPException(403, reason)
    notes = db.query(CustomerNote).filter(CustomerNote.poc_id == poc.poc_id).order_by(CustomerNote.created_at).all()
    return [{"id": n.id, "week_id": n.week_id, "section_id": n.section_id, "section_title": n.section_title, "item_id": n.item_id, "item_title": n.item_title, "note": n.note, "acknowledged_at": n.acknowledged_at.isoformat() if n.acknowledged_at else None, "se_reply": n.se_reply, "se_reply_at": n.se_reply_at.isoformat() if n.se_reply_at else None, "created_at": str(n.created_at)} for n in notes]
