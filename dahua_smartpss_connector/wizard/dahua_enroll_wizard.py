# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class DahuaEnrollWizard(models.TransientModel):
    _name = 'dahua.enroll.wizard'
    _description = 'Push / Enroll Employees on Dahua Device'

    device_id = fields.Many2one('dahua.device', string='Target Device', required=True)
    mode = fields.Selection([
        ('existing', 'Push existing employees'),
        ('new', 'Create a new employee and push'),
    ], string='Action', default='existing', required=True)

    # Existing employees
    employee_ids = fields.Many2many('hr.employee', string='Employees')

    # New employee
    new_name = fields.Char(string='Employee Name')
    new_person_id = fields.Char(
        string='Dahua Device User ID',
        help='The numeric User ID to assign on the device (must be unique).')
    new_card_no = fields.Char(string='Card Number (optional)')

    result_summary = fields.Text(string='Result', readonly=True)

    @api.onchange('mode')
    def _onchange_mode(self):
        if self.mode == 'new':
            self.employee_ids = False
        else:
            self.new_name = self.new_person_id = self.new_card_no = False

    def action_enroll(self):
        self.ensure_one()
        if not self.device_id:
            raise UserError('Please select a target device.')

        if self.mode == 'new':
            if not self.new_name or not self.new_person_id:
                raise UserError('Please provide both the employee name and the '
                                'Dahua Device User ID.')
            dup = self.env['hr.employee'].search(
                [('dahua_person_id', '=', self.new_person_id)], limit=1)
            if dup:
                raise UserError('Dahua Device User ID "%s" is already assigned to '
                                'employee "%s".' % (self.new_person_id, dup.name))
            employees = self.env['hr.employee'].create({
                'name': self.new_name,
                'dahua_person_id': self.new_person_id,
                'dahua_card_no': self.new_card_no or False,
            })
        else:
            employees = self.employee_ids
            if not employees:
                raise UserError('Please select at least one employee to push.')
            missing = employees.filtered(lambda e: not e.dahua_person_id)
            if missing:
                raise UserError('These employees have no Dahua Device User ID:\n- %s'
                                % '\n- '.join(missing.mapped('name')))

        results = self.device_id.push_employees(employees)

        ok_lines = ['%s (%s)' % (n, a) for n, a in results['ok']]
        fail_lines = ['%s: %s' % (n, err) for n, err in results['failed']]
        summary = 'Pushed successfully (%s):\n- %s' % (
            len(ok_lines), '\n- '.join(ok_lines) if ok_lines else 'none')
        if fail_lines:
            summary += '\n\nFailed (%s):\n- %s' % (len(fail_lines), '\n- '.join(fail_lines))

        # Re-open the wizard showing the result summary
        self.result_summary = summary
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dahua.enroll.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
