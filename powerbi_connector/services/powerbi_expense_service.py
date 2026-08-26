# -*- coding: utf-8 -*-
"""Extracts hr.expense records and transforms them into Power BI "Expenses"
row dicts.

Only fields verified to exist on Odoo 19's core `hr_expense` module are used
(name, date, employee_id, company_id, product_id, total_amount,
untaxed_amount, tax_amount, currency_id, state, payment_mode,
account_move_id, analytic_distribution, vendor_id). Odoo 19 merged the old
"expense report" (hr.expense.sheet) grouping into hr.expense's own approval
`state`; there is no separate report/sheet_id to export here (the field that
remains, `former_sheet_id`, is an internal legacy integer, not a relation) --
this is a deliberate, verified omission, not a missing feature.
"""
import json


def _iso_datetime(dt):
    if not dt:
        return None
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


def _iso_date(d):
    if not d:
        return None
    return d.strftime('%Y-%m-%dT00:00:00')


class PowerBIExpenseService:
    TABLE_EXPENSES = 'Expenses'

    def __init__(self, env):
        self.env = env

    # ------------------------------------------------------------------
    def build_domain(self, config, since=None, date_from=None, date_to=None):
        domain = []
        if not config.sync_all_companies:
            domain.append(('company_id', '=', config.company_id.id))
        if since:
            domain.append(('write_date', '>=', since))
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        return domain

    def extract_expenses(self, config, since=None, date_from=None, date_to=None):
        domain = self.build_domain(config, since=since, date_from=date_from, date_to=date_to)
        return self.env['hr.expense'].search(domain, order='id')

    # ------------------------------------------------------------------
    def _accounting_status(self, expense):
        move = getattr(expense, 'account_move_id', False)
        if move:
            return move.state or 'posted'
        return 'not_posted'

    def transform_expense(self, expense):
        vendor = getattr(expense, 'vendor_id', False)
        analytic = getattr(expense, 'analytic_distribution', False)
        row = {
            'OdooId': expense.id,
            'OdooModel': 'hr.expense',
            'Name': expense.name or '',
            'EmployeeId': expense.employee_id.id or 0,
            'Employee': expense.employee_id.name or '',
            'Date': _iso_date(expense.date),
            'ProductCategoryId': expense.product_id.id or 0,
            'ProductCategory': expense.product_id.display_name or '',
            'Description': expense.description or '',
            'UntaxedAmount': expense.untaxed_amount or 0.0,
            'TaxAmount': expense.tax_amount or 0.0,
            'TotalAmount': expense.total_amount or 0.0,
            'Currency': expense.currency_id.name or '',
            'CompanyId': expense.company_id.id or 0,
            'Company': expense.company_id.name or '',
            'AnalyticDistribution': json.dumps(analytic) if analytic else '',
            'PaymentMode': expense.payment_mode or '',
            'State': expense.state or '',
            'AccountingStatus': self._accounting_status(expense),
            'VendorId': vendor.id if vendor else 0,
            'Vendor': vendor.display_name if vendor else '',
            'CreateDate': _iso_datetime(expense.create_date),
            'WriteDate': _iso_datetime(expense.write_date),
        }
        return row

    # ------------------------------------------------------------------
    def build_rows(self, config, since=None, date_from=None, date_to=None):
        expenses = self.extract_expenses(config, since=since, date_from=date_from, date_to=date_to)
        rows = [self.transform_expense(e) for e in expenses]
        return rows, len(expenses)
