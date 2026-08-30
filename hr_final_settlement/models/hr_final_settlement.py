# -*- coding: utf-8 -*-
import calendar

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Financial fields that must not change once a settlement is Finalized,
# unless the record has been explicitly reopened by a manager.
PROTECTED_FIELDS = {
    'last_working_date', 'basic_salary', 'transportation_allowance',
    'housing_allowance', 'other_allowance', 'monthly_salary',
    'annual_leave_entitlement', 'annual_leave_used', 'annual_leave_balance',
    'daily_rate', 'final_salary_amount', 'sio_percentage', 'sio_deduction',
    'total_earnings', 'total_deductions', 'net_settlement', 'line_ids',
}


class HrFinalSettlement(models.Model):
    _name = 'hr.final.settlement'
    _description = 'Employee Final Settlement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'settlement_date desc, id desc'

    name = fields.Char(default='/', copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')

    employee_id = fields.Many2one(
        'hr.employee', string="Employee", required=True, tracking=True,
        domain="[('company_id', 'in', [company_id, False])]")
    version_id = fields.Many2one(
        'hr.version', string="Contract (hr.version)", tracking=True,
        help="Employee record (hr.version) this settlement was calculated from. "
             "Odoo 19 no longer has a separate hr.contract model: contract "
             "data lives on hr.version.")
    department_id = fields.Many2one('hr.department', string="Department")
    job_id = fields.Many2one('hr.job', string="Job Position")
    manager_id = fields.Many2one('hr.employee', string="Manager")

    employment_start_date = fields.Date(string="Employment Start Date")
    contract_start_date = fields.Date(string="Contract Start Date")
    contract_end_date = fields.Date(string="Contract End Date")
    last_working_date = fields.Date(string="Last Working Date", required=True, tracking=True)
    settlement_date = fields.Date(default=fields.Date.context_today, required=True)

    departure_reason_id = fields.Many2one('hr.departure.reason', string="Departure Reason", tracking=True)
    departure_description = fields.Text(string="Departure Details")

    # ---- Service duration -------------------------------------------------
    service_years = fields.Integer(readonly=True)
    service_months = fields.Integer(readonly=True)
    service_days = fields.Integer(readonly=True)
    service_duration_display = fields.Char(readonly=True)

    # ---- Salary snapshot ----------------------------------------------------
    basic_salary = fields.Monetary(string="Basic Salary (Wage)")
    transportation_allowance = fields.Monetary()
    housing_allowance = fields.Monetary()
    other_allowance = fields.Monetary()
    monthly_salary = fields.Monetary(
        string="Total Monthly Salary", compute='_compute_monthly_salary', store=True)

    final_settlement_structure_id = fields.Many2one(
        'hr.payroll.structure', string="Final Settlement Salary Structure",
        default=lambda self: self.env.company.fs_settlement_structure_id)

    # ---- Annual leave ---------------------------------------------------
    annual_leave_type_id = fields.Many2one(
        'hr.leave.type', string="Annual Leave Time Off Type",
        default=lambda self: self.env.company.fs_annual_leave_type_id)
    leave_calculation_method = fields.Selection(
        related='company_id.fs_leave_calculation_method', readonly=True)
    annual_leave_entitlement = fields.Float(string="Annual Leave Entitlement (Days)")
    annual_leave_used = fields.Float(string="Annual Leave Used (Days)")
    annual_leave_balance = fields.Float(string="Annual Leave Balance (Days)")

    # ---- Daily rate / final month salary --------------------------------
    daily_rate_method = fields.Selection(
        related='company_id.fs_daily_rate_method', readonly=True, string="Daily Rate Method")
    daily_rate = fields.Monetary(string="Daily Rate")
    daily_rate_basis_display = fields.Char(string="Daily Rate Calculation Basis", readonly=True)

    final_month_calendar_days = fields.Integer(string="Days in Final Month", readonly=True)
    final_month_worked_days = fields.Integer(string="Worked Days in Final Month", readonly=True)
    final_month_period_start = fields.Date(string="Final Month Period Start", readonly=True)
    final_salary_amount = fields.Monetary(string="Final Month Salary", readonly=True)
    final_salary_basis_display = fields.Char(string="Final Salary Calculation Basis", readonly=True)

    leave_encashment_amount = fields.Monetary(
        string="Annual Leave Encashment", compute='_compute_line_rollups', store=True)

    # ---- SIO --------------------------------------------------------------
    sio_enabled = fields.Boolean(default=lambda self: self.env.company.fs_sio_enabled)
    sio_percentage = fields.Float(default=lambda self: self.env.company.fs_sio_percentage)
    sio_base_amount = fields.Monetary(string="SIO Base Amount", readonly=True)
    sio_deduction = fields.Monetary(
        string="SIO Deduction", compute='_compute_line_rollups', store=True)
    sio_deduction_calculated = fields.Monetary(
        string="SIO Deduction (Calculated)",
        help="Technical helper holding the SIO amount computed by _calculate_sio() "
             "before the settlement line is built. The 'SIO Deduction' field above "
             "is always the effective amount rolled up from the settlement line "
             "(so a manual override on that line is reflected everywhere).")

    # ---- Lines & totals ---------------------------------------------------
    line_ids = fields.One2many('hr.final.settlement.line', 'settlement_id', string="Settlement Lines")
    other_earnings_amount = fields.Monetary(compute='_compute_line_rollups', store=True)
    other_deductions_amount = fields.Monetary(compute='_compute_line_rollups', store=True)
    total_earnings = fields.Monetary(compute='_compute_line_rollups', store=True)
    total_deductions = fields.Monetary(compute='_compute_line_rollups', store=True)
    net_settlement = fields.Monetary(compute='_compute_line_rollups', store=True, tracking=True)

    notice_period_served = fields.Char(string="Notice Period Served")

    # ---- Payslip ------------------------------------------------------------
    payslip_id = fields.Many2one('hr.payslip', string="Final Settlement Payslip", copy=False, readonly=True)
    payslip_state = fields.Selection(related='payslip_id.state', string="Payslip Status")

    # ---- Payment Details ------------------------------------------------------
    payment_method = fields.Selection([
        ('bank_transfer', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    ], string="Payment Method")
    bank_name_account = fields.Char(string="Bank Name & Account No")
    cheque_number = fields.Char(string="Cheque No.")
    payment_date = fields.Date(string="Date of Payment")

    # ---- Clearance ----------------------------------------------------------
    employee_acknowledged = fields.Boolean(string="Employee Acknowledgment")
    employee_acknowledgment_date = fields.Date()
    employer_cleared = fields.Boolean(string="Employer Clearance")
    employer_clearance_date = fields.Date()
    clearance_property_returned = fields.Boolean(string="Company Property Returned")
    clearance_equipment_returned = fields.Boolean(string="Company Equipment Returned")
    clearance_files_returned = fields.Boolean(string="Company Files Returned")
    clearance_data_returned = fields.Boolean(string="Company Data Returned")
    authorized_representative_id = fields.Many2one(
        'res.users', string="Employer Authorized Representative",
        default=lambda self: self.env.company.fs_authorized_representative_id)

    prepared_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    reviewed_by = fields.Many2one('res.users', readonly=True)
    approved_by = fields.Many2one('res.users', readonly=True)

    notes = fields.Text()

    state = fields.Selection([
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('hr_review', 'HR Review'),
        ('approved', 'Approved'),
        ('payslip_created', 'Payslip Created'),
        ('finalized', 'Finalized'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True, copy=False)

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.final.settlement') or '/'
        records = super().create(vals_list)
        for record in records:
            if record.employee_id and not record.version_id:
                record._onchange_employee_id()
        return records

    def write(self, vals):
        if not self.env.context.get('fs_allow_finalized_write'):
            protected = PROTECTED_FIELDS & set(vals.keys())
            for record in self:
                if record.state == 'finalized' and protected:
                    raise UserError(_(
                        "This Final Settlement is Finalized and its financial "
                        "data is locked. Use 'Reopen' first if a correction is required."))
        return super().write(vals)

    @api.constrains('last_working_date', 'employment_start_date')
    def _check_dates(self):
        for record in self:
            if record.employment_start_date and record.last_working_date \
                    and record.last_working_date < record.employment_start_date:
                raise ValidationError(_(
                    "Last Working Date cannot be earlier than the Employment Start Date."))

    # =========================================================================
    # Onchange / snapshot helpers
    # =========================================================================

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for record in self:
            employee = record.employee_id
            if not employee:
                continue
            version = employee.version_id
            record.version_id = version.id
            record.department_id = employee.department_id
            record.job_id = employee.job_id
            record.manager_id = employee.parent_id
            record.employment_start_date = employee._get_first_contract_date(no_gap=False) \
                if hasattr(employee, '_get_first_contract_date') else version.contract_date_start
            record.contract_start_date = version.contract_date_start
            record.contract_end_date = version.contract_date_end
            if not record.last_working_date:
                record.last_working_date = employee.departure_date or version.contract_date_end or fields.Date.context_today(record)
            if not record.departure_reason_id:
                record.departure_reason_id = employee.departure_reason_id

    # =========================================================================
    # Computed fields
    # =========================================================================

    @api.depends('basic_salary', 'transportation_allowance', 'housing_allowance', 'other_allowance')
    def _compute_monthly_salary(self):
        for record in self:
            record.monthly_salary = (
                record.basic_salary + record.transportation_allowance
                + record.housing_allowance + record.other_allowance
            )

    @api.depends('line_ids.amount', 'line_ids.line_type', 'line_ids.category')
    def _compute_line_rollups(self):
        for record in self:
            lines = record.line_ids
            earnings = lines.filtered(lambda l: l.line_type == 'earning')
            deductions = lines.filtered(lambda l: l.line_type == 'deduction')
            record.total_earnings = sum(earnings.mapped('amount'))
            record.total_deductions = sum(deductions.mapped('amount'))
            record.net_settlement = record.total_earnings - record.total_deductions
            record.leave_encashment_amount = sum(
                lines.filtered(lambda l: l.category == 'annual_leave').mapped('amount'))
            record.sio_deduction = sum(
                lines.filtered(lambda l: l.category == 'sio').mapped('amount'))
            record.other_earnings_amount = sum(
                lines.filtered(lambda l: l.category == 'other_earning').mapped('amount'))
            record.other_deductions_amount = sum(
                lines.filtered(lambda l: l.category in ('loan', 'advance', 'other_deduction')).mapped('amount'))

    # =========================================================================
    # Calculation engine
    # =========================================================================

    def _get_salary_basis(self):
        """Snapshot the salary components from hr.version (wage lives there
        in Odoo 19; allowances come from the optional hr_employee_allowances
        module if installed)."""
        self.ensure_one()
        version = self.version_id or self.employee_id.version_id
        return {
            'basic_salary': version.wage or 0.0,
            'transportation_allowance': getattr(version, 'transportation_allowance', 0.0) or 0.0,
            'housing_allowance': getattr(version, 'housing_allowance', 0.0) or 0.0,
            'other_allowance': getattr(version, 'other_allowance', 0.0) or 0.0,
        }

    def _compute_service_duration(self):
        """Compute service duration (years/months/days) between the
        Employment Start Date and the Last Working Date."""
        self.ensure_one()
        if not self.employment_start_date or not self.last_working_date:
            self.update({
                'service_years': 0, 'service_months': 0, 'service_days': 0,
                'service_duration_display': '',
            })
            return
        delta = relativedelta(self.last_working_date, self.employment_start_date)
        parts = []
        if delta.years:
            parts.append(_("%s Year(s)") % delta.years)
        if delta.months:
            parts.append(_("%s Month(s)") % delta.months)
        parts.append(_("%s Day(s)") % delta.days)
        self.update({
            'service_years': delta.years,
            'service_months': delta.months,
            'service_days': delta.days,
            'service_duration_display': ', '.join(parts),
        })

    def _get_leave_entitlement_used_balance(self):
        """Use the real Odoo Time Off balance (hr.leave.type.get_allocation_data),
        evaluated as of the Last Working Date, per the configured Annual Leave
        Time Off Type. Returns (entitlement, used, balance)."""
        self.ensure_one()
        leave_type = self.annual_leave_type_id
        if not leave_type:
            raise UserError(_(
                "Annual Leave Time Off Type has not been configured. Configure it on "
                "the Final Settlement or under Payroll > Configuration > Final Settlement."))
        if not self.last_working_date:
            raise UserError(_("Last Working Date is required before calculating leave balance."))

        data = leave_type.get_allocation_data(self.employee_id, target_date=self.last_working_date)
        employee_data = data.get(self.employee_id, [])
        # Each entry is (leave_type_name, info_dict, requires_allocation, leave_type_id) -
        # see hr.leave.type.get_allocation_data(). Only info_dict (index 1) is needed here.
        info = next((entry[1] for entry in employee_data if entry[1]), {})
        entitlement = info.get('max_leaves', 0.0) or 0.0
        used = info.get('leaves_taken', 0.0) or 0.0
        balance = info.get('remaining_leaves', 0.0) or 0.0
        return entitlement, used, balance

    def _get_leave_entitlement(self):
        """Convenience wrapper. Prefer _get_leave_entitlement_used_balance()
        when more than one of entitlement/used/balance is needed, to avoid
        recomputing the Time Off allocation data multiple times."""
        return self._get_leave_entitlement_used_balance()[0]

    def _get_leave_used(self):
        return self._get_leave_entitlement_used_balance()[1]

    def _get_leave_balance(self):
        return self._get_leave_entitlement_used_balance()[2]

    def _get_daily_rate(self):
        self.ensure_one()
        method = self.company_id.fs_daily_rate_method
        divisor = self.company_id.fs_daily_rate_divisor or 30
        if method == 'basic_div_30':
            basis, basis_label = self.basic_salary, _("Basic Salary")
        elif method == 'basic_allowances_div_30':
            basis = self.basic_salary + self.transportation_allowance + self.housing_allowance + self.other_allowance
            basis_label = _("Basic Salary + Allowances")
        else:
            basis, basis_label = self.monthly_salary, _("Monthly Salary")
        daily_rate = (basis / divisor) if divisor else 0.0
        display = _("%(basis)s (%(amount)s) / %(divisor)s") % {
            'basis': basis_label, 'amount': '%.3f' % basis, 'divisor': divisor,
        }
        return daily_rate, display

    def _get_final_month_worked_days(self):
        """Calendar-days basis: from the 1st of the Last Working Date's month
        (or the employment start date if later) through the Last Working Date."""
        self.ensure_one()
        last_day = self.last_working_date
        month_start = last_day.replace(day=1)
        period_start = max(month_start, self.employment_start_date) if self.employment_start_date else month_start
        worked_days = (last_day - period_start).days + 1
        calendar_days = calendar.monthrange(last_day.year, last_day.month)[1]
        return worked_days, calendar_days, period_start

    def _calculate_final_salary(self):
        self.ensure_one()
        divisor = self.company_id.fs_daily_rate_divisor or 30
        worked_days, calendar_days, period_start = self._get_final_month_worked_days()
        amount = (self.monthly_salary / divisor) * worked_days if divisor else 0.0
        display = _("Monthly Salary (%(salary)s) / %(divisor)s x %(days)s Worked Days") % {
            'salary': '%.3f' % self.monthly_salary, 'divisor': divisor, 'days': worked_days,
        }
        self.final_month_worked_days = worked_days
        self.final_month_calendar_days = calendar_days
        self.final_month_period_start = period_start
        self.final_salary_amount = amount
        self.final_salary_basis_display = display
        return amount

    def _calculate_leave_encashment(self):
        self.ensure_one()
        return self.annual_leave_balance * self.daily_rate

    def _calculate_end_of_service(self):
        """End of Service / Gratuity is intentionally NOT implemented in this
        version: the Mr. Adel reference template does not include an EOS
        line. Always returns 0.0. Kept as an explicit extension point
        ('eos' line category already exists) for a future, business-confirmed
        formula."""
        self.ensure_one()
        return 0.0

    def _calculate_sio(self):
        self.ensure_one()
        if not self.sio_enabled:
            self.sio_base_amount = 0.0
            return 0.0
        base = self.final_salary_amount
        self.sio_base_amount = base
        return base * (self.sio_percentage or 0.0) / 100.0

    def _calculate_other_earnings(self):
        """Manually-added 'other earning' lines are preserved across
        recalculation; nothing to compute here."""
        return

    def _calculate_deductions(self):
        """Manually-added deduction lines (loan/advance/other) are preserved
        across recalculation; nothing to compute here."""
        return

    def _prepare_system_line_values(self):
        """Build the vals for the system-calculated lines (final salary,
        leave encashment, SIO), based on the values already computed onto
        the record by action_calculate()."""
        self.ensure_one()
        currency = self.currency_id
        lines = [{
            'sequence': 10,
            'name': _("Final Month Salary"),
            'line_type': 'earning',
            'category': 'final_salary',
            'is_system_line': True,
            'quantity': self.final_month_worked_days,
            'rate': (self.monthly_salary / (self.company_id.fs_daily_rate_divisor or 30)),
            'calculated_amount': self.final_salary_amount,
            'input_code': 'FINAL_SALARY',
            'notes': self.final_salary_basis_display,
        }, {
            'sequence': 20,
            'name': _("Annual Leave Encashment"),
            'line_type': 'earning',
            'category': 'annual_leave',
            'is_system_line': True,
            'quantity': self.annual_leave_balance,
            'rate': self.daily_rate,
            'calculated_amount': round(self.annual_leave_balance * self.daily_rate, currency.decimal_places if currency else 2),
            'input_code': 'FINAL_LEAVE',
            'notes': _("Balance %(balance)s days x Daily Rate %(rate)s") % {
                'balance': self.annual_leave_balance, 'rate': '%.3f' % self.daily_rate},
        }]
        if self.sio_enabled and self.sio_deduction_calculated:
            lines.append({
                'sequence': 50,
                'name': _("Social Insurance Organization (SIO) Deduction"),
                'line_type': 'deduction',
                'category': 'sio',
                'is_system_line': True,
                'quantity': 1.0,
                'rate': self.sio_percentage,
                'calculated_amount': self.sio_deduction_calculated,
                'input_code': 'FINAL_SIO',
                'notes': _("%(pct)s%% of Final Month Salary (%(base)s)") % {
                    'pct': self.sio_percentage, 'base': '%.3f' % self.sio_base_amount},
            })
        return lines

    def action_calculate(self):
        for record in self:
            if record.state in ('finalized', 'cancelled') and not self.env.context.get('fs_allow_finalized_write'):
                raise UserError(_("This settlement is %s and cannot be recalculated. Reopen it first.") % record.state)
            if not record.employee_id.version_id:
                raise UserError(_("No active contract record (hr.version) was found for %s.") % record.employee_id.name)

            record = record.with_context(fs_allow_finalized_write=True)
            basis = record._get_salary_basis()
            record.update(basis)
            record._compute_service_duration()

            entitlement, used, balance = record._get_leave_entitlement_used_balance()
            record.annual_leave_entitlement = entitlement
            record.annual_leave_used = used
            record.annual_leave_balance = balance

            daily_rate, daily_rate_display = record._get_daily_rate()
            record.daily_rate = daily_rate
            record.daily_rate_basis_display = daily_rate_display

            record._calculate_final_salary()
            record.sio_deduction_calculated = record._calculate_sio()
            record._calculate_other_earnings()
            record._calculate_deductions()

            record.line_ids.filtered('is_system_line').unlink()
            record.line_ids = [(0, 0, vals) for vals in record._prepare_system_line_values()]

            if record.state == 'draft':
                record.state = 'calculated'
            record.message_post(body=_("Final Settlement calculated/recalculated."))
        return True

    action_recalculate = action_calculate

    # =========================================================================
    # Workflow actions
    # =========================================================================

    def _validate_settlement(self):
        self.ensure_one()
        if self.state == 'draft':
            raise UserError(_("Calculate the settlement before submitting it for review."))
        if not self.line_ids:
            raise UserError(_("There are no settlement lines to submit."))

    def action_submit_review(self):
        for record in self:
            record._validate_settlement()
            record.state = 'hr_review'

    def action_approve(self):
        for record in self:
            if record.state != 'hr_review':
                raise UserError(_("Only settlements in HR Review can be approved."))
            record.write({'state': 'approved', 'approved_by': self.env.user.id, 'reviewed_by': self.env.user.id})
            record.message_post(body=_("Final Settlement approved by %s.") % self.env.user.name)

    def action_reset_to_draft(self):
        for record in self:
            if record.state in ('payslip_created', 'finalized'):
                raise UserError(_("Use Reopen instead of Reset to Draft once a payslip has been created."))
            record.state = 'draft'

    def action_reopen(self):
        """Manager-only: reopen a finalized/approved settlement for correction.
        Every reopen is logged to the chatter for audit purposes."""
        for record in self:
            if not self.env.user.has_group('hr_final_settlement.group_hr_final_settlement_manager'):
                raise UserError(_("Only a Final Settlement Manager can reopen a settlement."))
            record.with_context(fs_allow_finalized_write=True).write({'state': 'calculated'})
            record.message_post(body=_("Final Settlement reopened by %s for correction.") % self.env.user.name)

    def action_cancel(self):
        for record in self:
            if record.payslip_id and record.payslip_id.state not in ('draft', 'cancel'):
                raise UserError(_("Cancel or reset the linked payslip before cancelling this settlement."))
            record.state = 'cancelled'

    # =========================================================================
    # Payslip integration
    # =========================================================================

    def _check_payslip_period_conflict(self, date_from, date_to):
        self.ensure_one()
        conflicting = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '!=', 'cancel'),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
        ])
        if conflicting:
            raise UserError(_(
                "An existing payslip (%s) covers part or all of the final settlement "
                "period. Please review the existing payslip before creating the final "
                "settlement payslip.") % ', '.join(conflicting.mapped('name')))

    def action_create_payslip(self):
        self.ensure_one()
        if self.payslip_id:
            raise UserError(_("A Final Settlement Payslip already exists for this settlement."))
        if self.state != 'approved':
            raise UserError(_("The settlement must be Approved before creating its payslip."))
        structure = self.final_settlement_structure_id or self.company_id.fs_settlement_structure_id
        if not structure:
            raise UserError(_(
                "The Final Settlement Salary Structure has not been configured. "
                "Configure it under Payroll > Configuration > Final Settlement."))

        date_from = self.last_working_date.replace(day=1)
        date_to = self.last_working_date
        self._check_payslip_period_conflict(date_from, date_to)

        payslip = self.env['hr.payslip'].create({
            'name': _("Final Settlement - %s") % self.employee_id.name,
            'employee_id': self.employee_id.id,
            'version_id': self.version_id.id,
            'struct_id': structure.id,
            'date_from': date_from,
            'date_to': date_to,
        })

        input_amounts = {
            'FINAL_SALARY': self.final_salary_amount,
            'FINAL_LEAVE': self.leave_encashment_amount,
            'FINAL_OTHER': self.other_earnings_amount,
            'FINAL_SIO': self.sio_deduction,
            'FINAL_DEDUCTION': self.other_deductions_amount,
        }
        input_type_by_code = {
            rec.code: rec.id for rec in self.env['hr.payslip.input.type'].search(
                [('code', 'in', list(input_amounts.keys()))])
        }
        payslip.input_line_ids = [
            (0, 0, {
                'input_type_id': input_type_by_code[code],
                'amount': amount,
            })
            for code, amount in input_amounts.items() if code in input_type_by_code
        ]
        payslip.compute_sheet()

        self.with_context(fs_allow_finalized_write=True).write({
            'payslip_id': payslip.id,
            'state': 'payslip_created',
        })
        self.message_post(body=_("Final Settlement Payslip %s created.") % payslip.name)
        return self.action_view_payslip()

    def action_view_payslip(self):
        self.ensure_one()
        if not self.payslip_id:
            return self.action_create_payslip()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'view_mode': 'form',
            'res_id': self.payslip_id.id,
        }

    def action_finalize(self):
        for record in self:
            if record.state != 'payslip_created':
                raise UserError(_("The settlement must have a created payslip before it can be finalized."))
            if record.payslip_id.state not in ('validated', 'paid'):
                raise UserError(_(
                    "Validate the Final Settlement Payslip before finalizing the settlement."))
            record.write({'state': 'finalized'})
            record.message_post(body=_("Final Settlement finalized by %s.") % self.env.user.name)

    def action_archive_employee(self):
        self.ensure_one()
        if self.state != 'finalized':
            raise UserError(_("The settlement must be Finalized before archiving the employee."))
        return self.employee_id.with_context(no_wizard=True, fs_settlement_archive=True).action_archive()

    # =========================================================================
    # Helpers used by the Employee Termination wizard
    # =========================================================================

    @api.model
    def _find_in_progress_settlement(self, employee):
        """A settlement still in progress (not finalized, not cancelled)
        blocks the creation of a duplicate for the same employee. A
        finalized or cancelled settlement does not: a re-hired employee
        who leaves again must be able to get a new one."""
        return self.search([
            ('employee_id', '=', employee.id),
            ('state', 'not in', ('cancelled', 'finalized')),
        ], limit=1)

    # =========================================================================
    # Smart-button navigation
    # =========================================================================

    def action_view_leave_records(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Leave Records"),
            'res_model': 'hr.leave',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.employee_id.id)],
        }
