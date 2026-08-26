# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PowerBISyncLog(models.Model):
    _name = 'powerbi.sync.log'
    _description = 'Power BI Synchronization Log'
    _order = 'start_datetime desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, default='New')
    config_id = fields.Many2one('powerbi.config', string='Connection', required=True,
                                 ondelete='cascade', index=True)
    company_id = fields.Many2one(related='config_id.company_id', store=True, string='Company')
    sync_type = fields.Selection([
        ('manual', 'Manual'),
        ('automatic', 'Automatic'),
        ('full', 'Full Sync'),
    ], string='Type', required=True, default='manual')
    data_type = fields.Selection([
        ('sales', 'Sales'),
        ('expenses', 'Expenses'),
    ], string='Data', required=True)
    start_datetime = fields.Datetime(string='Started')
    end_datetime = fields.Datetime(string='Finished')
    duration = fields.Float(string='Duration (s)')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ], string='Status', default='pending', required=True)
    records_processed = fields.Integer(string='Records Processed')
    records_created = fields.Integer(string='Rows Pushed')
    records_updated = fields.Integer(string='Rows Updated', help='Not applicable for push datasets '
                                     '(no row-level update); kept for future dataset strategies.')
    records_failed = fields.Integer(string='Records Failed')
    error_message = fields.Text(string='Error Message')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('powerbi.sync.log') or 'New'
        return super().create(vals_list)
