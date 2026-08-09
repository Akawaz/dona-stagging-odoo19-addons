from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def action_print_contract(self):
        self.ensure_one()

        return self.env.ref(
            "contract_print.action_report_employee_contract"
        ).report_action(self)