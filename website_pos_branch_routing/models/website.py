from odoo import models
from odoo.http import request

CONTEXT_SESSION_KEY = 'dona_order_context'


class Website(models.Model):
    _inherit = 'website'

    def _get_and_cache_current_cart(self):
        """Apply the visitor's stored branch/order-type/schedule context (set
        via ``/dona/order/context``) onto the cart every time it is fetched or
        created, so it is always present by the time checkout/payment
        confirms the order - not just at cart-creation time (section 4/20)."""
        cart = super()._get_and_cache_current_cart()
        if cart and cart.state == 'draft':
            context_data = request and request.session.get(CONTEXT_SESSION_KEY)
            if context_data:
                cart.sudo()._dona_apply_branch_context(context_data)
        return cart
