from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import date
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.database import get_db
from src.auth import verify_password, create_token, create_reset_token, decode_reset_token, hash_password, get_current_user
from src.models import User
from src.schemas import LoginRequest, TokenResponse, CompleteResetRequest, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
_limiter = Limiter(key_func=get_remote_address)


@router.post("/login", response_model=TokenResponse)
@_limiter.limit("10/minute")
def login(request: Request, req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account deactivated. Contact your HPE admin.")
    if user.expires_at and date.today() > user.expires_at:
        raise HTTPException(403, "Account expired. Contact your HPE admin for extension.")

    # Master admin is always exempt from force-reset
    if user.must_reset_password and not user.is_master:
        reset_tok = create_reset_token(user.id)
        return TokenResponse(must_reset=True, reset_token=reset_tok)

    token = create_token(user.id, user.email, user.role)
    return TokenResponse(token=token, role=user.role, name=user.name, email=user.email)


@router.post("/complete-reset", response_model=TokenResponse)
@_limiter.limit("10/minute")
def complete_reset(request: Request, req: CompleteResetRequest, db: Session = Depends(get_db)):
    payload = decode_reset_token(req.reset_token)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(400, "User not found")
    if not user.is_active:
        raise HTTPException(403, "Account deactivated. Contact your HPE admin.")

    user.password_hash = hash_password(req.new_password)
    user.must_reset_password = False
    db.commit()

    token = create_token(user.id, user.email, user.role)
    return TokenResponse(token=token, role=user.role, name=user.name, email=user.email)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user
