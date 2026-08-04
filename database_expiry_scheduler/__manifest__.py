{
    'name': 'Database Expiry Scheduler',
    'version': '19.0.1.0.0',
    'summary': 'Auto-extends database expiry date via daily cron job',
    'category': 'Technical',
    'author': 'Custom',
    'depends': ['base'],
    'data': [
        'data/cron_data.xml',
        'views/config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
