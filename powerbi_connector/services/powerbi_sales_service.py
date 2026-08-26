# -*- coding: utf-8 -*-
"""Extracts sale.order / sale.order.line records and transforms them into
Power BI "Sales" / "SalesLines" row dicts.

Only fields verified to exist on Odoo 19's core `sale` module are read
unconditionally (name, partner_id, state, date_order, user_id, team_id,
company_id, currency_id, amount_untaxed, amount_tax, amount_total,
invoice_status). Fields added by optional modules (e.g. delivery_status from
sale_stock) are read defensively with hasattr() so this module does not
depend on them and never invents data.
"""
def _iso(dt):
    if not dt:
        return None
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


def _iso_date(d):
    if not d:
        return None
    return d.strftime('%Y-%m-%dT00:00:00')


class PowerBISalesService:
    TABLE_SALES = 'Sales'
    TABLE_SALES_LINES = 'SalesLines'

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
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        return domain

    def extract_orders(self, config, since=None, date_from=None, date_to=None):
        domain = self.build_domain(config, since=since, date_from=date_from, date_to=date_to)
        return self.env['sale.order'].search(domain, order='id')

    # ------------------------------------------------------------------
    def _payment_status(self, order):
        if not hasattr(order, 'invoice_ids') or not order.invoice_ids:
            return 'not_invoiced'
        states = set(order.invoice_ids.mapped('payment_state'))
        if states <= {'paid', 'in_payment'}:
            return 'paid'
        if 'not_paid' in states and len(states) == 1:
            return 'not_paid'
        return 'partial'

    def transform_order(self, order):
        row = {
            'OdooId': order.id,
            'OdooModel': 'sale.order',
            'OrderNumber': order.name or '',
            'OrderDate': _iso(order.date_order),
            'CustomerId': order.partner_id.id or 0,
            'Customer': order.partner_id.display_name or '',
            'SalespersonId': order.user_id.id or 0,
            'Salesperson': order.user_id.name or '',
            'CompanyId': order.company_id.id or 0,
            'Company': order.company_id.name or '',
            'Currency': order.currency_id.name or '',
            'UntaxedAmount': order.amount_untaxed or 0.0,
            'TaxAmount': order.amount_tax or 0.0,
            'TotalAmount': order.amount_total or 0.0,
            'State': order.state or '',
            'InvoiceStatus': order.invoice_status or '',
            'DeliveryStatus': getattr(order, 'delivery_status', False) or '',
            'PaymentStatus': self._payment_status(order),
            'CreateDate': _iso(order.create_date),
            'WriteDate': _iso(order.write_date),
        }
        return row

    def transform_line(self, line):
        product = line.product_id
        return {
            'OdooId': line.id,
            'OdooModel': 'sale.order.line',
            'OrderId': line.order_id.id,
            'OrderNumber': line.order_id.name or '',
            'ProductId': product.id or 0,
            'Product': product.display_name or '',
            'ProductCategoryId': product.categ_id.id or 0,
            'ProductCategory': product.categ_id.name or '',
            'Quantity': line.product_uom_qty or 0.0,
            'UnitPrice': line.price_unit or 0.0,
            'Discount': line.discount or 0.0,
            'TaxAmount': line.price_tax or 0.0,
            'Subtotal': line.price_subtotal or 0.0,
            'Total': line.price_total or 0.0,
            'CompanyId': line.company_id.id or 0,
            'WriteDate': _iso(line.write_date),
        }

    # ------------------------------------------------------------------
    def build_rows(self, config, sync_lines=True, since=None, date_from=None, date_to=None):
        orders = self.extract_orders(config, since=since, date_from=date_from, date_to=date_to)
        sales_rows = [self.transform_order(o) for o in orders]
        line_rows = []
        if sync_lines:
            for order in orders:
                # display_type lines (sections/notes) carry no sellable data.
                for line in order.order_line.filtered(lambda l: not l.display_type):
                    line_rows.append(self.transform_line(line))
        return sales_rows, line_rows, len(orders)
