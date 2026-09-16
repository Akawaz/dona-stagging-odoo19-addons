from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dona_customer_note = fields.Text(
        string='Customer Note',
        help="Customer-entered comment for this specific product/variant, "
             "captured on the website product configurator. Carried over "
             "verbatim to the matching POS order line's native 'Customer "
             "Note' field when the order is routed to the branch POS.",
    )
