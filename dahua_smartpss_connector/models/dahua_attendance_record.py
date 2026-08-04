# -*- coding: utf-8 -*-
from odoo import fields, models


class DahuaAttendanceRecord(models.Model):
    _name = 'dahua.attendance.record'
    _description = 'Raw Dahua Attendance Punch Record'
    _order = 'punch_time desc'

    device_id = fields.Many2one('dahua.device', string='Device', required=True,
                                ondelete='cascade', index=True)
    rec_no = fields.Char(string='Device Record No.', index=True)
    device_user_id = fields.Char(string='Device User ID', index=True)
    card_name = fields.Char(string='Name on Device')
    punch_time = fields.Datetime(string='Punch Time (UTC)', index=True)
    employee_id = fields.Many2one('hr.employee', string='Matched Employee', ondelete='set null')
    attendance_id = fields.Many2one('hr.attendance', string='Attendance Entry', ondelete='set null')
