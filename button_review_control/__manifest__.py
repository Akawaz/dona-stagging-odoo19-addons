{
    'name': 'Button Review Control',
    'version': '19.0.1.0.0',
    'summary': 'Hide Confirm/Post/Delete buttons and add Request for Review',
    'category': 'Tools',
    'author': 'Custom',
    'depends': ['account', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'views/review_confirm_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
