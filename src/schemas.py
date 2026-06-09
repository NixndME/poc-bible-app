from pydantic import BaseModel, EmailStr, field_validator
from typing import Any, Optional, List
from datetime import date, datetime


# Auth
class LoginRequest(BaseModel):
    email: str  # allow any string to avoid leaking 'user not found' vs 'invalid email'
    password: str

class TokenResponse(BaseModel):
    must_reset: bool = False
    reset_token: Optional[str] = None   # present only when must_reset=True
    token: Optional[str] = None         # None when must_reset=True
    role: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None

class CompleteResetRequest(BaseModel):
    reset_token: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        if not v or len(v.strip()) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

# Users
class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str  # se, partner, or admin (master admin only)
    region: Optional[str] = None
    company: Optional[str] = None  # required for partners

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if not v or len(v.strip()) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v not in ('se', 'partner', 'admin'):
            raise ValueError('Role must be se, partner, or admin')
        return v

class ResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        if not v or len(v.strip()) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    region: Optional[str]
    company: Optional[str]
    expires_at: Optional[date]
    is_active: bool
    is_master: bool = False
    created_at: datetime

    class Config:
        from_attributes = True

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    region: Optional[str] = None
    company: Optional[str] = None
    expires_at: Optional[date] = None
    is_active: Optional[bool] = None

# POCs
class CreatePocRequest(BaseModel):
    poc_id: str  # POC-202605-042 -- only field the SE types
    customer_name: str
    start_date: date
    modules: Optional[dict] = {}
    license_type: Optional[str] = None
    requestor_type: Optional[str] = None
    duration_days: Optional[int] = None
    # Smartsheet lookup result fields (all auto-filled)
    smartsheet_row_id: Optional[str] = None
    smartsheet_end_date: Optional[date] = None
    smartsheet_status: Optional[str] = None
    product_family: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    sub_region: Optional[str] = None
    on_prem_hypervisors: Optional[str] = None
    public_cloud_providers: Optional[str] = None
    use_case: Optional[str] = None
    morpheus_version: Optional[str] = None
    approved_sockets: Optional[str] = None
    using_hvm: Optional[str] = None
    using_k8s: Optional[str] = None

class PocResponse(BaseModel):
    poc_id: str
    access_token: str
    customer_name: str
    se_id: int
    start_date: date
    end_date: date
    modules: Optional[dict]
    license_type: Optional[str]
    requestor_type: Optional[str]
    force_blocked: bool
    admin_override: bool
    smartsheet_status: Optional[str]
    smartsheet_row_id: Optional[str] = None
    watermark_text: Optional[str]
    status: str
    created_at: datetime
    customer_url: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_pushed_at: Optional[datetime] = None
    product_family: Optional[str] = None
    se_email: Optional[str] = None
    se_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    on_prem_hypervisors: Optional[str] = None
    public_cloud_providers: Optional[str] = None
    morpheus_version: Optional[str] = None
    approved_sockets: Optional[str] = None
    sub_region: Optional[str] = None
    use_case: Optional[str] = None
    progress_pct: Optional[int] = None
    progress_done: Optional[int] = None
    progress_total: Optional[int] = None
    sa_notes: Optional[str] = None

    class Config:
        from_attributes = True

# POC State
class SaveStateRequest(BaseModel):
    week_id: str
    checks: Any  # dict (new: {itemId: bool}) or list (legacy: [bool])
    signoff: bool = False

# Public POC (customer view)
class PublicPocResponse(BaseModel):
    poc_id: str
    customer_name: str
    start_date: date
    end_date: date
    modules: Optional[dict]
    watermark_text: Optional[str]
    status: str
    days_remaining: int

class AccessDeniedResponse(BaseModel):
    allowed: bool = False
    reason: str

