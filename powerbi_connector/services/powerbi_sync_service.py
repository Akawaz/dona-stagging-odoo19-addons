# -*- coding: utf-8 -*-
"""Orchestrates a synchronization run: builds the Power BI client once, then
runs each enabled data type (Sales, SalesLines, Expenses) independently so a
failure in one does not stop the others. Used identically by the manual
"Sync Now" / "Full Sync" buttons, the sync wizard, and the automatic cron --
there is exactly one code path that talks to Power BI.
"""
import logging

from odoo import fields

from .powerbi_auth import PowerBIAuth, PowerBIAuthError
from .powerbi_client import PowerBIClient, PowerBIAPIError
from .powerbi_dataset import PowerBIDatasetService, all_table_schemas
from .powerbi_sales_service import PowerBISalesService
from .powerbi_expense_service import PowerBIExpenseService

_logger = logging.getLogger(__name__)


class PowerBISyncService:

    def __init__(self, env):
        self.env = env

    def build_client(self, config):
        auth = PowerBIAuth(
            tenant_id=config.tenant_id,
            client_id=config.client_id,
            client_secret=config.client_secret,
            auth_base_url=config.auth_base_url,
        )
        return PowerBIClient(
            auth=auth,
            workspace_id=config.workspace_id,
            api_base_url=config.api_base_url,
        )

    # ------------------------------------------------------------------
    def run_sync(self, config, sync_type='manual', mode='incremental',
                 sync_sales=True, sync_lines=True, sync_expenses=True,
                 date_from=None, date_to=None):
        """Run one synchronization pass for ``config``.

        Returns a summary dict used to build the user-facing notification:
        {'sales': {...}, 'expenses': {...}, 'overall_status': 'success'|'partial'|'failed'}
        """
        summary = {}
        client = self.build_client(config)
        dataset_service = PowerBIDatasetService(client)

        try:
            dataset_id = dataset_service.ensure_dataset(
                config.dataset_id, config.dataset_name or config.name, all_table_schemas())
            if dataset_id != config.dataset_id:
                config.write({'dataset_id': dataset_id})
        except (PowerBIAuthError, PowerBIAPIError) as exc:
            # Dataset setup failed entirely: log one failed entry per requested
            # data type instead of silently doing nothing.
            for data_type, enabled in (('sales', sync_sales), ('expenses', sync_expenses)):
                if enabled:
                    self._write_failed_log(config, sync_type, data_type, exc)
            config.write({'last_sync_status': 'failed', 'last_sync_message': str(exc)})
            return {'overall_status': 'failed', 'error': str(exc)}

        statuses = []
        if sync_sales:
            result = self._sync_sales(config, dataset_service, dataset_id,
                                      sync_type, mode, sync_lines, date_from, date_to)
            summary['sales'] = result
            statuses.append(result['status'])

        if sync_expenses:
            result = self._sync_expenses(config, dataset_service, dataset_id,
                                         sync_type, mode, date_from, date_to)
            summary['expenses'] = result
            statuses.append(result['status'])

        if statuses and all(s == 'success' for s in statuses):
            overall = 'success'
        elif any(s == 'success' for s in statuses):
            overall = 'partial'
        else:
            overall = 'failed'
        summary['overall_status'] = overall

        config.write({
            'last_sync_status': overall,
            'last_sync_message': self._format_summary_message(summary),
        })
        return summary

    # ------------------------------------------------------------------
    def _sync_sales(self, config, dataset_service, dataset_id,
                    sync_type, mode, sync_lines, date_from, date_to):
        log = self._create_log(config, sync_type, 'sales')
        since = None if (mode == 'full' or date_from or date_to) else config.last_sync_sales_datetime
        try:
            service = PowerBISalesService(self.env)
            sales_rows, line_rows, order_count = service.build_rows(
                config, sync_lines=sync_lines, since=since, date_from=date_from, date_to=date_to)

            if mode == 'full':
                dataset_service.clear_table(dataset_id, service.TABLE_SALES)
                if sync_lines:
                    dataset_service.clear_table(dataset_id, service.TABLE_SALES_LINES)

            dataset_service.push_rows(dataset_id, service.TABLE_SALES, sales_rows, config.batch_size)
            lines_pushed = 0
            if sync_lines:
                _, _, lines_pushed = dataset_service.push_rows(
                    dataset_id, service.TABLE_SALES_LINES, line_rows, config.batch_size)

            self._close_log(log, 'success', records_processed=order_count,
                            records_created=len(sales_rows) + lines_pushed)
            config.write({'last_sync_sales_datetime': fields.Datetime.now()})
            return {'status': 'success', 'records': order_count, 'lines': lines_pushed}
        except (PowerBIAuthError, PowerBIAPIError) as exc:
            self._close_log(log, 'failed', error_message=self._safe_message(exc))
            return {'status': 'failed', 'error': self._safe_message(exc)}
        except Exception as exc:  # noqa: BLE001 - never let a sync crash Odoo
            _logger.exception('Power BI: unexpected error syncing sales for %s', config.name)
            self._close_log(log, 'failed', error_message='Unexpected error: %s' % exc)
            return {'status': 'failed', 'error': str(exc)}

    def _sync_expenses(self, config, dataset_service, dataset_id,
                       sync_type, mode, date_from, date_to):
        log = self._create_log(config, sync_type, 'expenses')
        since = None if (mode == 'full' or date_from or date_to) else config.last_sync_expenses_datetime
        try:
            service = PowerBIExpenseService(self.env)
            rows, count = service.build_rows(config, since=since, date_from=date_from, date_to=date_to)

            if mode == 'full':
                dataset_service.clear_table(dataset_id, service.TABLE_EXPENSES)

            dataset_service.push_rows(dataset_id, service.TABLE_EXPENSES, rows, config.batch_size)

            self._close_log(log, 'success', records_processed=count, records_created=len(rows))
            config.write({'last_sync_expenses_datetime': fields.Datetime.now()})
            return {'status': 'success', 'records': count}
        except (PowerBIAuthError, PowerBIAPIError) as exc:
            self._close_log(log, 'failed', error_message=self._safe_message(exc))
            return {'status': 'failed', 'error': self._safe_message(exc)}
        except Exception as exc:  # noqa: BLE001
            _logger.exception('Power BI: unexpected error syncing expenses for %s', config.name)
            self._close_log(log, 'failed', error_message='Unexpected error: %s' % exc)
            return {'status': 'failed', 'error': str(exc)}

    # ------------------------------------------------------------------
    def _create_log(self, config, sync_type, data_type):
        return self.env['powerbi.sync.log'].create({
            'config_id': config.id,
            'sync_type': sync_type,
            'data_type': data_type,
            'start_datetime': fields.Datetime.now(),
            'status': 'running',
        })

    def _close_log(self, log, status, records_processed=0, records_created=0,
                   records_failed=0, error_message=False):
        end = fields.Datetime.now()
        start = log.start_datetime or end
        log.write({
            'end_datetime': end,
            'duration': (end - start).total_seconds() if start else 0.0,
            'status': status,
            'records_processed': records_processed,
            'records_created': records_created,
            'records_failed': records_failed,
            'error_message': error_message or False,
        })

    @staticmethod
    def _safe_message(exc):
        # PowerBIAuthError/PowerBIAPIError.reason/message never contain the
        # secret or token; still avoid dumping raw technical_detail to users.
        return str(exc)

    @staticmethod
    def _format_summary_message(summary):
        parts = []
        for key in ('sales', 'expenses'):
            if key in summary:
                res = summary[key]
                if res['status'] == 'success':
                    parts.append('%s: %s records synchronized' % (key.capitalize(), res.get('records', 0)))
                else:
                    parts.append('%s: FAILED (%s)' % (key.capitalize(), res.get('error', 'unknown error')))
        return '\n'.join(parts) or 'Nothing to synchronize.'

    def _write_failed_log(self, config, sync_type, data_type, exc):
        log = self._create_log(config, sync_type, data_type)
        self._close_log(log, 'failed', error_message=self._safe_message(exc))
