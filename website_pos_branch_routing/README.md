# Website Orders to Branch POS

Routes confirmed Odoo 19 eCommerce website orders to the correct branch's
Point of Sale, based on the branch the customer selected on the website's
existing branch/pickup-delivery/date-time picker.

## Why this module exists / how it fits your current setup

Your instance already has one `res.company` and one `website` per physical
branch (Muharraq, Manama, Riffa) - see `DONAS_WONDERS_BRANCH_SETUP_GUIDE.md`
in the repo root. That setup determines which **company** an order belongs
to. It does **not** yet determine which **POS** (`pos.config`) should
receive the order - that mapping didn't exist anywhere in the backend, so
every website order was invisible to the point of sale.

This module adds that missing piece:

```
Website widget (already built)          This module (new)
--------------------------------        ---------------------------------
Customer picks a branch,                 pos.branch: backend-editable
pickup/delivery, date & time        ->   Branch -> Company -> POS mapping
        |
POST /dona/order/context            ->   Validated server-side, stored on
(already implemented in the widget)      the visitor's session + the cart
        |
Checkout / Payment (native Odoo)    ->   sale.order gets branch_id,
                                          order_type, scheduled_date/time
        |
sale.order.action_confirm()         ->   Routing engine resolves the
(fires once payment/approval is          branch's POS + open session and
actually settled - native Odoo)         creates the matching pos.order,
                                          preserving variants/comments/
                                          schedule, then notifies the
                                          branch's open POS over Odoo's own
                                          bus/synchronisation channel.
```

No Odoo core file is modified. Everything is additive: new model, new
fields, one new controller, and small, targeted overrides of
`sale.order.action_confirm()`, `website._get_and_cache_current_cart()` and
`pos.session.action_pos_session_open()`.

## 1. Installation

1. Copy `website_pos_branch_routing/` into `custom-addons/` (already done).
2. Update Apps list and install **Website Orders to Branch POS**. It depends
   on `base`, `sale_management`, `website`, `website_sale`, `point_of_sale` -
   all already installed on this instance.
3. No data migration is needed; nothing is auto-configured (see below).

## 2. Configuration (no JavaScript required)

Point of Sale app -> Configuration -> **Branches**.

For each branch (Muharraq, Manama, Riffa):

| Field | Value |
|---|---|
| Name | e.g. `DONAS WONDERS W.L.L-Muharraq` |
| Code | e.g. `MUHARRAQ` - **must exactly match** the `code`/`id` used in the website widget's `DONA_ORDER_BRANCHES` (case-insensitive; the module upper-cases it) |
| Company | the branch's existing company (e.g. `DONAS WONDERS WLL-Muharraq`) |
| Point of Sale | the `pos.config` that belongs to that company and must receive its orders |
| Online Payment Method | *(optional)* a POS payment method to mark the POS order "Paid" automatically when the website order was already paid online. Leave empty to always leave it as an open/draft POS order for the cashier to settle - the safer default while you're still deciding on a live payment gateway (see `DONAS_WONDERS_BRANCH_SETUP_GUIDE.md`, item 1). |
| Address / Phone | optional, for display on the sale order |

If a branch's POS doesn't exist yet, create it first under Point of Sale ->
Configuration -> Point of Sale, in that branch's company.

The branch list is intentionally **not** shipped as install data - there is
no hard-coded branch list anywhere in this module's Python/XML, per the
brief. You configure it once, here.

## 3. Required change to the existing website widget

The widget already POSTs its context to `/dona/order/context` and this
module now implements that endpoint - most of the wiring needs **no**
frontend change at all.

One real gap exists: the widget captures a per-product "Additional
comments" textarea into `state.product.additionalComments`, but never
actually sends it anywhere - `/shop/cart/add` has no field for it. Since
this text lives in the page's embedded HTML (Website Builder content, not a
module asset file), it can't be patched by installing an addon. Apply the
small patch documented in
[`static/src/js/dona_website_patch_reference.js`](static/src/js/dona_website_patch_reference.js)
(PATCH 1, required for comments to reach the POS; PATCH 2 is optional -
makes Odoo's branch list authoritative instead of the JS fallback array).

Everything else - the branch/date/time modal, the OpenStreetMap picker, the
product configurator, checkout - is untouched, per the brief's instruction
not to rebuild the existing branch selector.

## 4. How the complete flow works

1. **Branch selection.** The customer picks a branch/pickup-or-delivery/date/
   time in the existing modal. `confirmOrder()` already calls
   `pushContextToOdoo(ctx)`, POSTing to `/dona/order/context`.
2. **Server-side validation (section 19).** The controller
   (`controllers/website_order.py`) resolves the branch **only** from its
   `code`, via `pos.branch._get_by_code()` - a real, active `pos.branch`
   record. The browser's `branchPosKey` is read only for display purposes
   and is never used to pick a POS. Mode, date and time are all format- and
   range-checked before being trusted.
3. **Session storage.** The validated context is stored in the visitor's
   Odoo HTTP session (`request.session['dona_order_context']`) - not just
   `localStorage` - and applied immediately to the current cart if one
   exists.
4. **Cart sync.** `website._get_and_cache_current_cart()` is extended so
   that every time the visitor's cart is fetched or created (i.e. on every
   `/shop/cart/add`), the stored context is (re-)applied onto the
   `sale.order`: `branch_id`, `order_type`, `scheduled_date`,
   `scheduled_time`. This means the branch is attached to the order the
   moment the first product is added, and stays in sync if the customer
   changes branch mid-session, well before checkout/payment.
5. **Product variants & comments (sections 9-10).** The product
   configurator drawer already uses Odoo's own
   `/website_sale/product_configurator/*` endpoints and `/shop/cart/add`, so
   the exact selected `product.product` variant (and any `no_variant`/custom
   attribute values) is what ends up on `sale.order.line.product_id` -
   nothing here replaces it with the parent product. The per-product
   comment is written onto the new `sale.order.line.dona_customer_note`
   field via `/dona/order/line_note`, keyed by the `line_id` Odoo's own
   `/shop/cart/add` already returns.
6. **Payment & confirmation (section 13).** Nothing is routed to the POS
   until Odoo itself confirms the order - `sale.order.action_confirm()` is
   only called once by Odoo's own eCommerce/payment flow, whether that's
   automatic on payment success or a manual backend confirmation. This
   module only *hooks* that method; it never confirms an order itself and
   never touches unpaid/cancelled orders, because they never reach
   `action_confirm()`.
7. **Branch -> POS resolution (section 5).** On confirmation, the branch's
   `pos.branch.pos_config_id` is resolved and locked (`SELECT ... FOR
   UPDATE`) before anything else happens, guaranteeing one order can never
   be routed twice even under retries/concurrent requests (section 14).
8. **POS order creation (section 6).** A `pos.order` is created through the
   standard `pos.order.create()` ORM API (the same public method Odoo itself
   uses for backend-created orders) with:
   - `session_id` set to the branch's currently **open** session,
   - one `pos.order.line` per `sale.order.line`, carrying the exact
     `product_id`, quantity, price, tax, `no_variant`/custom attribute
     values and the per-line `customer_note`,
   - `shipping_date` / `preset_time` (both **native** POS fields, reused
     rather than duplicated) set from the requested date/time,
   - `general_customer_note` (native POS field) carrying the order-level
     note plus a clear "Paid online" / "To settle at the branch" marker,
   - `state` left `draft` (open, needs settling) unless the order was
     already paid online **and** the branch has an `online_payment_method_id`
     configured, in which case it's created `paid` with a matching
     `pos.payment`.
9. **Case A - POS session open.** The order is created directly against that
   session (above) and `pos_config.notify_synchronisation(...)` is called -
   the exact same native bus mechanism Odoo's multi-cashier "same session,
   different device" sync uses (`devices_synchronisation.js`). The branch's
   already-open POS picks it up live, no refresh needed.
10. **Case B - POS session closed (section 7).** No `pos.order` is created
    yet (a `pos.order` without an open session isn't valid). The website
    order is marked `pos_routing_state = 'queued'` instead. The moment that
    branch's POS session is opened, `pos.session.action_pos_session_open()`
    (overridden here) immediately routes every queued order for that
    config. A safety-net cron (`_dona_cron_retry_queued_orders`, every 15
    minutes) re-attempts any still-queued order in case that hook is ever
    missed.
11. **Traceability (section 18).** `sale.order.pos_order_id` and
    `pos.order.website_sale_order_id` link the two records both ways, with
    smart buttons on each form to jump to the other.
12. **Errors (section 15).** Every failure path (no branch, inactive branch,
    no POS configured, currency mismatch, no valid lines, any ORM error) sets
    `pos_routing_state = 'failed'` with a human-readable
    `pos_routing_error`, logs an ERROR-level message, and - critically -
    never raises out of `action_confirm()`. The website order confirmation
    itself always succeeds even if POS routing fails; a manager fixes the
    branch/POS configuration and re-triggers routing by writing
    `pos_routing_state` back to `pending` and calling
    `sale_order._dona_route_to_pos()` (e.g. from a server action).

## 5. Testing plan

Functional (needs a POS session open on at least one branch, and the
website widget live):

- [ ] **Branch routing**: place one order per branch (Muharraq, Manama,
  Riffa) and confirm each lands in that branch's POS only, never another's.
- [ ] **Order types**: one pickup order, one delivery order; confirm
  `order_type` shows correctly on both `sale.order` and the resulting
  `pos.order`'s notes.
- [ ] **Products**: a simple product, a product with variants (different
  attribute combination), multiple products in one order, quantities > 1.
- [ ] **Comments**: a product-specific comment (after applying PATCH 1) and
  confirm it appears on the matching POS order line's "Customer Note"; a
  general order note (if you wire one in) appears in the POS order's
  general note.
- [ ] **Scheduling**: an immediate ("now") order and a future ("order ahead")
  order; confirm `shipping_date`/`preset_time` are set on the POS order and
  differ visibly from `date_order` (order creation time).
- [ ] **Payment**: a successful payment (Cash on Delivery is enough per the
  setup guide), a failed transaction, a cancelled checkout - only the
  successful one should ever create a POS order.
- [ ] **POS sessions**: with the branch's POS session open, confirm the
  order and watch it appear in the open POS UI without a refresh; then close
  the session, place another order (state should become `queued`), reopen
  the session and confirm it appears automatically.
- [ ] **Reliability**: refresh the order confirmation page / resend the
  checkout POST twice; confirm only one `pos.order` is ever created
  (`sale_order.pos_order_id` stays stable). Try a branch code that doesn't
  exist in `pos.branch` and confirm the order is simply left without a
  branch (checkout still works) rather than erroring. Remove a branch's POS
  assignment and confirm the next order for that branch ends up `failed`
  with a clear `pos_routing_error`, not silently dropped.

Automated: standard Odoo `TransactionCase` tests are the natural fit for
`_dona_route_single_order_to_pos` (create a `pos.branch`, `pos.config` with
an opened `pos.session`, a confirmed `sale.order` with `branch_id` set, call
the method, assert `pos_order_id`/`pos_routing_state`); none are bundled
here so as not to guess at your CI setup, but the method is written to be
called directly and deterministically for exactly this purpose.

## 6. Known limitations / deliberate simplifications

- **Currency**: if a branch's POS runs in a different currency than the
  website order, routing fails fast with a clear error rather than silently
  converting - add currency conversion explicitly if you ever need
  multi-currency branches.
- **Online payment reconciliation**: this module does not invent a payment
  method mapping for you. Until you configure `online_payment_method_id` on
  a branch, POS orders always arrive as open/`draft`, which is the safe
  default while the real payment gateway decision (flagged as open in
  `DONAS_WONDERS_BRANCH_SETUP_GUIDE.md`) is still pending.
- **General (order-level) comment**: the current widget only has a
  per-product comment field; `sale.order.customer_note` exists and is wired
  through end-to-end, but nothing in the existing widget currently populates
  it. Add a field to the `/dona/order/context` payload (`note`) whenever a
  general-comments UI is added - the backend already accepts it.
