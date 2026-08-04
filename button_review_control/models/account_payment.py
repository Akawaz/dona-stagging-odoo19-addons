from odoo import api, fields, models, _


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    review_requested = fields.Boolean(
        string="Review Requested",
        default=False,
        copy=False,
    )
    review_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('to_review', 'Waiting for Review'),
            ('reviewed', 'Reviewed'),
        ],
        string="Review Status",
        default='draft',
        copy=False,
        tracking=True,
        help="Custom review workflow status, independent from the payment "
             "state (draft/in_process/paid/cancel).",
    )
    reviewed_by = fields.Many2one(
        'res.users',
        string='Reviewed By',
        copy=False,
        tracking=True,
    )
    reviewed_on = fields.Datetime(
        string='Reviewed On',
        copy=False,
        tracking=True,
    )
    can_request_review = fields.Boolean(
        compute='_compute_can_request_review',
        string='Can Request Review',
    )

    def _compute_can_request_review(self):
        maker_group = self.env.ref('button_review_control.group_maker', raise_if_not_found=False)
        checker_group = self.env.ref('button_review_control.group_checker', raise_if_not_found=False)
        checker_review = self.env['ir.config_parameter'].sudo().get_param(
            'button_review_control.review_for_checker', False)
        user = self.env.user
        is_maker = user in maker_group.user_ids if maker_group else False
        is_checker = user in checker_group.user_ids if checker_group else False
        for rec in self:
            rec.can_request_review = is_maker or (is_checker and checker_review)

    def _mark_review_activities_done(self, feedback):
        """Close all open activities on the given records with feedback."""
        for record in self:
            activities = self.env['mail.activity'].search([
                ('res_model', '=', record._name),
                ('res_id', '=', record.id),
            ])
            for activity in activities:
                activity.action_feedback(feedback=feedback)

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        from_invoice = self.env.context.get('active_model') in ('account.move', 'account.move.line')
        auto_send = self.env['ir.config_parameter'].sudo().get_param(
            'button_review_control.auto_send_review', False)
        checker_review = self.env['ir.config_parameter'].sudo().get_param(
            'button_review_control.review_for_checker', False)
        checker_group = self.env.ref('button_review_control.group_checker', raise_if_not_found=False)
        is_checker = checker_group and self.env.user in checker_group.user_ids
        do_auto_send = auto_send and not (is_checker and not checker_review)
        if from_invoice:
            for payment in payments:
                payment.review_state = 'reviewed'
                payment.reviewed_by = self.env.user
                payment.reviewed_on = fields.Datetime.now()
        elif do_auto_send or (checker_review and is_checker):
            for payment in payments:
                if payment.review_state == 'draft':
                    payment.action_request_review()
        return payments

    def action_mark_reviewed(self):
        """Server action: mark selected records as reviewed (checker only)."""
        for rec in self:
            if rec.review_state == 'to_review':
                rec._mark_review_activities_done(
                    _("Approved by %s") % self.env.user.name)
                rec.review_state = 'reviewed'
                rec.review_requested = False
                rec.reviewed_by = self.env.user
                rec.reviewed_on = fields.Datetime.now()

    def action_post(self):
        """Override: when a record is waiting for review, mark the review as
        done (activities closed, reviewed_by/on set) before posting.
        If the creator is the same as the confirmer, show a confirmation dialog."""
        to_review = self.filtered(lambda r: r.review_state == 'to_review')
        if to_review and not self.env.context.get('skip_review_confirm'):
            checker_review = self.env['ir.config_parameter'].sudo().get_param(
                'button_review_control.review_for_checker', False)
            if checker_review:
                self_confirm = to_review.filtered(lambda r: r.create_uid == self.env.user)
                if self_confirm and len(self) == 1:
                    return {
                        'type': 'ir.actions.act_window',
                        'name': _('Confirm Review'),
                        'res_model': 'review.confirm.wizard',
                        'view_mode': 'form',
                        'target': 'new',
                        'context': {
                            'default_model_name': self._name,
                            'default_res_id': self.id,
                        },
                    }
        if to_review:
            to_review._mark_review_activities_done(
                _("Approved by %s") % self.env.user.name)
            for rec in to_review:
                rec.review_state = 'reviewed'
                rec.review_requested = False
                rec.reviewed_by = self.env.user
                rec.reviewed_on = fields.Datetime.now()
        return super().action_post()

    def action_request_review(self):
        """Notify users in the Checker group."""
        self.ensure_one()
        group = self.env.ref('button_review_control.group_checker', raise_if_not_found=False)
        if not group or not group.user_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Checkers'),
                    'message': _('No users found in the Checker group.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        user_ids = [u.id for u in group.user_ids if u.id != self.env.user.id]
        if not user_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Other Checkers'),
                    'message': _('You are the only member of the Checker group.'),
                    'type': 'info',
                    'sticky': False,
                },
            }

        for user_id in user_ids:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_("Review Requested – %s") % self.name,
                note=_("%(user)s (Maker) requested a review for Payment %(name)s",
                       user=self.env.user.name,
                       name=self.name),
                user_id=user_id,
            )

        self.review_requested = True
        self.review_state = 'to_review'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Review Requested'),
                'message': _('Notification sent to %s checker(s).') % len(user_ids),
                'type': 'success',
                'sticky': False,
            },
        }

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            if vals['state'] in ('in_process', 'paid', 'cancel'):
                for payment in self:
                    open_activities = self.env['mail.activity'].search([
                        ('res_model', '=', 'account.payment'),
                        ('res_id', '=', payment.id),
                    ])
                    for activity in open_activities:
                        activity.action_feedback(feedback=_("Payment %s") % vals['state'])
            elif vals['state'] == 'draft':
                for payment in self:
                    payment.review_requested = False
                    payment.review_state = 'draft'
                    payment.reviewed_by = False
                    payment.reviewed_on = False
        return res
