from odoo import fields, models, api


class KitchenPrepareListLine(models.Model):
    _name = "kitchen.prepare.list.line"
    _description = "Kitchen Preparation Line"
    _order = "id"

    prepare_list_id = fields.Many2one(
        "kitchen.prepare.list",
        required=True,
        ondelete="cascade",
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
    )

    current_stock = fields.Float(
        string="Current Stock",
        compute="_compute_current_stock",
        store=False,
        readonly=True,
    )

    @api.depends("product_id")
    def _compute_current_stock(self):
        for line in self:
            line.current_stock = line.product_id.qty_available

    par_level_qty = fields.Float(
        string="Par Level",
        required=True,
    )

    prepare_qty = fields.Float(
        string="Prepare Qty",
        required=True,
    )

    produced_qty = fields.Float(
        string="Produced Qty",
        compute="_compute_produced_qty",
        store=True,
        readonly=True,
        copy=False,
    )

    bom_id = fields.Many2one(
        "mrp.bom",
        string="Bill of Materials",
        readonly=True,
    )

    manufacturing_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        readonly=True,
    )

    production_state = fields.Selection(
        related="manufacturing_id.state",
        string="Production Status",
        store=True,
        readonly=True,
    )

    note = fields.Text(
        string="Remarks",
    )

    def action_view_bom(self):
        self.ensure_one()

        bom = self.env["mrp.bom"].search([
            "|",
            ("product_id", "=", self.product_id.id),
            ("product_tmpl_id", "=", self.product_id.product_tmpl_id.id),
        ], limit=1)

        if not bom:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "No Bill of Material",
                    "message": f"No Bill of Material found for {self.product_id.display_name}.",
                    "type": "warning",
                    "sticky": False,
                },
            }

        return {
            "type": "ir.actions.act_window",
            "name": "Bill of Material",
            "res_model": "mrp.bom",
            "res_id": bom.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.depends(
        "manufacturing_id.state",
        "manufacturing_id.qty_produced",
    )
    def _compute_produced_qty(self):

        for line in self:

            if line.manufacturing_id:

                line.produced_qty = line.manufacturing_id.qty_produced

            else:

                line.produced_qty = 0.0