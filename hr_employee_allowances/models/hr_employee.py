# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    """Expose the version allowance fields on the employee.

    Group-restricted ``hr.version`` fields must be re-declared here with
    ``inherited=True`` so the delegation link is properly established
    (see the note in ``hr/models/hr_employee.py``).
    """

    _inherit = 'hr.employee'

    transportation_allowance = fields.Monetary(
        related='version_id.transportation_allowance',
        inherited=True, readonly=False, groups="hr.group_hr_manager")
    housing_allowance = fields.Monetary(
        related='version_id.housing_allowance',
        inherited=True, readonly=False, groups="hr.group_hr_manager")
    other_allowance = fields.Monetary(
        related='version_id.other_allowance',
        inherited=True, readonly=False, groups="hr.group_hr_manager")
