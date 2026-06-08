from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from src.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin, se, partner
    region = Column(String, nullable=True)
    company = Column(String, nullable=True)  # partner org name, NULL for HPE
    expires_at = Column(Date, nullable=True)  # partners: created_at + 6 months
    is_active = Column(Boolean, default=True)  # deactivate, never delete
    is_master = Column(Boolean, default=False)  # master admin: god-level, can manage other admins
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class Poc(Base):
    __tablename__ = "pocs"

    poc_id = Column(String, primary_key=True, index=True)  # POC-202605-042
    access_token = Column(String, unique=True, nullable=False, index=True)  # random 16-char hex
    customer_name = Column(String, nullable=False)
    se_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    modules = Column(JSON, default=dict)  # {hvm: bool, hks: bool, terraform: bool, ansible: bool}
    license_type = Column(String, nullable=True)
    requestor_type = Column(String, nullable=True)

    # Enriched fields from Smartsheet (populated at POC create time)
    product_family     = Column(String, nullable=True)   # HPE Morpheus Enterprise/Advanced/VM Essentials
    contact_name       = Column(String, nullable=True)   # customer contact name
    contact_email      = Column(String, nullable=True)   # customer contact email
    sub_region         = Column(String, nullable=True)   # e.g. Australia, India
    on_prem_hypervisors = Column(String, nullable=True)  # comma-separated e.g. "VMware vSphere,Nutanix AHV"
    public_cloud_providers = Column(String, nullable=True)  # comma-separated e.g. "AWS,Microsoft Azure"
    use_case           = Column(Text, nullable=True)     # use case description from Smartsheet
    morpheus_version   = Column(String, nullable=True)   # e.g. 8.1.2
    approved_sockets   = Column(String, nullable=True)   # approved socket count
    using_hvm          = Column(String, nullable=True)   # Yes/No/Currently Evaluating
    using_k8s          = Column(String, nullable=True)   # Yes - External/Yes - MKS/HKS/No

    # Access control
    force_blocked = Column(Boolean, default=False)
    blocked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    blocked_at = Column(DateTime, nullable=True)
    admin_override = Column(Boolean, default=False)
    override_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    override_at = Column(DateTime, nullable=True)

    # Smartsheet sync
    smartsheet_row_id = Column(String, nullable=True)
    smartsheet_status = Column(String, nullable=True)
    smartsheet_end_date = Column(Date, nullable=True)
    last_synced_at  = Column(DateTime, nullable=True)
    last_pushed_at  = Column(DateTime, nullable=True)

    # Watermark
    watermark_text = Column(String, nullable=True)

    # SE notes for SA (pushed to Smartsheet SE / Partner Notes column)
    sa_notes = Column(Text, nullable=True)

    status = Column(String, default="active")  # active, completed, expired, blocked
    last_accessed_at = Column(DateTime, nullable=True)  # when customer last opened their Bible
    created_at = Column(DateTime, server_default=func.now())


class PocState(Base):
    __tablename__ = "poc_state"

    poc_id = Column(String, ForeignKey("pocs.poc_id"), primary_key=True)
    week_id = Column(String, primary_key=True)  # week1, week2, etc.
    checks = Column(JSON, default=list)  # [true, false, true, ...]
    signoff = Column(Boolean, default=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CustomerNote(Base):
    __tablename__ = "customer_notes"

    id = Column(Integer, primary_key=True, index=True)
    poc_id = Column(String, ForeignKey("pocs.poc_id"), nullable=False, index=True)
    week_id = Column(String, nullable=False)      # week1, week2, etc.
    section_id = Column(String, nullable=True)    # grp-prereq, grp-network, etc.
    section_title = Column(String, nullable=True) # human-readable section name
    item_id = Column(String, nullable=True)       # p1, p2, n1, etc.
    item_title = Column(String, nullable=True)    # human-readable item name
    note = Column(Text, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)  # set by SE when note is read
    se_reply = Column(Text, nullable=True)            # one SE reply per customer note
    se_reply_at = Column(DateTime, nullable=True)     # when SE replied
    created_at = Column(DateTime, server_default=func.now())


class SyncLog(Base):
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, index=True)
    poc_id = Column(String, nullable=True)   # NULL for batch syncs
    sync_type = Column(String, nullable=True)  # bidaily, weekly_push
    payload = Column(JSON, nullable=True)
    synced_at = Column(DateTime, server_default=func.now())
    success = Column(Boolean, default=True)
