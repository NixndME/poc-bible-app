# Legacy POC Migration Plan

**Move** `POC Tracker (Deprecated - Utilize Aswath)` (`1749909477740420`, ~159 rows, 52 cols)
**into** `HPE Morpheus POC Tracker` (`6280689621094276`, 87 cols).

**Goal:** one sheet holding old + new POCs, no meaningful data lost, junk removed,
and the dashboard able to show old vs new. **This is a plan only — nothing has
been changed.**

---

## 1. The core challenge

The two sheets are different *kinds* of tracker:
- **Legacy** = a lightweight sales-pipeline log (status, dates, win/loss, GEO).
- **New** = a detailed intake + live approval engine (sockets, hypervisors,
  automations, region/product approver routing).

So this is an **archive import**, not a merge: we bring the ~20 meaningful legacy
fields across, tag the rows as "Legacy", and accept that the other ~60 new-tracker
fields stay blank for old rows. Crucially, the new tracker has **live automations
and DataMesh** that must be paused during import or they will fire on 159 old POCs.

---

## 2. Field mapping — what MOVES

| Legacy column | → New tracker column | Transform |
|---------------|----------------------|-----------|
| Account Name | Customer Name | direct |
| Product | Product Family | Enterprise→HPE Morpheus Enterprise; Advanced→HPE Morpheus Advanced; Essentials / Essentials Trial→HPE Morpheus VM Essentials |
| Owner SE (contact) | SE Name + SE Email | use the contact's name + email |
| Status | Status (+ Outcome) | see §3 — lossy, mapped |
| Start Date | Start Date | direct |
| Actual End Date (fallback Current → Planned) | **Legacy End Date** (new helper col) | Expected End Date is a formula, so historical end dates need their own column |
| Request Creation Date | Submission Date | direct (also fixes the otherwise-blank Submission Date) |
| Last Status Update | Latest Update Date | direct |
| Status Update | Weekly Status Update | direct |
| Business Objective | Business Justification | direct |
| Customer Use Cases (+ Technical Objectives) | Use Case Description | concatenate |
| POC Success Criteria | Success Criteria | direct |
| Industry | Industry | re-map values (lists differ) |
| GEO | Region | map to 5 regions — see §3 (lossy) |
| Customer Country | Sub-Region | direct (also used to refine Region) |
| Requires HVM (checkbox) | Using HPE HVM? | true→"Yes" |
| Notes | Internal Notes | direct |
| Win/Loss Reason | Lessons Learned | direct |
| Denied Reason | Rejection Reason / Internal Notes | direct |
| Opportunity Value | Deal Size / Budget (bucketed) or Internal Notes | bucket $ into bands, else keep raw in notes |

## 3. Value transforms

**Status** (legacy → new). New options: New Submission, Pending Review, Approved,
Extended, Completed, Rejected, Declined, Blocked.
| Legacy | New Status | Outcome |
|--------|-----------|---------|
| Completed - Won | Completed | (record "Won" in Outcome/Lessons) |
| Completed - Lost | Completed | (record "Lost") |
| Cancelled | Completed | (record "Cancelled") |
| Approved | Completed (archived) | — |
| In Progress / Waiting on Customer / At Risk / Blocked | Completed (archived) | original status → Internal Notes |

> Recommendation: map **everything to a terminal "Completed"** so no legacy row
> enters the live approval flow, and stash the original legacy status in Internal
> Notes so nothing is lost. (Alternative: keep mapped statuses — but then they
> show up in operational views; not advised.)

**Product:** Morpheus Enterprise→HPE Morpheus Enterprise; Advanced→HPE Morpheus
Advanced; Essentials & Essentials Trial→HPE Morpheus VM Essentials.

**GEO → Region** (lossy — this is the weakest mapping):
| GEO | Region |
|-----|--------|
| APAC, India, Japan | Asia Pacific |
| NA, LASER | Americas |
| Central, NWE | Europe |
| UKIMEA | Europe* |

\*UKIMEA spans UK + Ireland + Middle East + Africa, so **prefer deriving Region
from `Customer Country`** (more accurate) and use GEO only as a fallback. E.g.
country in Africa → Africa; Gulf states → Middle East; UK/EU → Europe.

**Industry:** map legacy values to the new picklist (most overlap; e.g. Financial
Services→Financial Services / Banking; "Hospitality & Travel"/"Aerospace & Defense"
→ Other if no match).

## 4. Fields NOT moved (low value / derived / no home)

Request ID, Opp ID *(you chose to drop both)*, Base Days, Number of Extensions,
Total Duration, Last Modified, Days Since Update, Days to Approve, Hours to
Approve, Request #, Row Created Date (all derived/system) · Opportunity Size,
Scope, Pain Points, Account Type, Derived Sub-Territory, Expected Opp Close Date,
the 3 "Suggested … SE" columns, Licenses Issued, Approved Date, Created By,
Requested By, Requested Start Date, Duration, Partner Contact, Customer State.

(If any of these matter to you, say so — Pain Points/Scope can fold into Use Case,
Opp Value into a deal band, etc.)

## 5. Helper columns to ADD to the new tracker

| Column | Type | Why |
|--------|------|-----|
| **Record Source** | Picklist (Live / Legacy) | tag every imported row "Legacy"; lets the dashboard and filters separate old vs new |
| **Legacy End Date** | Date | hold the historical end date (Expected End Date is a formula) |
| **POC Year** | Text/Date (from Start Date) | lets management slice the dashboard by year |

## 6. Junk to drop before import

- 2 rows with Account Name "asdfasdfasdf"
- 1 row with a blank Account Name
- → import ~156 real rows.

---

## 7. The SAFE import procedure (order matters)

1. **Add the 3 helper columns** (Record Source, Legacy End Date, POC Year). *(API — I can do)*
2. **Pause the live engine** so old rows don't trigger anything: *(UI / agent)*
   - Turn **OFF all ~16 workflows** (or at minimum: Auto-set Status, Notify SA on
     New Submission, POC Approval Request, Approval Fallback).
   - Set **DataMesh** Execution Frequency to **None** (or just don't let it run).
3. **Transform + import** the ~156 rows with: Customer Name, Product Family, SE
   Name/Email, **Status = Completed**, Start Date, Legacy End Date, Region,
   Sub-Region, Industry, Use Case, Business Justification, Success Criteria,
   Internal Notes (incl. original status), Weekly Status Update, Submission Date,
   Outcome/Lessons, **Record Source = Legacy**, POC Year. **Leave Approver Contact
   blank.** *(API — I can do, in batches)*
4. **Verify**: row count (~156 legacy + existing live), spot-check 10 rows, confirm
   no legacy row has Status "New Submission".
5. **Re-enable** workflows + restore DataMesh to **1 hour**. *(UI / agent)*
   - Safe because every legacy row is "Completed" (won't hit the New-Submission or
     Approved/Extended automations) and has past dates (date triggers won't fire).
6. **Keep the legacy sheet** as a backup until you've confirmed the import. Don't
   delete it.

---

## 8. Dashboard — showing old vs new

The dashboard reads the **POC Dashboard Metrics** sheet, whose cells are
cross-sheet `COUNTIF` formulas over the tracker. Once legacy rows are in the
tracker, those formulas would count **old + new together** — inflating your
current KPIs. To get a clean "old vs new" view:

- **Make current KPIs Live-only:** change the existing metric formulas from
  `COUNTIF(Status…)` to `COUNTIFS(Status…, Record Source = "Live")`.
- **Add a parallel set of metrics** for Legacy / All-time (same formulas filtered
  to `Record Source = "Legacy"` or unfiltered), and/or **by POC Year**.
- **Add dashboard widgets** for the historical/all-time view (a second section or
  a toggle).

> This is the one part that needs real metrics + dashboard rework. Decide what
> management actually wants to see: (a) current operations only, (b) all-time
> totals, (c) year-by-year, or (d) a split "Live vs Legacy". That choice drives
> how many new metric rows + widgets we build.

---

## 9. What NOT to do (important)

- **Do NOT import with automations or DataMesh active** — 159 old POCs would fire
  acknowledgment + approval emails and route approvals to managers. Email storm.
- **Do NOT give any legacy row Status "New Submission"** — it would enter the live
  approval flow. Use "Completed".
- **Do NOT try to write** POC Reference ID (auto-number), Expected End Date,
  Lookup Key, Approver Match, Reminder 10d, or Total Sockets (all formula/auto) —
  they're computed. Legacy rows get fresh POC IDs automatically.
- **Do NOT count legacy rows in current KPIs** without the Record Source filter, or
  your live dashboard numbers jump overnight.
- **Do NOT import the 3 junk rows.**
- **Do NOT delete the legacy sheet** until the import is verified.
- **Do NOT expect historical end dates in Expected End Date** — they go in Legacy
  End Date.

---

## 10. Who does which part

| Task | How |
|------|-----|
| Add helper columns; transform + import rows; set Record Source | **Me, via API** |
| Turn workflows off/on; pause/restore DataMesh | **You / Chrome agent (UI)** |
| Metrics-sheet formula edits | Me via API (cross-sheet ranges may need a UI touch) |
| Dashboard widgets for old vs new | **You / Chrome agent (UI)** |

---

## 11. Decisions I need from you before building

1. **Status mapping:** map *all* legacy rows to "Completed" (recommended, keeps
   them out of live flow) — yes/no?
2. **Region accuracy:** derive Region from `Customer Country` where possible
   (better) vs. straight GEO mapping (simpler but lossier on UKIMEA)?
3. **Dashboard view** management wants: current-only / all-time / by-year /
   live-vs-legacy split (pick one or more).
4. **Confirm drops:** Request ID + Opp ID dropped (you said yes). Any of the §4
   "not moved" fields you actually want kept?

Once you answer these four, I'll do the column adds + the transformed import (with
automations paused), and spec the dashboard segmentation.
