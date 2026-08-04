from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    contract_header = fields.Binary(
        string="Contract Header",
        attachment=True,
        config_parameter="hr_contract_print.contract_header",
    )

    contract_footer = fields.Binary(
        string="Contract Footer",
        attachment=True,
        config_parameter="hr_contract_print.contract_footer",
    )

    company_cr = fields.Char(
        string="Company CR",
        config_parameter="hr_contract_print.company_cr",
    )

    company_address = fields.Text(
        string="Company Address",
        config_parameter="hr_contract_print.company_address",
    )

    company_representative = fields.Char(
        string="Company Representative",
        config_parameter="hr_contract_print.company_representative",
    )