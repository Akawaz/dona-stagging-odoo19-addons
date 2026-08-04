# -*- coding: utf-8 -*-
import calendar
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError


class DahuaSyncWizard(models.TransientModel):
    _name = 'dahua.sync.wizard'
    _description = 'Sync Dahua Attendance (choose range)'

    device_id = fields.Many2one('dahua.device', string='Device', required=True)
    mode = fields.Selection([
        ('new', 'Only new punches (since last sync)'),
        ('from_date', 'From a specific date'),
        ('full', 'Full history (everything on the device)'),
    ], string='Fetch', default='new', required=True)
    from_date = fields.Datetime(
        string='From Date',
        help='Only punches on or after this date/time are imported (device time).')

    @api.onchange('mode')
    def _onchange_mode(self):
        if self.mode == 'from_date' and not self.from_date:
            # Default to the start of the current month for convenience.
            today = fields.Date.context_today(self)
            self.from_date = datetime(today.year, today.month, 1)

    def action_sync(self):
        self.ensure_one()
        device = self.device_id
        if self.mode == 'full':
            device._sync_one(full=True)
        elif self.mode == 'from_date':
            if not self.from_date:
                raise UserError('Please pick a "From Date".')
            # from_date is stored as naive UTC; device CreateTime is a UTC epoch.
            start_epoch = calendar.timegm(self.from_date.timetuple())
            device._sync_one(start_epoch=start_epoch)
        else:
            device._sync_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Fetched Records',
            'res_model': 'dahua.attendance.record',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', device.id)],
        }
