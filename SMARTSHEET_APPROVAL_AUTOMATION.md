# HPE Morpheus POC Tracker — Approval & Notification Automation

End-to-end reference for the Smartsheet POC approval workflow: sheets, columns,
approver routing, and every automation. This is the source of truth — read this
when something breaks or when onboarding a new admin.

> **Note on scope:** this documents the *Smartsheet* side (intake, approval
> routing, notifications). It is separate from the POC Bible web app.

---

## 1. Architecture at a glance

```
SE submits POC (form / row)                Managers maintain their own emails
        │                                  in "Regions & Managers" sheet
        ▼                                          │
HPE Morpheus POC Tracker  ◄──── DataMesh (hourly) ─┘
  • Lookup Key = Region|Product   copies "Approvers" → "Approver Contact"
  • Approver Contact (managers)         by matching Lookup Key
        │
        ├─► Automations fire on Status changes / dates
        │     → emails to SE Email + Approver Contact
        ▼
  POC Dashboard Metrics sheet ──► Dashboard (cross-sheet COUNTIF metrics)
```

**Routing is sheet-driven.** To change who approves a Region+Product, a manager
edits ONE cell in *Regions & Managers*; DataMesh propagates it to every POC
within the hour. Nothing is hardcoded in any workflow.

**Timing:** the SE acknowledgment is instant. The approver's email follows once
DataMesh populates the approver on the new row — within up to 1 hour (DataMesh's
fastest native cadence; true sub-hour would require a script, which is out of
scope).

---

## 2. Sheets

| Sheet | ID | Role |
|-------|----|------|
| HPE Morpheus POC Tracker | `6280689621094276` | Main intake + lifecycle + automations |
| Regions & Managers | `4489386979708804` | Approver source of truth (managers edit here) |
| POC Dashboard Metrics | `6564353554730884` | Key/value metrics (cross-sheet formulas) → dashboard |
| DataMesh config | "Approver Sync — Managers → POC Tracker" | Copies approvers into the tracker hourly |

---

## 3. Regions & Managers (the approver source)

4 columns. Managers maintain row by row, one row per Region + Product.

| Column | Type | Purpose |
|--------|------|---------|
| Region | Text | Asia Pacific / Americas / Europe / Africa / Middle East |
| Product | Text | HPE Morpheus Enterprise / Advanced / VM Essentials |
| Lookup Key | Text | `Region\|Product` — the match key DataMesh uses |
| **Approvers** | **Multi Contact** | **All managers for that Region+Product. THIS is what you edit to add/remove approvers.** |

15 rows = 5 regions × 3 products. A cell can hold multiple managers
(e.g. Americas | VM Essentials = Matt Haron + Alex Irizarry).

**To add/remove an approver:** open this sheet, find the Region+Product row, add
or remove people in the `Approvers` cell. Done. (Propagates within ~1 hour.)

---

## 4. POC Tracker — columns that drive automation

The tracker has ~80 intake fields (customer, sockets, hypervisors, etc.). The
columns that matter for approval/notification routing are:

| Column | Type | Purpose |
|--------|------|---------|
| Status | Picklist | New Submission / Approved / Extended / Completed / Rejected / Blocked — drives most triggers |
| Region | Picklist | part of the lookup key |
| Product Family | Picklist | part of the lookup key |
| SE Email | Contact | the requestor; recipient of every SE-facing email |
| **Lookup Key** | Text (formula) | `=Region \| Product Family` — match key for DataMesh |
| **Approver Contact** | **Multi Contact** | filled by DataMesh from `Approvers`; recipient of all manager emails |
| **Approver Match** | Text (formula) | `OK` if the Region+Product has a manager, else `UNMATCHED` — drives the fallback |
| Expected End Date | Date (formula) | Start + 45 (+45 if Extended) — basis for expiry reminders |
| **Reminder 10d** | Date (formula) | `Expected End Date − 10` — trigger date for the 10-day reminder |
| Last Modified | System (Modified By) | renamed from "Approved By"; shows last editor, not the approver |

Helper columns added for this design: `Lookup Key`, `Approver Match`,
`Reminder 10d`. `Approver Contact` was converted to Multi Contact.

---

## 5. DataMesh config — "Approver Sync — Managers → POC Tracker"

| Setting | Value |
|---------|-------|
| Source | Regions & Managers |
| Target | HPE Morpheus POC Tracker |
| Match | Source `Lookup Key` = Target `Lookup Key` |
| Copy | Source `Approvers` → Target `Approver Contact` |
| Data Mapping Format | **Copy Data** (never inserts rows into the tracker) |
| Overwrite existing | Yes |
| Execution Frequency | **1 hour** |

"Update Immediately" was rejected because it only watches the *source* sheet and
never fires on new tracker rows. "1 hour" re-scans all rows, so new POCs get
their approver within the hour.

---

## 6. Automation inventory

Status legend: ✅ live & correct · ⏳ to finish · 🔲 to build

### Utility (no email)
| Workflow | Trigger | Action |
|----------|---------|--------|
| Auto-set Status on New Submission ✅ | Row added, Status blank | Set Status = "New Submission" |
| Set Start Date on Approval ✅ | Status → Approved | Record Start Date = today |
| Stamp Latest Update Date ✅ | Weekly Status Update changes | Record Latest Update Date |

### Submission (Ask 1)
| Workflow | Trigger | Recipients | Purpose |
|----------|---------|-----------|---------|
| Notify SA on New POC Submission ✅ | Row added | **SE Email** | Requestor acknowledgment |
| POC Approval Request ✅ | `Approver Contact` changes AND Status = New Submission | **Approver Contact** (save response → Status) | Approver gets the new-submission / approve-decline email, routed by region+product |
| Approval Fallback - Unmatched ✅ | Status → New Submission AND `Approver Match` = UNMATCHED | **aswath@hpe.com** | Catch-all when no manager is mapped |

### Lifecycle (Ask 2) — all send to SE Email + Approver Contact
| Workflow | Trigger | Status |
|----------|---------|--------|
| Notify SE on POC Approval ✅ | Status → Approved | ✅ |
| Notify SE on POC Rejection ✅ | Status → Rejected | ✅ |
| Notify SE on POC Extension ✅ | Status → Extended | ✅ |
| Alert Manager on POC Blocked ✅ | Status → Blocked | ✅ |
| Notify SE on POC Completion ✅ | Status → Completed | ✅ (bonus) |

### Expiry reminders (Ask 3) — all send to SE Email + Approver Contact, condition Status in (Approved, Extended)
| Workflow | Trigger | Status |
|----------|---------|--------|
| POC License Expiring in 10 Days ✅ | On `Reminder 10d` (= expiry − 10) at 9:00 AM | ✅ |
| POC License Expiring in 7 Days ✅ | 1 week before Expected End Date | ✅ |
| POC License Expiring in 5 Days ✅ | 5 days before Expected End Date | ✅ |
| POC License Expiring in 3 Days ✅ | 3 days before Expected End Date | ✅ |
| POC License Expired ✅ | On Expected End Date | ✅ |

---

## 7. Mapping to the three requirements

**1. SE fills the tracker → requestor ack + approver notified.**
`Notify SA on New POC Submission` (SE Email, instant) + `POC Approval Request`
(Approver Contact, routed by region+product, ≤1 hr) + fallback to aswath. ✅

**2. Approve / blocked / extension / reject → approver + SE both emailed.**
The five lifecycle workflows above, each to SE Email + Approver Contact. ✅

**3. Expiry reminders at 10 / 7 / 5 / 3 days + expired → approver + SE.**
Five date-based workflows, all live (SE Email + Approver Contact, condition
Status in Approved/Extended). ✅

---

## 8. Remaining build — agent prompts

(Run in the Chrome agent — automations can't be edited via API.)

### Finish the 10-day reminder
```
Open the duplicated workflow "POC License Expiring in 10 Days - Reminder".
Trigger: "When a date is reached" → On the date in column "Reminder 10d" → 9:00 AM.
Condition: Status is one of "Approved","Extended".
Recipients: SE Email + Approver Contact.
Edit subject/body wording from "7 days" to "10 days". Show me before saving.
```

### Build 5-day, 3-day, and Expired
```
In Manage Workflows, for each of the three below: open
"POC License Expiring in 7 Days - Reminder" → 3-dot → Duplicate, then set the
name, trigger, and wording. Keep condition (Status is one of Approved, Extended)
and recipients (SE Email + Approver Contact). Show me each before saving.

A) Name: POC License Expiring in 5 Days - Reminder
   Trigger: 5 days before "Expected End Date" at 9:00 AM. Wording: "5 days".
B) Name: POC License Expiring in 3 Days - Reminder
   Trigger: 3 days before "Expected End Date" at 9:00 AM. Wording: "3 days".
C) Name: POC License Expired
   Trigger: "When a date is reached" → On "Expected End Date" at 9:00 AM.
   Wording: change to "has expired today".
```

---

## 9. Verification prompt (re-dump automations to confirm)

```
Smartsheet → HPE Morpheus POC Tracker → Automation → Manage Workflows (READ-ONLY,
do not change anything). For EVERY workflow, report: name, on/off, trigger,
condition, action, recipients, and email subject. List them all so I can confirm
the live state matches the documented set.
```

---

## 10. How approval actually flows (runbook)

1. SE submits → row added → `Auto-set Status` sets Status = New Submission.
2. `Notify SA on New POC Submission` emails the SE instantly (acknowledgment).
3. Within ≤1 hr, DataMesh writes the region+product managers into `Approver
   Contact`. That change fires `POC Approval Request` → managers get the
   approve/decline email. (If no manager mapped → `Approval Fallback` → aswath.)
4. A manager clicks Approve/Decline → response saved to Status. Smartsheet writes
   **"Pending Review"** while awaiting the decision, then **"Approved"** on approve
   or **"Declined"** on decline. (These are Smartsheet-generated values; "Pending
   Review", "Declined" and the picklist options are all valid Status values.)
   NOTE: the Rejection notification must trigger on **"Rejected" OR "Declined"**,
   since the Decline button writes "Declined", not "Rejected".
5. Status change fires the matching lifecycle email (Approval / Rejection /
   Extension / Blocked / Completion) → SE + managers.
6. As expiry nears, the 10/7/5/3-day and Expired reminders fire → SE + managers.

**Adding an approver later:** edit the `Approvers` cell in *Regions & Managers*.
That's the only step.
