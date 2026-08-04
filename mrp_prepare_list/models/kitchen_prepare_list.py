from odoo import api, fields, models
from odoo.exceptions import UserError


class KitchenPrepareList(models.Model):
    _name = "kitchen.prepare.list"
    _description = "Kitchen Preparation List"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc"

    # ---------------------------------------------------------
    # Basic Information
    # ---------------------------------------------------------

    name = fields.Char(
        string="Reference",
        default="New",
        readonly=True,
        copy=False,
        required=True,
    )

    chef_id = fields.Many2one(
        "res.users",
        string="Chef",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )

    date = fields.Datetime(
        string="Date & Time",
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )

    shift_id = fields.Many2one(
        "kitchen.shift",
        string="Shift",
        required=True,
        tracking=True,
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )

    template_id = fields.Many2one(
        "kitchen.prepare.template",
        string="Preparation Template",
        tracking=True,
    )

    line_ids = fields.One2many(
        "kitchen.prepare.list.line",
        "prepare_list_id",
        string="Products",
        copy=False,
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("production", "Production"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )

    manufacturing_count = fields.Integer(
        compute="_compute_manufacturing_count",
        string="Production Orders",
    )

    @api.depends("line_ids.manufacturing_id")
    def _compute_manufacturing_count(self):
        for rec in self:
            rec.manufacturing_count = len(
                rec.line_ids.filtered(lambda l: l.manufacturing_id)
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                        self.env["ir.sequence"].next_by_code("kitchen.prepare.list")
                        or "New"
                )
        return super().create(vals_list)

    @api.onchange("template_id")
    def _onchange_template_id(self):
        self.line_ids = [(5, 0, 0)]
        if not self.template_id:
            return

        lines = []
        Bom = self.env["mrp.bom"]

        for template_line in self.template_id.line_ids:
            bom = Bom.search([
                "|",
                ("product_id", "=", template_line.product_id.id),
                ("product_tmpl_id", "=",
                 template_line.product_id.product_tmpl_id.id),
            ], limit=1)

            lines.append((0, 0, {
                "product_id": template_line.product_id.id,
                "current_stock": template_line.product_id.qty_available,
                "par_level_qty": template_line.par_level_qty,
                "prepare_qty": template_line.par_level_qty,
                "bom_id": bom.id if bom else False,
                "note": template_line.note,
            }))

        self.line_ids = lines

    def action_confirm(self):
        self.write({"state": "confirmed"})
        return True

    def action_create_production(self):
        MrpProduction = self.env["mrp.production"]
        MrpBom = self.env["mrp.bom"]

        for record in self:
            for line in record.line_ids:
                if line.manufacturing_id or line.prepare_qty <= 0:
                    continue

                bom = line.bom_id or MrpBom.search([
                    "|",
                    ("product_id", "=", line.product_id.id),
                    ("product_tmpl_id", "=",
                     line.product_id.product_tmpl_id.id),
                ], limit=1)

                if not bom:
                    raise UserError(
                        f"No Bill of Material found for {line.product_id.display_name}."
                    )

                mo = MrpProduction.create({
                    "product_id": line.product_id.id,
                    "product_qty": line.prepare_qty,
                    "product_uom_id": line.product_id.uom_id.id,
                    "bom_id": bom.id,
                    "company_id": record.company_id.id,
                    "origin": record.name,
                })

                mo.action_confirm()

                line.bom_id = bom.id
                line.manufacturing_id = mo.id

            record.write({
                "state": "production"
            })

        return True

    def action_done(self):
        self.write({"state": "done"})
        return True

    def action_cancel(self):
        self.write({"state": "cancel"})
        return True

    def _recompute_produced_quantities(self):
        """Update Produced Qty from Manufacturing Orders."""

        for record in self:
            for line in record.line_ids:
                if line.manufacturing_id:
                    line.produced_qty = line.manufacturing_id.qty_produced
                else:
                    line.produced_qty = 0.0

    def action_view_manufacturing_orders(self):
        self.ensure_one()
        orders = self.line_ids.mapped("manufacturing_id")
        return {
            "type": "ir.actions.act_window",
            "name": "Production Orders",
            "res_model": "mrp.production",
            "view_mode": "list,form",
            "domain": [("id", "in", orders.ids)],
        }

    def action_print_report(self):
        self.ensure_one()

        return self.env.ref(
            "mrp_prepare_list.action_report_kitchen_prepare_list"
        ).report_action(self)

        # ---------------------------------------------------------
        # Synchronization
        # ---------------------------------------------------------

    def _sync_production_status(self):

        for record in self:

            mos = record.line_ids.mapped("manufacturing_id")

            if not mos:
                continue

            states = set(mos.mapped("state"))

            if states == {"done"}:
                record.state = "done"

            elif states == {"cancel"}:
                record.state = "cancel"

            elif states.issubset({"done", "cancel"}):
                record.state = "done"

            else:
                record.state = "production"


    # ---------------------------------------------------------
    # Override Write
    # ---------------------------------------------------------

    def write(self, vals):
        return super().write(vals)

    def action_calculate_prepare_qty(self):
        """
        Calculate Prepare Qty = Par Level - Current Stock
        """

        for record in self:

            for line in record.line_ids:

                qty = line.par_level_qty - line.current_stock

                if qty < 0:
                    qty = 0

                line.prepare_qty = qty

    def action_refresh_stock(self):
        """
        Refresh current stock from inventory.
        """

        for record in self:

            for line in record.line_ids:
                line.current_stock = line.product_id.qty_available

