from odoo import api, fields, models


class PrepareTemplate(models.Model):
    _name = "kitchen.prepare.template"
    _description = "Preparation Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(
        required=True,
        tracking=True,
    )

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    active = fields.Boolean(
        default=True,
        tracking=True,
    )

    line_ids = fields.One2many(
        "kitchen.prepare.template.line",
        "template_id",
        string="Products",
        copy=True,
    )


class PrepareTemplateLine(models.Model):
    _name = "kitchen.prepare.template.line"
    _description = "Preparation Template Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)

    template_id = fields.Many2one(
        "kitchen.prepare.template",
        string="Preparation Template",
        required=True,
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
    )

    uom_id = fields.Many2one(
        "uom.uom",
        related="product_id.uom_id",
        store=True,
        readonly=True,
    )

    par_level_qty = fields.Float(
        string="Par Level Qty",
        required=True,
        default=1.0,
    )

    note = fields.Char(
        string="Notes",
    )