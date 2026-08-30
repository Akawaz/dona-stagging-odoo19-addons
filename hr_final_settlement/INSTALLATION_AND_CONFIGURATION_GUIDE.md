# Employee Final Settlement — Installation & Configuration Guide

Module: `hr_final_settlement` · Odoo 19.0 · Requires **Odoo Enterprise** (depends on `hr_payroll`)

This guide covers getting the module installed and configured for production use. It assumes
the module code is already in place at `custom-addons/hr_final_settlement` (see the codebase
if not).

---

## 1. Requirements

| Requirement | Why |
|---|---|
| Odoo 19.0 | Built against Odoo 19's `hr.version` architecture (no `hr.contract` model) |
| Odoo **Enterprise** edition | `hr_payroll` is an Enterprise-only module (license `OEEL-1`) |
| `hr` and `hr_holidays` (Community) | Employee/termination and Time Off data |
| `hr_employee_allowances` (optional) | If installed, its `transportation_allowance` / `housing_allowance` / `other_allowance` fields on `hr.version` are picked up automatically as extra salary components. Not required — the module works with just `wage` if it isn't installed. |

No Odoo core files are modified. Everything is added through standard inheritance.

---

## 2. Installation

1. Copy (or confirm) the module is present at:
   ```
   <odoo-root>/custom-addons/hr_final_settlement
   ```
2. Make sure `custom-addons` is listed in your `addons_path` (check `odoo.conf`).
3. Restart the Odoo server.
4. In Odoo, go to **Apps**, click **Update Apps List** (you may need to enable
   developer mode first: Settings → General Settings → scroll down → Activate the
   developer mode).
5. Search for **"Employee Final Settlement"** and click **Install**.
   Odoo will also install `hr_payroll` and `hr_holidays` automatically if they aren't
   already installed.
6. Once installed, you'll see a new **Final Settlements** menu under the **Payroll** app,
   and a new **Final Settlement** section under **Payroll → Configuration** (via
   Settings, see below).

That's it for installation — nothing works usefully yet until you complete the
configuration steps below.

---

## 3. Configuration

All configuration lives in one place: **Settings → Payroll** (or the gear icon on the
Payroll app) → scroll to the **Final Settlement** section. You need
`hr_payroll.group_hr_payroll_manager` (Payroll Administrator) to see and change these.

### 3.1 Required before anyone can calculate a settlement

| Setting | Field | What to set |
|---|---|---|
| **Annual Leave Time Off Type** | `fs_annual_leave_type_id` | The `hr.leave.type` record used for annual leave (e.g. "Annual Leave"). Calculation will hard-error with a clear message if this is empty. |
| **Final Settlement Salary Structure** | `fs_settlement_structure_id` | Pre-filled to the structure the module creates on install ("Final Settlement"). Leave as-is unless you have a reason to use a different one. |

If either is missing, the relevant action (Calculate, or Create Payslip) will raise a
clear `UserError` telling you exactly what to configure — it will not fail silently or
with a Python traceback.

### 3.2 Financial parameters — **must be reviewed by HR/Payroll/Legal before go-live**

These ship with defaults that mirror the Mr. Adel reference template's example, but are
**not** legal guarantees — confirm them for your jurisdiction/company before relying on
them for real settlements.

| Setting | Field | Default | Notes |
|---|---|---|---|
| **SIO Deduction Enabled** | `fs_sio_enabled` | On | Toggles the Social Insurance Organization deduction entirely. |
| **SIO Percentage** | `fs_sio_percentage` | 8.0 | Applied to the **Final Month Salary** only (not the full settlement). |
| **Daily Rate Calculation Basis** | `fs_daily_rate_method` | Monthly Salary / 30 | Options: Monthly Salary / 30, Basic Salary / 30, Basic + Allowances / 30. Drives the **Annual Leave Encashment** rate. |
| **Divisor** | `fs_daily_rate_divisor` | 30 | Used both for the daily rate above and for the Final Month Salary formula (`monthly salary ÷ divisor × worked days`). |
| **Annual Leave Calculation Method** | `fs_leave_calculation_method` | Odoo Time Off Balance | Only one method is implemented in this version — see §3.4. |

### 3.3 Report branding

| Setting | Field | Notes |
|---|---|---|
| **Employer CR / Registration Number** | `fs_employer_cr_number` | Shown under the company name on the report header and in the footer. Leave blank to omit. |
| **Settlement Authorized Representative** | `fs_authorized_representative_id` | A `res.users` record, tracked on the settlement's Clearance tab for internal record-keeping. |
| **Report Brand Color** | `fs_report_brand_color` | Hex color (default `#C0272D`) used for headings and table headers on the printed statement. |
| Company logo | `res.company.logo` (standard Odoo field, Settings → General Settings) | Shown top-left on every page of the report and repeats automatically via the running header. |

### 3.3b Legal section text — **must be reviewed by legal counsel before go-live**

The report's numbered legal sections (4–7) each pull from a company-configurable Html
field, falling back to sensible generic wording if left empty. None of this is a legal
guarantee — it's a working draft, same as the reference template it's based on.

| Setting | Field | Section on the report |
|---|---|---|
| **Mutual Release Text** | `fs_report_release_text` | 4. Mutual Release and Discharge |
| **Return of Company Property Text** | `fs_report_property_return_text` | 5. Return of Company Property |
| **Continuing Obligations Text** | `fs_report_continuing_obligations_text` | 6. Continuing Obligations |
| **Governing Law Text** | `fs_report_governing_law_text` | 7. Governing Law |

### 3.4 Annual Leave Calculation Method — what "Odoo Time Off Balance" means

The module reads the employee's **real, approved** Time Off allocations and leaves via
`hr.leave.type.get_allocation_data()`, evaluated **as of the settlement's Last Working
Date** — not "today", and not a naive manual entry. This means:

- Allocations that start after the Last Working Date are correctly excluded.
- Only **validated/approved** leave is counted (not pending requests), matching the
  spec's "approved leave" requirement.
- If HR needs a different balance for a specific case, they don't edit this number
  directly — they override the **Annual Leave Encashment line** on the Settlement tab
  (with a mandatory reason, and the original system-calculated value is preserved for
  audit).

The template's alternate "2.5 days × months of service" method and a hybrid
Odoo+service-adjustment method were intentionally **not built** in this version — only
add them if HR actually needs them later; the `fs_leave_calculation_method` field is
already in place as the extension point.

### 3.5 Require Final Settlement Before Archive

| Setting | Field | Default |
|---|---|---|
| **Require Final Settlement Before Archive** | `fs_require_settlement_before_archive` | Off |

When **off** (default), standard Odoo archiving behavior is completely untouched.

When **on**: an employee cannot be archived — via the Employees list, the employee form,
or the standard Employee Termination wizard's **Apply** button — until a Final
Settlement for that employee has reached the **Finalized** state. HR must use **"Go to
Final Settlement"** instead of Apply. This is enforced at the single Odoo 19 chokepoint
(`hr.employee.action_archive()`), so it can't be bypassed by a different button or menu.

---

## 4. Security groups

Two groups are created (Settings → Users & Companies → Groups, or via **Access Rights**
on a user form under "Final Settlement"):

| Group | Can do |
|---|---|
| **User: Prepare Settlements** | View, create, calculate, and submit settlements for review. Cannot approve, override, create payslips, or finalize. |
| **Manager: Approve, Override & Finalize** | Everything above, plus Approve, Create Payslip, Finalize, and Reopen a finalized/approved settlement for correction. |

Assign these on top of the normal `hr.group_hr_user` / `hr_payroll.group_hr_payroll_user`
groups a person already needs to see employees and payslips.

---

## 5. Verifying the setup

A quick smoke test after configuration:

1. Open an employee record → **Archive** (or use the Employees list's Archive action).
2. In the Employee Termination wizard, fill in the departure reason and date, then click
   **Go to Final Settlement** (next to the normal Apply button).
3. The employee stays **active**, and a new Final Settlement record opens.
4. Click **Calculate**. If leave type / salary structure are configured correctly, you'll
   see Service Information, Salary, and Annual Leave tabs populate, and the Settlement
   tab show Final Month Salary, Annual Leave Encashment, and (if enabled) the SIO
   deduction line.
5. Submit for Review → Approve → Create Final Settlement Payslip → validate the payslip
   → Finalize. The **Archive Employee** button appears once Finalized.
6. Use the print button (top of the form) to generate the **Final Payment Settlement
   Statement** PDF and confirm the logo, brand color, and figures match expectations.

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Annual Leave Time Off Type has not been configured" | Set §3.1's leave type, or set it directly on the settlement record before calculating. |
| "The Final Settlement Salary Structure has not been configured" | Set §3.1's structure. |
| "No active contract record (hr.version) was found for..." | The employee has no `hr.version` record with data — check the employee's Contract/HR Settings tab. |
| Annual Leave Balance shows 0 unexpectedly | Check the allocation's **Start Date** — allocations starting *after* the settlement's Last Working Date are correctly excluded from the balance (this is deliberate, not a bug). |
| "An existing payslip... covers part or all of the final settlement period" | Another payslip already exists for that employee/period. Review or cancel it before creating the Final Settlement payslip — the module deliberately refuses to create a second payment for the same period. |
| "A Final Settlement Payslip already exists for this settlement" | Use **View Payslip** instead — one settlement can only ever have one payslip. |
| Employee can't be archived, error mentions Final Settlement | §3.5's "Require Final Settlement Before Archive" is on and no Finalized settlement exists yet for that employee — use "Go to Final Settlement" and complete the workflow, or turn the setting off if that's not the intended process. |
| "Only a Final Settlement Manager can reopen a settlement" | The acting user needs the **Manager** group (§4), not just **User**. |
| Multiple employees selected for termination | The module creates **one settlement per employee** automatically (never merges them) and opens a list view instead of a single form when more than one was created/found. |
| Company logo missing on the printed PDF | Set it under Settings → General Settings → Companies, or directly on the company record. No logo means the header area is simply left blank. |

---

## 7. What is intentionally *not* included in this version

So nothing is mistaken for an oversight:

- **End of Service / Gratuity (Indemnity) is not calculated.** The report's Final
  Settlement Breakdown table *does* show an "Indemnity / gratuity (if applicable)" row
  (per the current reference template), but its amount always reads "—" with a note
  that it isn't yet enabled — no invented Bahrain Labour Law 36/2012 formula is applied.
  The data model already has a reserved `eos` line category and a `_calculate_end_of_service()`
  stub as the extension point; wiring in a real amount requires the confirmed formula
  (tiered days-per-year, minimum service, termination-reason applicability, any cap) from
  HR/payroll/legal before it can be built.
- **The printed report is the English "Final Settlement & Mutual Release Statement"
  layout** (numbered legal sections — Parties, Employee & Employment Information, Final
  Settlement Breakdown, Mutual Release, Return of Company Property, Continuing
  Obligations, Governing Law, Payment Details, Signatures — plus the company-branded
  header/footer). Two earlier layouts (an Arabic legal-agreement version, then an
  English payment-statement version) were built and then superseded per later structural
  references; only the QWeb report template changed each time — the calculation engine
  underneath has been untouched since it was first built. Adding another
  language/layout later is a new QWeb template against the same settlement fields, not a
  rewrite of the calculation engine.
- **Service-based (2.5 days/month) and hybrid leave calculation methods** — only the real
  Odoo Time Off Balance method is implemented; see §3.4.
- **Page numbering in the report footer** was deliberately left out. Odoo's `Page X of Y`
  mechanism (`<span class="topage"/>`) requires wkhtmltopdf to run a second rendering
  pass to count total pages, and that reliably hung indefinitely in this environment's
  header/footer sub-render step. A plain footer disclaimer line is used instead. If you
  want page numbers back, test `<span class="page"/> of <span class="topage"/>` in
  `report/hr_final_settlement_report_templates.xml` against your actual server first.
