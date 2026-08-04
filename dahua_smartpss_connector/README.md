# Dahua SmartPSS-Style Attendance Connector (Odoo 19)

Connect Odoo directly to Dahua biometric / access-control terminals (e.g.
**ASI2212H-DW**, ASI3xxx/6xxx/7xxx) using **the same private RPC2 protocol that
SmartPSS Lite uses**, and pull attendance punches into `hr.attendance`.

---

## How SmartPSS Lite connects — and what this module does

When you add a device in **SmartPSS Lite**, you pick a *Method to add*:

| SmartPSS method | How it works | This module |
|-----------------|--------------|-------------|
| **IP** | TCP connection to the device on **port 37777** (default), login with a two-stage MD5 digest, then `RecordFinder` RPC calls pull records. | ✅ Implemented (connection mode **Private Protocol / DHIP**). |
| **HTTP RPC** | Same JSON-RPC payloads over `/RPC2` on port 80/443. | ✅ Implemented (connection mode **HTTP RPC**). |
| **SN** | "Add by serial number" → Dahua **P2P cloud relay** reaches the device behind NAT using its serial number. | ⚠️ Not implemented (needs Dahua's cloud relay servers). The **serial number is used here only to verify** the correct device is connected. |

So: this module replicates SmartPSS Lite's **IP-based** connection. You connect
by **IP + port**, and can optionally record the **serial number** for
verification. For remote sites, reach the device via VPN or port-forwarding
(see "Remote / cloud Odoo" below) — the same as pointing SmartPSS at a WAN IP.

### The connection flow (implemented in `models/dahua_rpc_client.py`)

1. Open transport — raw TCP socket to `:37777` (DHIP binary framing) **or** an
   HTTP session to `/RPC2`.
2. `global.login` (stage 1) → device returns `realm` + `random` + a session id.
3. Compute `MD5(user:realm:pass)` then `MD5(user:random:<that>)` and send
   `global.login` (stage 2) → authenticated.
4. `magicBox.getSerialNo` / `getDeviceType` / `getSoftwareVersion` for identity.
5. `RecordFinder.factory.create {name:"AccessControlCardRec"}` →
   `startFind` (time-ranged) → `doFind` (paginated) → `stopFind` → `destroy`.
6. Records are stored raw, then converted to check-in/check-out attendances.

---

## Requirements

- Odoo 19 with **hr_attendance** installed.
- Python `requests` (already an Odoo dependency).
- Network reachability from the Odoo server to the device IP/port.
- Device credentials (admin user/password) and the device's network port.

---

## Step 1 — Find the connection details on the device

- **IP address**: Device menu → *Network → TCP/IP* (set a **static IP**; reserve
  it in your router's DHCP too). In SmartPSS Lite this is the value under *IP*.
- **Port**: for the private protocol it is **37777** by default
  (Device menu → *Network → Port* → "TCP Port"). This is the same default
  SmartPSS Lite shows. If you use HTTP RPC instead, it's **80** (HTTP Port).
- **Serial Number (SN)**: Device menu → *System Info*, or in SmartPSS Lite the
  device list shows the SN. Optional but recommended for verification.
- **Username / Password**: the device admin account.

---

## Step 2 — Test the connection BEFORE configuring Odoo (recommended)

A standalone tester is bundled (uses the exact same client code, no Odoo needed).
Run it from any machine that can reach the device:

```bash
cd custom-addons/dahua_smartpss_connector/tools

# Private protocol (SmartPSS default, port 37777):
python3 test_connection.py --host 192.168.1.108 --user admin --password 'YourPass' --debug

# If 37777 is closed/unsupported, try HTTP RPC:
python3 test_connection.py --host 192.168.1.108 --mode http --port 80 \
        --user admin --password 'YourPass' --debug
```

**Expected output**: `Login OK`, a printed **Serial Number**, **Device Type**,
and a count of fetched records. If you see records, you're ready for Odoo.

`--debug` prints the raw protocol exchange (passwords masked) so you can see
exactly where a failure happens.

---

## Step 3 — Configure in Odoo

1. Install the **Dahua SmartPSS-Style Attendance Connector** app.
2. Go to **Attendances → Dahua Connector → Devices → New**.
3. Fill in:
   - **Connection Mode**: *Private Protocol / DHIP (TCP 37777)* (recommended) or *HTTP RPC*.
   - **IP Address**, **Port** (auto-fills 37777/80 when you pick the mode).
   - **Username / Password**.
   - **Serial Number** (optional) and tick **Verify Serial on Connect** to enforce it.
4. Click **Test Connection** → status turns **Connected**, and the device
   model/firmware/serial are read back and filled in automatically.
5. On each **Employee** → **Dahua Device** tab, set **Dahua Device User ID**
   (the enrolled User ID from the device / SmartPSS user list).
6. Click **Sync Now** to pull recent punches, or let the cron run.

---

## Step 4 — Syncing

- **Sync Now** (button) or the scheduled action **"Dahua SmartPSS: Sync
  Attendance Devices"** (every 5 min by default; adjust under *Settings →
  Technical → Automation → Scheduled Actions*).
- **First run** pulls the full device history; afterwards a per-device epoch
  watermark only fetches new punches. Use **Fetch All History** to re-import
  everything (duplicates are skipped by device record number).
- **Only successful punches are imported.** Denied/failed recognitions
  (Status 0 / ErrorCode set / no user ID) are ignored and never stored.
- **Every imported punch** is stored under **Fetched Records** (matched
  employee + resulting attendance) for auditability.
- Attendance is **toggled**: each punch alternates check-in / check-out against
  the employee's current open attendance (this terminal has no reliable in/out
  flag).

---

## Step 5 — Enrolling employees (Odoo → device push)

Besides pulling attendance, you can push employee user records onto the device
(SmartPSS-style enrollment). This creates/updates the person on the terminal so
their punches are recognised; **biometric templates (fingerprint/face) must still
be captured at the device**, but the user record and optional access card are
created from Odoo.

**Set up the employee**
1. Open an employee → **Dahua Device** tab.
2. Fill **Dahua Device User ID** (unique numeric ID used on the device) and,
   optionally, the **Dahua Card Number**.

**Push a single / selected employees**
- From the employee form, click **Push to Dahua Device**, pick the target device,
  and confirm. `Enrolled on Device` and `Last Pushed To` update on success.

**Bulk / new-employee enrollment (wizard)**
- **Attendances → Dahua Connector → Enroll Employees**, or the **Enroll
  Employees** button on the device form.
- Choose the **Target Device**, then either:
  - *Push existing employees* — select employees (must have a Device User ID); or
  - *Create a new employee and push* — enter name, Device User ID and optional
    card; the employee is created in Odoo and pushed in one step.
- The wizard reopens with a **Result** summary listing successes/failures.

**Test enrollment from the CLI first (optional)**

```bash
# Push a user (+ optional card):
python3 tools/test_connection.py --host 192.168.1.108 --user admin --password Abcd1234 \
        --push-user 1001 --push-name "John Doe" --push-card 0012345678

# Query / remove a user:
python3 tools/test_connection.py --host 192.168.1.108 --user admin --password Abcd1234 --get-user 1001
python3 tools/test_connection.py --host 192.168.1.108 --user admin --password Abcd1234 --remove-user 1001
```

> The client tries the modern `AccessUser.insertMulti/updateMulti` service first,
> then falls back to the legacy `RecordUpdater` path, so it works across ASI
> firmware variants. If your unit rejects the push, enable **Debug Mode** and
> capture the sync log for the exact device response.

---

## Debugging

- Turn on **Debug Mode** on the device, run a sync, then open the **Sync Log** —
  the *Debug Log* field contains the raw JSON request/response exchange.
- **Fetched Records** shows exactly what the device returned (`Raw Record`
  field), even for punches skipped because the user was unmapped.
- Common issues:
  - *"Unexpected response framing (not DHIP)"* → wrong port/mode; the device
    isn't speaking DHIP on that port. Try **HTTP RPC** mode, or confirm 37777.
  - *"Authentication failed"* → wrong credentials, or the account is temporarily
    locked after failed attempts (wait, or use the correct admin account).
  - *"did not return a RecordFinder object"* → this firmware doesn't expose
    attendance via RPC; capture the debug log and share it.
  - *Connection timeout* → firewall / no route to the device IP:port.

---

## Remote / cloud Odoo

If Odoo runs off-site, the server must still be able to open a TCP connection to
the device's IP:port. Either:
- **VPN** between the Odoo server and the device's LAN (recommended, secure), then
  use the device's LAN IP; **or**
- **Port-forward** the device port (e.g. 37777) on the site router to the Odoo
  server's public IP, and use the site's public IP / DDNS hostname + forwarded
  port in the device record. Restrict the forward to the Odoo server's IP if
  possible — exposing device ports publicly is risky.

---

## What's included / not included

- ✅ IP-based connection (DHIP 37777 + HTTP RPC), login, identity, attendance pull,
  raw record storage, hr.attendance creation, cron, debug logging, standalone tester.
- ✅ Pushing employee **user records + access cards** from Odoo → device (enrollment
  wizard, employee/device buttons, create-new-employee-and-push).
- ❌ SN-based **P2P cloud** connection (needs Dahua relay infrastructure).
- ❌ Pushing biometric **fingerprint/face templates** from Odoo (capture at device).

Field note: the exact `RecordFinder` record name/fields vary by firmware. The
client tries several `startFind` condition formats and filters client-side;
if your unit uses a different record set, capture a debug log and it can be adjusted.
