from odoo import models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def write(self, vals):

        result = super().write(vals)

        if "state" in vals or "qty_produced" in vals:

            lines = self.env[
                "kitchen.prepare.list.line"
            ].search([
                ("manufacturing_id", "in", self.ids)
            ])

            if lines:

                preparation_lists = lines.mapped(
                    "prepare_list_id"
                )

                preparation_lists._sync_production_status()

                lines._compute_produced_qty()

        return result