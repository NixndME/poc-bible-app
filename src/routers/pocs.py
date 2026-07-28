import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import List
from src.database import get_db
from src.auth import require_se_or_partner, get_current_user
from src.models import User, Poc, PocState, CustomerNote
from src.modules import MODULES, MODULE_BY_KEY, MODULE_KEYS
from src.schemas import (
    CreatePocRequest, PocResponse,
    SaveStateRequest,
)


WEEK_GROUPS_ITEMS = {
    "week1": ["p1","p2","p3","p4","p5","p6","n1","n2","i1","i2","i3","i4","i5","v1","v2","v3","s1","s2","s3","s4","s6","s7"],
    "week2": ["lp1","aws1","aws2","aws3","aws4","vc1","vc2","vc3","t1","t2","r1","r2","rdpol1","rdpol2","rdpol3","pol-naming","pol-tags","wv1","wv2","wv3"],
    "week3": ["w3a1","w3a2","w3a3","w3g1","w3g2","w3g3","w3cy1","w3t1","w3t2","w3t3","w3w1"],
    "week4": ["w4b1","w4b2","w4c1","w4c2","w4c3","w4f1","w4f2","w4f3"],
    "week5": ["w5e1","w5h1","w5h2","w5a1","w5a2","w5a3","w5s1","w5s2"],
}
WEEK_GROUPS_TOTAL = sum(len(v) for v in WEEK_GROUPS_ITEMS.values())

# Optional-module weeks (mirrors static/index.html MODULE_WEEKS group/item structure).
# Kept separate from WEEK_GROUPS_ITEMS/WEEK_GROUPS_TOTAL above -- module progress is
# reported per-module in get_poc_progress(), not folded into the core POC's overall %.
MODULE_LABELS = {
    "hvm-w1":   "HVM - KVM Cluster Provisioning & Workloads",
    "hks-w1":   "HKS/MKS - Kubernetes Service on VMware / HVM",
    "tf-w1":    "Terraform - Infrastructure as Code",
    "sdn-w1":   "SDN / Networking - Software-Defined Networking",
    "opl-w1":   "Option Lists - Custom Provisioning Inputs",
    "price-w1": "Prices & Price Sets - On-Prem Cost Visibility",
    "wl-w1":    "White Labelling - Branding & Tenant Defaults",
}
MODULE_GROUPS = {
    "hvm-w1": [
        {"id": "grp-hvm-install",   "name": "Prerequisites and cluster provisioning", "items": ["hvm-c1", "hvm-c2"]},
        {"id": "grp-hvm-inventory", "name": "Verify the cluster",                     "items": ["hvm-i1", "hvm-i2"]},
        {"id": "grp-hvm-provision", "name": "Provision and manage a workload",        "items": ["hvm-p1", "hvm-p2"]},
    ],
    "hks-w1": [
        {"id": "grp-hks-prereq",   "name": "Prerequisites & Infrastructure Planning",   "items": ["hks-pre1", "hks-pre2", "hks-pre3", "hks-pre4", "hks-pre4b", "hks-pre5", "hks-pre6"]},
        {"id": "grp-hks-configure","name": "Configure MKS Service in Morpheus Library", "items": ["hks-cfg1", "hks-cfg2", "hks-cfg3", "hks-cfg4"]},
        {"id": "grp-hks-provision","name": "Provision Kubernetes Cluster",              "items": ["hks-prv1", "hks-prv2", "hks-prv3", "hks-prv4", "hks-prv5"]},
        {"id": "grp-hks-validate", "name": "Validate & Day-2 Operations",               "items": ["hks-val1", "hks-val2", "hks-val3", "hks-val4", "hks-val5"]},
    ],
    "tf-w1": [
        {"id": "grp-tf-setup",    "name": "Connect the Terraform source",         "items": ["tf-s1", "tf-s2"]},
        {"id": "grp-tf-template", "name": "Create the Terraform App Blueprint",   "items": ["tf-b1", "tf-b2"]},
        {"id": "grp-tf-lifecycle","name": "Deploy, plan and destroy",             "items": ["tf-l1", "tf-l2"]},
    ],
    "sdn-w1": [
        {"id": "grp-sdn-support", "name": "Supported SDN integrations & version 9 changes", "items": ["sdn-s1", "sdn-s2"]},
        {"id": "grp-sdn-add",     "name": "Add the SDN integration (NSX-T example)",        "items": ["sdn-a1", "sdn-a2", "sdn-a3", "sdn-a4"]},
        {"id": "grp-sdn-net",     "name": "Networks, Network Groups & Domains",              "items": ["sdn-n1", "sdn-n2", "sdn-n3"]},
        {"id": "grp-sdn-ipam",    "name": "IPAM integration (optional)",                     "items": ["sdn-i1", "sdn-i2"]},
        {"id": "grp-sdn-sec",     "name": "Security Groups & rules",                         "items": ["sdn-sg1", "sdn-sg2"]},
        {"id": "grp-sdn-prov",    "name": "Provisioning experience",                         "items": ["sdn-p1", "sdn-p2"]},
    ],
    "opl-w1": [
        {"id": "grp-opl-create", "name": "Create the Option List",              "items": ["opl-c1", "opl-c2"]},
        {"id": "grp-opl-input",  "name": "Bind the Option List to an Input",    "items": ["opl-i1"]},
        {"id": "grp-opl-use",    "name": "Surface the Input on forms",         "items": ["opl-u1", "opl-u2"]},
    ],
    "price-w1": [
        {"id": "grp-price-prices","name": "Create the Prices",                     "items": ["price-p0", "price-p1"]},
        {"id": "grp-price-sets",  "name": "Group Prices into a Price Set",         "items": ["price-s1"]},
        {"id": "grp-price-attach","name": "Attach to Service Plan and Cloud",      "items": ["price-a1", "price-a2"]},
        {"id": "grp-price-verify","name": "Verify cost visibility",               "items": ["price-v1"]},
    ],
    "wl-w1": [
        {"id": "grp-wl-enable", "name": "Enable and brand the master appliance", "items": ["wl-e1", "wl-e2"]},
        {"id": "grp-wl-tenant", "name": "Per-tenant branding and defaults",      "items": ["wl-t1"]},
    ],
}

# Guide sections the SE may skip per-POC (cloud/connection-specific groups).
# Skipping hides the section in the customer guide and excludes its items from
# progress totals. Non-destructive: saved checks are preserved if re-enabled.
SKIPPABLE_GROUPS = {
    "grp-aws":             {"label": "Add AWS Cloud",                 "week": "week2", "items": ["aws1","aws2","aws3","aws4"]},
    "grp-vmware":          {"label": "Add VMware vCenter Cloud",      "week": "week2", "items": ["vc1","vc2","vc3"]},
    "grp-w3-aws":          {"label": "Provision on AWS",              "week": "week3", "items": ["w3a1","w3a2","w3a3"]},
    "grp-w3-golden-linux": {"label": "Linux Golden Image on VMware",  "week": "week3", "items": ["w3g1","w3g2","w3g3"]},
    "grp-w3-golden-win":   {"label": "Windows Golden Image on VMware","week": "week3", "items": ["w3w1"]},
}

def _skipped_items_by_week(poc) -> dict:
    """{week_id: set(item_ids)} for this POC's active skips."""
    skips = poc.skips if isinstance(poc.skips, dict) else {}
    out = {}
    for gid, on in skips.items():
        g = SKIPPABLE_GROUPS.get(gid)
        if on and g:
            out.setdefault(g["week"], set()).update(g["items"])
    return out

router = APIRouter(prefix="/api/pocs", tags=["pocs"])


LICENSE_DURATIONS = {
    "Morpheus Standard License (45 Days)": 45,
    "VM Essentials License (30 Days)": 30,
    "NFR License (6 Months)": 183,
    "Internal Lab License": 90,
    "Custom License": None,  # uses duration_days field
    # Legacy fallbacks for existing POCs already in the DB
    "Standard License": 45,
    "Standard Morpheus License - 45 Days": 45,
    "VM Essentials - 30 Day Standard": 30,
    "NFR": 183,
    "Internal Lab": 90,
}


def generate_watermark(user: User, customer_name: str, license_type: str) -> str:
    if license_type == "Internal Lab":
        return user.name
    return customer_name


@router.post("", response_model=PocResponse)
def create_poc(req: CreatePocRequest, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    if db.query(Poc).filter(Poc.poc_id == req.poc_id).first():
        raise HTTPException(409, f"POC {req.poc_id} already exists")

    # Always validate against Smartsheet before creating -- this is the hard gate.
    # The frontend lookup is advisory UX only; this is the real enforcement.
    from src.config import SMARTSHEET_API_KEY
    if SMARTSHEET_API_KEY:
        from src.smartsheet_service import lookup_poc
        # Server-side validation: check status AND ownership using the real user's email
        ss = lookup_poc(req.poc_id, requester_email=user.email, is_admin=user.role == "admin")
        if not ss.get("allowed"):
            raise HTTPException(
                400,
                detail=ss.get("reason") or "This POC is not approved in the Smartsheet tracker."
            )
        if not ss.get("is_owner"):
            raise HTTPException(
                403,
                detail="Only the assigned SE on this POC can create a Bible link. Contact your HPE SE."
            )
        # Sync Smartsheet data into request if backend lookup returned richer data
        if ss.get("customer_name") and not req.customer_name:
            req.customer_name = ss["customer_name"]
        if ss.get("end_date") and not req.smartsheet_end_date:
            req.smartsheet_end_date = ss["end_date"]
        if ss.get("row_id") and not req.smartsheet_row_id:
            req.smartsheet_row_id = ss["row_id"]
        if ss.get("status") and not req.smartsheet_status:
            req.smartsheet_status = ss["status"]
        # Always enrich from Smartsheet lookup -- these are the authoritative values
        if ss.get("product_family"):  req.product_family  = ss["product_family"]
        if ss.get("license_type"):    req.license_type    = ss["license_type"]
        if ss.get("contact_name"):    req.contact_name    = ss["contact_name"]
        if ss.get("contact_email"):   req.contact_email   = ss["contact_email"]
        if ss.get("sub_region"):      req.sub_region      = ss["sub_region"]
        if ss.get("on_prem_hypervisors"): req.on_prem_hypervisors = ss["on_prem_hypervisors"]
        if ss.get("public_cloud_providers"): req.public_cloud_providers = ss["public_cloud_providers"]
        if ss.get("use_case"):        req.use_case        = ss["use_case"]
        if ss.get("morpheus_version"): req.morpheus_version = ss["morpheus_version"]
        if ss.get("approved_sockets"): req.approved_sockets = ss["approved_sockets"]
        if ss.get("using_hvm"):       req.using_hvm       = ss["using_hvm"]
        if ss.get("using_k8s"):       req.using_k8s       = ss["using_k8s"]
        # Apply auto-detected modules if SE didn't provide explicit modules
        if not req.modules and ss.get("modules_auto"):
            req.modules = ss["modules_auto"]

    access_token = secrets.token_hex(8)

    if req.smartsheet_end_date:
        end_date = req.smartsheet_end_date
    else:
        duration = LICENSE_DURATIONS.get(req.license_type or "Morpheus Standard License (45 Days)", 45)
        if duration is None:
            duration = req.duration_days or 45
        end_date = req.start_date + timedelta(days=duration)

    watermark = generate_watermark(user, req.customer_name, req.license_type or "")

    poc = Poc(
        poc_id=req.poc_id,
        access_token=access_token,
        customer_name=req.customer_name,
        se_id=user.id,
        start_date=req.start_date,
        end_date=end_date,
        modules=req.modules or {},
        license_type=req.license_type,
        requestor_type=req.requestor_type,
        watermark_text=watermark,
        smartsheet_row_id=req.smartsheet_row_id or None,
        smartsheet_status=req.smartsheet_status or None,
        smartsheet_end_date=end_date if req.smartsheet_end_date else None,
        product_family=req.product_family,
        contact_name=req.contact_name,
        contact_email=req.contact_email,
        sub_region=req.sub_region,
        on_prem_hypervisors=req.on_prem_hypervisors,
        public_cloud_providers=req.public_cloud_providers,
        use_case=req.use_case,
        morpheus_version=req.morpheus_version,
        approved_sockets=req.approved_sockets,
        using_hvm=req.using_hvm,
        using_k8s=req.using_k8s,
    )
    db.add(poc)
    db.commit()
    db.refresh(poc)
    poc.customer_url = f"/poc/{poc.access_token}"
    return poc


@router.get("")
def list_my_pocs(user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    if user.role == "admin":
        pocs = db.query(Poc).order_by(Poc.created_at.desc()).all()
    else:
        pocs = db.query(Poc).filter(Poc.se_id == user.id).order_by(Poc.created_at.desc()).all()
    result = []
    for p in pocs:
        states = db.query(PocState).filter(PocState.poc_id == p.poc_id).all()
        skipped = _skipped_items_by_week(p)
        total = WEEK_GROUPS_TOTAL - sum(len(v) for v in skipped.values())
        done = 0
        for s in states:
            chks = s.checks if isinstance(s.checks, dict) else {}
            wk_skipped = skipped.get(s.week_id, set())
            for iid in WEEK_GROUPS_ITEMS.get(s.week_id, []):
                if iid not in wk_skipped and chks.get(iid): done += 1
        pct = round(done / total * 100) if total > 0 else 0
        result.append({
            "poc_id": p.poc_id,
            "access_token": p.access_token,
            "customer_name": p.customer_name,
            "se_id": p.se_id,
            "start_date": str(p.start_date),
            "end_date": str(p.end_date),
            "modules": p.modules,
            "skips": p.skips if isinstance(p.skips, dict) else {},
            "license_type": p.license_type,
            "requestor_type": p.requestor_type,
            "force_blocked": p.force_blocked,
            "admin_override": p.admin_override,
            "sequential_lock": p.sequential_lock if p.sequential_lock is not None else True,
            "gate_changed_at": p.gate_changed_at.isoformat() if p.gate_changed_at else None,
            "smartsheet_status": p.smartsheet_status,
            "watermark_text": p.watermark_text,
            "status": p.status,
            "created_at": str(p.created_at),
            "customer_url": f"/poc/{p.access_token}",
            "last_synced_at": p.last_synced_at.isoformat() if p.last_synced_at else None,
            "last_pushed_at": p.last_pushed_at.isoformat() if p.last_pushed_at else None,
            "last_accessed_at": p.last_accessed_at.isoformat() if p.last_accessed_at else None,
            "smartsheet_row_id": p.smartsheet_row_id,
            "se_name": user.name,
            "se_email": user.email,
            "sa_notes": p.sa_notes or "",
            "progress_total": total,
            "progress_done": done,
            "progress_pct": pct,
            "customer_note_count": db.query(CustomerNote).filter(CustomerNote.poc_id == p.poc_id).count(),
            # Enriched Smartsheet fields
            "product_family":        p.product_family,
            "contact_name":          p.contact_name,
            "contact_email":         p.contact_email,
            "sub_region":            p.sub_region,
            "on_prem_hypervisors":   p.on_prem_hypervisors,
            "public_cloud_providers": p.public_cloud_providers,
            "use_case":              p.use_case,
            "morpheus_version":      p.morpheus_version,
            "approved_sockets":      p.approved_sockets,
        })
    return result


@router.get("/{poc_id}", response_model=PocResponse)
def get_my_poc(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    poc.customer_url = f"/poc/{poc.access_token}"
    return poc


@router.put("/{poc_id}/block")
def block_my_poc(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    poc.force_blocked = True
    poc.blocked_by = user.id
    poc.blocked_at = datetime.utcnow()
    poc.status = "blocked"
    db.commit()
    return {"message": f"POC {poc_id} access blocked for customer."}


@router.put("/{poc_id}/unblock")
def unblock_my_poc(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    poc.force_blocked = False
    poc.blocked_by = None
    poc.blocked_at = None
    poc.status = "active"
    db.commit()
    return {"message": f"POC {poc_id} access restored for customer."}


@router.put("/{poc_id}/unlock-gate")
def unlock_week_gate(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    """Remove the week-order gate for this POC: all weeks become visible/editable
    regardless of prior sign-off. Default is locked (sequential_lock=True) for
    every POC; this is an explicit per-POC opt-out."""
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    poc.sequential_lock = False
    poc.gate_changed_by = user.id
    poc.gate_changed_at = datetime.utcnow()
    db.commit()
    return {"message": f"Week gate removed for {poc_id}. All weeks are now unlocked."}


@router.put("/{poc_id}/lock-gate")
def lock_week_gate(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    """Re-apply the week-order gate. Nothing is deleted -- all saved checks and
    sign-offs remain in poc_state. But any week that was reached without an
    explicit sign-off (or without 100% of its own items checked) becomes
    inaccessible again until the weeks before it are complete, in order."""
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    poc.sequential_lock = True
    poc.gate_changed_by = user.id
    poc.gate_changed_at = datetime.utcnow()
    db.commit()
    return {"message": f"Week gate re-applied for {poc_id}."}


# --- State management ---

@router.put("/{poc_id}/request-completion")
def request_completion(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    if poc.status == "completed":
        raise HTTPException(400, "POC is already completed")
    poc.status = "completion_requested"
    db.commit()
    return {"status": "completion_requested"}

@router.put("/{poc_id}/cancel-completion")
def cancel_completion(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    if poc.status != "completion_requested":
        raise HTTPException(400, "No pending completion request")
    poc.status = "active"
    db.commit()
    return {"status": "active"}


@router.get("/{poc_id}/progress")
def get_poc_progress(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")

    WEEK_LABELS = {
        "week1": "Week 1 - Installation & Setup",
        "week2": "Week 2 - Add Clouds and Build Governance",
        "week3": "Week 3 - Provision Workloads and Golden Images",
        "week4": "Week 4 - Blueprints, Multi-Cloud Catalog and FinOps",
        "week5": "Week 5 - Review, Validation and Sign-Off",
    }
    WEEK_GROUPS = {
        "week1": [
            {"id":"grp-prereq","name":"Pre-installation requirements","items":["p1","p2","p3","p4","p5","p6"]},
            {"id":"grp-network","name":"Network and firewall verification","items":["n1","n2"]},
            {"id":"grp-install","name":"Package download and installation","items":["i1","i2","i3","i4","i5"]},
            {"id":"grp-verify","name":"Post-installation verification","items":["v1","v2","v3"]},
            {"id":"grp-setup","name":"Initial appliance setup and license","items":["s1","s2","s3","s4","s6","s7"]},
        ],
        "week2": [
            {"id":"grp-license-planning","name":"POC license planning","items":["lp1"]},
            {"id":"grp-aws","name":"Add AWS cloud","items":["aws1","aws2","aws3","aws4"]},
            {"id":"grp-vmware","name":"Add VMware vCenter cloud","items":["vc1","vc2","vc3"]},
            {"id":"grp-tenants","name":"Tenants and groups","items":["t1","t2"]},
            {"id":"grp-roles","name":"Roles and users","items":["r1","r2"]},
            {"id":"grp-policies","name":"Policies","items":["rdpol1","rdpol2","rdpol3","pol-naming","pol-tags"]},
            {"id":"grp-w2verify","name":"Verify governance","items":["wv1","wv2","wv3"]},
        ],
        "week3": [
            {"id":"grp-w3-aws","name":"Provision on AWS","items":["w3a1","w3a2","w3a3"]},
            {"id":"grp-w3-golden-linux","name":"Linux golden image on VMware","items":["w3g1","w3g2","w3g3"]},
            {"id":"grp-w3-automation","name":"Application automation and service catalog","items":["w3cy1","w3t1","w3t2","w3t3"]},
            {"id":"grp-w3-golden-win","name":"Windows golden image on VMware","items":["w3w1"]},
        ],
        "week4": [
            {"id":"grp-w4-blueprints","name":"App blueprints","items":["w4b1","w4b2"]},
            {"id":"grp-w4-catalog","name":"Multi-cloud catalog item","items":["w4c1","w4c2","w4c3"]},
            {"id":"grp-w4-finops","name":"FinOps - cost visibility and governance","items":["w4f1","w4f2","w4f3"]},
        ],
        "week5": [
            {"id":"grp-w5-e2e","name":"End-to-end scenario run","items":["w5e1"]},
            {"id":"grp-w5-health","name":"Appliance health and backup","items":["w5h1","w5h2"]},
            {"id":"grp-w5-analytics","name":"Analytics, guidance and reports","items":["w5a1","w5a2","w5a3"]},
            {"id":"grp-w5-signoff","name":"Success criteria review and sign-off","items":["w5s1","w5s2"]},
        ],
    }

    states = db.query(PocState).filter(PocState.poc_id == poc_id).all()
    state_map = {s.week_id: s for s in states}

    def count_checks(checks):
        if not checks:
            return 0, 0
        if isinstance(checks, dict):
            return sum(1 for v in checks.values() if v), len(checks)
        return sum(1 for c in checks if c), len(checks)

    poc_skips = poc.skips if isinstance(poc.skips, dict) else {}

    result = []
    for wid, label in WEEK_LABELS.items():
        s = state_map.get(wid)
        checks_dict = (s.checks if isinstance(s.checks, dict) else {}) if s else {}

        groups_out = []
        for g in WEEK_GROUPS.get(wid, []):
            g_skipped = bool(poc_skips.get(g["id"]))
            g_total = len(g["items"])
            g_done = sum(1 for iid in g["items"] if checks_dict.get(iid))
            groups_out.append({
                "id": g["id"],
                "name": g["name"],
                "done": g_done,
                "total": g_total,
                "skipped": g_skipped,
            })

        # Total MUST come from WEEK_GROUPS definition, not len(checks)
        # len(checks) = only keys ever stored; WEEK_GROUPS = expected items
        # Skipped groups are excluded from week totals entirely.
        total = sum(g["total"] for g in groups_out if not g["skipped"])
        done = sum(g["done"] for g in groups_out if not g["skipped"])

        result.append({
            "week_id": wid,
            "label": label,
            "done": done,
            "total": total,
            "pct": round(done / total * 100) if total > 0 else 0,
            "signoff": s.signoff if s else False,
            "updated_at": str(s.updated_at) if s and s.updated_at else None,
            "groups": groups_out,
        })

    # Append rows for enabled optional modules (HVM, HKS, Terraform, SDN, Option
    # Lists, Pricing, White Labelling) so they show up in "Week progress" the
    # same way core weeks do. Ansible has no dedicated guide section (no week_ids
    # in MODULE_BY_KEY) so it never produces a row here.
    poc_modules = poc.modules if isinstance(poc.modules, dict) else {}
    for m in MODULES:
        if not poc_modules.get(m["key"]):
            continue
        for mwid in m.get("week_ids", []):
            if mwid not in MODULE_GROUPS:
                continue
            s = state_map.get(mwid)
            checks_dict = (s.checks if isinstance(s.checks, dict) else {}) if s else {}
            groups_out = []
            for g in MODULE_GROUPS[mwid]:
                g_total = len(g["items"])
                g_done = sum(1 for iid in g["items"] if checks_dict.get(iid))
                groups_out.append({
                    "id": g["id"], "name": g["name"],
                    "done": g_done, "total": g_total, "skipped": False,
                })
            total = sum(g["total"] for g in groups_out)
            done = sum(g["done"] for g in groups_out)
            result.append({
                "week_id": mwid,
                "label": MODULE_LABELS.get(mwid, m["label"]),
                "done": done,
                "total": total,
                "pct": round(done / total * 100) if total > 0 else 0,
                "signoff": s.signoff if s else False,
                "updated_at": str(s.updated_at) if s and s.updated_at else None,
                "groups": groups_out,
                "is_module": True,
            })
    return result



@router.get("/{poc_id}/state")
def get_poc_state(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    states = db.query(PocState).filter(PocState.poc_id == poc_id).all()
    # Return plain dicts (same format as admin endpoint) -- avoids Pydantic validation issues
    return [
        {
            "poc_id":  s.poc_id,
            "week_id": s.week_id,
            "checks":  s.checks or [],
            "signoff": bool(s.signoff),
        }
        for s in states
    ]


@router.put("/{poc_id}/state")
def save_poc_state(poc_id: str, req: SaveStateRequest, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    state = db.query(PocState).filter(PocState.poc_id == poc_id, PocState.week_id == req.week_id).first()
    if state:
        state.checks = req.checks
        state.signoff = req.signoff
    else:
        state = PocState(poc_id=poc_id, week_id=req.week_id, checks=req.checks, signoff=req.signoff)
        db.add(state)
    db.commit()
    return {"message": f"State saved for {poc_id} / {req.week_id}"}


# --- Scope modules: self-service editing (append-only for SE; admin unrestricted) ---

def _module_has_progress(db: Session, poc_id: str, key: str) -> bool:
    """True if the customer has any saved progress or sign-off on the module's section(s)."""
    m = MODULE_BY_KEY.get(key)
    if not m or not m.get("week_ids"):
        return False
    states = db.query(PocState).filter(
        PocState.poc_id == poc_id,
        PocState.week_id.in_(m["week_ids"]),
    ).all()
    for s in states:
        if s.signoff:
            return True
        if isinstance(s.checks, dict) and any(s.checks.values()):
            return True
        if isinstance(s.checks, list) and any(s.checks):
            return True
    return False


@router.get("/meta/modules")
def list_scope_modules(user: User = Depends(require_se_or_partner)):
    """Registry of available scope modules, for the edit-scope UI."""
    return {"modules": [{"key": m["key"], "label": m["label"]} for m in MODULES]}


@router.put("/{poc_id}/modules")
def update_poc_modules_se(poc_id: str, body: dict, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    """
    SE/partner self-service scope editing.
    Adding a module is always allowed. Removing a module is allowed for the owner
    only while the customer has NO progress on it (safe undo); once the customer
    has any progress or sign-off, removal is admin-only. Admins may add or remove
    anything at any time.
    """
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")

    requested = body.get("modules") or {}
    current = poc.modules if isinstance(poc.modules, dict) else {}
    is_admin = user.role == "admin"
    result = dict(current)

    for key in MODULE_KEYS:
        want = bool(requested.get(key, current.get(key, False)))
        have = bool(current.get(key, False))
        if want == have:
            continue
        if want and not have:
            result[key] = True                      # add: always allowed
        else:                                       # remove
            if is_admin or not _module_has_progress(db, poc_id, key):
                result[key] = False                 # admin, or SE safe-undo (no progress)
            else:
                raise HTTPException(
                    403,
                    f"Module '{key}' has customer progress and can only be removed by an admin."
                )

    poc.modules = result
    db.commit()
    return {"poc_id": poc_id, "modules": result}


# --- Guide section skips: SE can hide cloud/connection sections per POC ---


@router.get("/meta/skippable")
def list_skippable_sections(user: User = Depends(require_se_or_partner)):
    """Registry of guide sections the SE may skip, for the edit-scope UI."""
    return {"sections": [
        {"id": gid, "label": g["label"], "week": g["week"]}
        for gid, g in SKIPPABLE_GROUPS.items()
    ]}


@router.put("/{poc_id}/skips")
def update_poc_skips(poc_id: str, body: dict, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    """
    SE/partner self-service section skipping. Skipping hides the section in the
    customer guide and removes its items from progress totals. Non-destructive:
    saved checks are kept, so re-enabling a section restores prior progress.
    """
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")

    requested = body.get("skips") or {}
    current = poc.skips if isinstance(poc.skips, dict) else {}
    result = dict(current)
    for gid in SKIPPABLE_GROUPS:
        if gid in requested:
            result[gid] = bool(requested[gid])
    # Drop unknown/stale keys
    result = {k: v for k, v in result.items() if k in SKIPPABLE_GROUPS}
    poc.skips = result
    db.commit()
    return {"poc_id": poc_id, "skips": result}


# --- Notes ---




@router.patch("/{poc_id}/customer-notes/{note_id}/acknowledge")
def acknowledge_customer_note(poc_id: str, note_id: int, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    note = db.query(CustomerNote).filter(CustomerNote.id == note_id, CustomerNote.poc_id == poc_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    from datetime import datetime
    note.acknowledged_at = datetime.utcnow()
    db.commit()
    return {"acknowledged": note_id, "acknowledged_at": str(note.acknowledged_at)}


@router.patch("/{poc_id}/customer-notes/{note_id}/reply")
def reply_to_customer_note(
    poc_id: str, note_id: int,
    body: dict,
    user: User = Depends(require_se_or_partner),
    db: Session = Depends(get_db)
):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc: raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    note = db.query(CustomerNote).filter(
        CustomerNote.id == note_id, CustomerNote.poc_id == poc_id
    ).first()
    if not note: raise HTTPException(404, "Note not found")
    reply_text = (body.get("reply") or "").strip()
    note.se_reply = reply_text if reply_text else None
    note.se_reply_at = datetime.utcnow() if reply_text else None
    db.commit()
    return {"note_id": note_id, "se_reply": note.se_reply}


@router.delete("/{poc_id}/customer-notes/{note_id}")
def delete_customer_note(poc_id: str, note_id: int, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    note = db.query(CustomerNote).filter(CustomerNote.id == note_id, CustomerNote.poc_id == poc_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    db.delete(note)
    db.commit()
    return {"deleted": note_id}


@router.get("/{poc_id}/sa-notes")
def get_sa_notes(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    return {"poc_id": poc_id, "sa_notes": poc.sa_notes or ""}


@router.put("/{poc_id}/sa-notes")
def save_sa_notes(poc_id: str, body: dict, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    poc.sa_notes = (body.get("sa_notes") or "").strip() or None
    db.commit()
    return {"poc_id": poc_id, "sa_notes": poc.sa_notes or ""}


@router.post("/{poc_id}/push-status")
def push_poc_to_smartsheet(poc_id: str, body: dict, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    from datetime import datetime as _dt
    from src.routers.sync_router import _build_progress_text
    from src.smartsheet_service import push_weekly_status

    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    if not poc.smartsheet_row_id:
        raise HTTPException(400, "No Smartsheet row linked to this POC. Run a full sync first.")

    mode = (body.get("mode") or "both").strip()
    comment = (body.get("comment") or "").strip()

    if mode == "note":
        progress_text = f"Note: {comment}" if comment else ""
    elif mode == "progress":
        progress_text = _build_progress_text(poc, db)
    else:  # both
        progress_text = _build_progress_text(poc, db)
        if comment:
            progress_text += f"\n\nNote: {comment}"

    if not progress_text:
        raise HTTPException(400, "Nothing to push — add a comment or switch to Progress mode.")

    ok = push_weekly_status(poc.smartsheet_row_id, poc.poc_id, poc.customer_name, progress_text, sa_notes=poc.sa_notes or "")

    if not ok:
        raise HTTPException(502, "Push to Smartsheet failed. Check the Smartsheet API key and connection.")

    poc.last_pushed_at = _dt.utcnow()
    db.commit()

    return {"pushed": True, "mode": mode, "last_pushed_at": poc.last_pushed_at.isoformat()}


@router.get("/{poc_id}/customer-notes")
def get_customer_notes_for_se(poc_id: str, user: User = Depends(require_se_or_partner), db: Session = Depends(get_db)):
    poc = db.query(Poc).filter(Poc.poc_id == poc_id).first()
    if not poc:
        raise HTTPException(404, "POC not found")
    if poc.se_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your POC")
    notes = db.query(CustomerNote).filter(CustomerNote.poc_id == poc_id).order_by(CustomerNote.created_at).all()
    return [{"id": n.id, "week_id": n.week_id, "section_id": n.section_id, "section_title": n.section_title, "item_id": n.item_id, "item_title": n.item_title, "note": n.note, "acknowledged_at": n.acknowledged_at.isoformat() if n.acknowledged_at else None, "se_reply": n.se_reply, "se_reply_at": n.se_reply_at.isoformat() if n.se_reply_at else None, "created_at": str(n.created_at)} for n in notes]
