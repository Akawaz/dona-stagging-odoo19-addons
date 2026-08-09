# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    contract_representative = fields.Char(
        related="company_id.contract_representative",
        readonly=False,
    )

    contract_cr_number = fields.Char(
        related="company_id.contract_cr_number",
        readonly=False,
    )

    contract_address = fields.Text(
        related="company_id.contract_address",
        readonly=False,
    )

    contract_header_image = fields.Binary(
        related="company_id.contract_header_image",
        readonly=False,
    )

    contract_footer_image = fields.Binary(
        related="company_id.contract_footer_image",
        readonly=False,
    )