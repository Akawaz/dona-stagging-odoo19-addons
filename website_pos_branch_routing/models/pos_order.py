from odoo import _, fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    website_sale_order_id = fields.Many2one(
        'sale.order', string='Website Order', copy=False, readonly=True, index=True,
        help="The website sale order this POS order was automatically routed "
             "from (section 18: traceability between sale.order and pos.order).",
    )

    def action_view_website_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Website Order"),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.website_sale_order_id.id,
        }
