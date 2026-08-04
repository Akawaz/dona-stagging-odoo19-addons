from odoo import api, models


class HrContractReport(models.AbstractModel):
    _name = "report.hr_contract_print.contract_report"
    _description = "Employee Contract Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        employees = self.env["hr.employee"].browse(docids)

        header = self.env["ir.config_parameter"].sudo().get_param("hr_contract_print.contract_header")
        footer = self.env["ir.config_parameter"].sudo().get_param("hr_contract_print.contract_footer")
        company_cr = self.env["ir.config_parameter"].sudo().get_param("hr_contract_print.company_cr") or ""
        company_address = self.env["ir.config_parameter"].sudo().get_param("hr_contract_print.company_address") or ""
        representative = self.env["ir.config_parameter"].sudo().get_param("hr_contract_print.company_representative") or ""

        return {
            "doc_ids": docids,
            "doc_model": "hr.employee",
            "docs": employees,
            "header": header,
            "footer": footer,
            "company_cr": company_cr,
            "company_address": company_address,
            "representative": representative,
        }