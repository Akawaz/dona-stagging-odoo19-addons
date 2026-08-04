from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    db_expiry_parameter_key = fields.Char(
        string='Expiry Parameter Key',
        config_parameter='database_expiry_scheduler.parameter_key',
        default='database.expiration_date',
        help="The ir.config_parameter key that holds the expiry date."
    )
    db_expiry_threshold_days = fields.Integer(
        string='Threshold (Days)',
        config_parameter='database_expiry_scheduler.threshold_days',
        default=30,
        help="If expiry is within this many days, it will be auto-extended."
    )
    db_expiry_extend_years = fields.Integer(
        string='Extend By (Years)',
        config_parameter='database_expiry_scheduler.extend_years',
        default=1,
        help="Number of years to add when extending the expiry."
    )
    db_expiry_auto_extend = fields.Boolean(
        string='Auto Extend Enabled',
        config_parameter='database_expiry_scheduler.auto_extend',
        default=True,
        help="Enable or disable the daily auto-extension cron job."
    )
