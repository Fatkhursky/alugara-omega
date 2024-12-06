from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    custom_decimal_accuracy = fields.Integer(
        string="Custom Decimal Accuracy",
        help="Set custom decimal accuracy for this product if needed."
    )

class ProductProduct(models.Model):
    _inherit = 'product.product'

    def get_display_value(self, value):
        """Method to display value based on custom decimal accuracy"""
        decimal_places = self.custom_decimal_accuracy or 2  # Default to 2 if not set
        return f"{value:.{decimal_places}f}"
