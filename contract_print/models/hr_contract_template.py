# -*- coding: utf-8 -*-

from odoo import models, fields


class HrContractTemplate(models.Model):
    _name = "hr.contract.template"
    _description = "Employment Contract Template"
    _order = "nationality_type, name"

    name = fields.Char(
        string="Template Name",
        required=True,
    )

    nationality_type = fields.Selection(
        [
            ("bahraini", "Bahraini"),
            ("non_bahraini", "Non-Bahraini"),
        ],
        string="Nationality",
        required=True,
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )

    body = fields.Html(
        string="Contract Body",
        sanitize=False,
    )

    active = fields.Boolean(
        default=True,
    )