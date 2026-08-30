# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHrFinalSettlement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'fs_sio_enabled': True,
            'fs_sio_percentage': 8.0,
            'fs_daily_rate_method': 'monthly_div_30',
            'fs_daily_rate_divisor': 30,
        })

        cls.leave_type = cls.env['hr.leave.type'].create({
            'name': 'Test Annual Leave',
            'requires_allocation': True,
            'allocation_validation_type': 'no_validation',
            'company_id': cls.company.id,
        })
        cls.company.fs_annual_leave_type_id = cls.leave_type

        cls.structure_type = cls.env.ref('hr_final_settlement.structure_type_final_settlement')
        cls.structure = cls.env.ref('hr_final_settlement.structure_final_settlement')
        cls.company.fs_settlement_structure_id = cls.structure
        cls.env.user.write({'group_ids': [(4, cls.env.ref('hr_final_settlement.group_hr_final_settlement_manager').id)]})

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee',
            'company_id': cls.company.id,
        })
        cls.employee.version_id.write({
            'wage': 500.0,
            'contract_date_start': date(2023, 1, 1),
            'structure_type_id': cls.structure_type.id,
        })
        if 'transportation_allowance' in cls.employee.version_id._fields:
            cls.employee.version_id.write({
                'transportation_allowance': 50.0,
                'housing_allowance': 100.0,
                'other_allowance': 50.0,
            })

        allocation = cls.env['hr.leave.allocation'].create({
            'name': 'Annual allocation',
            'employee_id': cls.employee.id,
            'holiday_status_id': cls.leave_type.id,
            'number_of_days': 30,
            'date_from': date(2023, 1, 1),
        })
        allocation.write({'state': 'validate'})

    def _new_settlement(self, last_working_date):
        return self.env['hr.final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_date': last_working_date,
        })

    def test_sequence_and_snapshot(self):
        settlement = self._new_settlement(date(2026, 8, 5))
        self.assertTrue(settlement.name and settlement.name != '/')
        self.assertEqual(settlement.version_id, self.employee.version_id)
        self.assertEqual(settlement.employment_start_date, date(2023, 1, 1))

    def test_date_validation(self):
        with self.assertRaises(ValidationError):
            self._new_settlement(date(2020, 1, 1))

    def test_calculation_flow(self):
        settlement = self._new_settlement(date(2026, 8, 5))
        settlement.action_calculate()

        self.assertEqual(settlement.state, 'calculated')
        # Basic salary always comes from wage; allowances only add up if the
        # optional hr_employee_allowances module is installed in this DB.
        self.assertEqual(settlement.basic_salary, 500.0)
        self.assertEqual(
            settlement.monthly_salary,
            settlement.basic_salary + settlement.transportation_allowance
            + settlement.housing_allowance + settlement.other_allowance)
        monthly_salary = settlement.monthly_salary

        self.assertAlmostEqual(settlement.annual_leave_entitlement, 30.0)
        self.assertAlmostEqual(settlement.annual_leave_balance, 30.0)
        self.assertAlmostEqual(settlement.daily_rate, monthly_salary / 30, places=2)

        # 1-5 August -> 5 worked days
        self.assertEqual(settlement.final_month_worked_days, 5)
        self.assertAlmostEqual(settlement.final_salary_amount, monthly_salary / 30 * 5, places=2)

        # The encashment is deliberately computed from the ROUNDED daily rate
        # (as displayed to HR/the employee), so it reconciles with the
        # printed rate x balance shown on the settlement/report.
        expected_leave_encashment = round(30.0 * settlement.daily_rate, 2)
        self.assertAlmostEqual(settlement.leave_encashment_amount, expected_leave_encashment, places=2)

        # Deduction amounts are stored/displayed negative (SIO, loans, etc.)
        # so totals are a straight sum, never a subtraction.
        expected_sio = settlement.final_salary_amount * 0.08
        self.assertAlmostEqual(settlement.sio_deduction, -expected_sio, places=2)

        expected_earnings = settlement.final_salary_amount + settlement.leave_encashment_amount
        self.assertAlmostEqual(settlement.total_earnings, expected_earnings, places=2)
        self.assertAlmostEqual(settlement.total_deductions, -expected_sio, places=2)
        self.assertAlmostEqual(settlement.net_settlement, expected_earnings - expected_sio, places=2)

    def test_deduction_amounts_are_negative_and_net_is_correct(self):
        """Scenario: Gross 1,000, one deduction entered as a positive 100 ->
        must be stored/displayed as -100, and Net must be 900, not 1,100
        (which is what you'd get from double-subtracting a negative)."""
        settlement = self._new_settlement(date(2026, 8, 5))
        settlement.action_calculate()
        settlement.line_ids.filtered('is_system_line').unlink()
        settlement.line_ids = [(0, 0, {
            'name': 'Gross line', 'line_type': 'earning', 'category': 'other_earning',
            'calculated_amount': 1000.0,
        }), (0, 0, {
            'name': 'Loan deduction', 'line_type': 'deduction', 'category': 'loan',
            'calculated_amount': 100.0,  # entered positive on purpose
        })]
        loan_line = settlement.line_ids.filtered(lambda l: l.category == 'loan')
        self.assertEqual(loan_line.amount, -100.0, "Deduction must be stored negative even if entered positive")
        self.assertEqual(settlement.total_earnings, 1000.0)
        self.assertEqual(settlement.total_deductions, -100.0)
        self.assertEqual(settlement.net_settlement, 900.0)

        # A second deduction, entered already-negative, must not be double-negated.
        settlement.line_ids = [(0, 0, {
            'name': 'Advance deduction', 'line_type': 'deduction', 'category': 'advance',
            'calculated_amount': -50.0,
        })]
        self.assertEqual(settlement.total_deductions, -150.0)
        self.assertEqual(settlement.net_settlement, 850.0)

    def test_zero_leave_balance_zero_encashment(self):
        # An employee with no allocation at all for the configured leave type
        # must show a zero balance and zero encashment, not an error.
        other_employee = self.env['hr.employee'].create({'name': 'No Leave Employee'})
        other_employee.version_id.write({'wage': 300.0, 'contract_date_start': date(2024, 1, 1)})
        settlement2 = self.env['hr.final.settlement'].create({
            'employee_id': other_employee.id,
            'last_working_date': date(2026, 8, 5),
        })
        settlement2.action_calculate()
        self.assertEqual(settlement2.annual_leave_balance, 0.0)
        self.assertEqual(settlement2.leave_encashment_amount, 0.0)

    def test_manual_override_with_audit_trail(self):
        settlement = self._new_settlement(date(2026, 8, 5))
        settlement.action_calculate()
        leave_line = settlement.line_ids.filtered(lambda l: l.category == 'annual_leave')
        original_amount = leave_line.calculated_amount
        leave_line.write({'is_manual_override': True, 'override_amount': original_amount - 10, 'override_reason': 'Manager adjustment'})
        self.assertEqual(leave_line.amount, original_amount - 10)
        self.assertEqual(leave_line.override_uid, self.env.user)
        self.assertTrue(leave_line.override_date)
        # calculated_amount is preserved for audit even though overridden
        self.assertEqual(leave_line.calculated_amount, original_amount)

    def test_state_transitions_and_payslip(self):
        settlement = self._new_settlement(date(2026, 8, 5))
        with self.assertRaises(UserError):
            settlement.action_submit_review()

        settlement.action_calculate()
        settlement.action_submit_review()
        self.assertEqual(settlement.state, 'hr_review')

        with self.assertRaises(UserError):
            settlement.action_create_payslip()

        settlement.action_approve()
        self.assertEqual(settlement.state, 'approved')

        settlement.action_create_payslip()
        self.assertEqual(settlement.state, 'payslip_created')
        self.assertTrue(settlement.payslip_id)

        with self.assertRaises(UserError):
            settlement.action_create_payslip()

        with self.assertRaises(UserError):
            settlement.action_finalize()

        settlement.payslip_id.action_payslip_done()
        settlement.action_finalize()
        self.assertEqual(settlement.state, 'finalized')

        with self.assertRaises(UserError):
            settlement.write({'basic_salary': 999})

        settlement.with_context(fs_allow_finalized_write=True).action_reopen()
        self.assertEqual(settlement.state, 'calculated')

    def test_duplicate_payslip_period_conflict(self):
        settlement = self._new_settlement(date(2026, 8, 5))
        settlement.action_calculate()
        settlement.action_submit_review()
        settlement.action_approve()

        self.env['hr.payslip'].create({
            'name': 'Unrelated existing payslip',
            'employee_id': self.employee.id,
            'version_id': self.employee.version_id.id,
            'struct_id': self.structure.id,
            'date_from': date(2026, 8, 1),
            'date_to': date(2026, 8, 31),
        })
        with self.assertRaises(UserError):
            settlement.action_create_payslip()

    def test_wizard_creates_and_reuses_settlement(self):
        wizard = self.env['hr.departure.wizard'].with_context(
            active_ids=self.employee.ids, employee_termination=True,
        ).create({
            'employee_ids': [(6, 0, self.employee.ids)],
            'departure_date': date(2026, 8, 5),
        })
        action = wizard.action_go_to_final_settlement()
        self.assertEqual(action['res_model'], 'hr.final.settlement')
        self.assertTrue(self.employee.active, "Employee must stay active until the settlement is finalized")

        settlement = self.env['hr.final.settlement'].browse(action['res_id'])
        self.assertEqual(settlement.employee_id, self.employee)

        # Re-opening the wizard for the same employee should reuse it, not duplicate it.
        wizard2 = self.env['hr.departure.wizard'].with_context(
            active_ids=self.employee.ids, employee_termination=True,
        ).create({
            'employee_ids': [(6, 0, self.employee.ids)],
            'departure_date': date(2026, 8, 6),
        })
        action2 = wizard2.action_go_to_final_settlement()
        self.assertEqual(action2['res_id'], settlement.id)

    def test_report_renders(self):
        settlement = self._new_settlement(date(2026, 8, 5))
        settlement.write({
            'notice_period_served': '30 days',
            'payment_method': 'bank_transfer',
            'bank_name_account': 'Test Bank - 1234567890',
            'payment_date': date(2026, 8, 10),
        })
        settlement.action_calculate()
        pdf_content, _content_type = self.env['ir.actions.report']._render_qweb_pdf(
            'hr_final_settlement.action_report_hr_final_settlement', settlement.ids)
        self.assertTrue(pdf_content)
        self.assertGreater(len(pdf_content), 1000)

    def test_archive_gate_blocks_with_actionable_redirect(self):
        self.company.fs_require_settlement_before_archive = True
        employee = self.env['hr.employee'].create({'name': 'Archive Gate Employee', 'company_id': self.company.id})
        with self.assertRaises(RedirectWarning) as cm:
            employee.action_archive()
        # The whole point is it's not a dead-end error: it must carry an
        # action the user can click to go create the settlement.
        action = cm.exception.args[1]
        self.assertEqual(action['res_model'], 'hr.final.settlement')
        self.assertEqual(action['context']['default_employee_id'], employee.id)

    def test_archive_gate_allows_once_settlement_exists_even_if_not_finalized(self):
        """A settlement only needs to EXIST (not be Finalized) to unblock
        archiving - the workflow is meant to support "create it, archive
        later once it's done", not force full completion up front."""
        self.company.fs_require_settlement_before_archive = True
        employee = self.env['hr.employee'].create({'name': 'Draft Settlement Employee', 'company_id': self.company.id})
        self.env['hr.final.settlement'].create({
            'employee_id': employee.id,
            'last_working_date': date(2026, 8, 5),
        })
        employee.action_archive()
        self.assertFalse(employee.active)

    def test_archive_gate_disabled_restores_plain_odoo_behavior(self):
        self.company.fs_require_settlement_before_archive = False
        employee = self.env['hr.employee'].create({'name': 'No Gate Employee', 'company_id': self.company.id})
        employee.action_archive()
        self.assertFalse(employee.active)

    def test_full_workflow_then_archive(self):
        settlement = self._new_settlement(date(2026, 8, 5))
        settlement.action_calculate()
        settlement.action_submit_review()
        settlement.action_approve()
        settlement.action_create_payslip()
        settlement.payslip_id.action_payslip_done()
        settlement.action_finalize()

        settlement.action_archive_employee()
        self.assertFalse(self.employee.active)
