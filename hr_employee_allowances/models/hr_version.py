# -*- coding: utf-8 -*-
from odoo import fields, models


class HrVersion(models.Model):
    """Store the allowances on the contract version, alongside ``wage``."""

    _inherit = 'hr.version'

    transportation_allowance = fields.Monetary(
        string='Transportation Allowance',
        tracking=True,
        groups="hr.group_hr_manager",
        help="Employee's monthly transportation allowance.",
    )
    housing_allowance = fields.Monetary(
        string='Housing Allowance',
        tracking=True,
        groups="hr.group_hr_manager",
        help="Employee's monthly housing allowance.",
    )
    other_allowance = fields.Monetary(
        string='Other Allowances',
        tracking=True,
        groups="hr.group_hr_manager",
        help="Any other monthly allowances granted to the employee.",
    )
