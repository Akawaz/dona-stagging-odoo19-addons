# -*- coding: utf-8 -*-
"""Push-dataset management: ensure the dataset/tables exist, push or clear rows.

Power BI push datasets (defaultMode="Push") are the only Power BI REST API
surface that lets a server push rows without a gateway, Power BI Desktop, or
an interactive user. Their trade-off, which shapes the sync design in
powerbi_sync_service.py, is:

    * POST .../tables/{table}/rows  -> appends rows. There is NO "update a
      row by key" or "delete one row" operation.
    * DELETE .../tables/{table}/rows -> clears ALL rows in that table.

So "incremental sync" here means "append rows changed since last sync" -- it
cannot update a Power BI row in place. "Full Sync" clears each table first so
the table is rebuilt cleanly. See README.md for the operational implications.

Reference:
  https://learn.microsoft.com/rest/api/power-bi/push-datasets/datasets-post-dataset-in-group
  https://learn.microsoft.com/rest/api/power-bi/push-datasets/datasets-post-rows-in-group
"""
import logging

from .powerbi_client import PowerBIAPIError

_logger = logging.getLogger(__name__)

MAX_ROWS_PER_REQUEST = 10000  # Power BI push dataset hard limit per POST


def sales_schema():
    return {
        'name': 'Sales',
        'columns': [
            {'name': 'OdooId', 'dataType': 'Int64'},
            {'name': 'OdooModel', 'dataType': 'string'},
            {'name': 'OrderNumber', 'dataType': 'string'},
            {'name': 'OrderDate', 'dataType': 'DateTime'},
            {'name': 'CustomerId', 'dataType': 'Int64'},
            {'name': 'Customer', 'dataType': 'string'},
            {'name': 'SalespersonId', 'dataType': 'Int64'},
            {'name': 'Salesperson', 'dataType': 'string'},
            {'name': 'CompanyId', 'dataType': 'Int64'},
            {'name': 'Company', 'dataType': 'string'},
            {'name': 'Currency', 'dataType': 'string'},
            {'name': 'UntaxedAmount', 'dataType': 'Double'},
            {'name': 'TaxAmount', 'dataType': 'Double'},
            {'name': 'TotalAmount', 'dataType': 'Double', 'formatString': 'Currency'},
            {'name': 'State', 'dataType': 'string'},
            {'name': 'InvoiceStatus', 'dataType': 'string'},
            {'name': 'DeliveryStatus', 'dataType': 'string'},
            {'name': 'PaymentStatus', 'dataType': 'string'},
            {'name': 'CreateDate', 'dataType': 'DateTime'},
            {'name': 'WriteDate', 'dataType': 'DateTime'},
        ],
    }


def sales_lines_schema():
    return {
        'name': 'SalesLines',
        'columns': [
            {'name': 'OdooId', 'dataType': 'Int64'},
            {'name': 'OdooModel', 'dataType': 'string'},
            {'name': 'OrderId', 'dataType': 'Int64'},
            {'name': 'OrderNumber', 'dataType': 'string'},
            {'name': 'ProductId', 'dataType': 'Int64'},
            {'name': 'Product', 'dataType': 'string'},
            {'name': 'ProductCategoryId', 'dataType': 'Int64'},
            {'name': 'ProductCategory', 'dataType': 'string'},
            {'name': 'Quantity', 'dataType': 'Double'},
            {'name': 'UnitPrice', 'dataType': 'Double'},
            {'name': 'Discount', 'dataType': 'Double'},
            {'name': 'TaxAmount', 'dataType': 'Double'},
            {'name': 'Subtotal', 'dataType': 'Double'},
            {'name': 'Total', 'dataType': 'Double', 'formatString': 'Currency'},
            {'name': 'CompanyId', 'dataType': 'Int64'},
            {'name': 'WriteDate', 'dataType': 'DateTime'},
        ],
    }


def expenses_schema():
    return {
        'name': 'Expenses',
        'columns': [
            {'name': 'OdooId', 'dataType': 'Int64'},
            {'name': 'OdooModel', 'dataType': 'string'},
            {'name': 'Name', 'dataType': 'string'},
            {'name': 'EmployeeId', 'dataType': 'Int64'},
            {'name': 'Employee', 'dataType': 'string'},
            {'name': 'Date', 'dataType': 'DateTime'},
            {'name': 'ProductCategoryId', 'dataType': 'Int64'},
            {'name': 'ProductCategory', 'dataType': 'string'},
            {'name': 'Description', 'dataType': 'string'},
            {'name': 'UntaxedAmount', 'dataType': 'Double'},
            {'name': 'TaxAmount', 'dataType': 'Double'},
            {'name': 'TotalAmount', 'dataType': 'Double', 'formatString': 'Currency'},
            {'name': 'Currency', 'dataType': 'string'},
            {'name': 'CompanyId', 'dataType': 'Int64'},
            {'name': 'Company', 'dataType': 'string'},
            {'name': 'AnalyticDistribution', 'dataType': 'string'},
            {'name': 'PaymentMode', 'dataType': 'string'},
            {'name': 'State', 'dataType': 'string'},
            {'name': 'AccountingStatus', 'dataType': 'string'},
            {'name': 'VendorId', 'dataType': 'Int64'},
            {'name': 'Vendor', 'dataType': 'string'},
            {'name': 'CreateDate', 'dataType': 'DateTime'},
            {'name': 'WriteDate', 'dataType': 'DateTime'},
        ],
    }


def all_table_schemas():
    return [sales_schema(), sales_lines_schema(), expenses_schema()]


class PowerBIDatasetService:
    """Create/find the push dataset and push or clear rows in its tables."""

    def __init__(self, client):
        self.client = client

    # ------------------------------------------------------------------
    def get_dataset(self, dataset_id):
        try:
            return self.client.get(self.client.workspace_path('datasets/%s' % dataset_id))
        except PowerBIAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def find_dataset_by_name(self, name):
        result = self.client.get(self.client.workspace_path('datasets'))
        for dataset in result.get('value', []):
            if dataset.get('name') == name:
                return dataset.get('id')
        return None

    def create_dataset(self, name, table_schemas):
        body = {
            'name': name,
            'defaultMode': 'Push',
            'tables': [
                {'name': t['name'], 'columns': t['columns']} for t in table_schemas
            ],
            'relationships': [
                {
                    'name': 'SalesLinesToSales',
                    'fromTable': 'SalesLines',
                    'fromColumn': 'OrderId',
                    'toTable': 'Sales',
                    'toColumn': 'OdooId',
                    'crossFilteringBehavior': 'OneDirection',
                },
            ],
        }
        result = self.client.post(self.client.workspace_path('datasets?defaultRetentionPolicy=basicFIFO'),
                                  json_body=body)
        dataset_id = result.get('id')
        if not dataset_id:
            raise PowerBIAPIError('Power BI did not return a dataset ID when creating "%s".' % name)
        _logger.info('Power BI: created push dataset "%s" (%s)', name, dataset_id)
        return dataset_id

    def ensure_dataset(self, dataset_id, dataset_name, table_schemas=None):
        """Return a usable dataset ID: verify the configured one, else find-or-create by name."""
        table_schemas = table_schemas or all_table_schemas()
        if dataset_id:
            existing = self.get_dataset(dataset_id)
            if existing:
                return dataset_id
            _logger.warning('Power BI: configured dataset %s no longer exists, looking up by name', dataset_id)

        found_id = self.find_dataset_by_name(dataset_name)
        if found_id:
            return found_id

        return self.create_dataset(dataset_name, table_schemas)

    # ------------------------------------------------------------------
    def clear_table(self, dataset_id, table_name):
        _logger.info('Power BI: clearing all rows from table %s', table_name)
        self.client.delete(self.client.workspace_path('datasets/%s/tables/%s/rows' % (dataset_id, table_name)))

    def push_rows(self, dataset_id, table_name, rows, batch_size=500):
        """Push rows in batches; returns (batches_succeeded, batches_total, rows_pushed).

        Stops at the first failing batch so already-pushed batches are not
        silently hidden -- the caller records rows_pushed as a partial result.
        """
        batch_size = min(max(int(batch_size or 500), 1), MAX_ROWS_PER_REQUEST)
        total = len(rows)
        if total == 0:
            return 0, 0, 0

        batches = [rows[i:i + batch_size] for i in range(0, total, batch_size)]
        pushed = 0
        for index, batch in enumerate(batches, start=1):
            self.client.post(
                self.client.workspace_path('datasets/%s/tables/%s/rows' % (dataset_id, table_name)),
                json_body={'rows': batch})
            pushed += len(batch)
            _logger.info('Power BI: table %s batch %s/%s pushed (%s rows)',
                         table_name, index, len(batches), len(batch))
        return len(batches), len(batches), pushed
