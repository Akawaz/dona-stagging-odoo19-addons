# -*- coding: utf-8 -*-
"""Tests the sales extraction/transform layer against real Odoo sale.order
records, and the sync orchestration (logging, incremental filtering, last-
sync timestamps) with the Power BI HTTP layer replaced by mocks -- there is
no live Power BI connection available in this environment.
"""
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.powerbi_connector.services.powerbi_sales_service import PowerBISalesService
from odoo.addons.powerbi_connector.services.powerbi_sync_service import PowerBISyncService


def _mocked_dataset_service():
    instance = MagicMock()
    instance.ensure_dataset.return_value = 'ds-test-1'

    def _push_rows(dataset_id, table_name, rows, batch_size):
        return (1 if rows else 0), (1 if rows else 0), len(rows)

    instance.push_rows.side_effect = _push_rows
    return instance


class TestSalesSync(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'PBI Test Customer'})
        self.product = self.env['product.product'].create({
            'name': 'PBI Test Product', 'list_price': 100.0,
        })
        self.order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 2,
                'price_unit': 50.0,
            })],
        })
        self.config = self.env['powerbi.config'].create({
            'name': 'Test Connection',
            'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
            'workspace_id': 'w',
        })

    def test_transform_order_fields(self):
        service = PowerBISalesService(self.env)
        row = service.transform_order(self.order)
        self.assertEqual(row['OdooId'], self.order.id)
        self.assertEqual(row['OdooModel'], 'sale.order')
        self.assertEqual(row['Customer'], 'PBI Test Customer')
        self.assertEqual(row['TotalAmount'], self.order.amount_total)
        self.assertIn('T', row['OrderDate'] or '')

    def test_transform_line_fields(self):
        service = PowerBISalesService(self.env)
        line = self.order.order_line[0]
        row = service.transform_line(line)
        self.assertEqual(row['OrderId'], self.order.id)
        self.assertEqual(row['Product'], self.product.display_name)
        self.assertEqual(row['Quantity'], 2)
        self.assertEqual(row['UnitPrice'], 50.0)

    def test_run_sync_full_creates_success_log_and_updates_timestamp(self):
        with patch('odoo.addons.powerbi_connector.services.powerbi_sync_service.PowerBIClient'), \
             patch('odoo.addons.powerbi_connector.services.powerbi_sync_service.PowerBIDatasetService',
                  return_value=_mocked_dataset_service()):
            sync_service = PowerBISyncService(self.env)
            summary = sync_service.run_sync(
                self.config, sync_type='manual', mode='full',
                sync_sales=True, sync_lines=True, sync_expenses=False)

        self.assertEqual(summary['overall_status'], 'success')
        self.assertTrue(self.config.last_sync_sales_datetime)
        self.assertEqual(self.config.last_sync_status, 'success')

        log = self.env['powerbi.sync.log'].search([
            ('config_id', '=', self.config.id), ('data_type', '=', 'sales')])
        self.assertEqual(len(log), 1)
        self.assertEqual(log.status, 'success')
        self.assertEqual(log.records_processed, 1)

    def test_incremental_domain_uses_write_date(self):
        service = PowerBISalesService(self.env)
        since = fields.Datetime.now()
        domain = service.build_domain(self.config, since=since)
        self.assertIn(('write_date', '>=', since), domain)

    def test_run_sync_continues_expenses_when_sales_fails(self):
        dataset_service = _mocked_dataset_service()
        dataset_service.push_rows.side_effect = [
            Exception('simulated Sales push failure'),
            (0, 0, 0),
        ]
        with patch('odoo.addons.powerbi_connector.services.powerbi_sync_service.PowerBIClient'), \
             patch('odoo.addons.powerbi_connector.services.powerbi_sync_service.PowerBIDatasetService',
                  return_value=dataset_service):
            sync_service = PowerBISyncService(self.env)
            summary = sync_service.run_sync(
                self.config, sync_type='manual', mode='full',
                sync_sales=True, sync_lines=False, sync_expenses=True)

        self.assertEqual(summary['sales']['status'], 'failed')
        # Expenses table push (second call) still ran even though Sales failed.
        self.assertIn('expenses', summary)
