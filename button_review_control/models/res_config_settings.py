from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auto_send_review = fields.Boolean(
        string="Auto Send for Review",
        config_parameter='button_review_control.auto_send_review',
        help="When enabled, invoices and bills are automatically sent for "
             "review when saved in draft state.",
    )
    review_for_checker = fields.Boolean(
        string="Review for Checker",
        config_parameter='button_review_control.review_for_checker',
        help="When enabled, entries created by checkers are also sent for "
             "review to other checkers, and the Request for Review button "
             "is shown to checkers.",
    )
