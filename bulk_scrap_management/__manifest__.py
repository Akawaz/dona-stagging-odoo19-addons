{
    'name': 'Bulk Scrap Management',
    'version': '19.0.1.0.0',
    'summary': 'Manage bulk scrap operations with review workflow and reporting',
    'category': 'Inventory',
    'author': 'Custom',
    'depends': ['stock', 'mail', 'product', 'uom'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/bulk_scrap_views.xml',
        'views/menu.xml',
        'report/report_bulk_scrap.xml',
        'report/bulk_scrap_report.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
