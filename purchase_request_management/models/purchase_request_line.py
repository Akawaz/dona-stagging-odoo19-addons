from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseRequestLine(models.Model):
    _name = 'purchase.request.line'
    _description = 'Purchase Request Line'
    _inherit = ['mail.thread']

    request_id = fields.Many2one(
        'purchase.request',
        string='Purchase Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    state = fields.Selection(
        related='request_id.state',
        string='Status',
        readonly=True,
        store=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('purchase_ok', '=', True)],
        tracking=True,
    )
    product_category_id = fields.Many2one(
        related='product_id.categ_id',
        string='Product Category',
        readonly=True,
        store=True,
    )
    description = fields.Char(
        string='Description',
        compute='_compute_description',
        store=True,
        readonly=False,
        tracking=True,
    )
    required_qty = fields.Float(
        string='Required Quantity',
        required=True,
        default=1.0,
        tracking=True,
    )
    available_qty = fields.Float(
        string='Available Quantity',
        compute='_compute_available_qty',
        readonly=True,
    )
    available_qty_location_ids = fields.Many2many(
        'stock.quant',
        string='Available Quant Breakdown',
        compute='_compute_available_qty',
    )
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        tracking=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Location',
        domain="[('usage', '=', 'internal'), '|', ('warehouse_id', '=', False), ('warehouse_id', '=', request_warehouse_id)]",
        tracking=True,
    )
    request_warehouse_id = fields.Many2one(
        related='request_id.warehouse_id',
        string='Request Warehouse',
        readonly=True,
        store=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='UOM',
        compute='_compute_uom_id',
        store=True,
        readonly=False,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        related='request_id.company_id',
        string='Company',
        readonly=True,
        store=True,
    )
    request_user_id = fields.Many2one(
        related='request_id.request_user_id',
        string='Request User',
        readonly=True,
        store=True,
    )
    date = fields.Date(
        related='request_id.date',
        string='Date',
        readonly=True,
        store=True,
    )
    purchase_order_line_id = fields.Many2one(
        'purchase.order.line',
        string='Purchase Order Line',
        readonly=True,
        copy=False,
    )
    purchase_order_id = fields.Many2one(
        related='purchase_order_line_id.order_id',
        string='Purchase Order',
        readonly=True,
        store=True,
    )

    @api.depends('product_id')
    def _compute_description(self):
        for line in self:
            if line.product_id:
                line.description = line.product_id.display_name
            else:
                line.description = False

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            if line.product_id:
                line.uom_id = line.product_id.uom_id
            else:
                line.uom_id = False

    @api.depends('product_id')
    def _compute_available_qty(self):
        for line in self:
            if line.product_id:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('quantity', '>', 0),
                ])
                line.available_qty = sum(quants.mapped('quantity'))
                line.available_qty_location_ids = quants.ids
            else:
                line.available_qty = 0.0
                line.available_qty_location_ids = [(6, 0, [])]

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.uom_id = self.product_id.uom_id
            # Select vendor with lowest price from product suppliers
            sellers = self.product_id.seller_ids.filtered(lambda s: s.partner_id.active)
            if sellers:
                best_seller = min(sellers, key=lambda s: s.price)
                self.vendor_id = best_seller.partner_id

    def _get_product_catalog_lines_data(self, **kwargs):
        """ Return information about purchase request lines for the product catalog. """
        if len(self) == 1:
            return {
                'quantity': self.required_qty,
                'readOnly': self.request_id._is_readonly(),
                'uomDisplayName': self.uom_id.display_name,
            }
        elif self:
            return {
                'quantity': sum(self.mapped('required_qty')),
                'readOnly': True,
                'uomDisplayName': self[0].uom_id.display_name,
            }
        return {'quantity': 0}

    def action_add_from_catalog(self):
        request = self.env['purchase.request'].browse(self.env.context.get('order_id'))
        return request.with_context(child_field='line_ids').action_add_from_catalog()

    def action_view_stock_quant_breakdown(self):
        self.ensure_one()
        if not self.available_qty_location_ids:
            raise UserError(_('No stock quant breakdown available.'))
        action = self.env.ref('stock.action_view_quants').read()[0]
        action['domain'] = [('id', 'in', self.available_qty_location_ids.ids)]
        action['context'] = {'search_default_product_id': self.product_id.id}
        return action

    def action_add_to_rfq(self):
        self.ensure_one()
        if not self.vendor_id:
            raise UserError(_('Please select a vendor for this product.'))
        if self.request_id.state != 'approved':
            raise UserError(_('The purchase request must be approved to create RFQ.'))
        return {
            'name': _('Create RFQ'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.request.line.make.purchase.order',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.request_id.id,
                'active_ids': self.request_id.ids,
                'active_model': 'purchase.request',
                'default_line_ids': [self.id],
            },
        }
