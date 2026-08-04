from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PurchaseRequestApprovalHierarchy(models.Model):
    _name = 'purchase.request.approval.hierarchy'
    _description = 'Purchase Request Approval Hierarchy'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(string='Active', default=True)
    delegated_ids = fields.One2many(
        'purchase.request.approval.delegated',
        'hierarchy_id',
        string='Delegated Approvers',
        copy=True,
    )

    _check_one_active_per_company = models.Constraint(
        "UNIQUE (company_id)",
        'Only one approval hierarchy is allowed per company.',
    )

    @api.model
    def get_company_hierarchy(self, company_id=None):
        company_id = company_id or self.env.company.id
        hierarchy = self.search([('company_id', '=', company_id)], limit=1)
        if not hierarchy:
            hierarchy = self.create({
                'name': _('Default Approval Hierarchy'),
                'company_id': company_id,
            })
        return hierarchy
