# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    contract_representative = fields.Char(
        string="Contract Representative"
    )

    contract_cr_number = fields.Char(
        string="CR Number"
    )

    contract_address = fields.Text(
        string="Contract Address"
    )

    contract_header_image = fields.Binary(
        string="Contract Header",
        attachment=True,
    )

    contract_footer_image = fields.Binary(
        string="Contract Footer",
        attachment=True,
    )