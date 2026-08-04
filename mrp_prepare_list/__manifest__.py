{
    'name': 'Kitchen Preparation List',
    'version': '1.0.0',
    'summary': 'Kitchen Preparation and Manufacturing Planning',
    'description': """
Kitchen Preparation List

This module allows kitchen staff to:
- Create preparation templates
- Manage kitchen shifts
- Create daily preparation lists
- Generate Manufacturing Orders from preparation lists
    """,

    'author': 'Your Company',
    'website': '',

    'category': 'Manufacturing',

    'license': 'LGPL-3',

    'depends': [
        'mrp',
        'stock',
        'product',
        'mail',
        'hr',
    ],

    'data': [
    'security/ir.model.access.csv',

    'data/sequence.xml',

    'views/kitchen_prepare_shift_views.xml',
    'views/kitchen_prepare_template_views.xml',

    'report/kitchen_prepare_report_templates.xml',
    'report/kitchen_prepare_report.xml',

    'views/kitchen_prepare_list_views.xml',

    'views/menus.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
}