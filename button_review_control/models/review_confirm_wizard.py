from odoo import fields, models


class ReviewConfirmWizard(models.TransientModel):
    _name = 'review.confirm.wizard'
    _description = 'Review Confirmation'

    model_name = fields.Char(string="Model")
    res_id = fields.Integer(string="Record ID")

    def action_confirm(self):
        self.ensure_one()
        record = self.env[self.model_name].browse(self.res_id)
        return record.with_context(skip_review_confirm=True).action_post()
