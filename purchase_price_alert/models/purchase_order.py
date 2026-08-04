import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    has_price_increase = fields.Boolean(
        string="Has Price Increase",
        compute='_compute_has_price_increase',
        store=False,
    )

    @api.depends('order_line.is_above_cost', 'order_line.comparison_basis')
    def _compute_has_price_increase(self):
        for order in self:
            order.has_price_increase = any(
                line.is_above_cost for line in order.order_line
            )

    def action_open_price_review_wizard(self):
        """Open the price review wizard."""
        self.ensure_one()
        if not self.has_price_increase:
            raise UserError(_("No price increase detected on this order."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.price.review.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_order_id': self.id,
            },
        }

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            if vals['state'] in ('purchase', 'cancel'):
                # Close all open activities on confirm / cancel
                for order in self:
                    open_activities = self.env['mail.activity'].search([
                        ('res_model', '=', 'purchase.order'),
                        ('res_id', '=', order.id),
                    ])
                    for activity in open_activities:
                        activity.action_feedback(feedback=_("Order %s") % vals['state'])
            elif vals['state'] == 'draft':
                # Reset alert flags so alerts can be re-sent after cancel → draft
                for order in self:
                    order.order_line.write({'line_alert_sent': False})
        return res
