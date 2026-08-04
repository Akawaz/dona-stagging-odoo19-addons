from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # ==========================================================
    # Contract Information
    # ==========================================================

    contract_start_date = fields.Date(
        string="Contract Start Date"
    )

    contract_salary = fields.Float(
        string="Total Salary (BHD)",
        compute="_compute_contract_salary",
        store=True,
    )

    contract_basic = fields.Float(
        string="Basic Salary"
    )

    contract_housing = fields.Float(
        string="Housing Allowance"
    )

    contract_food = fields.Float(
        string="Food Allowance"
    )

    contract_transport = fields.Float(
        string="Transport Allowance"
    )

    working_hours = fields.Char(
        string="Working Hours",
        default="9 Hours + 1 Hour Break"
    )

    weekly_off = fields.Char(
        string="Weekly Off",
        default="1 Day"
    )

    contract_type = fields.Selection(
        [
            ("open", "Open Ended"),
            ("limited", "Limited"),
        ],
        string="Contract Type",
        default="open",
    )

    probation_period = fields.Integer(
        string="Probation Period (Months)",
        default=3,
    )

    # ==========================================================
    # Compute Methods
    # ==========================================================

    @api.depends("contract_basic", "contract_housing", "contract_food", "contract_transport")
    def _compute_contract_salary(self):
        for employee in self:
            employee.contract_salary = (
                employee.contract_basic
                + employee.contract_housing
                + employee.contract_food
                + employee.contract_transport
            )

    # ==========================================================
    # Print Contract
    # ==========================================================

    def action_print_contract(self):
        self.ensure_one()

        if self.country_id.code == "BH":
            return self.env.ref(
                "hr_contract_print.action_report_bahraini_contract"
            ).report_action(self)

        return self.env.ref(
            "hr_contract_print.action_report_non_bahraini_contract"
        ).report_action(self)

    # ==========================================================
    # Contract Template
    # ==========================================================

    def _get_contract_template(self):
        self.ensure_one()

        template_type = (
            "bahraini"
            if self.country_id.code == "BH"
            else "non_bahraini"
        )

        return self.env["hr.contract.template"].search(
            [
                ("contract_type", "=", template_type),
                ("active", "=", True),
            ],
            limit=1,
        )