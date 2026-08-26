# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.powerbi_sync_service import PowerBISyncService


class PowerBISyncWizard(models.TransientModel):
    _name = 'powerbi.sync.wizard'
    _description = 'Power BI Synchronization Wizard'

    config_id = fields.Many2one('powerbi.config', string='Connection', required=True,
                                default=lambda self: self.env.context.get('default_config_id'))
    sync_sales = fields.Boolean(string='Sales', default=True)
    sync_expenses = fields.Boolean(string='Expenses', default=True)
    mode = fields.Selection([
        ('incremental', 'Incremental (only new/changed records since last sync)'),
        ('full', 'Full (clears and rebuilds each Power BI table)'),
    ], string='Mode', default='incremental', required=True)
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    show_full_sync_warning = fields.Boolean(compute='_compute_show_full_sync_warning')

    @api.depends('mode')
    def _compute_show_full_sync_warning(self):
        for wizard in self:
            wizard.show_full_sync_warning = wizard.mode == 'full'

    def action_synchronize(self):
        self.ensure_one()
        if not self.sync_sales and not self.sync_expenses:
            raise UserError(_('Select at least one data type to synchronize.'))
        if not self.env.user.has_group('powerbi_connector.group_powerbi_manager'):
            raise UserError(_('Only Power BI Administrators may run a synchronization.'))

        sync_service = PowerBISyncService(self.env)
        summary = sync_service.run_sync(
            self.config_id,
            sync_type='full' if self.mode == 'full' else 'manual',
            mode=self.mode,
            sync_sales=self.sync_sales,
            sync_lines=self.config_id.sync_sales_lines,
            sync_expenses=self.sync_expenses,
            date_from=self.date_from,
            date_to=self.date_to,
        )

        message = self.config_id._build_notification_message(summary)
        status = summary.get('overall_status')
        notif_type = {'success': 'success', 'partial': 'warning', 'failed': 'danger'}.get(status, 'warning')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Power BI synchronization finished'),
                'message': message,
                'type': notif_type,
                'sticky': status != 'success',
            },
        }
