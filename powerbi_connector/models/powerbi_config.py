# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.powerbi_auth import PowerBIAuth, PowerBIAuthError
from ..services.powerbi_client import PowerBIClient, PowerBIAPIError
from ..services.powerbi_dataset import PowerBIDatasetService
from ..services.powerbi_sync_service import PowerBISyncService

_logger = logging.getLogger(__name__)

FREQUENCY_TO_MINUTES = {
    'manual': 0,
    '15_min': 15,
    '30_min': 30,
    'hourly': 60,
    '6_hours': 360,
    'daily': 1440,
}


class PowerBIConfig(models.Model):
    _name = 'powerbi.config'
    _description = 'Power BI Connection'
    _order = 'name'

    name = fields.Char(string='Connection Name', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company)
    sync_all_companies = fields.Boolean(string='Sync All Allowed Companies', default=False,
                                        help='If enabled, records from every company are '
                                        'synchronized instead of only the Company above.')

    # -- Microsoft Entra ID / Power BI connection --------------------------
    tenant_id = fields.Char(string='Tenant ID', required=True,
                            help='Microsoft Entra (Azure AD) Directory (tenant) ID.')
    client_id = fields.Char(string='Client ID', required=True,
                            help='Application (client) ID of the Entra app registration '
                            'used as the service principal.')
    client_secret = fields.Char(string='Client Secret', required=True,
                                groups='powerbi_connector.group_powerbi_manager')
    authentication_type = fields.Selection([
        ('service_principal', 'Service Principal (Client Secret)'),
    ], string='Authentication Type', default='service_principal', required=True)
    workspace_id = fields.Char(string='Workspace ID', required=True,
                               help='Power BI workspace (group) ID. "My workspace" is not '
                               'supported for service-principal access.')
    dataset_name = fields.Char(string='Dataset Name', default='Odoo Sales & Expenses', required=True)
    dataset_id = fields.Char(string='Dataset ID', readonly=True, copy=False,
                             help='Filled in automatically the first time a sync creates or '
                             'finds the dataset. You may also paste an existing push dataset '
                             'ID here to reuse it.')
    api_base_url = fields.Char(string='API Base URL', default='https://api.powerbi.com/v1.0/myorg',
                               required=True)
    auth_base_url = fields.Char(string='Auth Base URL', default='https://login.microsoftonline.com',
                                required=True)

    # -- Synchronization options --------------------------------------------
    sync_sales = fields.Boolean(string='Sync Sales', default=True)
    sync_sales_lines = fields.Boolean(string='Sync Sales Lines', default=True)
    sync_expenses = fields.Boolean(string='Sync Expenses', default=True)
    sync_frequency = fields.Selection([
        ('manual', 'Manual'),
        ('15_min', 'Every 15 minutes'),
        ('30_min', 'Every 30 minutes'),
        ('hourly', 'Hourly'),
        ('6_hours', 'Every 6 hours'),
        ('daily', 'Daily'),
    ], string='Sync Frequency', default='manual', required=True)
    batch_size = fields.Integer(string='Batch Size', default=500,
                                help='Rows sent per Power BI API call (max 10,000).')

    # -- Status --------------------------------------------------------------
    connection_state = fields.Selection([
        ('not_tested', 'Not Tested'),
        ('success', 'Connected'),
        ('failed', 'Failed'),
    ], string='Connection Status', default='not_tested', readonly=True, copy=False)
    last_test_result = fields.Text(string='Last Test Result', readonly=True, copy=False)
    last_sync_sales_datetime = fields.Datetime(string='Last Sales Sync', readonly=True, copy=False)
    last_sync_expenses_datetime = fields.Datetime(string='Last Expenses Sync', readonly=True, copy=False)
    last_cron_run_datetime = fields.Datetime(string='Last Automatic Run', readonly=True, copy=False)
    last_sync_status = fields.Selection([
        ('none', 'Never Run'),
        ('success', 'Success'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ], string='Last Sync Result', default='none', readonly=True, copy=False)
    last_sync_message = fields.Text(string='Last Sync Details', readonly=True, copy=False)

    sync_log_ids = fields.One2many('powerbi.sync.log', 'config_id', string='Sync Logs')
    sync_log_count = fields.Integer(compute='_compute_sync_log_count')

    def _compute_sync_log_count(self):
        counts = self.env['powerbi.sync.log']._read_group(
            [('config_id', 'in', self.ids)], ['config_id'], ['__count'])
        mapped = {config.id: count for config, count in counts}
        for record in self:
            record.sync_log_count = mapped.get(record.id, 0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _require_manager(self):
        if not self.env.user.has_group('powerbi_connector.group_powerbi_manager'):
            raise UserError(_('Only Power BI Administrators may perform this action.'))

    def _build_client(self):
        self.ensure_one()
        auth = PowerBIAuth(self.tenant_id, self.client_id, self.client_secret, self.auth_base_url)
        return PowerBIClient(auth, self.workspace_id, self.api_base_url)

    # ------------------------------------------------------------------
    # Test Connection
    # ------------------------------------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        self._require_manager()
        lines = []
        ok = True

        client = self._build_client()
        try:
            client.auth.get_token()
            lines.append(_('Microsoft authentication: OK'))
        except PowerBIAuthError as exc:
            lines.append(_('Microsoft authentication: FAILED\nReason: %s') % exc.reason)
            ok = False

        if ok:
            try:
                groups = client.get('groups', params={'$top': 5000}).get('value', [])
                if any(g.get('id') == self.workspace_id for g in groups):
                    lines.append(_('Workspace access: OK'))
                else:
                    ok = False
                    lines.append(_(
                        'Workspace access: FAILED\nReason: The service principal cannot see '
                        'workspace %s. Either the Workspace ID is wrong, or the service '
                        'principal (or its security group) has not been added as a Member/Admin '
                        'of that workspace.') % self.workspace_id)
            except PowerBIAPIError as exc:
                ok = False
                lines.append(_('Workspace access: FAILED\nReason: %s') % str(exc))

        if ok and self.dataset_id:
            dataset_service = PowerBIDatasetService(client)
            try:
                dataset = dataset_service.get_dataset(self.dataset_id)
                if dataset:
                    lines.append(_('Dataset access: OK (%s)') % dataset.get('name', self.dataset_id))
                else:
                    ok = False
                    lines.append(_('Dataset access: FAILED\nReason: Dataset %s was not found '
                                   'in this workspace.') % self.dataset_id)
            except PowerBIAPIError as exc:
                ok = False
                lines.append(_('Dataset access: FAILED\nReason: %s') % str(exc))
        elif ok:
            lines.append(_('Dataset access: SKIPPED (no dataset created yet - it will be '
                           'created automatically on first sync)'))

        self._finish_test(ok, lines)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection successful') if ok else _('Power BI connection failed'),
                'message': self._format_test_message(lines),
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
            },
        }

    def _finish_test(self, ok, lines):
        self.write({
            'connection_state': 'success' if ok else 'failed',
            'last_test_result': self._format_test_message(lines),
        })

    @staticmethod
    def _format_test_message(lines):
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Synchronization
    # ------------------------------------------------------------------
    def action_sync_now(self):
        self.ensure_one()
        self._require_manager()
        return self._run_and_notify(sync_type='manual', mode='incremental')

    def action_full_sync(self):
        self.ensure_one()
        self._require_manager()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Full Synchronization'),
            'res_model': 'powerbi.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_mode': 'full',
            },
        }

    def action_open_sync_wizard(self):
        self.ensure_one()
        self._require_manager()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Synchronize with Power BI'),
            'res_model': 'powerbi.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_config_id': self.id, 'default_mode': 'incremental'},
        }

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Logs'),
            'res_model': 'powerbi.sync.log',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }

    def _run_and_notify(self, sync_type, mode, date_from=None, date_to=None):
        self.ensure_one()
        sync_service = PowerBISyncService(self.env)
        summary = sync_service.run_sync(
            self, sync_type=sync_type, mode=mode,
            sync_sales=self.sync_sales, sync_lines=self.sync_sales_lines,
            sync_expenses=self.sync_expenses, date_from=date_from, date_to=date_to)

        notif_type = {'success': 'success', 'partial': 'warning', 'failed': 'danger'}.get(
            summary.get('overall_status'), 'warning')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Power BI synchronization %s') % (
                    _('completed') if summary.get('overall_status') == 'success' else _('finished with issues')),
                'message': self._build_notification_message(summary),
                'type': notif_type,
                'sticky': summary.get('overall_status') != 'success',
            },
        }

    @staticmethod
    def _build_notification_message(summary):
        parts = []
        sales = summary.get('sales')
        if sales:
            if sales['status'] == 'success':
                parts.append(_('Sales: %s orders synchronized (%s line rows).') % (
                    sales.get('records', 0), sales.get('lines', 0)))
            else:
                parts.append(_('Sales: FAILED - %s') % sales.get('error'))
        expenses = summary.get('expenses')
        if expenses:
            if expenses['status'] == 'success':
                parts.append(_('Expenses: %s records synchronized.') % expenses.get('records', 0))
            else:
                parts.append(_('Expenses: FAILED - %s') % expenses.get('error'))
        if 'error' in summary and not sales and not expenses:
            parts.append(str(summary['error']))
        return '\n'.join(parts) or _('Nothing was synchronized (no data type enabled).')

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_auto_sync(self):
        # Runs with elevated rights regardless of the cron's assigned user so
        # automatic sync is never blocked by the record rules that scope
        # interactive (non-manager) access.
        configs = self.sudo().search([('active', '=', True), ('sync_frequency', '!=', 'manual')])
        sync_service = PowerBISyncService(self.env(su=True))
        for config in configs:
            if not config._is_due():
                continue
            try:
                config.last_cron_run_datetime = fields.Datetime.now()
                sync_service.run_sync(
                    config, sync_type='automatic', mode='incremental',
                    sync_sales=config.sync_sales, sync_lines=config.sync_sales_lines,
                    sync_expenses=config.sync_expenses)
            except Exception:  # noqa: BLE001 - one bad config must not block the others
                _logger.exception('Power BI: automatic sync failed for connection "%s"', config.name)

    def _is_due(self):
        self.ensure_one()
        minutes = FREQUENCY_TO_MINUTES.get(self.sync_frequency, 0)
        if not minutes:
            return False
        if not self.last_cron_run_datetime:
            return True
        elapsed = fields.Datetime.now() - self.last_cron_run_datetime
        return elapsed.total_seconds() >= minutes * 60
