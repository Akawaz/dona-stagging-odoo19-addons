{
    'name': 'Purchase Request Management',
    'version': '1.0.0',
    'summary': 'Purchase Request Module with Approval Workflow and RFQ Generation',
    'description': """
        Purchase Request Module with the following features:
        - Purchase Requests with product lines
        - Catalog view grouped by product category
        - Multi-level approval workflow with notifications
        - RFQ creation (merge with existing or create new)
        - Print purchase request reports
    """,
    'author': 'Odoo Developer',
    'category': 'Purchases',
    'depends': [
        'base',
        'purchase',
        'stock',
        'mail',
        'product',
    ],
    'data': [
        'security/purchase_request_groups.xml',
        'security/ir.model.access.csv',
        'security/purchase_request_security.xml',
        'data/purchase_request_sequence.xml',
        'data/mail_template_data.xml',
        'wizard/purchase_request_line_make_purchase_order_views.xml',
        'views/purchase_request_approval_hierarchy_views.xml',
        'views/purchase_request_views.xml',
        'views/purchase_request_line_views.xml',
        'views/purchase_order_views.xml',
        'report/purchase_request_report_templates.xml',
        'report/purchase_request_reports.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'purchase_request_management/static/src/product_catalog/kanban_controller_patch.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
