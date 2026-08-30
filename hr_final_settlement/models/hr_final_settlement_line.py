# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrFinalSettlementLine(models.Model):
    _name = 'hr.final.settlement.line'
    _description = 'Final Settlement Line'
    _order = 'settlement_id, sequence, id'

    settlement_id = fields.Many2one(
        'hr.final.settlement', string="Final Settlement",
        required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='settlement_id.company_id', store=True)
    currency_id = fields.Many2one(related='settlement_id.currency_id')

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    description = fields.Text()

    line_type = fields.Selection([
        ('earning', 'Earning'),
        ('deduction', 'Deduction'),
        ('information', 'Information'),
    ], required=True, default='earning')

    category = fields.Selection([
        ('final_salary', 'Final Salary'),
        ('annual_leave', 'Annual Leave Encashment'),
        ('eos', 'End of Service'),
        ('allowance', 'Allowance'),
        ('other_earning', 'Other Earnings'),
        ('sio', 'SIO'),
        ('loan', 'Loan'),
        ('advance', 'Advance'),
        ('other_deduction', 'Other Deduction'),
    ], required=True)

    is_system_line = fields.Boolean(
        default=False,
        help="System-calculated line (final salary, leave encashment, SIO). "
             "These are rebuilt on every recalculation; manually added lines are kept.")

    quantity = fields.Float(default=1.0)
    rate = fields.Monetary(help="Unit rate used in the calculation (e.g. daily rate, days count).")

    calculated_amount = fields.Monetary(
        string="System Calculated Amount",
        help="Amount as computed by the calculation engine, kept even if overridden.")

    is_manual_override = fields.Boolean(string="Manually Overridden")
    override_amount = fields.Monetary(string="Override Amount")
    override_reason = fields.Char(string="Override Reason")
    override_uid = fields.Many2one('res.users', string="Overridden By", readonly=True)
    override_date = fields.Datetime(string="Overridden On", readonly=True)

    amount = fields.Monetary(
        string="Amount", compute='_compute_amount', store=True,
        help="Effective amount used in the settlement totals: the override "
             "amount if manually overridden, otherwise the calculated amount.")

    salary_rule_id = fields.Many2one('hr.salary.rule', string="Salary Rule")
    input_code = fields.Char(string="Payslip Input Code")

    notes = fields.Text()

    @api.depends('is_manual_override', 'override_amount', 'calculated_amount')
    def _compute_amount(self):
        for line in self:
            line.amount = line.override_amount if line.is_manual_override else line.calculated_amount

    def write(self, vals):
        if 'override_amount' in vals or vals.get('is_manual_override'):
            vals = dict(vals)
            vals['override_uid'] = self.env.uid
            vals['override_date'] = fields.Datetime.now()
        return super().write(vals)
