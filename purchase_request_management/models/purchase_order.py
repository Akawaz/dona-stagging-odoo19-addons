from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    purchase_request_count = fields.Integer(
        string='Purchase Requests',
        compute='_compute_purchase_request_count',
    )
    purchase_request_ids = fields.Many2many(
        'purchase.request',
        string='Purchase Requests',
        compute='_compute_purchase_request_ids',
    )

    def _get_purchase_request_lines(self):
        """Get purchase request lines linked to this order's lines."""
        self.ensure_one()
        po_line_ids = self.order_line.ids
        if not po_line_ids:
            return self.env['purchase.request.line']
        return self.env['purchase.request.line'].search([
            ('purchase_order_line_id', 'in', po_line_ids)
        ])

    @api.depends('order_line')
    def _compute_purchase_request_count(self):
        for order in self:
            request_lines = order._get_purchase_request_lines()
            request_ids = request_lines.mapped('request_id')
            order.purchase_request_count = len(request_ids)

    @api.depends('order_line')
    def _compute_purchase_request_ids(self):
        for order in self:
            request_lines = order._get_purchase_request_lines()
            request_ids = request_lines.mapped('request_id')
            order.purchase_request_ids = request_ids

    def action_view_purchase_requests(self):
        self.ensure_one()
        request_lines = self._get_purchase_request_lines()
        request_ids = request_lines.mapped('request_id')
        action = self.env.ref('purchase_request_management.action_purchase_request').read()[0]
        if len(request_ids) > 1:
            action['domain'] = [('id', 'in', request_ids.ids)]
        elif len(request_ids) == 1:
            action['views'] = [
                (self.env.ref('purchase_request_management.view_purchase_request_form').id, 'form')
            ]
            action['res_id'] = request_ids.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action
