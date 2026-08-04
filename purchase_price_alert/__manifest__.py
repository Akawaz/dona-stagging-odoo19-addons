# -*- coding: utf-8 -*-
{
    'name': "Purchase Price Alert",
    'summary': "Highlight price increases on PO lines and notify reviewers via activities",
    'version': "19.0.1.0.0",
    'category': "Purchase",
    'depends': ['purchase', 'account', 'mail'],
    'installable': True,
    'application': False,
    'license': "LGPL-3",
    'data': [
        'wizards/price_review_wizard.xml',
        'views/purchase_order_views.xml',
    ],
}
