import json
import logging
import re
from datetime import date

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
_ALLOWED_MODES = ('pickup', 'delivery')
_CONTEXT_SESSION_KEY = 'dona_order_context'
_MAX_NOTE_LEN = 2000


def _read_json_body():
    try:
        raw = request.httprequest.get_data(as_text=True) or '{}'
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


class DonaWebsiteOrderController(http.Controller):
    """Bridges the existing embedded website ordering widget (branch / pickup
    or delivery / date / time picker, posting to ``/dona/order/context``) to
    the backend ``pos.branch`` configuration and the customer's Odoo
    eCommerce cart (section 4, 19, 20).

    Every value received here is untrusted browser input and is validated
    before being stored. In particular, the branch is always re-resolved
    server-side from its code against real ``pos.branch`` records - a
    ``branchPosKey``/POS id sent by the browser is never used to pick a POS
    (section 19).
    """

    @http.route('/dona/order/context', type='http', auth='public', website=True,
                csrf=False, methods=['POST'])
    def dona_order_context(self, **post):
        payload = _read_json_body()
        if payload is None:
            return request.make_json_response(
                {'error': {'message': 'Invalid JSON payload.'}}, status=400,
            )

        branch_code = str(payload.get('branchCode') or payload.get('branch_code') or '').strip()
        branch = request.env['pos.branch']._get_by_code(branch_code)
        if not branch_code or not branch:
            _logger.info(
                "Website order context POST rejected: unknown/inactive branch code %r",
                branch_code,
            )
            return request.make_json_response(
                {'error': {'message': 'Unknown or inactive branch.'}}, status=400,
            )

        mode = payload.get('mode')
        if mode not in _ALLOWED_MODES:
            mode = None

        order_date = payload.get('date')
        if order_date:
            try:
                date.fromisoformat(order_date)
            except (TypeError, ValueError):
                order_date = None

        order_time = payload.get('time')
        if order_time and not _TIME_RE.match(order_time):
            order_time = None

        note = payload.get('note') or payload.get('customerNote')
        if note:
            note = str(note)[:_MAX_NOTE_LEN]

        context_data = {
            'branch_code': branch.code,
            'mode': mode,
            'date': order_date,
            'time': order_time,
            'note': note,
        }
        request.session[_CONTEXT_SESSION_KEY] = context_data

        # Apply immediately to an existing cart too, not just future ones -
        # covers a customer changing branch after already adding products.
        cart = request.cart
        if cart and cart.state == 'draft':
            cart.sudo()._dona_apply_branch_context(context_data)

        return request.make_json_response({
            'success': True,
            'branch': {'code': branch.code, 'name': branch.name},
        })

    @http.route('/dona/order/branches', type='http', auth='public', website=True,
                methods=['GET'])
    def dona_order_branches(self, **kwargs):
        """Odoo as source of truth for the branch list (section 16). The
        existing JavaScript fallback data can stay in place as a fallback for
        when this endpoint is unreachable, but the backend is authoritative."""
        branches = request.env['pos.branch'].sudo().search([('active', '=', True)])
        data = [{
            'id': branch.code,
            'code': branch.code,
            'name': branch.name,
            'address': branch.address or '',
            'phone': branch.phone or '',
        } for branch in branches]
        return request.make_json_response(data)

    @http.route('/dona/order/line_note', type='http', auth='public', website=True,
                csrf=False, methods=['POST'])
    def dona_order_line_note(self, **post):
        """Receives the per-product comment captured on the website product
        configurator drawer and attaches it to the matching cart line
        (section 10). ``line_id`` is the ``line_id`` already returned by the
        native ``/shop/cart/add`` response - no new cart mechanism needed."""
        payload = _read_json_body()
        if payload is None:
            return request.make_json_response(
                {'error': {'message': 'Invalid JSON payload.'}}, status=400,
            )

        try:
            line_id = int(payload.get('line_id'))
        except (TypeError, ValueError):
            line_id = None

        cart = request.cart
        if not cart or cart.state != 'draft' or not line_id:
            return request.make_json_response(
                {'error': {'message': 'No active cart or missing line_id.'}}, status=400,
            )

        line = cart.sudo().order_line.filtered(lambda l: l.id == line_id)
        if not line:
            return request.make_json_response(
                {'error': {'message': 'Line not found on the current cart.'}}, status=404,
            )

        note = payload.get('note')
        line.sudo().write({
            'dona_customer_note': str(note)[:_MAX_NOTE_LEN] if note else False,
        })
        return request.make_json_response({'success': True})
