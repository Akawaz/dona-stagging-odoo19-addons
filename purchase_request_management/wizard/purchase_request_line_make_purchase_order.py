from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseRequestLineMakePurchaseOrder(models.TransientModel):
    _name = 'purchase.request.line.make.purchase.order'
    _description = 'Purchase Request Line Make Purchase Order'

    supplier_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        domain=[('supplier_rank', '>', 0)],
        required=True,
    )
    item_ids = fields.One2many(
        'purchase.request.line.make.purchase.order.item',
        'wizard_id',
        string='Items',
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Add to Existing RFQ',
        domain=[('state', '=', 'draft')],
        help='If selected, products will be added to this existing RFQ. Otherwise, a new RFQ will be created.',
    )
    request_id = fields.Many2one(
        'purchase.request',
        string='Purchase Request',
        readonly=True,
    )
    existing_po_ids = fields.Many2many(
        'purchase.order',
        string='Existing RFQs for this Vendor',
        compute='_compute_existing_pos',
        store=False,
    )
    existing_po_count = fields.Integer(
        string='Existing RFQ Count',
        compute='_compute_existing_pos',
        store=False,
    )
    force_new_rfq = fields.Boolean(
        string='Create New RFQ',
        help='Tick this if you want to create a new RFQ even when existing draft RFQs exist for this vendor.',
    )
    new_rfq_warning = fields.Char(
        string='Warning',
        compute='_compute_new_rfq_warning',
    )

    @api.depends('purchase_order_id', 'existing_po_count')
    def _compute_new_rfq_warning(self):
        for wiz in self:
            if not wiz.purchase_order_id and wiz.existing_po_count > 0:
                wiz.new_rfq_warning = _(
                    'There are already %s draft RFQ(s) for this vendor. '
                    'If you want to create a new one, tick the checkbox below.'
                ) % wiz.existing_po_count
            else:
                wiz.new_rfq_warning = False

    @api.depends('supplier_id')
    def _compute_existing_pos(self):
        for wiz in self:
            if wiz.supplier_id:
                pos = self.env['purchase.order'].search([
                    ('partner_id', '=', wiz.supplier_id.id),
                    ('state', '=', 'draft'),
                    ('company_id', '=', self.env.company.id),
                ], order='id desc')
                wiz.existing_po_ids = [(6, 0, pos.ids)]
                wiz.existing_po_count = len(pos)
            else:
                wiz.existing_po_ids = [(6, 0, [])]
                wiz.existing_po_count = 0

    @api.model
    def default_get(self, fields_list):
        res = super(PurchaseRequestLineMakePurchaseOrder, self).default_get(fields_list)
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        request_id = self.env.context.get('default_request_id')
        supplier_id = self.env.context.get('default_supplier_id')

        # Use explicit request_id from context if available
        if request_id:
            request = self.env['purchase.request'].browse(request_id)
        elif active_model == 'purchase.request' and active_id:
            request = self.env['purchase.request'].browse(active_id)
        else:
            request = self.env['purchase.request']

        if request:
            res['request_id'] = request.id
            # Filter lines: unprocessed and matching the target vendor
            target_vendor_id = supplier_id or False
            domain = [('purchase_order_line_id', '=', False)]
            if target_vendor_id:
                domain.append(('vendor_id', '=', target_vendor_id))
            lines = request.line_ids.filtered(lambda l: not l.purchase_order_line_id)
            if target_vendor_id:
                lines = lines.filtered(lambda l: l.vendor_id.id == target_vendor_id)
            items = []
            for line in lines:
                items.append({
                    'line_id': line.id,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.uom_id.id,
                    'description': line.description,
                    'product_qty': line.required_qty,
                    'vendor_id': line.vendor_id.id,
                })
            res['item_ids'] = [(0, 0, item) for item in items]
            if lines and lines[0].vendor_id:
                res['supplier_id'] = lines[0].vendor_id.id
        return res

    def make_purchase_order(self):
        self.ensure_one()
        if not self.item_ids:
            raise UserError(_('No items selected for RFQ creation.'))

        purchase_order = self.purchase_order_id
        if not purchase_order:
            # User wants to create a new RFQ
            if self.existing_po_count > 0 and not self.force_new_rfq:
                raise UserError(_(
                    'There are already %s draft RFQ(s) for this vendor. '
                    'If you want to create a new one, please tick the "Create New RFQ" checkbox and try again.'
                ) % self.existing_po_count)
            purchase_order = self.env['purchase.order'].create({
                'partner_id': self.supplier_id.id,
                'origin': self._get_origin(),
                'company_id': self.env.company.id,
            })

        # Add lines to the purchase order
        for item in self.item_ids:
            if item.product_qty <= 0:
                continue
            # Read product/uom from line_id as reliable fallback since transient
            # readonly fields can lose values during form save
            product = item.product_id or item.line_id.product_id
            product_uom = item.product_uom_id or item.line_id.uom_id
            if not product or not product_uom:
                continue
            # Determine the line name explicitly
            line_name = item.description or item.line_id.description or ''
            if not line_name:
                line_name = product.display_name or product.name or 'Product'
            if not line_name:
                line_name = 'Product'
            # Check if same product already exists in PO
            existing_line = purchase_order.order_line.filtered(
                lambda l: l.product_id == product and l.product_uom_id == product_uom
            )
            if existing_line:
                # Update quantity on existing line
                existing_line[0].write({
                    'product_qty': existing_line[0].product_qty + item.product_qty,
                })
                item.line_id.write({'purchase_order_line_id': existing_line[0].id})
            else:
                po_line = self.env['purchase.order.line'].create({
                    'order_id': purchase_order.id,
                    'product_id': product.id,
                    'product_qty': item.product_qty,
                    'product_uom_id': product_uom.id,
                    'name': line_name,
                })
                item.line_id.write({'purchase_order_line_id': po_line.id})

        # Check if there are more unprocessed lines with other vendors
        request = self.item_ids[0].line_id.request_id
        remaining_lines = request.line_ids.filtered(lambda l: not l.purchase_order_line_id)
        if remaining_lines:
            # More vendors to process — chain to next vendor wizard
            next_vendor = remaining_lines[0].vendor_id
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.request.line.make.purchase.order',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'active_id': request.id,
                    'active_ids': request.ids,
                    'active_model': 'purchase.request',
                    'default_request_id': request.id,
                    'default_supplier_id': next_vendor.id,
                },
                'name': _('Create RFQ for %s') % next_vendor.name,
            }
        else:
            # All lines processed — close the PR and show the last PO
            request.write({'state': 'done'})
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'view_mode': 'form',
                'res_id': purchase_order.id,
                'target': 'current',
            }

    def _get_origin(self):
        origins = set()
        for item in self.item_ids:
            if item.line_id.request_id.name:
                origins.add(item.line_id.request_id.name)
        return ', '.join(origins) if origins else False


class PurchaseRequestLineMakePurchaseOrderItem(models.TransientModel):
    _name = 'purchase.request.line.make.purchase.order.item'
    _description = 'Purchase Request Line Make Purchase Order Item'

    wizard_id = fields.Many2one(
        'purchase.request.line.make.purchase.order',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    line_id = fields.Many2one(
        'purchase.request.line',
        string='Purchase Request Line',
        required=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
    )
    description = fields.Char(string='Description')
    product_qty = fields.Float(string='Quantity', required=True)
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
    )
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
    )
