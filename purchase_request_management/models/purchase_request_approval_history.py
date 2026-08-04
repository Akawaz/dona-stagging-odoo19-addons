from odoo import models, fields, api


class PurchaseRequestApprovalHistory(models.Model):
    _name = 'purchase.request.approval.history'
    _description = 'Purchase Request Approval History'
    _order = 'sequence, id'

    request_id = fields.Many2one(
        'purchase.request',
        string='Purchase Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    level = fields.Integer(
        string='Level',
        required=True,
        default=1,
    )
    name = fields.Char(string='Name')
    user_id = fields.Many2one(
        'res.users',
        string='Approver User',
        readonly=True,
    )
    group_id = fields.Many2one(
        'res.groups',
        string='Approver Group',
        readonly=True,
    )
    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='pending',
        required=True,
    )
    approved_date = fields.Datetime(
        string='Approved/Rejected Date',
        readonly=True,
    )
    approver_user_id = fields.Many2one(
        'res.users',
        string='Action By',
        readonly=True,
        help='User who actually approved or rejected.',
    )
