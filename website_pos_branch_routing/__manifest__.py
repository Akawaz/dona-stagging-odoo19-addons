{
    'name': "Website Orders to Branch POS",
    'summary': "Route confirmed eCommerce website orders to the correct branch's Point of Sale, live.",
    'description': """
Website Orders to Branch POS
=============================

Connects a multi-branch Odoo eCommerce website (branch/pickup-delivery/date-time
picker) to Point of Sale, so every confirmed website order is created in the
correct branch's POS automatically.

* Backend-configurable Branch -> POS mapping (``pos.branch``). No JavaScript
  changes are needed to reassign a branch's POS.
* Server-side branch/order-type/schedule capture on ``sale.order`` via the
  existing ``/dona/order/context`` mechanism, validated against real
  ``pos.branch`` records - a browser can never pick an arbitrary POS.
* Deterministic routing on order confirmation (after payment), preserving
  product variants, quantities, per-item customer comments and the
  pickup/delivery schedule.
* Safe queueing when the branch's POS has no active session, automatically
  flushed the next time that POS opens.
* Live POS notification over Odoo's native bus/synchronisation channel - no
  manual refresh needed on an already-open POS session.
* Idempotent: the same website order can never create two POS orders.
""",
    'version': '19.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['base', 'sale_management', 'website', 'website_sale', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_branch_views.xml',
        'views/sale_order_views.xml',
        'views/pos_order_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
