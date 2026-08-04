from odoo import fields, models


class KitchenShift(models.Model):
    _name = "kitchen.shift"
    _description = "Kitchen Shift"
    _order = "sequence, start_time"

    name = fields.Char(
        string="Shift Name",
        required=True,
    )

    code = fields.Char(
        string="Code",
        help="Example: MORNING, EVENING, NIGHT",
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    start_time = fields.Float(
        string="Start Time",
        required=True,
        help="24-hour format. Example: 5.5 = 05:30",
    )

    end_time = fields.Float(
        string="End Time",
        required=True,
        help="24-hour format. Example: 13.0 = 13:00",
    )

    preparation_start = fields.Float(
        string="Preparation Starts",
        help="Optional. When preparation should begin.",
    )

    preparation_end = fields.Float(
        string="Preparation Ends",
        help="Optional. Target completion time.",
    )

    active = fields.Boolean(
        default=True,
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )

    notes = fields.Text(
        string="Notes",
    )

    _sql_constraints = [
        (
            "kitchen_shift_company_unique",
            "unique(name, company_id)",
            "The shift name must be unique per company.",
        )
    ]