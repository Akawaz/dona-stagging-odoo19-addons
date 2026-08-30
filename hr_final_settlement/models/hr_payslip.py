# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    final_settlement_ids = fields.One2many(
        'hr.final.settlement', 'payslip_id', string="Final Settlement",
        help="Final Settlement this payslip was generated from, if any.")

    def action_view_final_settlement(self):
        self.ensure_one()
        settlement = self.final_settlement_ids[:1]
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.final.settlement',
            'view_mode': 'form',
            'res_id': settlement.id,
        }
