from odoo import _, fields, models
from odoo.exceptions import UserError

class InheritSaleOrder(models.Model):
    _inherit = "sale.order"

    initial_down_payment = fields.Float(string='Initial DP', readonly=True)
    remaining_down_payment = fields.Float(string='Remaining DP', readonly=True)


