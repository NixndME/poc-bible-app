"""
Smartsheet integration service for HPE Morpheus POC Bible.
"""
import logging
from datetime import date, datetime
from typing import Optional, Dict, Any, List

import smartsheet

from src.config import (
    SMARTSHEET_API_KEY, SMARTSHEET_SHEET_ID,
    SS_COL_POC_ID, SS_COL_STATUS, SS_COL_CUSTOMER, SS_COL_SE_NAME,
    SS_COL_SE_EMAIL, SS_COL_START_DATE, SS_COL_END_DATE,
    SS_COL_PRODUCT_FAMILY, SS_COL_LICENSE_TYPE,
    SS_COL_REGION, SS_COL_SUB_REGION,
    SS_COL_CONTACT_NAME, SS_COL_CONTACT_EMAIL,
    SS_COL_USE_CASE, SS_COL_MORPHEUS_VER,
    SS_COL_ON_PREM_HV, SS_COL_PUBLIC_CLOUD,
    SS_COL_USING_HVM, SS_COL_USING_K8S,
    SS_COL_APPROVED_SOCKETS,
    SS_COL_WEEKLY_STATUS, SS_COL_LAST_UPDATE,
    SS_COL_SE_PARTNER_NOTES,
    SS_ALLOWED_STATUSES,
)

logger = logging.getLogger(__name__)
SHEET_ID = int(SMARTSHEET_SHEET_ID) if SMARTSHEET_SHEET_ID else 0

_ALL_FETCH_COLS = [
    SS_COL_POC_ID, SS_COL_STATUS, SS_COL_PRODUCT_FAMILY, SS_COL_LICENSE_TYPE,
    SS_COL_CUSTOMER, SS_COL_SE_NAME, SS_COL_SE_EMAIL,
    SS_COL_REGION, SS_COL_SUB_REGION,
    SS_COL_CONTACT_NAME, SS_COL_CONTACT_EMAIL,
    SS_COL_START_DATE, SS_COL_END_DATE,
    SS_COL_USE_CASE, SS_COL_MORPHEUS_VER,
    SS_COL_ON_PREM_HV, SS_COL_PUBLIC_CLOUD,
    SS_COL_USING_HVM, SS_COL_USING_K8S,
    SS_COL_APPROVED_SOCKETS,
]


def _client() -> smartsheet.Smartsheet:
    client = smartsheet.Smartsheet(SMARTSHEET_API_KEY)
    client.errors_as_exceptions(True)
    return client


def _cell_value(row, column_id: int) -> Optional[str]:
    for cell in row.cells:
        if cell.column_id == column_id:
            val = cell.value
            if val is None:
                return None
            return str(val).strip()
    return None


def _parse_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return datetime.strptime(val[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _module_auto_detect(using_hvm: str, using_k8s: str, on_prem_hv: str) -> dict:
    """Auto-detect modules from Smartsheet flags."""
    hvm = False
    hks = False
    if using_hvm and using_hvm.lower() in ("yes", "currently evaluating"):
        hvm = True
    if on_prem_hv and "hpe hvm" in on_prem_hv.lower():
        hvm = True
    if using_k8s and using_k8s.lower().startswith("yes"):
        hks = True
    return {"hvm": hvm, "hks": hks, "terraform": False, "ansible": False}


def lookup_poc(poc_id: str, requester_email: str = "", is_admin: bool = False) -> Dict[str, Any]:
    """
    Look up a POC Reference ID in Smartsheet.
    requester_email: logged-in user's email. Used to determine if they're the assigned SE.
    is_admin: True for admin/master-admin users -- always gets full data.
    Returns is_owner=True if the requester matches the SE Email on that Smartsheet row.
    """
    if not SMARTSHEET_API_KEY:
        return {"found": False, "allowed": False, "reason": "Smartsheet API not configured"}

    try:
        client = _client()
        sheet = client.Sheets.get_sheet(SHEET_ID, column_ids=_ALL_FETCH_COLS)
    except Exception as e:
        logger.error(f"Smartsheet lookup error: {e}")
        return {"found": False, "allowed": False, "reason": "Could not connect to Smartsheet tracker"}

    for row in sheet.rows:
        row_poc_id = _cell_value(row, SS_COL_POC_ID)
        if row_poc_id and row_poc_id.upper() == poc_id.upper():
            status         = _cell_value(row, SS_COL_STATUS) or ""
            product_family = _cell_value(row, SS_COL_PRODUCT_FAMILY) or ""
            license_type   = _cell_value(row, SS_COL_LICENSE_TYPE) or "Standard License"
            customer       = _cell_value(row, SS_COL_CUSTOMER) or ""
            se_name        = _cell_value(row, SS_COL_SE_NAME) or ""
            region         = _cell_value(row, SS_COL_REGION) or ""
            sub_region     = _cell_value(row, SS_COL_SUB_REGION) or ""
            contact_name   = _cell_value(row, SS_COL_CONTACT_NAME) or ""
            contact_email  = _cell_value(row, SS_COL_CONTACT_EMAIL) or ""
            start_date     = _parse_date(_cell_value(row, SS_COL_START_DATE))
            end_date       = _parse_date(_cell_value(row, SS_COL_END_DATE))
            use_case       = _cell_value(row, SS_COL_USE_CASE) or ""
            morpheus_ver   = _cell_value(row, SS_COL_MORPHEUS_VER) or ""
            on_prem_hv     = _cell_value(row, SS_COL_ON_PREM_HV) or ""
            public_cloud   = _cell_value(row, SS_COL_PUBLIC_CLOUD) or ""
            using_hvm      = _cell_value(row, SS_COL_USING_HVM) or ""
            using_k8s      = _cell_value(row, SS_COL_USING_K8S) or ""
            approved_sockets = _cell_value(row, SS_COL_APPROVED_SOCKETS) or ""

            # For CONTACT_LIST columns, cell.value IS the email address (confirmed via API)
            # display_value is the contact name shown in UI ("Saravanan Arumugam")
            se_email_in_sheet = _cell_value(row, SS_COL_SE_EMAIL) or ""
            logger.debug(f"SE email from Smartsheet for {poc_id}: {se_email_in_sheet!r}")

            # Option B: strict email ownership check
            is_owner = is_admin  # admins always have full access
            if not is_owner and requester_email and se_email_in_sheet:
                is_owner = requester_email.lower() == se_email_in_sheet.lower()
                logger.debug(f"is_owner: {requester_email!r} vs {se_email_in_sheet!r} → {is_owner}")

            allowed = status in SS_ALLOWED_STATUSES
            reason  = ""
            if not allowed:
                reason_map = {
                    "New Submission": "This POC has not been approved yet. Wait for manager approval.",
                    "Rejected":       "This POC has been rejected. Contact your manager.",
                    "Blocked":        "This POC is currently blocked. Contact your manager.",
                    "Completed":      "This POC is already marked as Completed in the tracker.",
                }
                reason = reason_map.get(status, f"Status '{status}' does not allow Bible creation.")

            modules = _module_auto_detect(using_hvm, using_k8s, on_prem_hv)

            return {
                "found":           True,
                "allowed":         allowed,
                "status":          status,
                "reason":          reason,
                "row_id":          str(row.id),
                "is_owner":        is_owner,
                "se_email_sheet":  se_email_in_sheet,  # for debugging
                "customer_name":   customer,
                "product_family":  product_family,
                "license_type":    license_type,
                "se_name":         se_name,
                "region":          region,
                "sub_region":      sub_region,
                # Sensitive fields -- caller decides whether to expose based on is_owner
                "contact_name":    contact_name,
                "contact_email":   contact_email,
                "use_case":        use_case,
                # Non-sensitive technical fields
                "start_date":      start_date,
                "end_date":        end_date,
                "morpheus_version": morpheus_ver,
                "on_prem_hypervisors": on_prem_hv,
                "public_cloud_providers": public_cloud,
                "using_hvm":       using_hvm,
                "using_k8s":       using_k8s,
                "approved_sockets": approved_sockets,
                "modules_auto":    modules,
            }

    return {
        "found":   False,
        "allowed": False,
        "reason":  "POC ID not found in Smartsheet tracker. Check the ID with your manager.",
    }


def push_weekly_status(row_id: str, poc_id: str, customer_name: str, progress_text: str, sa_notes: str = "") -> bool:
    """Replace weekly status in Smartsheet. Also writes SE/Partner Notes column if provided."""
    if not SMARTSHEET_API_KEY or not row_id:
        return False
    try:
        client = _client()

        today = date.today().strftime("%d %b %Y")
        new_value = progress_text  # content already includes date in header

        row_update = smartsheet.models.Row()
        row_update.id = int(row_id)

        status_cell = smartsheet.models.Cell()
        status_cell.column_id = SS_COL_WEEKLY_STATUS
        status_cell.value = new_value
        row_update.cells.append(status_cell)

        date_cell = smartsheet.models.Cell()
        date_cell.column_id = SS_COL_LAST_UPDATE
        date_cell.value = date.today().strftime("%Y-%m-%d")
        row_update.cells.append(date_cell)

        if sa_notes and sa_notes.strip():
            notes_cell = smartsheet.models.Cell()
            notes_cell.column_id = SS_COL_SE_PARTNER_NOTES
            notes_cell.value = sa_notes.strip()
            row_update.cells.append(notes_cell)

        client.Sheets.update_rows(SHEET_ID, [row_update])
        logger.info(f"Weekly status pushed (replace) for {poc_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to push weekly status for {poc_id}: {e}")
        return False


def push_poc_status(row_id: str, poc_id: str, status_value: str) -> bool:
    """Push app completion status back to the Smartsheet Status column."""
    if not SMARTSHEET_API_KEY or not row_id:
        return False
    # Map app status to Smartsheet picklist values
    STATUS_MAP = {
        "completed": "Completed",
        "active":    "Approved",
        "extended":  "Extended",   # reopen with extension
    }
    ss_status = STATUS_MAP.get(status_value)
    if not ss_status:
        logger.warning(f"No Smartsheet status mapping for '{status_value}' — skipping push")
        return False
    try:
        client = _client()
        row_update = smartsheet.models.Row()
        row_update.id = int(row_id)
        status_cell = smartsheet.models.Cell()
        status_cell.column_id = SS_COL_STATUS
        status_cell.value = ss_status
        row_update.cells.append(status_cell)
        client.Sheets.update_rows(SHEET_ID, [row_update])
        logger.info(f"Status '{ss_status}' pushed to Smartsheet for {poc_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to push status for {poc_id}: {e}")
        return False


def sync_all_pocs_from_smartsheet() -> Dict[str, Any]:
    """Pull Status + End Date for ALL rows in one fetch. Returns { poc_id: {...} }"""
    if not SMARTSHEET_API_KEY:
        return {}
    try:
        client = _client()
        sheet = client.Sheets.get_sheet(SHEET_ID, column_ids=[SS_COL_POC_ID, SS_COL_STATUS, SS_COL_END_DATE])
        result = {}
        for row in sheet.rows:
            poc_id   = _cell_value(row, SS_COL_POC_ID)
            status   = _cell_value(row, SS_COL_STATUS) or ""
            end_date = _parse_date(_cell_value(row, SS_COL_END_DATE))
            if poc_id:
                result[poc_id.upper()] = {"status": status, "end_date": end_date, "row_id": str(row.id)}
        return result
    except Exception as e:
        logger.error(f"Smartsheet full sync error: {e}")
        return {}
