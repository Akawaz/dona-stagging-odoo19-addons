from odoo import fields, models


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    bulk_scrap_id = fields.Many2one(
        'bulk.scrap', string='Bulk Scrap', readonly=True, index=True)
