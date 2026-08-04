from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BulkScrap(models.Model):
    _name = 'bulk.scrap'
    _description = 'Bulk Scrap Management'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Scrap Number',
        default='New',
        copy=False, readonly=True, required=True)
    user_id = fields.Many2one(
        'res.users', string='Created By',
        default=lambda self: self.env.user, readonly=True)
    date = fields.Datetime(
        string='Date & Time',
        default=fields.Datetime.now, required=True)
    location_id = fields.Many2one(
        'stock.location', string='Source Location',
        domain=[('usage', '=', 'internal')],
        required=True, check_company=True)
    scrap_location_id = fields.Many2one(
        'stock.location', string='Destination Location',
        domain=[('usage', '=', 'inventory')],
        required=True, check_company=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True)
    source_document = fields.Char(string='Source Document')
    notes = fields.Text(string='Notes')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_review', 'Submitted for Review'),
        ('validated', 'Validated'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', readonly=True, tracking=True)

    line_ids = fields.One2many(
        'bulk.scrap.line', 'bulk_scrap_id',
        string='Products')
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Attachments')

    reviewer_id = fields.Many2one(
        'res.users', string='Validated By', readonly=True)
    validated_date = fields.Datetime(string='Validated Date', readonly=True)
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('bulk.scrap') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.cost')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = sum(rec.line_ids.mapped('cost'))

    def action_submit_for_review(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one product line before submitting.'))
        for line in self.line_ids:
            if not line.reason:
                raise UserError(_('Reason is required for all product lines.'))

        self.state = 'to_review'

        # Notify inventory admins
        inv_group = self.env.ref('stock.group_stock_manager', raise_if_not_found=False)
        pur_group = self.env.ref('purchase.group_purchase_manager', raise_if_not_found=False)

        target_users = set()
        if inv_group:
            target_users.update(inv_group.user_ids.ids)
        if pur_group:
            target_users.update(pur_group.user_ids.ids)

        if not target_users:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Admins Found'),
                    'message': _('No Inventory or Purchase managers found to notify. Submit recorded but no activity created.'),
                    'type': 'warning',
                    'sticky': True,
                },
            }

        for user_id in target_users:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_("Review Bulk Scrap – %s") % self.name,
                note=_("%(user)s submitted bulk scrap %(name)s for review.",
                       user=self.env.user.name, name=self.name),
                user_id=user_id,
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Submitted'),
                'message': _('Bulk scrap submitted for review. Activity created for %s admin(s).') % len(target_users),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_validate(self):
        self.ensure_one()
        if self.state != 'to_review':
            raise UserError(_('Only submitted-for-review records can be validated.'))
        if not self.line_ids:
            raise UserError(_('No products to scrap.'))

        for line in self.line_ids:
            scrap = self.env['stock.scrap'].create({
                'product_id': line.product_id.id,
                'scrap_qty': line.quantity,
                'product_uom_id': line.product_uom_id.id,
                'location_id': self.location_id.id,
                'scrap_location_id': self.scrap_location_id.id,
                'origin': self.source_document or self.name,
                'company_id': self.company_id.id,
                'should_replenish': line.replenish_qty,
                'bulk_scrap_id': self.id,
            })
            line.scrap_id = scrap.id
            scrap.action_validate()

        self.write({
            'state': 'validated',
            'reviewer_id': self.env.user.id,
            'validated_date': fields.Datetime.now(),
        })

        # Close all open activities on this record
        open_acts = self.env['mail.activity'].search([
            ('res_model', '=', 'bulk.scrap'),
            ('res_id', '=', self.id),
        ])
        if open_acts:
            open_acts.action_feedback(feedback=_("Validated by %s") % self.env.user.name)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Validated'),
                'message': _('All scrap entries validated successfully.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == 'validated':
                raise UserError(_('Cannot cancel a validated bulk scrap.'))
            rec.state = 'cancelled'
            open_acts = self.env['mail.activity'].search([
                ('res_model', '=', 'bulk.scrap'),
                ('res_id', '=', rec.id),
            ])
            open_acts.action_feedback(feedback=_("Cancelled by %s") % self.env.user.name)
        return True

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ('cancelled', 'to_review'):
                raise UserError(_('Only cancelled or to-review records can be reset.'))
            rec.state = 'draft'
        return True

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('bulk_scrap_management.action_report_bulk_scrap').report_action(self)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_validated(self):
        for rec in self:
            if rec.state == 'validated':
                raise UserError(_('You cannot delete a validated bulk scrap.'))

    def unlink(self):
        # Proactively delete linked stock.scrap records (if not done) before the parent is removed
        for rec in self:
            for line in rec.line_ids:
                if line.scrap_id and line.scrap_id.state == 'draft':
                    line.scrap_id.unlink()
        return super().unlink()


class BulkScrapLine(models.Model):
    _name = 'bulk.scrap.line'
    _description = 'Bulk Scrap Line'

    bulk_scrap_id = fields.Many2one(
        'bulk.scrap', string='Bulk Scrap', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        'product.product', string='Product',
        domain=[('type', '=', 'consu')],
        required=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    product_uom_id = fields.Many2one(
        'uom.uom', string='Unit',
        related='product_id.uom_id', store=True)
    reason = fields.Char(string='Reason', required=True)
    replenish_qty = fields.Boolean(string='Replenish Quantity')
    scrap_id = fields.Many2one(
        'stock.scrap', string='Scrap Entry', readonly=True, ondelete='cascade')
    on_hand_qty = fields.Float(
        string='On Hand Qty',
        compute='_compute_on_hand_qty')
    cost = fields.Float(
        string='Cost',
        compute='_compute_cost', store=True)

    @api.depends('product_id', 'bulk_scrap_id.location_id')
    def _compute_on_hand_qty(self):
        for line in self:
            if line.product_id and line.bulk_scrap_id.location_id:
                line.on_hand_qty = self.env['stock.quant']._get_available_quantity(
                    line.product_id,
                    line.bulk_scrap_id.location_id,
                )
            else:
                line.on_hand_qty = 0.0

    @api.depends('product_id', 'quantity')
    def _compute_cost(self):
        for line in self:
            line.cost = line.product_id.standard_price * line.quantity
