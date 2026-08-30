# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fs_employer_cr_number = fields.Char(
        string="Employer CR / Registration Number",
        help="Commercial Registration number shown as the employer identifier "
             "on the Final Settlement report.")

    fs_require_settlement_before_archive = fields.Boolean(
        string="Require Final Settlement Before Archive",
        help="If enabled, an employee cannot be archived until a Final "
             "Settlement for that employee has reached the Finalized state.")

    fs_settlement_structure_id = fields.Many2one(
        'hr.payroll.structure', string="Final Settlement Salary Structure",
        help="Payroll structure used when generating a Final Settlement payslip.")

    fs_annual_leave_type_id = fields.Many2one(
        'hr.leave.type', string="Annual Leave Time Off Type",
        help="Time Off type used to compute the annual leave balance and "
             "encashment on Final Settlements.")

    fs_leave_calculation_method = fields.Selection([
        ('time_off_balance', 'Odoo Time Off Balance'),
    ], string="Annual Leave Calculation Method", default='time_off_balance', required=True,
        help="How the annual leave entitlement/used/balance shown on a Final "
             "Settlement is computed. Only the real Odoo Time Off balance "
             "(as of the Last Working Date) is supported in this version.")

    fs_daily_rate_method = fields.Selection([
        ('monthly_div_30', 'Monthly Salary / 30'),
        ('basic_div_30', 'Basic Salary / 30'),
        ('basic_allowances_div_30', 'Basic Salary + Allowances / 30'),
    ], string="Daily Rate Calculation Basis", default='monthly_div_30', required=True)

    fs_daily_rate_divisor = fields.Integer(
        string="Daily Rate Divisor", default=30,
        help="Number of days used to divide the monthly salary basis when "
             "computing the daily rate.")

    fs_final_month_worked_days_method = fields.Selection([
        ('calendar_div_30', 'Monthly Salary / 30 x Calendar Days Worked'),
    ], string="Final Month Salary Calculation Basis", default='calendar_div_30', required=True)

    fs_sio_enabled = fields.Boolean(string="SIO Deduction Enabled", default=True)
    fs_sio_percentage = fields.Float(string="SIO Percentage", default=8.0,
        help="Percentage applied on the final month salary as a Social "
             "Insurance Organization (SIO) deduction. Must be validated by "
             "the company's payroll/legal team before production use.")

    fs_authorized_representative_id = fields.Many2one(
        'res.users', string="Settlement Authorized Representative",
        help="Employer representative recorded on the Final Settlement's Clearance tab.")

    fs_report_brand_color = fields.Char(
        string="Final Settlement Report Brand Color", default='#C0272D',
        help="Accent color (hex) used for headings and table headers on the "
             "Final Settlement report.")

    fs_report_release_text = fields.Html(
        string="Mutual Release Text",
        help="Legal text shown in the 'Mutual Release and Discharge' section of "
             "the Final Settlement report. Leave empty to use the built-in default.")

    fs_report_property_return_text = fields.Html(
        string="Return of Company Property Text",
        help="Legal text shown in the 'Return of Company Property' section of "
             "the Final Settlement report. Leave empty to use the built-in default.")

    fs_report_continuing_obligations_text = fields.Html(
        string="Continuing Obligations Text",
        help="Legal text shown in the 'Continuing Obligations' (confidentiality / "
             "non-competition) section of the Final Settlement report. Leave empty "
             "to use the built-in default.")

    fs_report_governing_law_text = fields.Html(
        string="Governing Law Text",
        help="Legal text shown in the 'Governing Law' section of the Final "
             "Settlement report. Leave empty to use the built-in default.")
