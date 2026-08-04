from odoo import fields, models


class HrContractTemplate(models.Model):
    _name = "hr.contract.template"
    _description = "Employment Contract Template"
    _order = "name"

    name = fields.Char(
        required=True,
    )

    contract_type = fields.Selection(
        [
            ("bahraini", "Bahraini"),
            ("non_bahraini", "Non Bahraini"),
        ],
        required=True,
        default="bahraini",
    )

    active = fields.Boolean(
        default=True,
    )

    body = fields.Html(
        string="Contract Body",
        sanitize=False,
    )