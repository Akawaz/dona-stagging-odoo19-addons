# -*- coding: utf-8 -*-
"""Tests the expense extraction/transform layer against real hr.expense
records, and the sync orchestration with the Power BI HTTP layer mocked out
(no live Power BI connection available in this environment).
"""
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from odoo.addons.powerbi_connector.services.powerbi_expense_service import PowerBIExpenseService
from odoo.addons.powerbi_connector.services.powerbi_sync_service import PowerBISyncService


def _mocked_dataset_service():
    instance = MagicMock()
    instance.ensure_dataset.return_value = 'ds-test-1'

    def _push_rows(dataset_id, table_name, rows, batch_size):
        return (1 if rows else 0), (1 if rows else 0), len(rows)

    instance.push_rows.side_effect = _push_rows
    return instance


class TestExpenseSync(TransactionCase):

    def setUp(self):
        super().setUp()
        self.employee = self.env['hr.employee'].create({'name': 'PBI Test Employee'})
        self.expense_product = self.env['product.product'].create({
            'name': 'PBI Test Expense Category',
            'can_be_expensed': True,
            'list_price': 0.0,
        })
        self.expense = self.env['hr.expense'].create({
            'name': 'Taxi fare',
            'employee_id': self.employee.id,
            'product_id': self.expense_product.id,
            'total_amount_currency': 42.5,
        })
        self.config = self.env['powerbi.config'].create({
            'name': 'Test Connection',
            'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
            'workspace_id': 'w',
        })

    def test_transform_expense_fields(self):
        service = PowerBIExpenseService(self.env)
        row = service.transform_expense(self.expense)
        self.assertEqual(row['OdooId'], self.expense.id)
        self.assertEqual(row['OdooModel'], 'hr.expense')
        self.assertEqual(row['Employee'], 'PBI Test Employee')
        self.assertEqual(row['Name'], 'Taxi fare')
        self.assertEqual(row['State'], self.expense.state)

    def test_run_sync_full_creates_success_log(self):
        with patch('odoo.addons.powerbi_connector.services.powerbi_sync_service.PowerBIClient'), \
             patch('odoo.addons.powerbi_connector.services.powerbi_sync_service.PowerBIDatasetService',
                  return_value=_mocked_dataset_service()):
            sync_service = PowerBISyncService(self.env)
            summary = sync_service.run_sync(
                self.config, sync_type='manual', mode='full',
                sync_sales=False, sync_lines=False, sync_expenses=True)

        self.assertEqual(summary['overall_status'], 'success')
        self.assertTrue(self.config.last_sync_expenses_datetime)

        log = self.env['powerbi.sync.log'].search([
            ('config_id', '=', self.config.id), ('data_type', '=', 'expenses')])
        self.assertEqual(len(log), 1)
        self.assertEqual(log.status, 'success')
        self.assertEqual(log.records_processed, 1)

    def test_incremental_domain_uses_write_date(self):
        from odoo import fields
        service = PowerBIExpenseService(self.env)
        since = fields.Datetime.now()
        domain = service.build_domain(self.config, since=since)
        self.assertIn(('write_date', '>=', since), domain)
