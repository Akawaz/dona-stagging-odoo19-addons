import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PriceReviewWizard(models.TransientModel):
    _name = 'purchase.price.review.wizard'
    _description = "Price Increase Review Wizard"

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string="Purchase Order",
        required=True,
        readonly=True,
    )
    price_increase_summary = fields.Html(
        string="Price Increase Summary",
        compute='_compute_price_increase_summary',
        store=False,
    )

    @api.depends('purchase_order_id.order_line.is_above_cost')
    def _compute_price_increase_summary(self):
        for wizard in self:
            if not wizard.purchase_order_id:
                wizard.price_increase_summary = ''
                continue

            increased_lines = wizard.purchase_order_id.order_line.filtered(
                lambda l: l.is_above_cost
            )
            if not increased_lines:
                wizard.price_increase_summary = ''
                continue

            symbol = wizard.purchase_order_id.currency_id.symbol or ''
            rows = []
            for line in increased_lines:
                basis_label = {
                    'vendor': _('Same vendor'),
                    'any': _('Any vendor'),
                }.get(line.comparison_basis, '')
                rows.append(
                    '<tr>'
                    f"<td style='padding:6px;border:1px solid #ddd;'>{line.product_id.display_name}</td>"
                    f"<td style='padding:6px;border:1px solid #ddd;text-align:right;'>{basis_label}</td>"
                    f"<td style='padding:6px;border:1px solid #ddd;text-align:right;'>{symbol}{line.product_cost:.2f}</td>"
                    f"<td style='padding:6px;border:1px solid #ddd;text-align:right;'>{symbol}{line.price_unit:.2f}</td>"
                    f"<td style='padding:6px;border:1px solid #ddd;text-align:right;color:red;font-weight:bold;'>+{line.price_vs_cost_percent:.2f}%</td>"
                    '</tr>'
                )

            table = (
                '<table style="width:100%;border-collapse:collapse;margin-top:10px;">'
                '<thead style="background:#f0f0f0;">'
                '<tr>'
                '<th style="padding:6px;border:1px solid #ddd;text-align:left;">Product</th>'
                '<th style="padding:6px;border:1px solid #ddd;text-align:right;">Compared Against</th>'
                '<th style="padding:6px;border:1px solid #ddd;text-align:right;">Last Price</th>'
                '<th style="padding:6px;border:1px solid #ddd;text-align:right;">PO Price</th>'
                '<th style="padding:6px;border:1px solid #ddd;text-align:right;">Increase %</th>'
                '</tr>'
                '</thead>'
                '<tbody>'
                + ''.join(rows)
                + '</tbody></table>'
            )
            wizard.price_increase_summary = table

    def action_send_alerts(self):
        """Send per-line price review activities for all un-alerted lines."""
        self.ensure_one()
        if not self.purchase_order_id.has_price_increase:
            raise UserError(_("No price increase detected on this order."))

        increased_lines = self.purchase_order_id.order_line.filtered(
            lambda l: l.is_above_cost and not l.line_alert_sent
        )
        if not increased_lines:
            raise UserError(_("All price alerts have already been sent for this order."))

        sent_count = 0
        for line in increased_lines:
            line._create_line_review_activity()
            sent_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Alerts Sent'),
                'message': _('Price review activities created for %s product(s).') % sent_count,
                'type': 'success',
                'sticky': False,
            },
        }
