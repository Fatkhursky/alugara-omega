from odoo import models, fields, api

class SaleTransferReport(models.Model):
    _inherit = "stock.move.line"

    sale_id = fields.Many2one('sale.order', string='Sales', store=True, compute='_compute_transaction')
    purchase_id = fields.Many2one('purchase.order', string='Purchase', store=True, compute='_compute_transaction')
    sale_line_id = fields.Many2one('sale.order.line', string='Sales Line', store=True, compute='_compute_transaction')
    purchase_line_id = fields.Many2one('purchase.order.line', string='Purchase Line', store=True, compute='_compute_transaction')
    sale_user_id = fields.Many2one(related='sale_id.user_id', store=True)
    purchase_user_id = fields.Many2one(related='purchase_id.user_id', store=True)
    sale_price_tax = fields.Float(related='sale_line_id.price_tax', store=True)
    purchase_price_unit = fields.Float(related='purchase_line_id.price_unit', store=True)
    sale_discount = fields.Float(string='Disc Sale', compute='_compute_transaction', store=True)
    purchase_discount = fields.Float(string='Disc Purchase', compute='_compute_transaction', store=True)
    transaction = fields.Char(string='Trans No', store=True, compute='_compute_transaction')
    ref = fields.Char(string='Ref No', store=True, compute='_compute_transaction')
    date_done = fields.Datetime('Posting Date', related='picking_id.date_done', store=True)
    product_from = fields.Many2one('stock.location', string='Source', store=True, compute='_compute_transaction')
    product_to = fields.Many2one('stock.location', string='Destination', store=True, compute='_compute_transaction')
    analytic_distribution = fields.Json(string='Analytic', store=True)
    analytic_precision = fields.Integer(store=False, default=lambda self: self.env['decimal.precision'].precision_get("Percentage Analytic"),)
    product_subtotal = fields.Float(string='Price', store=True, compute='_compute_transaction')
    qty_done = fields.Float('Done', default=0.0, digits='Product Unit of Measure', copy=False)

    def get_to_loc(self):
        transfer_id = self.move_id.order_id
        if transfer_id.route_id:
            print(transfer_id.route_id)
            rule_ids = transfer_id.route_id.rule_ids
            rule_ids = rule_ids.search([('id','in',rule_ids.ids)],order="sequence asc")
            if not rule_ids:
                product_from = False
                product_to = False
            else:
                product_from = rule_ids[0].location_src_id and rule_ids[0].location_src_id.id or False
                product_to = rule_ids[-1].location_id and rule_ids[-1].location_id.id or False
        else:
            product_from = False
            product_to = False
        return product_from,product_to

    @api.depends('move_id.sale_line_id', 'move_id.purchase_line_id')
    def _compute_transaction(self):
        for rec in self:
            if rec.move_id.sale_line_id:
                rec.sale_id = rec.move_id.sale_line_id.order_id
                rec.sale_line_id = rec.move_id.sale_line_id
                rec.transaction = rec.sale_id.name if rec.sale_id else False
                rec.ref = rec.sale_id.origin if rec.sale_id else False
                rec.product_from = rec.location_id
                rec.product_to = rec.location_dest_id
                rec.analytic_distribution = rec.sale_line_id.analytic_distribution or {}
                rec.product_subtotal = rec.move_id.sale_line_id.price_total
                rec.sale_discount = rec.move_id.sale_line_id.price_unit * rec.move_id.sale_line_id.discount / 100
                rec.purchase_id = False
                rec.purchase_line_id = False
                rec.purchase_discount = 0
            elif rec.move_id.purchase_line_id:
                rec.purchase_id = rec.move_id.purchase_line_id.order_id
                rec.purchase_line_id = rec.move_id.purchase_line_id
                rec.transaction = rec.purchase_id.name if rec.purchase_id else False
                rec.ref = rec.purchase_id.origin if rec.purchase_id else False
                rec.product_from = rec.location_id
                rec.product_to = rec.location_dest_id
                rec.analytic_distribution = rec.purchase_line_id.analytic_distribution or {}
                rec.product_subtotal = rec.move_id.purchase_line_id.price_total
                rec.purchase_discount = rec.move_id.purchase_line_id.price_unit * rec.move_id.purchase_line_id.discount / 100
                rec.sale_id = False
                rec.sale_line_id = False
                rec.sale_discount = 0
            else:
                rec.sale_id = False
                rec.purchase_id = False
                rec.sale_line_id = False
                rec.purchase_line_id = False
                rec.transaction = False
                rec.ref = False
                rec.product_from = False
                rec.product_to = False
                rec.analytic_distribution = {}
                rec.product_subtotal = 0
                rec.sale_discount = 0
                rec.purchase_discount = 0
