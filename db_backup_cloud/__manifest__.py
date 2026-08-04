# -*- coding: utf-8 -*-
{
    'name': 'Database Backup (Local + Cloud)',
    'version': '19.0.1.0.1',
    'category': 'Administration/Tools',
    'summary': 'Scheduled database + filestore backups to a local folder, Google Drive, OneDrive and AWS S3',
    'description': """
Database Backup (Local + Cloud)
===============================
Take full database backups (SQL dump **with filestore**, standard Odoo ``.zip``
format) and store them:

* in a **local folder** on the server,
* on **Google Drive** (service account),
* on **Microsoft OneDrive** (Microsoft Graph, app-only),
* on **AWS S3** (or any S3-compatible bucket).

Features
--------
* One-click **Backup Now** and an automatic **scheduled** backup (cron).
* Per-destination enable/disable, configured from **Settings**.
* Local retention (keep the last *N* backups).
* A **Backup History** log with status, size and destinations.

Optional Python packages (only needed for the matching destination):
``boto3`` (S3), ``google-api-python-client`` + ``google-auth`` (Drive).
OneDrive uses only ``requests`` (already bundled with Odoo).
""",
    'author': 'Arun A George',
    'website': 'https://arunalexgeorge.online',
    'support': 'admin@arunalexgeorge.online',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/db_backup_cron.xml',
        'views/db_backup_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'external_dependencies': {
        # NOT hard-required so the module always installs and local backups work;
        # cloud uploads raise a clear error if the package is missing.
        'python': [],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
