# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class HrDepartureWizard(models.TransientModel):
    _inherit = 'hr.departure.wizard'

    def action_go_to_final_settlement(self):
        """Alternative to the standard 'Apply' button (action_register_departure).

        Unlike Apply, this does NOT archive the employee: it only records the
        departure information and opens (or creates) the Final Settlement
        record(s), so the employee stays active through Calculation, HR
        Review, Approval, Payslip and Finalization. Archiving happens later,
        either via the Final Settlement's own 'Archive Employee' button or
        through the standard Archive action once the settlement is Finalized
        (see hr_employee.py's action_archive() override).
        """
        if not self.employee_ids:
            raise UserError(_("Select at least one employee."))

        Settlement = self.env['hr.final.settlement']
        settlements = Settlement

        for employee in self.employee_ids:
            existing = Settlement._find_in_progress_settlement(employee)
            if existing:
                settlements |= existing
                continue

            employee.write({
                'departure_reason_id': self.departure_reason_id.id,
                'departure_description': self.departure_description,
                'departure_date': self.departure_date,
            })
            if self.set_date_end and employee.version_id and employee.version_id.contract_date_start:
                employee.version_id.write({'contract_date_end': self.departure_date})

            settlement = Settlement.create({
                'employee_id': employee.id,
                'last_working_date': self.departure_date,
                'departure_reason_id': self.departure_reason_id.id,
                'departure_description': html2plaintext(self.departure_description or ''),
            })
            try:
                settlement.action_calculate()
            except UserError as exc:
                settlement.message_post(body=_(
                    "Initial calculation could not be completed automatically: %s "
                    "Please review the configuration and use Calculate manually."
                ) % exc.args[0])
            settlements |= settlement

        if len(settlements) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _("Final Settlement"),
                'res_model': 'hr.final.settlement',
                'view_mode': 'form',
                'res_id': settlements.id,
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _("Final Settlements"),
            'res_model': 'hr.final.settlement',
            'view_mode': 'list,form',
            'domain': [('id', 'in', settlements.ids)],
        }
