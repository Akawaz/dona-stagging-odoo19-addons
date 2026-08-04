from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class PurchaseRequest(models.Model):
    _name = 'purchase.request'
    _description = 'Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'product.catalog.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        default=lambda self: _('New'),
        copy=False,
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('to_approve', 'To Approve'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        required=True,
        copy=False,
    )
    request_user_id = fields.Many2one(
        'res.users',
        string='Request User',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        check_company=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Location',
        domain="[('warehouse_id', '=', warehouse_id), ('usage', '=', 'internal')]",
        check_company=True,
    )
    line_ids = fields.One2many(
        'purchase.request.line',
        'request_id',
        string='Products',
        copy=True,
    )
    hierarchy_id = fields.Many2one(
        'purchase.request.approval.hierarchy',
        string='Company Approval Hierarchy',
        compute='_compute_hierarchy',
        store=False,
    )
    hierarchy_approver_ids = fields.One2many(
        'purchase.request.approval.delegated',
        related='hierarchy_id.delegated_ids',
        string='Approval Flow',
        readonly=True,
    )
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        copy=False,
    )
    approved_date = fields.Datetime(
        string='Approved Date',
        readonly=True,
        copy=False,
    )
    rejected_by = fields.Many2one(
        'res.users',
        string='Rejected By',
        readonly=True,
        copy=False,
    )
    rejected_date = fields.Datetime(
        string='Rejected Date',
        readonly=True,
        copy=False,
    )
    description = fields.Text(string='Description')
    purchase_count = fields.Integer(
        string='Purchase Orders',
        compute='_compute_purchase_count',
    )
    origin = fields.Char(string='Source Document')
    current_approval_level = fields.Integer(
        string='Current Approval Level',
        default=0,
        readonly=True,
        copy=False,
        help='Tracks the current approval level being processed. 0 means not submitted yet.',
    )
    approval_history_ids = fields.One2many(
        'purchase.request.approval.history',
        'request_id',
        string='Approval History',
        readonly=True,
        copy=False,
    )

    @api.depends('line_ids', 'line_ids.purchase_order_line_id')
    def _compute_purchase_count(self):
        for request in self:
            po_ids = request.line_ids.mapped('purchase_order_line_id.order_id')
            request.purchase_count = len(po_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'purchase.request'
                ) or _('New')
        return super(PurchaseRequest, self).create(vals_list)

    def copy(self, default=None):
        default = dict(default or {})
        default['name'] = _('New')
        default['state'] = 'draft'
        default['approved_by'] = False
        default['approved_date'] = False
        default['rejected_by'] = False
        default['rejected_date'] = False
        default['current_approval_level'] = 0
        return super(PurchaseRequest, self).copy(default)

    def action_draft(self):
        for request in self:
            request.approval_history_ids.unlink()
            request.activity_ids.filtered(lambda a: a.state == 'open').action_feedback(feedback=_('Reset to Draft'))
        return self.write({
            'state': 'draft',
            'current_approval_level': 0,
            'approved_by': False,
            'approved_date': False,
            'rejected_by': False,
            'rejected_date': False,
        })

    def action_submit_for_approval(self):
        for request in self:
            if not request.line_ids:
                raise UserError(_('You cannot submit a purchase request without products.'))
            for line in request.line_ids:
                if line.required_qty <= 0:
                    raise UserError(
                        _('Required quantity must be positive for product %s.')
                        % line.product_id.name
                    )
            # Clear old history and rebuild from hierarchy
            request.approval_history_ids.unlink()
            hierarchy = request.hierarchy_id
            if hierarchy:
                for approver in hierarchy.delegated_ids.filtered(lambda d: d.active).sorted('sequence'):
                    self.env['purchase.request.approval.history'].create({
                        'request_id': request.id,
                        'sequence': approver.sequence,
                        'level': approver.level,
                        'name': approver.name,
                        'user_id': approver.user_id.id,
                        'group_id': approver.group_id.id,
                        'state': 'pending',
                    })
            # Determine first approval level
            first_level = request._get_first_approval_level()
            request.write({
                'state': 'to_approve',
                'current_approval_level': first_level.level if first_level else 0,
            })
            request._send_notification_for_approval()
        return True

    def action_approve(self):
        for request in self:
            if not request._check_approval_rights():
                raise UserError(_('You do not have permission to approve this request.'))
            # Mark current level pending activities as done
            request._mark_approval_activities_done()
            # Mark current level approvers as approved
            current_histories = request.approval_history_ids.filtered(
                lambda h: h.level == request.current_approval_level and h.state == 'pending'
            )
            for hist in current_histories:
                hist.write({
                    'state': 'approved',
                    'approved_date': fields.Datetime.now(),
                    'approver_user_id': self.env.user.id,
                })
            # Check if there are more levels to approve
            next_level = request._get_next_pending_level()
            if next_level:
                # Move to next level
                request.write({
                    'current_approval_level': next_level.level,
                })
                request._send_notification_for_approval()
            else:
                # All levels approved - close any remaining approval activities
                for activity in request.activity_ids.filtered(
                    lambda a: a.summary and 'Approve Purchase Request' in (a.summary or '')
                ):
                    activity.action_feedback(feedback=_('Fully Approved'))
                request.write({
                    'state': 'approved',
                    'approved_by': self.env.user.id,
                    'approved_date': fields.Datetime.now(),
                })
                request._send_approval_notification()
        return True

    def action_reject(self):
        for request in self:
            if not request._check_approval_rights():
                raise UserError(_('You do not have permission to reject this request.'))
            # Mark current level pending activities as done
            request._mark_approval_activities_done()
            # Mark current level approvers as rejected
            current_histories = request.approval_history_ids.filtered(
                lambda h: h.level == request.current_approval_level and h.state == 'pending'
            )
            for hist in current_histories:
                hist.write({
                    'state': 'rejected',
                    'approved_date': fields.Datetime.now(),
                    'approver_user_id': self.env.user.id,
                })
            request.write({
                'state': 'rejected',
                'rejected_by': self.env.user.id,
                'rejected_date': fields.Datetime.now(),
            })
            request._send_rejection_notification()
        return True

    def action_cancel(self):
        return self.write({'state': 'cancel'})

    def action_done(self):
        return self.write({'state': 'done'})

    def action_view_purchase_orders(self):
        po_ids = self.line_ids.mapped('purchase_order_line_id.order_id')
        action = self.env.ref('purchase.purchase_rfq').read()[0]
        if len(po_ids) > 1:
            action['domain'] = [('id', 'in', po_ids.ids)]
        elif len(po_ids) == 1:
            action['views'] = [
                (self.env.ref('purchase.purchase_order_form').id, 'form')
            ]
            action['res_id'] = po_ids.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def action_create_rfq(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved requests can be used to create RFQ.'))
        # Validate all lines have a vendor chosen
        lines_without_vendor = self.line_ids.filtered(lambda l: not l.vendor_id)
        if lines_without_vendor:
            product_names = ', '.join(lines_without_vendor.mapped('product_id.display_name'))
            raise UserError(
                _('Please select a vendor for the following products before creating RFQ: %s')
                % product_names
            )
        # Find the first vendor among unprocessed lines
        unprocessed_lines = self.line_ids.filtered(lambda l: not l.purchase_order_line_id)
        if not unprocessed_lines:
            raise UserError(_('All products have already been processed into RFQs.'))
        first_vendor = unprocessed_lines[0].vendor_id
        return {
            'name': _('Create RFQ for %s') % first_vendor.name,
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.request.line.make.purchase.order',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_ids': self.ids,
                'active_model': 'purchase.request',
                'default_request_id': self.id,
                'default_supplier_id': first_vendor.id,
            },
        }

    @api.depends('company_id')
    def _compute_hierarchy(self):
        for request in self:
            request.hierarchy_id = self.env['purchase.request.approval.hierarchy'].get_company_hierarchy(
                request.company_id.id
            )

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        if self.location_id and self.location_id.warehouse_id != self.warehouse_id:
            self.location_id = False

    def _check_approval_rights(self):
        self.ensure_one()
        # Admins always have rights
        if self.env.user.has_group('purchase_request_management.group_purchase_request_admin'):
            return True
        # Approvers can approve if they match current level
        hierarchy = self.hierarchy_id
        if hierarchy and self.state == 'to_approve':
            current_level_approvers = hierarchy.delegated_ids.filtered(
                lambda d: d.active and d.level == self.current_approval_level
            )
            for approver in current_level_approvers:
                if approver.user_id and approver.user_id.id == self.env.user.id:
                    return True
                if approver.group_id and approver.group_id.id in self.env.user.groups_id.ids:
                    return True
        # Fallback: general approver group can approve anything
        return self.env.user.has_group('purchase_request_management.group_purchase_request_approver')

    def _send_notification_for_approval(self):
        self.ensure_one()
        approvers = self._get_current_level_approvers()
        level_text = _('Level %s') % self.current_approval_level
        partner_ids = []
        user_ids = []
        if approvers:
            for approver in approvers:
                if approver.user_id:
                    partner_ids.append(approver.user_id.partner_id.id)
                    user_ids.append(approver.user_id.id)
                if approver.group_id:
                    for user in approver.group_id.user_ids:
                        partner_ids.append(user.partner_id.id)
                        user_ids.append(user.id)
        if not user_ids:
            # Fallback: create activity for all approver group users
            approver_group = self.env.ref('purchase_request_management.group_purchase_request_approver', raise_if_not_found=False)
            if approver_group:
                for user in approver_group.user_ids:
                    user_ids.append(user.id)
                    partner_ids.append(user.partner_id.id)
        user_ids = list(set(user_ids))
        partner_ids = list(set(partner_ids))
        if partner_ids:
            self.message_subscribe(partner_ids=partner_ids)
            self.message_post(
                body=_('Purchase Request %s is waiting for your approval (%s).') % (self.name, level_text),
                partner_ids=partner_ids,
                subtype_xmlid='mail.mt_comment',
            )
            self._send_email_notification(
                'purchase_request_management.email_template_purchase_request_for_approval',
                partner_ids,
            )
        # Create activities for approver users
        if user_ids:
            activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
            if not activity_type:
                activity_type = self.env['mail.activity.type'].sudo().search([], limit=1)
            for user_id in user_ids:
                self.activity_schedule(
                    activity_type_id=activity_type.id,
                    user_id=user_id,
                    summary=_('Approve Purchase Request %s') % self.name,
                    note=_('Purchase Request %s is waiting for your approval at %s.') % (self.name, level_text),
                )

    def _send_approval_notification(self):
        self.ensure_one()
        if self.request_user_id and self.request_user_id.partner_id:
            self.message_post(
                body=_('Your Purchase Request %s has been approved.') % self.name,
                partner_ids=[self.request_user_id.partner_id.id],
                subtype_xmlid='mail.mt_comment',
            )
            self._send_email_notification(
                'purchase_request_management.email_template_purchase_request_approved',
                [self.request_user_id.partner_id.id],
            )

    def _send_rejection_notification(self):
        self.ensure_one()
        if self.request_user_id and self.request_user_id.partner_id:
            self.message_post(
                body=_('Your Purchase Request %s has been rejected.') % self.name,
                partner_ids=[self.request_user_id.partner_id.id],
                subtype_xmlid='mail.mt_comment',
            )
            self._send_email_notification(
                'purchase_request_management.email_template_purchase_request_rejected',
                [self.request_user_id.partner_id.id],
            )

    def _mark_approval_activities_done(self):
        self.ensure_one()
        activities = self.activity_ids.filtered(
            lambda a: a.summary and 'Approve Purchase Request' in (a.summary or '')
        )
        for activity in activities:
            activity.action_feedback(feedback=_('Approved or Rejected'))

    def _send_email_notification(self, template_xmlid, partner_ids):
        self.ensure_one()
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for partner_id in partner_ids:
                template.with_context(
                    partner_id=partner_id,
                    lang=self.env['res.partner'].browse(partner_id).lang or 'en_US',
                ).send_mail(self.id, force_send=True)

    def _get_first_approval_level(self):
        self.ensure_one()
        hierarchy = self.hierarchy_id
        if hierarchy:
            approvers = hierarchy.delegated_ids.filtered(lambda d: d.active).sorted('level')
            return approvers[:1] or False
        return False

    def _get_current_level_approvers(self):
        self.ensure_one()
        hierarchy = self.hierarchy_id
        if hierarchy and self.current_approval_level > 0:
            return hierarchy.delegated_ids.filtered(
                lambda d: d.active and d.level == self.current_approval_level
            )
        return self.env['purchase.request.approval.delegated']

    def _get_next_pending_level(self):
        self.ensure_one()
        hierarchy = self.hierarchy_id
        if not hierarchy:
            return False
        all_levels = sorted(set(hierarchy.delegated_ids.filtered(lambda d: d.active).mapped('level')))
        if not all_levels:
            return False
        current_index = all_levels.index(self.current_approval_level) if self.current_approval_level in all_levels else -1
        if current_index + 1 < len(all_levels):
            next_level_val = all_levels[current_index + 1]
            return hierarchy.delegated_ids.filtered(
                lambda d: d.active and d.level == next_level_val
            )[:1] or False
        return False

    # ------------------------------------------------------------
    # Product Catalog Mixin Methods
    # ------------------------------------------------------------

    def action_add_from_catalog(self):
        res = super().action_add_from_catalog()
        res['context']['order_id'] = self.id
        return res

    def _get_action_add_from_catalog_extra_context(self):
        return {
            **super()._get_action_add_from_catalog_extra_context(),
            'precision': self.env['decimal.precision'].precision_get('Product Unit'),
        }

    def _get_product_catalog_domain(self):
        from odoo.fields import Domain
        return super()._get_product_catalog_domain() & Domain('purchase_ok', '=', True)

    def _get_product_catalog_record_lines(self, product_ids, **kwargs):
        grouped_lines = {}
        for line in self.line_ids.filtered(lambda l: l.product_id.id in product_ids):
            product = line.product_id
            if product not in grouped_lines:
                grouped_lines[product] = self.env['purchase.request.line']
            grouped_lines[product] |= line
        return grouped_lines

    def _get_product_catalog_order_line_info(self, product_ids, child_field=False, **kwargs):
        """Defensive override to ensure product keys are recordsets."""
        self.ensure_one()
        order_line_info = {}
        record_lines_map = self._get_product_catalog_record_lines(product_ids, child_field=child_field, **kwargs)
        for product, record_lines in record_lines_map.items():
            # Defensive: if product is an int, convert to recordset
            if isinstance(product, int):
                product = self.env['product.product'].browse(product)
            order_line_info[product.id] = {
                **record_lines._get_product_catalog_lines_data(parent_record=self, **kwargs),
                'productType': product.type,
                'code': product.code if product.code else '',
            }
            if not order_line_info[product.id].get('uomDisplayName'):
                order_line_info[product.id]['uomDisplayName'] = product.uom_id.display_name

        default_data = self._default_order_line_values(child_field)
        products = self.env['product.product'].browse(product_ids)
        product_data = self._get_product_catalog_order_data(products, **kwargs)

        for product_id, data in product_data.items():
            if product_id in order_line_info:
                continue
            order_line_info[product_id] = {**default_data, **data}

        return order_line_info

    def _update_order_line_info(self, product_id, quantity, **kwargs):
        self.ensure_one()
        product = self.env['product.product'].browse(product_id)
        lines = self.line_ids.filtered(lambda l: l.product_id.id == product_id)
        if lines:
            if quantity != 0:
                lines[0].required_qty = quantity
                # Remove extra lines for same product
                if len(lines) > 1:
                    lines[1:].unlink()
            else:
                lines.unlink()
        elif quantity > 0:
            vendor = False
            sellers = product.seller_ids.filtered(lambda s: s.partner_id.active)
            if sellers:
                best_seller = min(sellers, key=lambda s: s.price)
                vendor = best_seller.partner_id
            self.env['purchase.request.line'].create({
                'request_id': self.id,
                'product_id': product_id,
                'required_qty': quantity,
                'description': product.display_name,
                'uom_id': product.uom_id.id,
                'vendor_id': vendor.id if vendor else False,
            })
        return product.standard_price

    def _is_readonly(self):
        self.ensure_one()
        return self.state in ('cancel', 'done')

    def _get_parent_field_on_child_model(self):
        return 'request_id'

    def unlink(self):
        for request in self:
            if request.state not in ('draft', 'cancel'):
                raise UserError(_('You can only delete draft or cancelled purchase requests.'))
        return super(PurchaseRequest, self).unlink()
