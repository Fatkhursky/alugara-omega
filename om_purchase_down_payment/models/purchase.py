# Copyright 2019 Elico Corp, Dominique K. <dominique.k@elico-corp.com.sg>
# Copyright 2019 Ecosoft Co., Ltd., Kitti U. <kittiu@ecosoft.co.th>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    dp_blanket = fields.Float(
        string="Down Payment",
        copy=False,
        force_save=True,
    )
    dp_order = fields.Float(
        string="Order Down Payment", readonly=False,
    )
    dp_order_latest = fields.Float(
        string="Order Down Payment Latest", readonly=False,
    )
    dp_sisa = fields.Float(
        string="Remaining Down Payment", readonly=True,
        compute="_compute_dp_sisa"
    )
    amount_total = fields.Monetary(string="Total", compute='_compute_amounts', tracking=4)
    any_received = fields.Boolean(compute='_compute_any_received_product', string='Any Received', readonly=False)

    def _compute_any_received_product(self):
        for order in self:
            any_received = False
            for line in order.order_line:
                if line.qty_received > 0:
                    any_received = True
            order.any_received = any_received
    
    @api.depends('')
    def _compute_field_name(self):
        pass

    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'order_line.price_total', 'dp_order')
    def _compute_amounts(self):
        """Compute the total amounts of the SO, deducting dp_order."""
        for order in self:
            order = order.with_company(order.company_id)
            order_lines = order.order_line.filtered(lambda x: not x.display_type)

            if order.company_id.tax_calculation_rounding_method == 'round_globally':
                tax_results = order.env['account.tax']._compute_taxes([
                    line._convert_to_tax_base_line_dict()
                    for line in order_lines
                ])
                totals = tax_results['totals']
                amount_untaxed = totals.get(order.currency_id, {}).get('amount_untaxed', 0.0)
                amount_tax = totals.get(order.currency_id, {}).get('amount_tax', 0.0)
            else:
                amount_untaxed = sum(order_lines.mapped('price_subtotal'))
                amount_tax = sum(order_lines.mapped('price_tax'))

            # Deduct dp_order from the total amount
            # dp_order = order.dp_order if hasattr(order, 'dp_order') else 0.0
            order.amount_untaxed = amount_untaxed
            order.amount_tax = amount_tax
            order.amount_total = order.amount_untaxed + order.amount_tax

    @api.depends('dp_blanket', 'dp_order')
    def _compute_dp_sisa(self):
        for order in self:
            order.dp_sisa = order.dp_blanket - order.dp_order

    def copy_data(self, default=None):
        if default is None:
            default = {}
        default["order_line"] = [
            (0, 0, line.copy_data()[0])
            for line in self.order_line
            if not line.is_deposit
        ]
        return super().copy_data(default)

    @api.onchange('dp_order_latest')
    def _onchange_dp_order_latest(self):
        if self.dp_order_latest > self.dp_order:
            raise ValidationError("DP order latest exceeds DP order")
        if self.dp_order_latest:
            self.dp_order += self.dp_order_latest

    def action_create_invoice(self):
        res = super(PurchaseOrder, self).action_create_invoice()
        advance_payment = self.env['purchase.advance.payment.inv'].search([('purchase_order_ids', 'in', self.id)],
                                                                          limit=1)
        deposit_product_id = advance_payment.purchase_deposit_product_id if advance_payment else None
        latest_invoice = self.env['account.move'].search(
            [('invoice_origin', '=', self.name)], order="create_date desc", limit=1
        )

        if latest_invoice and deposit_product_id:
            # Ensure down payment product line exists in the invoice
            deposit_line = latest_invoice.invoice_line_ids.filtered(lambda line: line.product_id == deposit_product_id)
            if not deposit_line:
                # Create a new line for the down payment product if missing
                latest_invoice.write({
                    'invoice_line_ids': [(0, 0, {
                        'product_id': deposit_product_id.id,
                        'quantity': -1.0,
                        'price_unit': 0.0,  # Placeholder; will be updated below
                    })]
                })

            # for line in latest_invoice.invoice_line_ids:
            #     if line.product_id == deposit_product_id:
            #         # Set price_unit according to the down payment values
            #         if self.dp_order_latest != 0:
            #             line.price_unit = self.dp_order_latest
            #         elif self.dp_order != 0:
            #             line.price_unit = self.dp_order
            #         else:
            #             line.price_unit = self.dp_blanket
            
            count_deposit_product_id = 0
            for line in latest_invoice.invoice_line_ids:
                if line.product_id == deposit_product_id:
                    count_deposit_product_id += 1
                    if count_deposit_product_id > 1:
                        line.unlink()
                    else:
                        # Set price_unit according to the down payment values
                        if self.dp_order_latest != 0:
                            line.price_unit = self.dp_order_latest
                        elif self.dp_order != 0:
                            line.price_unit = self.dp_order
                        else:
                            line.price_unit = self.dp_blanket

            # double_deposit_product_id = latest_invoice.invoice_line_ids.filtered(lambda line: line.product_id == deposit_product_id)
            # if len(double_deposit_product_id) > 1:

                            

            # Reset dp_order_latest to 0 after applying it to the invoice
            self.dp_order_latest = 0

        return res

class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    is_deposit = fields.Boolean(
        string="Is a deposit payment",
        help="Deposit payments are made when creating bills from a purchase"
        " order. They are not copied when duplicating a purchase order.",
    )

    def _prepare_account_move_line(self, move=False):
        res = super()._prepare_account_move_line(move=move)
        if self.is_deposit:
            res["quantity"] = -1 * self.qty_invoiced
        return res
