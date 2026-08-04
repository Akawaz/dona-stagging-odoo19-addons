# -*- coding: utf-8 -*-
from odoo import fields, models


class DahuaSyncLog(models.Model):
    _name = 'dahua.sync.log'
    _description = 'Dahua Sync Log'
    _order = 'create_date desc'

    device_id = fields.Many2one('dahua.device', string='Device', ondelete='cascade', index=True)
    start_time = fields.Datetime(string='Run Started')
    end_time = fields.Datetime(string='Run Finished')
    status = fields.Selection([
        ('success', 'Success'),
        ('partial', 'Partial (some records skipped)'),
        ('error', 'Error'),
    ], string='Status', default='success')
    records_fetched = fields.Integer(string='Records Fetched', default=0)
    records_created = fields.Integer(string='Attendance Entries Created', default=0)
    records_skipped = fields.Integer(string='Records Skipped', default=0)
    message = fields.Text(string='Details')
    debug_log = fields.Text(string='Debug Log (raw protocol exchange)')
