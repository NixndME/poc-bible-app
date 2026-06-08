"""
Smartsheet lookup endpoint.
Ownership gate: non-owners see nothing except "valid but not yours".
"""
from fastapi import APIRouter, Depends
from src.auth import require_se_or_partner
from src.models import User
from src.smartsheet_service import lookup_poc

router = APIRouter(prefix="/api/smartsheet", tags=["smartsheet"])


@router.get("/lookup/{poc_id}")
def lookup_poc_id(poc_id: str, user: User = Depends(require_se_or_partner)):
    is_admin = user.role == "admin"
    result = lookup_poc(poc_id.strip().upper(), requester_email=user.email, is_admin=is_admin)

    # POC not found at all
    if not result.get("found"):
        return {"found": False, "allowed": False, "is_owner": False,
                "reason": result.get("reason", "POC ID not found in Smartsheet tracker.")}

    is_owner = result.get("is_owner", False)

    # Non-owner: confirm the ID exists but reveal nothing else
    if not is_owner:
        return {
            "found":    True,
            "allowed":  False,       # block creation on frontend too
            "is_owner": False,
            "reason":   "This POC ID is valid but you are not the assigned SE. You cannot create a Bible link for this customer.",
        }

    # Status gate (Rejected, Blocked, etc.) -- only reached by owner or admin
    if not result.get("allowed"):
        return {
            "found":    True,
            "allowed":  False,
            "is_owner": True,
            "reason":   result.get("reason", "This POC status does not allow Bible creation."),
        }

    # Owner + approved: return full data
    return {
        "found":          True,
        "allowed":        True,
        "is_owner":       True,
        "status":         result.get("status", ""),
        "row_id":         result.get("row_id", ""),
        "customer_name":  result.get("customer_name", ""),
        "product_family": result.get("product_family", ""),
        "license_type":   result.get("license_type", "Standard License"),
        "se_name":        result.get("se_name", ""),
        "region":         result.get("region", ""),
        "sub_region":     result.get("sub_region", ""),
        "contact_name":   result.get("contact_name", ""),
        "contact_email":  result.get("contact_email", ""),
        "start_date":     str(result["start_date"]) if result.get("start_date") else "",
        "end_date":       str(result["end_date"])   if result.get("end_date")   else "",
        "morpheus_version":      result.get("morpheus_version", ""),
        "on_prem_hypervisors":   result.get("on_prem_hypervisors", ""),
        "public_cloud_providers": result.get("public_cloud_providers", ""),
        "approved_sockets":      result.get("approved_sockets", ""),
        "use_case":              result.get("use_case", ""),
        "modules_auto":          result.get("modules_auto", {}),
        "using_hvm":             result.get("using_hvm", ""),
        "using_k8s":             result.get("using_k8s", ""),
    }
