from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PurchaseRequestApprovalDelegated(models.Model):
    _name = 'purchase.request.approval.delegated'
    _description = 'Purchase Request Approval Delegated'
    _order = 'sequence, id'

    hierarchy_id = fields.Many2one(
        'purchase.request.approval.hierarchy',
        string='Approval Hierarchy',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Name')
    sequence = fields.Integer(string='Sequence', default=10)
    level = fields.Integer(
        string='Level',
        required=True,
        default=1,
        help='Approval level in the chain. Lower number = earlier approval.',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Approver User',
        domain=[('share', '=', False)],
        help='Specific user who can approve at this level.',
    )
    group_id = fields.Many2one(
        'res.groups',
        string='Approver Group',
        help='Any user in this group can approve at this level.',
    )
    active = fields.Boolean(string='Active', default=True)

    @api.constrains('user_id', 'group_id')
    def _check_user_or_group(self):
        for record in self:
            if not record.user_id and not record.group_id:
                raise ValidationError(
                    _('Please select either an approver user or an approver group.')
                )
