# -*- coding: utf-8 -*-
{
    'name': 'Dahua SmartPSS-Style Attendance Connector',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Connect Odoo to Dahua biometric/access devices over the private '
               'RPC2/DHIP protocol (the same protocol SmartPSS Lite uses) and '
               'fetch attendance data by IP + port, with serial-number verification.',
    'description': """
Dahua SmartPSS-Style Attendance Connector
=========================================
Connects Odoo directly to Dahua access-control / biometric terminals using
Dahua's **private RPC2 protocol** - the same protocol used internally by
**SmartPSS Lite** and the device web UI.

How SmartPSS Lite connects (and what this module replicates)
------------------------------------------------------------
* **IP method**: a TCP connection to the device on port **37777** (default),
  authenticated with username/password using Dahua's two-stage MD5 digest
  handshake, then `RecordFinder` RPC calls pull the access/attendance records.
  This module implements that exact flow (DHIP binary framing on 37777).
* **HTTP RPC**: the identical JSON-RPC payloads also work over `/RPC2` on
  port 80/443 - offered here as an alternative transport for firmwares that
  expose HTTP RPC but not 37777.
* **SN method**: SmartPSS Lite's "add by serial number" uses Dahua's P2P cloud
  relay. True cloud P2P needs Dahua's relay servers and is out of scope; here
  the **serial number is used to verify** you are talking to the right device
  (read back via `magicBox.getSerialNo`).

Features
--------
* Configure devices by IP + port (+ optional serial-number verification).
* Test Connection button (logs in, reads serial number & device type).
* Manual "Sync Now" and scheduled (cron) sync.
* Every fetched punch is stored as a raw record for full auditability/debugging.
* Raw punches are turned into hr.attendance check-in/check-out entries.
* Verbose debug mode captures the raw protocol exchange into the sync log.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['hr_attendance', 'base'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'wizard/dahua_enroll_wizard_views.xml',
        'wizard/dahua_sync_wizard_views.xml',
        'views/dahua_device_views.xml',
        'views/dahua_attendance_record_views.xml',
        'views/dahua_sync_log_views.xml',
        'views/hr_employee_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
}
