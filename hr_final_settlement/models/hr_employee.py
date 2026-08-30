# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import RedirectWarning


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
        if not self.final_settlement_count:
            # No settlement yet for this employee: go straight to a blank,
            # pre-filled form instead of an empty list - this is the "Create
            # Final Settlement" affordance for employees who don't yet have one.
            action.update({'view_mode': 'form', 'name': _("Create Final Settlement")})
        elif self.final_settlement_count == 1:
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
        without touching core archiving behavior when the setting is off.

        Requires a Final Settlement to *exist* (any state other than
        Cancelled) - it does not need to be Finalized. Blocking on full
        completion would make "create the settlement, then archive later
        once it's done" impossible, which is exactly the workflow this is
        meant to support."""
        if not self.env.context.get('fs_settlement_archive'):
            for employee in self.filtered('active'):
                if not employee.company_id.fs_require_settlement_before_archive:
                    continue
                has_settlement = self.env['hr.final.settlement'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '!=', 'cancelled'),
                ], limit=1)
                if not has_settlement:
                    message = _(
                        "%s cannot be archived yet: this company requires a Final "
                        "Settlement to exist for the employee first. Use the button "
                        "below to create one now."
                    ) % employee.name
                    action = {
                        'type': 'ir.actions.act_window',
                        'name': _("Create Final Settlement"),
                        'res_model': 'hr.final.settlement',
                        'view_mode': 'form',
                        'target': 'current',
                        'context': {'default_employee_id': employee.id},
                    }
                    raise RedirectWarning(message, action, _("Create Final Settlement"))
        return super().action_archive()
