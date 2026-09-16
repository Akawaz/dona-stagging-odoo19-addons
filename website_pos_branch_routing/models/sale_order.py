import logging
from datetime import datetime, time as dt_time

import pytz

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ROUTING_STATES = [
    ('pending', 'Pending'),
    ('queued', 'Queued'),
    ('sent', 'Sent'),
    ('failed', 'Failed'),
    ('cancelled', 'Cancelled'),
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    branch_id = fields.Many2one(
        'pos.branch', string='Branch', copy=False, tracking=True,
        help="Branch selected by the customer on the website ordering widget. "
             "Resolved and validated server-side from the branch code - never "
             "trusted directly from the browser.",
    )
    branch_code = fields.Char(related='branch_id.code', store=True, readonly=True)
    branch_name = fields.Char(related='branch_id.name', store=True, readonly=True)
    branch_address = fields.Char(related='branch_id.address', store=True, readonly=True)
    branch_phone = fields.Char(related='branch_id.phone', store=True, readonly=True)
    pos_config_id = fields.Many2one(
        'pos.config', related='branch_id.pos_config_id', store=True, readonly=True,
        string='Branch POS',
    )

    order_type = fields.Selection(
        [('pickup', 'Pickup'), ('delivery', 'Delivery')],
        string='Order Type', copy=False, tracking=True,
    )
    scheduled_date = fields.Date(
        string='Requested Date', copy=False,
        help="Date the customer asked to collect/receive the order - not the "
             "date the order was placed.",
    )
    scheduled_time = fields.Char(
        string='Requested Time', copy=False, size=5,
        help="24h HH:MM, branch-local time, as requested by the customer.",
    )
    scheduled_datetime = fields.Datetime(
        string='Requested Date & Time', compute='_compute_scheduled_datetime', store=True,
        help="scheduled_date + scheduled_time combined and converted to UTC, "
             "for sorting/reporting. Computed on a best-effort basis; never "
             "blocks order confirmation if it cannot be resolved.",
    )
    customer_note = fields.Text(string='Order Notes', copy=False)

    pos_order_id = fields.Many2one(
        'pos.order', string='POS Order', copy=False, readonly=True,
    )
    pos_routing_state = fields.Selection(
        ROUTING_STATES, string='POS Routing Status', default='pending',
        copy=False, tracking=True,
    )
    pos_routing_error = fields.Text(string='POS Routing Error', copy=False, readonly=True)

    @api.depends('scheduled_date', 'scheduled_time', 'branch_id.company_id')
    def _compute_scheduled_datetime(self):
        for order in self:
            order.scheduled_datetime = order._dona_compute_scheduled_datetime()

    def _dona_compute_scheduled_datetime(self):
        self.ensure_one()
        if not self.scheduled_date or not self.scheduled_time:
            return False
        try:
            hour, minute = (int(part) for part in self.scheduled_time.split(':'))
            naive_dt = datetime.combine(self.scheduled_date, dt_time(hour=hour, minute=minute))
            tz_name = (
                self.branch_id.company_id.partner_id.tz
                or self.company_id.partner_id.tz
                or 'Asia/Bahrain'
            )
            local_dt = pytz.timezone(tz_name).localize(naive_dt)
            return local_dt.astimezone(pytz.UTC).replace(tzinfo=None)
        except Exception:  # noqa: BLE001 - display convenience only, never fatal
            _logger.warning(
                "Website POS Routing: could not compute scheduled_datetime for %s "
                "(date=%s, time=%s)", self.name, self.scheduled_date, self.scheduled_time,
            )
            return False

    # ------------------------------------------------------------------
    # Website session/cart -> sale.order context capture (section 4/20)
    # ------------------------------------------------------------------
    def _dona_apply_branch_context(self, context_data):
        """Apply a validated ``/dona/order/context`` payload onto this cart.

        Only ever called on a draft (cart) order, with an already
        branch-validated ``context_data`` dict (see ``pos.branch._get_by_code``
        and the controller). Silently ignores an unknown/blank branch code so
        that a stale or malformed context never corrupts an existing cart.
        """
        self.ensure_one()
        if self.state != 'draft':
            return False

        branch = self.env['pos.branch']._get_by_code(context_data.get('branch_code'))
        if not branch:
            return False

        vals = {}
        if self.branch_id != branch:
            vals['branch_id'] = branch.id

        mode = context_data.get('mode')
        if mode in ('pickup', 'delivery') and self.order_type != mode:
            vals['order_type'] = mode

        order_date = context_data.get('date')
        if order_date and str(self.scheduled_date or '') != order_date:
            vals['scheduled_date'] = order_date

        order_time = context_data.get('time')
        if order_time and self.scheduled_time != order_time:
            vals['scheduled_time'] = order_time

        note = context_data.get('note')
        if note and self.customer_note != note:
            vals['customer_note'] = note

        if vals:
            self.write(vals)
        return True

    def action_view_pos_order(self):
        """Smart button: sale.order <-> pos.order traceability (section 18)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("POS Order"),
            'res_model': 'pos.order',
            'view_mode': 'form',
            'res_id': self.pos_order_id.id,
        }

    # ------------------------------------------------------------------
    # Confirmation hook (section 13/21): route only once truly confirmed.
    # ------------------------------------------------------------------
    def action_confirm(self):
        res = super().action_confirm()
        confirmed = self.filtered(lambda o: o.state == 'sale' and o.website_id)
        if confirmed:
            confirmed.sudo()._dona_route_to_pos()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        self.filtered(
            lambda o: o.pos_routing_state in ('pending', 'queued', 'failed')
        ).write({'pos_routing_state': 'cancelled'})
        return res

    # ------------------------------------------------------------------
    # Routing engine (sections 5-9, 11-15, 17-18)
    # ------------------------------------------------------------------
    def _dona_route_to_pos(self):
        for order in self:
            order._dona_route_single_order_to_pos()

    def _dona_route_single_order_to_pos(self):
        self.ensure_one()

        # Idempotency guard: lock the row and re-check under the lock so that
        # a page refresh, a retried webhook, a concurrent request or a manual
        # re-confirmation can never create a second POS order (section 14).
        self.env.cr.execute(
            "SELECT pos_order_id, pos_routing_state FROM sale_order WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        row = self.env.cr.fetchone()
        if not row:
            return
        current_pos_order_id, current_state = row
        if current_pos_order_id or current_state == 'sent':
            return

        branch = self.branch_id
        if not branch:
            self._dona_fail_routing(_("No branch was selected for this website order."))
            return
        if not branch.active:
            self._dona_fail_routing(_(
                "The selected branch (%s) is no longer active.", branch.name,
            ))
            return

        pos_config = branch.pos_config_id
        if not pos_config:
            self._dona_fail_routing(_(
                "No POS is configured for the selected branch (%s).", branch.name,
            ))
            return

        session = pos_config.current_session_id
        if not session or session.state != 'opened':
            self.write({'pos_routing_state': 'queued', 'pos_routing_error': False})
            _logger.info(
                "Website POS Routing QUEUED:\nSale Order: %s\nBranch: %s\n"
                "Reason: No active POS session",
                self.name, branch.code,
            )
            return

        try:
            with self.env.cr.savepoint():
                pos_order = self._dona_create_pos_order(pos_config, session)
        except Exception as exc:  # noqa: BLE001 - must never break order confirmation
            self._dona_fail_routing(str(exc))
            _logger.exception("Website POS Routing FAILED for sale order %s", self.name)
            return

        self.write({
            'pos_order_id': pos_order.id,
            'pos_routing_state': 'sent',
            'pos_routing_error': False,
        })
        _logger.info(
            "Website POS Routing:\nSale Order: %s\nBranch: %s\nPOS: %s\n"
            "POS Session: %s\nStatus: Sent",
            self.name, branch.code, pos_config.name, session.id,
        )
        # Native bus notification: wakes up the branch's already-open POS
        # session so the order appears without a manual refresh (section 8).
        pos_config.notify_synchronisation(session.id, 0)

    @api.model
    def _dona_cron_retry_queued_orders(self):
        """Safety-net retry for orders queued while a branch's POS had no open
        session (section 7). The ``pos.session.action_pos_session_open``
        override already retries immediately when a session opens; this cron
        only exists to cover the rare case that hook is missed (e.g. a
        session opened by another process in the same instant an order was
        confirmed)."""
        queued_orders = self.search([('pos_routing_state', '=', 'queued')])
        if queued_orders:
            _logger.info("Website POS Routing: retrying %d queued order(s).", len(queued_orders))
            queued_orders._dona_route_to_pos()

    def _dona_fail_routing(self, message):
        self.write({'pos_routing_state': 'failed', 'pos_routing_error': message})
        _logger.error(
            "Website POS Routing FAILED:\nSale Order: %s\nBranch: %s\nReason: %s",
            self.name, self.branch_code or 'UNKNOWN', message,
        )

    def _dona_create_pos_order(self, pos_config, session):
        self.ensure_one()
        company = pos_config.company_id

        if self.currency_id != pos_config.currency_id:
            raise UserError(_(
                "Currency mismatch between the website order (%(order_cur)s) and "
                "the branch POS (%(pos_cur)s). Routing was stopped rather than "
                "risk creating a POS order with the wrong amount.",
                order_cur=self.currency_id.name, pos_cur=pos_config.currency_id.name,
            ))

        fiscal_position = pos_config.default_fiscal_position_id
        line_commands = []
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            taxes = (
                fiscal_position.map_tax(line.product_id.taxes_id)
                if fiscal_position else line.tax_ids
            )
            line_commands.append(Command.create({
                'product_id': line.product_id.id,
                'name': line.name,
                'full_product_name': line.name,
                'qty': line.product_uom_qty,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [Command.set(taxes.ids)],
                'price_subtotal': line.price_subtotal,
                'price_subtotal_incl': line.price_total,
                'customer_note': line.dona_customer_note or False,
                # Preserve the exact selected variant/option combination, not
                # just the parent product (section 9): dynamic/always variants
                # are already carried by product_id itself; no_variant
                # attributes and free-text custom values need to be copied
                # across explicitly since they live on the line, not the
                # product.
                'attribute_value_ids': [
                    Command.set(line.product_no_variant_attribute_value_ids.ids)
                ],
                'custom_attribute_value_ids': [
                    Command.create({
                        'custom_product_template_attribute_value_id':
                            custom_value.custom_product_template_attribute_value_id.id,
                        'custom_value': custom_value.custom_value,
                    })
                    for custom_value in line.product_custom_attribute_value_ids
                ],
            }))
        if not line_commands:
            raise UserError(_("This order has no valid product lines to send to the POS."))

        is_paid_online = self.payment_state in ('paid', 'in_payment')
        state = 'draft'
        amount_paid = 0.0
        if is_paid_online and self.branch_id.online_payment_method_id:
            state = 'paid'
            amount_paid = self.amount_total

        order_type_label = dict(self._fields['order_type'].selection).get(self.order_type)
        note_parts = [
            _("Website order %s", self.name),
            _("Paid online") if is_paid_online else _("To settle at the branch"),
        ]
        if order_type_label:
            note_parts.append(order_type_label)
        if self.customer_note:
            note_parts.append(self.customer_note)

        pos_order = self.env['pos.order'].sudo().with_company(company).create({
            'session_id': session.id,
            'config_id': pos_config.id,
            'company_id': company.id,
            'partner_id': self.partner_id.id or False,
            'lines': line_commands,
            'amount_tax': self.amount_tax,
            'amount_total': self.amount_total,
            'amount_paid': amount_paid,
            'amount_return': 0.0,
            'state': state,
            'general_customer_note': '\n'.join(filter(None, note_parts)),
            'shipping_date': self.scheduled_date or False,
            'preset_time': self.scheduled_datetime or False,
            'website_sale_order_id': self.id,
        })

        if state == 'paid':
            self.env['pos.payment'].sudo().with_company(company).create({
                'pos_order_id': pos_order.id,
                'payment_method_id': self.branch_id.online_payment_method_id.id,
                'amount': self.amount_total,
            })

        return pos_order
