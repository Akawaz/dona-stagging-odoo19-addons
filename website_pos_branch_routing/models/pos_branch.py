from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosBranch(models.Model):
    """Backend configuration of a website ordering branch and the POS that must
    receive every website order placed for that branch.

    This intentionally reuses the company/website structure already in place
    for this multi-branch business (one ``res.company`` and one ``website``
    per physical branch) instead of inventing a parallel branch model: a
    branch here simply *is* one of those companies, plus the POS assignment
    the existing setup did not yet have.
    """
    _name = 'pos.branch'
    _description = 'Website Ordering Branch'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char(
        required=True,
        help="Must match the branchCode / branchId sent by the website ordering "
             "widget (e.g. MUHARRAQ, MANAMA, RIFFA). Stored upper-case.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        help="The branch's own company. Website orders resolved to this branch "
             "are created in the branch's POS under this company.",
    )
    website_id = fields.Many2one(
        'website', string='Website',
        help="Optional: the specific website record for this branch, if this "
             "business also splits branches across separate websites.",
    )
    pos_config_id = fields.Many2one(
        'pos.config', string='Point of Sale', required=True,
        domain="[('company_id', '=', company_id)]",
        help="The POS that must receive every website order placed for this branch.",
    )
    online_payment_method_id = fields.Many2one(
        'pos.payment.method', string='Online Payment Method',
        help="POS payment method used to record the payment when the website "
             "order was already fully paid online. Leave empty to always leave "
             "the resulting POS order unpaid (draft) for the cashier to settle "
             "manually - the safer default when unsure.",
    )
    address = fields.Char(string='Branch Address')
    phone = fields.Char(string='Branch Phone')
    pos_key = fields.Char(
        string='Legacy POS Key',
        help="Informational only - mirrors the website widget's `posKey`. "
             "Never used for security or POS selection: routing is always "
             "resolved server-side from `code`.",
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'A branch with this code already exists.'),
    ]

    @api.constrains('pos_config_id', 'company_id')
    def _check_pos_config_company(self):
        for branch in self:
            if branch.pos_config_id and branch.pos_config_id.company_id != branch.company_id:
                raise ValidationError(_(
                    "The POS assigned to branch %(branch)s must belong to the "
                    "branch's own company (%(company)s).",
                    branch=branch.name, company=branch.company_id.name,
                ))

    @api.onchange('code')
    def _onchange_code_upper(self):
        for branch in self:
            if branch.code:
                branch.code = branch.code.strip().upper()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].strip().upper()
        return super().write(vals)

    @api.model
    def _get_by_code(self, code):
        """Trusted, server-side resolution of a branch from its code.

        This is the ONLY path used to turn a browser-supplied branch code into
        an actual POS assignment - a POS id or key sent directly by the
        browser is never trusted (see controllers/website_order.py).
        """
        code = (code or '').strip().upper()
        if not code:
            return self.browse()
        return self.sudo().search([('code', '=', code), ('active', '=', True)], limit=1)
