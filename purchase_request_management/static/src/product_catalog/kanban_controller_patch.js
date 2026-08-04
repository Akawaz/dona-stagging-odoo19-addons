/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductCatalogKanbanController } from "@product/product_catalog/kanban_controller";

patch(ProductCatalogKanbanController.prototype, {
    _defineButtonContent() {
        if (this.orderResModel === "purchase.request") {
            this.buttonString = _t("Back to Purchase Request");
            return;
        }
        super._defineButtonContent(...arguments);
    },
});
