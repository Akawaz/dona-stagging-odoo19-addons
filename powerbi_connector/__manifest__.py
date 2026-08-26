# -*- coding: utf-8 -*-
{
    'name': 'Microsoft Power BI Connector',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Synchronize Odoo Sales and Expenses into Microsoft Power BI',
    'description': """
Microsoft Power BI Connector
=============================
Connects Odoo to Microsoft Power BI using a Microsoft Entra ID service
principal and the Power BI REST API **push datasets** feature, and
synchronizes Sales (orders + lines) and Expenses into Power BI tables.

Features
--------
* Configure one or more Power BI connections (tenant/client/secret/workspace).
* Test Connection button with step-by-step diagnostics (auth / workspace /
  dataset access).
* Manual "Sync Now" and "Full Sync" (with confirmation wizard).
* Automatic scheduled synchronization (ir.cron), frequency configurable per
  connection.
* Incremental sync based on write_date; Full Sync clears and reloads tables
  (push datasets have no row-level update, see README for details).
* Per-run synchronization logs with record counts and error detail.
* Secrets (client secret) are never logged and are restricted to the
  Power BI Administrator group.
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'sale', 'hr_expense'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/ir_cron.xml',
        'wizard/powerbi_sync_wizard_views.xml',
        'views/powerbi_config_views.xml',
        'views/powerbi_sync_log_views.xml',
        'views/powerbi_menus.xml',
    ],
    'installable': True,
    'application': True,
}
