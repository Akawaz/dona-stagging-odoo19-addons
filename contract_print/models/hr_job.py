# -*- coding: utf-8 -*-

from odoo import fields, models


class HrJob(models.Model):
    _inherit = "hr.job"

    contract_job_description = fields.Html(
        string="Contract Job Description",
        sanitize=False,
    )