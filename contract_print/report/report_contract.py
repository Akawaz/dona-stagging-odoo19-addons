# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class ReportEmployeeContract(models.AbstractModel):
    _name = "report.contract_print.employee_contract"
    _description = "Employee Contract Report"

    @api.model
    def _get_report_values(self, docids, data=None):

        employees = self.env["hr.employee"].browse(docids)

        if not employees:
            return {}

        employee = employees[0]
        company = employee.company_id
        version = employee.version_id

        if not version:
            raise UserError(
                "This employee does not have an active contract/version assigned."
            )

        # Determine nationality
        nationality = (
            "bahraini"
            if employee.country_id
            and employee.country_id.code == "BH"
            else "non_bahraini"
        )

        # Find the appropriate contract template
        template = self.env["hr.contract.template"].search(
            [
                ("nationality_type", "=", nationality),
                ("company_id", "=", company.id),
                ("active", "=", True),
            ],
            limit=1,
        )

        if not template:
            raise UserError(
                "No active contract template was found for this employee."
            )

        values = {

            # -------------------------------------------------
            # Employee
            # -------------------------------------------------

            "employee_name": employee.name or "",

            "employee_id": employee.identification_id or "",

            "employee_address": employee.private_street or "",

            "nationality": employee.country_id.name or "",

            # -------------------------------------------------
            # Job
            # -------------------------------------------------

            "job_title": (
                version.job_id.name
                if version.job_id
                else ""
            ),

            "job_description": (
                version.job_id.contract_job_description
                if version.job_id
                else ""
            ),

            # -------------------------------------------------
            # Contract
            # -------------------------------------------------

            "salary": version.wage or 0,

            "contract_start": (
                version.contract_date_start.strftime("%d/%m/%Y")
                if version.contract_date_start
                else ""
            ),

            "contract_end": (
                version.contract_date_end.strftime("%d/%m/%Y")
                if version.contract_date_end
                else ""
            ),

            "agreement_date": fields.Date.context_today(self).strftime(
                "%d/%m/%Y"
            ),

            # -------------------------------------------------
            # Company
            # -------------------------------------------------

            "company_name": company.name or "",

            "company_address": company.contract_address or "",

            "company_cr": company.contract_cr_number or "",

            "representative": company.contract_representative or "",
        }

        return {
            "doc_ids": docids,
            "doc_model": "hr.employee",
            "docs": employees,
            "employee": employee,
            "company": company,
            "version": version,
            "template": template,
            "values": values,
        }