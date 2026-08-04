# ☁️ Database Backup — Local + Cloud

**Automatic, scheduled Odoo database backups (with filestore) to a local folder,
Google Drive, OneDrive and AWS S3 — configured entirely from Settings.**

Never lose your Odoo data again. This module produces a **full backup** — the SQL
dump **plus the filestore**, in the standard Odoo `.zip` format — and stores it
wherever you choose: on the server, and/or on your favourite cloud.

---

## ✨ Highlights

- 💾 **Full backups** — database **+ filestore** in the standard Odoo `.zip` (restorable from Odoo's own database manager)
- 🗂️ **Local folder** — keep copies on the server, with automatic retention (keep the last *N*)
- ☁️ **AWS S3** — or any S3-compatible bucket (MinIO, Wasabi, DigitalOcean Spaces…)
- 📁 **Google Drive** — via a service account
- 🪟 **Microsoft OneDrive** — via Microsoft Graph (app-only)
- ⏰ **Scheduled** daily backup (cron) + one-click **Backup Now**
- 🧾 **Backup History** — every run logged with status, size and destinations
- 🔀 **Multi-destination** — push the same backup to several targets at once; one failing destination never blocks the others

---

## ⚙️ Configuration

Everything is configured from **Settings → Database Backup**:

| Destination | What you need |
|---|---|
| **Local folder** | A writable server path + how many backups to keep |
| **AWS S3** | Access key, secret, bucket, region (+ optional prefix / custom endpoint) |
| **Google Drive** | Service-account JSON + target folder ID (share the folder with the service account) |
| **OneDrive** | Azure app client id / secret / tenant + drive target + folder |

Toggle each destination on/off independently, then enable the **daily scheduled
backup** or run **Backup Now**.

---

## 🚀 Installation

1. Copy `db_backup_cloud` into your Odoo addons path.
2. **Apps → Update Apps List**, then install **Database Backup (Local + Cloud)**.
3. Open **Settings → Database Backup** and configure your destinations.

### Requirements
- `pg_dump` available on the Odoo server (same major version as PostgreSQL) — needed for the database dump.
- Optional Python packages, only for the matching cloud destination:
  - **AWS S3** → `boto3`
  - **Google Drive** → `google-api-python-client`, `google-auth`
  - **OneDrive** → none (uses `requests`, already bundled with Odoo)

If a package is missing, that destination shows a clear message; local backups and
the other destinations keep working.

---

## 🖥️ Compatibility

| | |
|---|---|
| **Odoo version** | 19.0 (Community / Enterprise) |
| **License** | LGPL-3 |
| **Price** | Free |

---

## 👤 Author & Support

**Arun A George**
🌐 [arunalexgeorge.online](https://arunalexgeorge.online)
✉️ admin@arunalexgeorge.online
