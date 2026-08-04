from odoo import models, api


class PurchaseRequestReport(models.AbstractModel):
    _name = 'report.purchase_request_management.report_purchase_request'
    _description = 'Purchase Request Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['purchase.request'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'purchase.request',
            'docs': docs,
            'company': self.env.company,
        }
