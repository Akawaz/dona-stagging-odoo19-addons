# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fs_employer_cr_number = fields.Char(
        related='company_id.fs_employer_cr_number', readonly=False)
    fs_require_settlement_before_archive = fields.Boolean(
        related='company_id.fs_require_settlement_before_archive', readonly=False)
    fs_settlement_structure_id = fields.Many2one(
        related='company_id.fs_settlement_structure_id', readonly=False)
    fs_annual_leave_type_id = fields.Many2one(
        related='company_id.fs_annual_leave_type_id', readonly=False)
    fs_leave_calculation_method = fields.Selection(
        related='company_id.fs_leave_calculation_method', readonly=False)
    fs_daily_rate_method = fields.Selection(
        related='company_id.fs_daily_rate_method', readonly=False)
    fs_daily_rate_divisor = fields.Integer(
        related='company_id.fs_daily_rate_divisor', readonly=False)
    fs_final_month_worked_days_method = fields.Selection(
        related='company_id.fs_final_month_worked_days_method', readonly=False)
    fs_sio_enabled = fields.Boolean(
        related='company_id.fs_sio_enabled', readonly=False)
    fs_sio_percentage = fields.Float(
        related='company_id.fs_sio_percentage', readonly=False)
    fs_authorized_representative_id = fields.Many2one(
        related='company_id.fs_authorized_representative_id', readonly=False)
    fs_report_brand_color = fields.Char(
        related='company_id.fs_report_brand_color', readonly=False)
    fs_report_release_text = fields.Html(
        related='company_id.fs_report_release_text', readonly=False)
    fs_report_property_return_text = fields.Html(
        related='company_id.fs_report_property_return_text', readonly=False)
    fs_report_continuing_obligations_text = fields.Html(
        related='company_id.fs_report_continuing_obligations_text', readonly=False)
    fs_report_governing_law_text = fields.Html(
        related='company_id.fs_report_governing_law_text', readonly=False)
