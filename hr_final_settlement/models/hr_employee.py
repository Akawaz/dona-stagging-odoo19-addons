# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    final_settlement_ids = fields.One2many(
        'hr.final.settlement', 'employee_id', string="Final Settlements")
    final_settlement_count = fields.Integer(compute='_compute_final_settlement_count')

    @api.depends('final_settlement_ids')
    def _compute_final_settlement_count(self):
        for employee in self:
            employee.final_settlement_count = len(employee.final_settlement_ids)

    def action_view_final_settlements(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _("Final Settlements"),
            'res_model': 'hr.final.settlement',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
        if self.final_settlement_count == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.final_settlement_ids.id,
            })
        else:
            action['view_mode'] = 'list,form'
        return action

    def action_archive(self):
        """Odoo 19's single archiving chokepoint (hit by the list/kanban
        Archive action, the employee form Archive button, and the standard
        Employee Termination wizard's Apply button, which calls this before
        writing departure data - see hr/wizard/hr_departure_wizard.py). Gate
        it here so the requirement is enforced regardless of entry point,
        without touching core archiving behavior when the setting is off."""
        if not self.env.context.get('fs_settlement_archive'):
            for employee in self.filtered('active'):
                if not employee.company_id.fs_require_settlement_before_archive:
                    continue
                finalized = self.env['hr.final.settlement'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'finalized'),
                ], limit=1)
                if not finalized:
                    raise UserError(_(
                        "%s cannot be archived: this company requires a Final "
                        "Settlement to be Finalized before an employee can be "
                        "archived. Use 'Go to Final Settlement' on the "
                        "Employee Termination wizard first."
                    ) % employee.name)
        return super().action_archive()
