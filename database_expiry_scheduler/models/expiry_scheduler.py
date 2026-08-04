import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DatabaseExpiryScheduler(models.Model):
    _name = 'database.expiry.scheduler'
    _description = 'Database Expiry Scheduler'

    @api.model
    def _cron_check_and_extend_expiry(self):
        param_obj = self.env['ir.config_parameter'].sudo()

        # Read configuration
        param_key = param_obj.get_param(
            'database_expiry_scheduler.parameter_key',
            default='database.expiration_date'
        )
        threshold = int(param_obj.get_param(
            'database_expiry_scheduler.threshold_days',
            default='30'
        ))
        extend_years = int(param_obj.get_param(
            'database_expiry_scheduler.extend_years',
            default='1'
        ))
        auto_extend = param_obj.get_param(
            'database_expiry_scheduler.auto_extend',
            default='True'
        )

        if not param_key:
            _logger.warning("No expiry parameter key configured. Skipping check.")
            return

        if str(auto_extend).lower() not in ('1', 'true', 'yes'):
            _logger.info("Auto-extend is disabled. Skipping expiry check.")
            return

        expiry_str = param_obj.get_param(param_key)
        if not expiry_str:
            _logger.info("Expiry parameter '%s' is not set. Nothing to check.", param_key)
            return

        try:
            expiry_date = fields.Date.to_date(expiry_str)
        except ValueError:
            _logger.error("Invalid expiry date format for key '%s': %s", param_key, expiry_str)
            return

        today = fields.Date.today()
        days_remaining = (expiry_date - today).days

        _logger.info(
            "Expiry check: key=%s, expiry=%s, today=%s, days_remaining=%s, threshold=%s",
            param_key, expiry_date, today, days_remaining, threshold
        )

        if days_remaining <= threshold:
            new_expiry = expiry_date + relativedelta(years=extend_years)
            param_obj.set_param(param_key, fields.Date.to_string(new_expiry))
            _logger.info(
                "Database expiry auto-extended: %s -> %s (+%s year(s))",
                expiry_date, new_expiry, extend_years
            )
        else:
            _logger.info("Database expiry is not near. No action taken.")

        return True
