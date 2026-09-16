from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def action_pos_session_open(self):
        """When a branch's POS session opens, flush any website order that was
        queued while that POS had no active session (section 7, Case B)."""
        res = super().action_pos_session_open()
        for session in self:
            if session.state != 'opened':
                continue
            queued_orders = self.env['sale.order'].sudo().search([
                ('pos_routing_state', '=', 'queued'),
                ('branch_id.pos_config_id', '=', session.config_id.id),
            ])
            if queued_orders:
                queued_orders._dona_route_to_pos()
        return res
