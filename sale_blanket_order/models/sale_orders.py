# Copyright 2018 ACSONE SA/NV
# Copyright 2019 Eficent and IT Consulting Services, S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    blanket_order_id = fields.Many2one(
        "sale.blanket.order",
        string="Origin blanket order",
        related="order_line.blanket_order_line.order_id",
    )
    dp_blanket = fields.Float(
        string="Down Payment",
        # related="blanket_order_id.down_payment",
    )
    dp_order = fields.Float(
        string="Order Down Payment", readonly=True,
        # compute="_compute_dp_order"
    )
    dp_sisa = fields.Float(
        string="Remaining Down Payment", readonly=True,
        compute="_compute_dp_sisa"
    )
    amount_total = fields.Monetary(string="Total", compute='_compute_amounts', tracking=4)

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
            # print('0', dp_order)
            # print('1', order.amount_untaxed)
            # print('2', order.amount_tax)
            # print('3', order.amount_total)
            # order.write({'amount_total': order.amount_total})

    # @api.depends('blanket_order_id')
    # def _compute_dp_order(self):
    #     for order in self:
            # if order.id and order.blanket_order_id:
            #     blanket = self.env['sale.blanket.order'].browse(order.blanket_order_id.id)
            #     if blanket:
            #         print('SO', blanket)
            #         print(order.dp_order)
            #         order.dp_order = blanket.dp_order  # Assign nilai blanket.dp_order ke order.dp_order
            #     else:
            #         order.dp_order = 0.0

            # dp_order_value = 0.0
            #
            # # for line in order.order_line:
            # if order.dp_order <= 0:
            #     print(order.dp_order)
            #     blanket = self.env['sale.blanket.order'].browse(order.blanket_order_id.id)
            #     dp_order_value += blanket.dp_order
            #
            #     order.dp_order = dp_order_value
            #     print('after if', order.dp_order)

    @api.depends('dp_blanket', 'dp_order')
    def _compute_dp_sisa(self):
        for order in self:
            order.dp_sisa = order.dp_blanket - order.dp_order
            # # Sum dp_order for all SaleOrders with the same blanket_order_id
            # if order.blanket_order_id:
            #     total_dp_order = sum(
            #         o.dp_order for o in self.search([('blanket_order_id', '=', order.blanket_order_id.id)])
            #     )
            # else:
            #     total_dp_order = 0.0
    
            # order.dp_sisa = order.dp_blanket - total_dp_order

    @api.model
    def _check_exchausted_blanket_order_line(self):
        return any(
            line.blanket_order_line.remaining_qty < 0.0 for line in self.order_line
        )

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            if order._check_exchausted_blanket_order_line():
                raise ValidationError(
                    _(
                        "Cannot confirm order %s as one of the lines refers "
                        "to a blanket order that has no remaining quantity."
                    )
                    % order.name
                )
        return res

    @api.constrains("partner_id")
    def check_partner_id(self):
        for line in self.order_line:
            if line.blanket_order_line:
                if line.blanket_order_line.partner_id != self.partner_id:
                    raise ValidationError(
                        _(
                            "The customer must be equal to the "
                            "blanket order lines customer"
                        )
                    )

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    blanket_order_line = fields.Many2one(
        "sale.blanket.order.line", string="Blanket Order line", copy=False
    )
    dp_blanket_line = fields.Float(
        string="Blanket Down Payment",
        related="order_id.dp_blanket",
        readonly=True,
    )
    dp_order_line = fields.Float(
        string="Down Payment Line",  # Adjust the label as needed
        # related="order_id.amount_invoiced"
        compute='_compute_dp_line'
    )

    # remaining_qty = fields.Float('Remain QTY', compute='_compute_remaining_qty')

    # @api.depends('product_uom_qty', 'qty_delivered')
    # def _compute_remaining_qty(self):
    #     for line in self:
    #         line.remaining_qty = line.product_uom_qty - line.qty_delivered

    # @api.depends('price_unit')
    # def _compute_dp_line(self):
    #     if self.price_unit < 0:
    #         self.dp_order_line = self.price_unit

    #dp_order_lama
    @api.depends('price_unit', 'product_uom_qty')  # Adjust dependencies as needed
    def _compute_dp_line(self):
        for line in self:
            if line.price_unit < 0:
                line.dp_order_line = 0.0  # Set to 0 if quantity is 0
            else:
                # Calculate down payment line (example logic)
                line.dp_order_line = line.price_unit * 1

    # @api.model
    # def create(self, vals):
    #     # Create the order line
    #     order_line = super(SaleOrderLine, self).create(vals)
    #
    #     # Update the dp_order field in the associated sale order
    #     if order_line.order_id:
    #         order_line.order_id._compute_dp_order()  # Call the method to update dp_order
    #
    #     return order_line
    #
    # def write(self, vals):
    #     # Update the sale order lines
    #     result = super(SaleOrderLine, self).write(vals)
    #
    #     # Update the dp_order field in the associated sale order
    #     for order_line in self:
    #         if order_line.order_id:
    #             order_line.order_id._compute_dp_order()
    #
    #     return result

    def _get_assigned_bo_line(self, bo_lines):
        # We get the blanket order line with enough quantity and closest
        # scheduled date
        assigned_bo_line = False
        date_planned = date.today()
        date_delta = timedelta(days=365)
        for line in bo_lines.filtered(lambda bo_line: bo_line.date_schedule):
            date_schedule = line.date_schedule
            if date_schedule and abs(date_schedule - date_planned) < date_delta:
                assigned_bo_line = line
                date_delta = abs(date_schedule - date_planned)
        if assigned_bo_line:
            return assigned_bo_line
        non_date_bo_lines = bo_lines.filtered(lambda bo_line: not bo_line.date_schedule)
        if non_date_bo_lines:
            return non_date_bo_lines[0]

    def _get_eligible_bo_lines_domain(self, base_qty):
        filters = [
            ("product_id", "=", self.product_id.id),
            ("remaining_qty", ">=", base_qty),
            ("currency_id", "=", self.order_id.currency_id.id),
            ("order_id.state", "=", "open"),
        ]
        if self.order_id.partner_id:
            filters.append(("partner_id", "=", self.order_id.partner_id.id))
        return filters

    def _get_eligible_bo_lines(self):
        base_qty = self.product_uom._compute_quantity(
            self.product_uom_qty, self.product_id.uom_id
        )
        filters = self._get_eligible_bo_lines_domain(base_qty)
        return self.env["sale.blanket.order.line"].search(filters)

    def get_assigned_bo_line(self):
        self.ensure_one()
        eligible_bo_lines = self._get_eligible_bo_lines()
        if eligible_bo_lines:
            if (
                not self.blanket_order_line
                or self.blanket_order_line not in eligible_bo_lines
            ):
                self.blanket_order_line = self._get_assigned_bo_line(eligible_bo_lines)
        else:
            self.blanket_order_line = False
        self.onchange_blanket_order_line()
        return {"domain": {"blanket_order_line": [("id", "in", eligible_bo_lines.ids)]}}

    @api.onchange("product_id", "order_partner_id")
    def onchange_product_id(self):
        # If product has changed remove the relation with blanket order line
        if self.product_id:
            return self.get_assigned_bo_line()
        return

    @api.onchange("product_uom", "product_uom_qty")
    def product_uom_change(self):
        if not self.product_uom or not self.product_id:
            self.price_unit = 0.0
            return
        if self.order_id.pricelist_id and self.order_id.partner_id:
            product = self.product_id.with_context(
                lang=self.order_id.partner_id.lang,
                partner=self.order_id.partner_id,
                quantity=self.product_uom_qty,
                date=self.order_id.date_order,
                pricelist=self.order_id.pricelist_id.id,
                uom=self.product_uom.id,
                fiscal_position=self.env.context.get("fiscal_position"),
            )
            self.price_unit = product._get_tax_included_unit_price(
                self.company_id or self.order_id.company_id,
                self.order_id.currency_id,
                self.order_id.date_order,
                "sale",
                fiscal_position=self.order_id.fiscal_position_id,
                product_price_unit=self._get_display_price(),
                product_currency=self.order_id.currency_id,
            )
        if self.product_id and not self.env.context.get("skip_blanket_find", False):
            return self.get_assigned_bo_line()
        return

    @api.onchange("blanket_order_line")
    def onchange_blanket_order_line(self):
        bol = self.blanket_order_line
        if bol:
            self.product_id = bol.product_id
            if bol.product_uom != self.product_uom:
                price_unit = bol.product_uom._compute_price(
                    bol.price_unit, self.product_uom
                )
            else:
                price_unit = bol.price_unit
            self.price_unit = price_unit
            if bol.taxes_id:
                self.tax_id = bol.taxes_id
        else:
            if not self.tax_id:
                self._compute_tax_id()
            self.with_context(skip_blanket_find=True).product_uom_change()

    @api.constrains("product_id")
    def check_product_id(self):
        for line in self:
            if (
                line.blanket_order_line
                and line.product_id != line.blanket_order_line.product_id
            ):
                raise ValidationError(
                    _(
                        "The product in the blanket order and in the "
                        "sales order must match"
                    )
                )

    @api.constrains("currency_id")
    def check_currency(self):
        for line in self:
            if line.blanket_order_line:
                if line.currency_id != line.blanket_order_line.order_id.currency_id:
                    raise ValidationError(
                        _(
                            "The currency of the blanket order must match with "
                            "that of the sale order."
                        )
                    )
