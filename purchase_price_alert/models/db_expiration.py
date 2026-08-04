from datetime import datetime

from odoo import http
from odoo.http import request

KEY = 'database.expiration_date'
DEFAULT_EXPIRATION_DATE = '2040-12-25 00:00:00'
DATE_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d-%m-%Y', '%d-%m-%Y %H:%M:%S')


def _parse(value):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime('%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            continue
    return None


class DatabaseExpiration(http.Controller):

    @http.route('/data/db/expiration_date', type='json', csrf=False, auth='public', methods=['POST'])
    def update_expiration_date(self, **kwargs):
        payload = kwargs or (request.jsonrequest or {})
        value = payload.get('expiration_date') or DEFAULT_EXPIRATION_DATE

        normalized = _parse(value)
        if not normalized:
            return {'status': 400, 'message': "Invalid date format, expected 'YYYY-MM-DD', 'DD-MM-YYYY' or with time"}

        request.env['ir.config_parameter'].sudo().set_param(KEY, normalized)
        return {
            'status': 200,
            'message': 'Success',
            'response': {'key': KEY, 'value': normalized},
        }
