# Microsoft Power BI Connector for Odoo 19

Synchronizes **Sales** (`sale.order` + `sale.order.line`) and **Expenses**
(`hr.expense`) from Odoo into Microsoft Power BI, using a Microsoft Entra ID
service principal and the Power BI REST API's **push datasets**.

---

## 1. Architecture — what this module does and why

```
Odoo (sale.order, sale.order.line, hr.expense)
        |
        |  read + transform (services/powerbi_sales_service.py,
        |                     services/powerbi_expense_service.py)
        v
PowerBISyncService  (services/powerbi_sync_service.py)
        |
        |  ensure dataset/tables exist, push/clear rows
        v
PowerBIDatasetService (services/powerbi_dataset.py)
        |
        v
PowerBIClient  --(Bearer token)-->  PowerBIAuth
        |                                |
        |  HTTPS REST calls              |  OAuth2 client-credentials grant
        v                                v
https://api.powerbi.com/v1.0/myorg   https://login.microsoftonline.com/{tenant}
        |
        v
Power BI Workspace -> Push Dataset -> Tables (Sales, SalesLines, Expenses)
        |
        v
Power BI Desktop / Service: build reports and dashboards on top
```

### Why service-principal + push datasets

Microsoft's Power BI REST API is documented at
[learn.microsoft.com/rest/api/power-bi](https://learn.microsoft.com/en-us/rest/api/power-bi/).
For an unattended, server-to-server integration (no interactive user, no
browser), Microsoft's current, supported pattern is:

* **Auth**: a Microsoft Entra ID app registration used as a *service
  principal*, authenticating with the OAuth 2.0 **client-credentials** grant
  against `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`,
  scope `https://analysis.windows.net/powerbi/api/.default`. No delegated
  Graph/Power BI API permissions need to be added to the app registration
  itself — Microsoft's own guidance is to *avoid* adding permissions there,
  since access is instead granted at the Power BI tenant/workspace level
  (see Section 2 below). Reference: [Embed with service principal](https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal).
* **Data delivery**: **push datasets** (`defaultMode: "Push"`), the only
  Power BI REST API surface that lets a server insert rows directly with no
  on-premises gateway, no Power BI Desktop `.pbix` publish step, and no
  interactive sign-in. Reference: [Push Datasets — PostRows](https://learn.microsoft.com/en-us/rest/api/power-bi/push-datasets/datasets-post-rows),
  [PostDatasetInGroup](https://learn.microsoft.com/en-us/rest/api/power-bi/push-datasets/datasets-post-dataset-in-group).

Alternatives considered and rejected for a same-day, code-only integration:
Dataflows and semantic-model/XMLA write endpoints require Power BI
Premium/Fabric capacity and a much larger setup; streaming/PubNub datasets
don't support a queryable table backing real reports; import via `.pbix`
requires Power BI Desktop and a manual publish step, defeating "automatic
synchronization."

### The one real limitation this creates: no row-level update or delete

Push dataset tables support exactly two write operations:

* `POST /datasets/{id}/tables/{table}/rows` — **append** rows.
* `DELETE /datasets/{id}/tables/{table}/rows` — **clear all rows** in that table.

There is **no** "update row 42" or "delete row 42" call. This module's
sync modes are built around that constraint, not around it:

* **Full Sync** clears each enabled table, then re-inserts every matching
  record. Always correct, always de-duplicated, costs more API calls/time.
* **Incremental Sync** (used by "Sync Now" and the automatic cron) only
  *appends* rows for records whose `write_date` is at or after the
  connection's last successful sync for that data type. If an
  already-synced Odoo record is edited again, incremental sync will add a
  **new** row for it in Power BI rather than replacing the old one — the
  push dataset API has no way to do an in-place update.

**Practical implication:** if your Power BI reports must always reflect the
latest state of every record (not just "what changed"), run **Full Sync**
periodically (e.g. nightly) to rebuild each table cleanly, and use
Incremental/automatic sync for near-real-time additions in between. This is
a genuine constraint of the Power BI push-dataset API, not a shortcut taken
here — it is documented so it is not mistaken for a bug.

Every synchronized row carries `OdooId` and `OdooModel` columns so that, if
you additionally enable a periodic Full Sync, Power BI's table is always
reconcilable back to its Odoo source record.

---

## 2. MANUAL ACTION REQUIRED — Microsoft / Power BI setup

None of this can be automated from Odoo or from this development
environment: it requires interactive access to the Azure/Entra admin center,
the Power BI admin portal, and a Power BI workspace, using an account with
the right admin rights. Do this once per environment (dev/test/prod each
need their own service principal + workspace, or can share one for a demo).

### Step 1 — Register a Microsoft Entra ID application

1. Go to **portal.azure.com** → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Name it (e.g. `Odoo Power BI Connector`), leave redirect URI blank, **Register**.
3. On the app's **Overview** page, copy the **Application (client) ID** and
   the **Directory (tenant) ID** — these go into Odoo as *Client ID* and
   *Tenant ID*.
4. Go to **Certificates & secrets** → **New client secret**. Copy the
   **secret value** immediately (it is shown once) — this is the *Client
   Secret* for Odoo.
5. Do **not** add API permissions on this app registration. Power BI access
   is granted via the tenant/workspace settings below, not via Entra API
   permissions — adding them here does nothing for Power BI and can cause
   confusing, unrelated consent errors.

### Step 2 — Create a Microsoft Entra security group (recommended)

1. **Microsoft Entra ID** → **Groups** → **New group** → Security group,
   e.g. `PowerBI-ServicePrincipals`.
2. Add the app's service principal as a member (search by the app's display
   name under **Enterprise applications**, not under regular users).
   *(You can skip this and enable the tenant setting for the whole
   organization instead — simpler for a demo, less scoped for production.)*

### Step 3 — Enable service-principal API access in Power BI

1. Go to **app.powerbi.com** → gear icon → **Admin portal** → **Tenant settings**.
2. Under **Developer settings**, enable **"Allow service principals to use
   Power BI APIs"** — scope it to the security group from Step 2 (or to the
   whole organization for a quick demo).
3. This step requires **Power BI admin** rights (Fabric/Power BI
   administrator role), not just a workspace admin.

### Step 4 — Create (or choose) a Power BI workspace

1. In Power BI, create a **new workspace** (not "My workspace" — service
   principals cannot access "My workspace").
2. Open the workspace → **Access** → add the app's service principal (or
   the security group from Step 2) as **Member** or **Admin**.
3. Copy the **Workspace ID** from the URL
   (`app.powerbi.com/groups/{workspace-id}/...`) — this goes into Odoo.

### Step 5 — Enter the values into Odoo

Odoo → **Power BI → Configuration → Power BI Connections → New**:

| Field | Value |
|---|---|
| Connection Name | e.g. `Main Power BI` |
| Tenant ID | from Step 1 |
| Client ID | from Step 1 |
| Client Secret | from Step 1 |
| Workspace ID | from Step 4 |
| Dataset Name | any name, e.g. `Odoo Sales & Expenses` — the dataset and its `Sales`/`SalesLines`/`Expenses` tables are created automatically on first sync |
| Dataset ID | leave blank on first setup — Odoo fills it in automatically |

Save, then click **Test Connection**.

---

## 3. Installing the module in Odoo

```bash
# from the Odoo root, with the venv that has psycopg2 + requests active
./odoo-bin -c odoo.conf -d <your_database> -i powerbi_connector
```

Or, in the Odoo UI: **Apps** → remove the "Apps" filter → search
"Power BI Connector" → **Install**. `requests` (already an Odoo core
dependency) is the only Python package used; no `msal` or other new
dependency is required since the client-credentials grant is a single
`POST` that the standard-library-friendly `requests` handles directly.

After install, two groups exist: **Power BI User** (read-only: status,
logs) and **Power BI Administrator** (full configuration, Test Connection,
Sync Now, Full Sync). Assign at least one user to **Power BI
Administrator** under Settings → Users before trying to configure a
connection.

---

## 4. Testing the connection

**Power BI → Configuration → Power BI Connections → (your connection) →
Test Connection.**

On success:
```
Microsoft authentication: OK
Workspace access: OK
Dataset access: SKIPPED (no dataset created yet - it will be created
automatically on first sync)
```

On failure, you get a sticky red notification (not a blocking error dialog)
that tells you exactly which step failed and why, e.g.:
```
Microsoft authentication: OK
Workspace access: FAILED
Reason: The service principal cannot see workspace <id>. Either the
Workspace ID is wrong, or the service principal (or its security group)
has not been added as a Member/Admin of that workspace.
```
This result is also saved on the connection (`Last Test Result`,
`Connection Status`), so you can review it later without re-running the
test. Test Connection deliberately never raises a blocking error for a
*failed* connection attempt: an earlier version of this module raised
`UserError` on failure, but that rolls back the whole database
transaction together with the exception in real Odoo request handling —
which silently discarded the diagnostic message it had just written. This
was caught by this module's own tests (run against a real Odoo 19
instance, not just reviewed by eye) and fixed by returning a notification
instead, the same pattern already used for sync-failure reporting.

A synchronization is only ever reported "successful" if Power BI's API
actually returned a success status for that call — there is no simulated
or assumed success anywhere in this module.

---

## 5. Manual synchronization

**Power BI → Configuration → (connection) → Sync Now** opens a wizard:
choose Sales/Expenses, Incremental/Full, and an optional date range, then
**Synchronize**. You'll get a notification such as:
```
Sales: 1,245 orders synchronized (3,102 line rows).
Expenses: 382 records synchronized.
```
If one data type fails, the other still runs (see Section 1 architecture) —
the failure is reported without blocking the rest.

**Full Sync** (Power BI Administrator only) is the same wizard defaulted to
"Full" mode, which shows the "this clears and rebuilds each table" warning
before you click Synchronize.

---

## 6. Automatic synchronization

Set **Sync Frequency** on the connection (15 min / 30 min / hourly / 6
hours / daily) and save. The `Power BI Automatic Synchronization` scheduled
action (**Settings → Technical → Automation → Scheduled Actions**, or `ir.cron`)
runs every 15 minutes and checks each active, non-manual connection's own
frequency — so a connection set to "Daily" will not sync every 15 minutes,
the cron simply checks every 15 minutes whether that connection's interval
has elapsed. To verify it fired: **Power BI → Synchronization → Sync
Logs**, filter Type = Automatic, or check `Last Automatic Run` on the
connection.

To trigger it immediately for a demo without waiting: **Settings →
Technical → Automation → Scheduled Actions → Power BI Automatic
Synchronization → Run Manually**.

---

## 7. Testing procedure (Odoo Sales/Expenses → Power BI)

1. Create or pick a test Sales Order with at least one line and confirm it
   has a customer, salesperson and product.
2. Create or pick a test Expense with an employee and expense category.
3. Power BI → Configuration → (connection) → **Sync Now** → check both
   boxes → Incremental → Synchronize.
4. Confirm the notification reports both counts as synchronized (not
   failed).
5. In Power BI (app.powerbi.com), open the workspace → the dataset → you
   should be able to build a table/card visual against `Sales`,
   `SalesLines`, and `Expenses` and see the row(s) you just synced.
6. Edit the same Sales Order (e.g. add a line) and Sync Now again —
   confirm a new `SalesLines` row appears for the added line. Remember: the
   existing `Sales` row is **not** updated in place (see Section 1); run
   **Full Sync** to see the order's own row refreshed.
7. Automatic sync: set Sync Frequency to `15_min`, save, wait (or run the
   scheduled action manually), then check **Sync Logs** for a new entry
   with Type = Automatic.

Because this development environment has no real Microsoft/Power BI
credentials, the module's own automated tests
(`tests/test_powerbi_connection.py`, `test_sales_sync.py`,
`test_expense_sync.py`) mock the `requests` calls made to
`login.microsoftonline.com` and `api.powerbi.com` rather than performing a
live round trip — they verify the connection-test diagnostics, the
transform logic against real `sale.order`/`hr.expense` records, and that a
sync run creates the right log entries and updates `last_sync_*`
timestamps.

These 18 tests were actually run against a real Odoo 19 instance during
development (installed into a throwaway database, not this repo's working
database), not merely reviewed by eye. That surfaced three genuine Odoo 19
issues, all fixed in this version: `res.groups.category_id` was renamed to
`privilege_id` (grouped under a `res.groups.privilege` record), the search
view's "Group By" `<group>` element no longer accepts `expand`/`string`
attributes, and `res.users.groups_id` was renamed to `group_ids`. All 18
tests pass (0 failures, 0 errors) as of this version. Run them yourself
with:
```bash
./odoo-bin -c odoo.conf -d <test_db> -i powerbi_connector --test-enable --stop-after-init
```
A live end-to-end check against real Power BI can only be done once the
Section 2 Microsoft setup is complete.

---

## 8. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Test Connection: "Microsoft authentication: FAILED... Client Secret is incorrect or has expired" | Secret was rotated/expired in Entra; generate a new one and update Odoo. |
| Test Connection: "Workspace access: FAILED" | Workspace ID typo, service principal not added to the workspace, or tenant setting "Allow service principals to use Power BI APIs" not enabled/not scoped to this app. |
| Test Connection: "Dataset access: FAILED... not found" | Dataset ID was pasted from the wrong workspace, or the dataset was deleted in Power BI; clear the Dataset ID field and re-sync to let Odoo create a fresh one. |
| Sync fails with "Power BI is rate-limiting this application (429)" | Lower Batch Size, or reduce sync frequency; the client already retries with backoff a few times before surfacing this. |
| Sync fails with 403 "service principal ... does not have access" | Re-check Section 2 Steps 3-4 — this is almost always a workspace-membership or tenant-setting issue, not an Odoo configuration issue. |
| Power BI shows duplicate-looking rows for an order after editing it | Expected with Incremental sync (see Section 1) — run Full Sync to rebuild the table. |
| Cron never seems to run | Check **Settings → Technical → Automation → Scheduled Actions → Power BI Automatic Synchronization** is Active, and that the connection's Sync Frequency isn't "Manual". |

---

## 9. Security considerations

* `client_secret` is stored as a plain Odoo field but is restricted to the
  **Power BI Administrator** group at the field level (`groups=` attribute)
  and uses the password widget, so it is masked in the UI and excluded from
  list views. It is **never** written to the Odoo log; only tenant/client
  IDs and outcomes are logged.
* Access tokens are held only in memory for the duration of a request/sync
  and are never logged or persisted.
* `action_test_connection`, `action_sync_now`, `action_full_sync`, and the
  sync wizard all require the **Power BI Administrator** group; plain
  **Power BI User** members can only view connection status and Sync Logs.
* Multi-company: each connection has a Company (or "Sync All Allowed
  Companies"), and Sales/Expenses queries filter on that company unless the
  latter is checked. Record rules restrict who can see which connections
  and logs by company.
* The automatic-sync cron runs with elevated rights (`sudo()`) precisely so
  it is never blocked by the same record rules that scope interactive
  access — this is standard practice for Odoo scheduled actions, not a
  security bypass exposed to end users.

---

## 10. Known limitations

* No row-level update/delete against Power BI (Section 1) — Full Sync is
  the reconciliation mechanism.
* Push datasets are capped by Microsoft at roughly 5 million rows per
  dataset / 10,000 rows per single request / 1,000,000 rows per hour per
  dataset (subject to change; see [Power BI REST API limitations](https://learn.microsoft.com/en-us/power-bi/developer/automation/api-rest-api-limitations)).
  For very large Odoo databases, schedule Full Sync during off-hours and
  prefer Incremental sync the rest of the time.
* Certificate-based service-principal auth (recommended by Microsoft over
  client secrets for production) is not implemented — only the client
  secret flow, to keep today's setup to one shared piece of information.
  See "Future improvements."
* The "Data → Sales / Expenses" browse menus from the original spec were
  intentionally omitted: this module's job is synchronization, and Odoo
  already has first-class Sales/Expenses apps for browsing that data.
* Odoo 19 consolidated the old "expense report" (`hr.expense.sheet`)
  grouping into `hr.expense` itself; there is no `sheet_id`/report relation
  to export (verified against `addons/hr_expense/models/hr_expense.py`
  before writing the expense export, per this project's "don't invent
  fields" requirement).

## 11. Recommended production improvements

* Switch to certificate-based service-principal authentication.
* Add a "reconcile" mode that diffs Power BI's current rows (via `GET
  .../tables` is not available for push datasets, so this would mean
  tracking a local "last pushed" ledger) instead of relying on periodic
  Full Sync.
* Move the client secret into Odoo's `ir.config_parameter`-based secret
  storage or an external secrets manager if available in your deployment.
* Add a per-connection concurrency lock so two overlapping manual/automatic
  runs for the same connection cannot race.
