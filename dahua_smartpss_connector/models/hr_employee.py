# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dahua_person_id = fields.Char(
        string='Dahua Device User ID (SmartPSS)',
        help='The User ID as enrolled on the Dahua device (SmartPSS person/user ID). '
             'Used to match punch records pulled from the device to this employee.',
        copy=False,
    )
    dahua_card_no = fields.Char(
        string='Dahua Card Number',
        help='Optional RFID/access card number to push to the device with this user.',
        copy=False,
    )
    dahua_enrolled = fields.Boolean(
        string='Enrolled on Device', readonly=True, copy=False,
        help='Set automatically after the employee is successfully pushed to a device.')
    dahua_last_pushed_device_id = fields.Many2one(
        'dahua.device', string='Last Pushed To', readonly=True, copy=False)

    def action_push_to_dahua(self):
        """Open the enrollment wizard pre-filled with the selected employees."""
        missing = self.filtered(lambda e: not e.dahua_person_id)
        if missing:
            raise UserError(
                'These employees have no "Dahua Device User ID" set:\n- %s\n\n'
                'Set a unique device user ID first.'
                % '\n- '.join(missing.mapped('name')))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Push Employees to Dahua Device',
            'res_model': 'dahua.enroll.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_mode': 'existing',
                'default_employee_ids': [(6, 0, self.ids)],
            },
        }
