import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    product_cost = fields.Float(
        string="Reference Price",
        compute='_compute_product_cost',
        store=False,
        digits=(16, 2),
    )
    comparison_basis = fields.Selection(
        selection=[
            ('vendor', 'Same Vendor'),
            ('any', 'Any Vendor'),
            ('none', 'No History'),
        ],
        string="Compared Against",
        compute='_compute_product_cost',
        store=False,
    )
    price_vs_cost_percent = fields.Float(
        string="Over Reference %",
        compute='_compute_price_vs_cost_percent',
        store=False,
        digits=(16, 2),
    )
    is_above_cost = fields.Boolean(
        string="Above Reference",
        compute='_compute_is_above_cost',
        store=False,
    )
    price_alert_icon = fields.Char(
        string="Alert",
        compute='_compute_price_alert_icon',
        store=False,
    )
    line_alert_sent = fields.Boolean(
        string="Line Alert Sent",
        default=False,
        copy=False,
        help="True if review activities have already been created for this line.",
    )

    @api.depends('price_unit', 'product_id', 'order_id.partner_id')
    def _compute_product_cost(self):
        for line in self:
            if not line.product_id or not line.order_id.partner_id:
                line.product_cost = 0.0
                line.comparison_basis = 'none'
                continue

            # 1. Same vendor last confirmed price
            same_vendor = self.env['purchase.order.line'].search([
                ('product_id', '=', line.product_id.id),
                ('order_id.partner_id', '=', line.order_id.partner_id.id),
                ('order_id.state', 'in', ('purchase', 'done')),
                ('order_id.id', '!=', line.order_id.id),
            ])
            same_vendor = same_vendor.sorted(
                key=lambda l: l.order_id.date_approve or l.order_id.create_date,
                reverse=True,
            )
            if same_vendor:
                line.product_cost = same_vendor[:1].price_unit
                line.comparison_basis = 'vendor'
                continue

            # 2. Any vendor last confirmed price
            any_vendor = self.env['purchase.order.line'].search([
                ('product_id', '=', line.product_id.id),
                ('order_id.state', 'in', ('purchase', 'done')),
                ('order_id.id', '!=', line.order_id.id),
            ])
            any_vendor = any_vendor.sorted(
                key=lambda l: l.order_id.date_approve or l.order_id.create_date,
                reverse=True,
            )
            if any_vendor:
                line.product_cost = any_vendor[:1].price_unit
                line.comparison_basis = 'any'
                continue

            # 3. Never purchased — no alert
            line.product_cost = 0.0
            line.comparison_basis = 'none'

    @api.depends('price_unit', 'product_cost')
    def _compute_price_vs_cost_percent(self):
        for line in self:
            if line.product_cost > 0:
                line.price_vs_cost_percent = round(
                    ((line.price_unit - line.product_cost) / line.product_cost) * 100, 2
                )
            else:
                line.price_vs_cost_percent = 0.0

    @api.depends('price_unit', 'product_cost')
    def _compute_is_above_cost(self):
        for line in self:
            line.is_above_cost = (
                line.price_unit > line.product_cost and line.product_cost > 0
            )

    @api.depends('is_above_cost')
    def _compute_price_alert_icon(self):
        for line in self:
            line.price_alert_icon = '⚠️' if line.is_above_cost else ''

    def _create_line_review_activity(self):
        """Create review activities for Purchase and Accounting managers for this line only."""
        self.ensure_one()
        if self.line_alert_sent or not self.is_above_cost:
            return

        symbol = self.order_id.currency_id.symbol or ''
        basis_tag = {
            'vendor': _('(same vendor)'),
            'any': _('(any vendor)'),
        }.get(self.comparison_basis, '')

        note_body = _(
            "%(product)s %(basis)s: Last %(symbol)s%(cost)s → PO Price %(symbol)s%(price)s (+%(pct)s%%)",
            product=self.product_id.display_name,
            basis=basis_tag,
            symbol=symbol,
            cost=self.product_cost,
            price=self.price_unit,
            pct=self.price_vs_cost_percent,
        )

        purchase_group = self.env.ref('purchase.group_purchase_manager', raise_if_not_found=False)
        account_group = self.env.ref('account.group_account_manager', raise_if_not_found=False)

        user_ids = set()
        if purchase_group:
            user_ids.update(purchase_group.user_ids.ids)
        if account_group:
            user_ids.update(account_group.user_ids.ids)

        if not user_ids:
            _logger.warning("No Purchase or Accounting managers found to notify for PO %s", self.order_id.name)
            return

        # Check for existing activities on this PO for these users FOR THIS PRODUCT
        product_name = self.product_id.display_name
        existing = self.env['mail.activity'].search([
            ('res_model', '=', 'purchase.order'),
            ('res_id', '=', self.order_id.id),
            ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_todo').id),
            ('user_id', 'in', list(user_ids)),
        ])
        existing_user_ids = set()
        for act in existing:
            if product_name in (act.summary or ''):
                existing_user_ids.add(act.user_id.id)

        notified = 0
        for user in self.env['res.users'].browse(list(user_ids)):
            if user.id in existing_user_ids:
                continue
            self.order_id.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_("Review Price Increase – %s on %s") % (self.product_id.display_name, self.order_id.name),
                note=note_body,
                user_id=user.id,
            )
            notified += 1

        if notified:
            self.order_id.message_post(
                body=_("Price review activity created for %s on %s (%s manager(s))",
                       self.product_id.display_name, self.order_id.name, notified),
                subtype_xmlid='mail.mt_note',
            )

        self.line_alert_sent = True

    def action_show_price_history(self):
        """Show cost comparison notification and create review activities for admins."""
        self.ensure_one()

        basis_label = {
            'vendor': _('last vendor price'),
            'any': _('last purchase price'),
            'none': _('reference price'),
        }.get(self.comparison_basis, _('reference price'))

        if not self.is_above_cost:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Price OK'),
                    'message': _('Purchase price is at or below %(basis)s for %(product)s.',
                                 basis=basis_label, product=self.product_id.display_name),
                    'type': 'info',
                    'sticky': False,
                },
            }

        symbol = self.order_id.currency_id.symbol or ''
        basis_short = {
            'vendor': _('Last vendor price'),
            'any': _('Last purchase price'),
        }.get(self.comparison_basis, _('Reference price'))

        # Already alerted for this line — just show info
        if self.line_alert_sent:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Price Above Reference – %s') % self.product_id.display_name,
                    'message': _(
                        "%(basis)s: %(symbol)s%(cost)s → PO Price: %(symbol)s%(price)s  (↑ +%(pct)s%%). "
                        "Alert already sent for this product.",
                        basis=basis_short,
                        symbol=symbol,
                        cost=self.product_cost,
                        price=self.price_unit,
                        pct=self.price_vs_cost_percent,
                    ),
                    'type': 'danger',
                    'sticky': False,
                },
            }

        # First time for this line — create activities
        self._create_line_review_activity()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Price Alert Sent'),
                'message': _(
                    "%(basis)s: %(symbol)s%(cost)s → PO Price: %(symbol)s%(price)s  (↑ +%(pct)s%%). "
                    "Review activity created for admins.",
                    basis=basis_short,
                    symbol=symbol,
                    cost=self.product_cost,
                    price=self.price_unit,
                    pct=self.price_vs_cost_percent,
                ),
                'type': 'danger',
                'sticky': False,
            },
        }
