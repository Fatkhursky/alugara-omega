# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import format_date, frozendict

class AccountMove(models.Model):
    _inherit = 'account.move'

    sale_blanket_order_ids = fields.Many2many(
        'sale.blanket.order',
        'account_move_sale_blanket_order_rel',
        'account_move_id',
        string="Sale Blanket Order"
    )

class SaleBlanketAdvancePaymentInv(models.TransientModel):
    _name = 'sale.blanket.advance.payment.inv'
    _description = "Sales Blanket Advance Payment Invoice"

    advance_payment_method = fields.Selection(
        selection=[
            # ('delivered', "Regular invoice"),
            ('percentage', "Down payment (percentage)"),
            ('fixed', "Down payment (fixed amount)"),
        ],
        string="Create Invoice",
        default='fixed',
        required=True,
        help="A standard invoice is issued with all the order lines ready for invoicing,"
            "according to their invoicing policy (based on ordered or delivered quantity).")
    count = fields.Integer(string="Order Count", compute='_compute_count')
    sale_blanket_order_ids = fields.Many2many(
        'sale.blanket.order', default=lambda self: self.env.context.get('active_ids'))

    # Down Payment logic
    has_down_payments = fields.Boolean(
        string="Has down payments", compute="_compute_has_down_payments")
    deduct_down_payments = fields.Boolean(string="Deduct down payments", default=True)

    # New Down Payment
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Down Payment Product",
        domain=[('type', '=', 'service')],
        compute='_compute_product_id',
        readonly=False,
        store=True)
    amount = fields.Float(
        string="Down Payment Amount",
        help="The percentage of amount to be invoiced in advance.")
    fixed_amount = fields.Monetary(
        string="Down Payment Amount (Fixed)",
        help="The fixed amount to be invoiced in advance.")
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency_id',
        store=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        compute='_compute_company_id',
        store=True)
    amount_invoiced = fields.Monetary(
        string="Already invoiced",
        compute="_compute_invoice_amounts",
        help="Only confirmed down payments are considered.")
    amount_to_invoice = fields.Monetary(
        string="Amount to invoice",
        compute="_compute_invoice_amounts",
        help="The amount to invoice = Sale Order Total - Confirmed Down Payments.")

    # Only used when there is no down payment product available
    #  to setup the down payment product
    deposit_account_id = fields.Many2one(
        comodel_name='account.account',
        string="Income Account",
        domain=[('deprecated', '=', False)],
        check_company=True,
        help="Account used for deposits")
    deposit_taxes_id = fields.Many2many(
        comodel_name='account.tax',
        string="Customer Taxes",
        domain=[('type_tax_use', '=', 'sale')],
        check_company=True,
        help="Taxes used for deposits")

    # UI
    display_draft_invoice_warning = fields.Boolean(compute="_compute_display_draft_invoice_warning")
    display_invoice_amount_warning = fields.Boolean(compute="_compute_display_invoice_amount_warning")
    consolidated_billing = fields.Boolean(
        string="Consolidated Billing", default=True,
        help="Create one invoice for all orders related to same customer and same invoicing address"
    )

    #=== COMPUTE METHODS ===#

    @api.depends('sale_blanket_order_ids')
    def _compute_count(self):
        for wizard in self:
            wizard.count = len(wizard.sale_blanket_order_ids)

    @api.depends('sale_blanket_order_ids')
    def _compute_has_down_payments(self):
        for wizard in self:
            wizard.has_down_payments = bool(
                wizard.sale_blanket_order_ids.line_ids.filtered('is_downpayment')
            )

    # next computed fields are only used for down payments invoices and therefore should only
    # have a value when 1 unique SO is invoiced through the wizard
    @api.depends('sale_blanket_order_ids')
    def _compute_currency_id(self):
        self.currency_id = False
        for wizard in self:
            if wizard.count == 1:
                wizard.currency_id = wizard.sale_blanket_order_ids.currency_id

    @api.depends('sale_blanket_order_ids')
    def _compute_company_id(self):
        self.company_id = False
        for wizard in self:
            if wizard.count == 1:
                wizard.company_id = wizard.sale_blanket_order_ids.company_id

    @api.depends('company_id')
    def _compute_product_id(self):
        self.product_id = False
        for wizard in self:
            if wizard.count == 1:
                wizard.product_id = wizard.company_id.sale_down_payment_product_id

    @api.depends('amount', 'fixed_amount', 'advance_payment_method', 'amount_to_invoice')
    def _compute_display_invoice_amount_warning(self):
        for wizard in self:
            invoice_amount = wizard.fixed_amount
            if wizard.advance_payment_method == 'percentage':
                invoice_amount = wizard.amount / 100 * sum(wizard.sale_blanket_order_ids.mapped('amount_total'))
            wizard.display_invoice_amount_warning = invoice_amount > wizard.amount_to_invoice

    @api.depends('sale_blanket_order_ids')
    def _compute_display_draft_invoice_warning(self):
        for wizard in self:
            wizard.display_draft_invoice_warning = wizard.sale_blanket_order_ids.invoice_ids.filtered(lambda invoice: invoice.state == 'draft')

    @api.depends('sale_blanket_order_ids')
    def _compute_invoice_amounts(self):
        for wizard in self:
            wizard.amount_invoiced = sum(wizard.sale_blanket_order_ids._origin.mapped('amount_invoiced'))
            wizard.amount_to_invoice = sum(wizard.sale_blanket_order_ids._origin.mapped('amount_to_invoice'))

    #=== ONCHANGE METHODS ===#

    @api.onchange('advance_payment_method')
    def _onchange_advance_payment_method(self):
        if self.advance_payment_method == 'percentage':
            amount = self.default_get(['amount']).get('amount')
            return {'value': {'amount': amount}}

    #=== CONSTRAINT METHODS ===#

    def _check_amount_is_positive(self):
        for wizard in self:
            if wizard.advance_payment_method == 'percentage' and wizard.amount <= 0.00:
                raise UserError(_('The value of the down payment amount must be positive.'))
            elif wizard.advance_payment_method == 'fixed' and wizard.fixed_amount <= 0.00:
                raise UserError(_('The value of the down payment amount must be positive.'))

    @api.constrains('product_id')
    def _check_down_payment_product_is_valid(self):
        for wizard in self:
            if wizard.count > 1 or not wizard.product_id:
                continue
            if wizard.product_id.invoice_policy != 'order':
                raise UserError(_(
                    "The product used to invoice a down payment should have an invoice policy"
                    "set to \"Ordered quantities\"."
                    " Please update your deposit product to be able to create a deposit invoice."))
            if wizard.product_id.type != 'service':
                raise UserError(_(
                    "The product used to invoice a down payment should be of type 'Service'."
                    " Please use another product or update this product."))

    #=== ACTION METHODS ===#

    def create_invoices(self):
        self._check_amount_is_positive()
        sale_blanket_order_ids = self.env['sale.blanket.order'].browse(self._context.get('active_ids'))
        for order in sale_blanket_order_ids:
            if self.advance_payment_method == 'fixed':
                order.down_payment += self.fixed_amount
            elif self.advance_payment_method == 'percentage':
                order.down_payment += (self.amount / 100.0) * order.amount_total
        invoices = self._create_invoices(self.sale_blanket_order_ids)
        return self.sale_blanket_order_ids.action_view_invoice(invoices=invoices)

#create jurnal dp di blanket
    def view_draft_invoices(self):
        return {
            'name': _('Draft Invoices'),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'views': [(False, 'list'), (False, 'form')],
            'res_model': 'account.move',
            'domain': [('line_ids.sale_line_ids.order_id', 'in', self.sale_blanket_order_ids.ids), ('state', '=', 'draft')],
        }

    # === BUSINESS METHODS ===#

    def _create_invoices(self, sale_orders):
        self.ensure_one()

        self.sale_blanket_order_ids.ensure_one()
        self = self.with_company(self.company_id)
        order = self.sale_blanket_order_ids

        # Create deposit product if necessary
        if not self.product_id:
            self.company_id.sudo().sale_down_payment_product_id = self.env['product.product'].create(
                self._prepare_down_payment_product_values()
            )
            self._compute_product_id()

        #dikomen awal mel
        # Create down payment section if necessary
        # SaleOrderline = self.env['sale.blanket.order.line'].with_context(sale_no_log_for_new_lines=True)
        # if not any(line.display_type and line.is_downpayment for line in order.line_ids):
        #     SaleOrderline.create(
        #         self._prepare_down_payment_section_values(order)
        #     )
        #
        # down_payment_lines = SaleOrderline.create(
        #     self._prepare_down_payment_lines_values(order)
        # )

        invoice = self.env['account.move'].sudo().create(
            self._prepare_invoice_values(order)
        )

        # Ensure the invoice total is exactly the expected fixed amount.
        if self.advance_payment_method == 'fixed':
            delta_amount = (invoice.amount_total - self.fixed_amount) * (1 if invoice.is_inbound() else -1)
            if not order.currency_id.is_zero(delta_amount):
                receivable_line = invoice.line_ids\
                    .filtered(lambda aml: aml.account_id.account_type == 'asset_receivable')[:1]
                product_lines = invoice.line_ids\
                    .filtered(lambda aml: aml.display_type == 'product')
                tax_lines = invoice.line_ids\
                    .filtered(lambda aml: aml.tax_line_id.amount_type not in (False, 'fixed'))

                if product_lines and tax_lines and receivable_line:
                    line_commands = [Command.update(receivable_line.id, {
                        'amount_currency': receivable_line.amount_currency + delta_amount,
                    })]
                    delta_sign = 1 if delta_amount > 0 else -1
                    for lines, attr, sign in (
                        (product_lines, 'price_total', -1),
                        (tax_lines, 'amount_currency', 1),
                    ):
                        remaining = delta_amount
                        lines_len = len(lines)
                        for line in lines:
                            if order.currency_id.compare_amounts(remaining, 0) != delta_sign:
                                break
                            amt = delta_sign * max(
                                order.currency_id.rounding,
                                abs(order.currency_id.round(remaining / lines_len)),
                            )
                            remaining -= amt
                            line_commands.append(Command.update(line.id, {attr: line[attr] + amt * sign}))
                    invoice.line_ids = line_commands

        # Unsudo the invoice after creation if not already sudoed
        invoice = invoice.sudo(self.env.su)

        poster = self.env.user._is_internal() and self.env.user.id or SUPERUSER_ID
        invoice.with_user(poster).message_post_with_source(
            'mail.message_origin_link',
            render_values={'self': invoice, 'origin': order},
            subtype_xmlid='mail.mt_note',
        )

        title = _("Down payment invoice")
        order.with_user(poster).message_post(
            body=_("%s has been created", invoice._get_html_link(title=title)),
        )

        return invoice

    def _prepare_down_payment_product_values(self):
        self.ensure_one()
        return {
            'name': _('Down payment'),
            'type': 'service',
            'invoice_policy': 'order',
            'company_id': self.company_id.id,
            'property_account_income_id': self.deposit_account_id.id,
            'taxes_id': [Command.set(self.deposit_taxes_id.ids)],
        }

    def _prepare_down_payment_section_values(self, order):
        context = {'lang': order.partner_id.lang}

        so_values = {
            'name': _('Down Payments'),
            'product_uom_qty': 0.0,
            'order_id': order.id,
            'display_type': 'line_section',
            'is_downpayment': True,
            'sequence': order.line_ids and order.line_ids[-1].sequence + 1 or 10,
        }

        del context
        return so_values


    #dikomen awal mel
    # def _prepare_down_payment_lines_values(self, order):
    #     """ Create one down payment line per tax or unique taxes combination.
    #         Apply the tax(es) to their respective lines.
    #
    #         :param order: Order for which the down payment lines are created.
    #         :return:      An array of dicts with the down payment lines values.
    #     """
    #     self.ensure_one()
    #
    #     # Calculate percentage for down payment
    #     if self.advance_payment_method == 'percentage':
    #         percentage = self.amount / 100
    #     else:
    #         percentage = self.fixed_amount / order.amount_total if order.amount_total else 1
    #
    #     order_lines = order.line_ids.filtered(lambda l: not l.display_type and not l.is_downpayment)
    #     base_downpayment_lines_values = self._prepare_base_downpayment_line_values(order)
    #
    #     # Ensure discount key is set in the base line for each order line
    #     tax_base_line_dicts = [
    #         {
    #             'record': line.id,  # Ensure you add this key
    #             **line._convert_to_tax_base_line_dict(
    #                 analytic_distribution=line.analytic_distribution,
    #                 handle_price_include=False
    #             )
    #         }
    #         for line in order_lines
    #     ]
    #     for line in tax_base_line_dicts:
    #         # Ensure key exists, default to 0 if missing
    #         line['discount'] = line.get('discount', 0.0)
    #         line['currency'] = line.get('currency', order.currency_id)
    #         line['rate'] = line.get('rate', 1.0)
    #         quantity = line.get('quantity', 1)  # Default to 1 if missing
    #
    #         # Instead of isinstance with uom.uom, ensure quantity is a numeric type
    #         if isinstance(quantity, (float, int)):
    #             line['quantity'] = float(quantity)  # Convert to float if it’s a float or int
    #         else:
    #             # You may want to log or raise an error if quantity is not a number
    #             line['quantity'] = 1.0
    #
    #     # Compute taxes
    #     computed_taxes = self.env['account.tax']._compute_taxes(tax_base_line_dicts)
    #     down_payment_values = []
    #     for line, tax_repartition in computed_taxes['base_lines_to_update']:
    #         taxes = line['taxes'].flatten_taxes_hierarchy()
    #         fixed_taxes = taxes.filtered(lambda tax: tax.amount_type == 'fixed')
    #         down_payment_values.append([
    #             taxes - fixed_taxes,
    #             line['analytic_distribution'],
    #             tax_repartition['price_subtotal']
    #         ])
    #         for fixed_tax in fixed_taxes:
    #             if fixed_tax.price_include:
    #                 continue
    #             pct_tax = self.env['account.tax'] if not fixed_tax.include_base_amount else taxes[list(taxes).index(
    #                 fixed_tax) + 1:].filtered(lambda t: t.is_base_affected and t.amount_type != 'fixed')
    #             down_payment_values.append([
    #                 pct_tax,
    #                 line['analytic_distribution'],
    #                 line['quantity'] * fixed_tax.amount
    #             ])
    #
    #     # Remaining logic for handling down payment lines...
    #
    #     downpayment_line_map = {}
    #     analytic_map = {}
    #     for taxes_id, analytic_distribution, price_subtotal in down_payment_values:
    #         grouping_key = frozendict({'taxes_id': tuple(sorted(taxes_id.ids))})
    #         downpayment_line_map.setdefault(grouping_key, {
    #             **base_downpayment_lines_values,
    #             **grouping_key,
    #             'product_uom_qty': 0.0,
    #             'price_unit': 0.0,
    #         })
    #         downpayment_line_map[grouping_key]['price_unit'] += price_subtotal
    #         if analytic_distribution:
    #             analytic_map.setdefault(grouping_key, [])
    #             analytic_map[grouping_key].append((price_subtotal, analytic_distribution))
    #
    #     lines_values = []
    #     for key, line_vals in downpayment_line_map.items():
    #         # don't add line if price is 0 and prevent division by zero
    #         if order.currency_id.is_zero(line_vals['price_unit']):
    #             continue
    #         # weight analytic account distribution
    #         if analytic_map.get(key):
    #             line_analytic_distribution = {}
    #             for price_subtotal, account_distribution in analytic_map[key]:
    #                 for account, distribution in account_distribution.items():
    #                     line_analytic_distribution.setdefault(account, 0.0)
    #                     line_analytic_distribution[account] += price_subtotal / line_vals['price_unit'] * distribution
    #             line_vals['analytic_distribution'] = line_analytic_distribution
    #         # round price unit
    #         line_vals['price_unit'] = order.currency_id.round(line_vals['price_unit'] * percentage)
    #         lines_values.append(line_vals)
    #
    #     return lines_values

    # def _prepare_base_downpayment_line_values(self, order):
    #     self.ensure_one()
    #     context = {'lang': order.partner_id.lang}
    #     so_values = {
    #         'name': _(
    #             'Down Payment: %(date)s (Draft)', date=format_date(self.env, fields.Date.today())
    #         ),
    #         'product_uom_qty': 0.0,
    #         'order_id': order.id,
    #         'discount': 0.0,
    #         'product_id': self.product_id.id,
    #         'is_downpayment': True,
    #         'sequence': order.line_ids and order.line_ids[-1].sequence + 1 or 10,
    #     }
    #     del context
    #     return so_values

    def _prepare_invoice_values(self, order):
        
        global price_unit
        self.ensure_one()
        # Prepare the base invoice values
        invoice_values = order._prepare_invoice()

        # Create invoice line values
        invoice_line_ids = []

        # for order_line in order.order_line:
        #     ol = {
        #         'product_id': order_line.product_id.id,
        #         'price_unit': order_line.price_unit,
        #         'quantity': order_line.product_uom_qty,
        #         # 'discount': line.discount,
        #         # 'tax_ids': [(6, 0, line.taxes_id.ids)],
        #         # 'analytic_distribution': line.analytic_distribution,
        #         'account_id': line.account_id.id,
        #         # 'analytic_account_id': order.analytic_account_id.id if order.analytic_account_id else False,
        #         'product_uom_id': line.product_uom.id,
        #         # 'name': self._get_down_payment_description(order) or line.product_id.name,
        #     }

        #     # Append the prepared line values to the invoice line list
        #     invoice_line_ids.append(Command.create(ol))


        for line in order:
            if self.advance_payment_method == 'fixed':
                price_unit = self.fixed_amount
            elif self.advance_payment_method == 'percentage':
                price_unit = (self.amount / 100.0) * order.amount_total
            # Manually prepare the line values
            line_values = {
                'product_id': line.company_id.sale_down_payment_product_id.id,
                'price_unit': price_unit,
                'quantity': 1.0,
                # 'discount': line.discount,
                # 'tax_ids': [(6, 0, line.taxes_id.ids)],
                # 'analytic_distribution': line.analytic_distribution,
                'account_id': line.company_id.sale_down_payment_product_id.property_account_income_id.id,
                # 'analytic_account_id': order.analytic_account_id.id if order.analytic_account_id else False,
                'product_uom_id': line.company_id.sale_down_payment_product_id.uom_id.id,
                # 'name': self._get_down_payment_description(order) or line.product_id.name,
            }

            # Append the prepared line values to the invoice line list
            invoice_line_ids.append(Command.create(line_values))

        # Update the invoice values with the line IDs
        invoice_values['invoice_line_ids'] = invoice_line_ids
        return invoice_values

    def _get_down_payment_description(self, order):
        self.ensure_one()
        context = {'lang': order.partner_id.lang}
        if self.advance_payment_method == 'percentage':
            name = _("Down payment of %s%%", self.amount)
        else:
            name = _('Down Payment')
        del context
        return name

class InheritSaleAdvance(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    dp_blanket = fields.Float('Down Payment')
    dp_order = fields.Float(string="Order Down Payment")
    dp_sisa = fields.Float(string="Remaining Down Payment")

    def _check_amount_is_positive(self):
        for wizard in self:
            if wizard.dp_order <= 0.00:
                raise UserError(_('The value of the down payment amount must be positive.'))

    def create_invoices(self):
        self._check_amount_is_positive()

        invoices = self._create_invoices(self.sale_order_ids)

        for rec in self:
            if self.dp_blanket != False and self.dp_order > self.dp_sisa:
                raise UserError("Order Down Payment Exceeding Remaining Down Payment")
            # for line in rec.sale_order_ids.order_line:
            #     if line.qty_delivered != 0:
            #         if rec.dp_order > line.price_unit:
            #             raise UserError("Order Down Payment Exceeding Unit Price")

            rec.sale_order_ids.write({
                # LAST
                # 'dp_order': rec.dp_order,
                'dp_order': rec.sale_order_ids.dp_order + rec.dp_order,
                'dp_sisa': rec.dp_blanket - rec.dp_order,
                # 'amount_total': rec.sale_order_ids.amount_total - rec.dp_order,
            })
            for order in rec.sale_order_ids:
                order.amount_total = order.amount_total - rec.dp_order

            print('order', rec.dp_order)
            print('sisa', rec.dp_blanket - rec.dp_order)
            print('total', rec.sale_order_ids.amount_total - rec.dp_order)

        return self.sale_order_ids.action_view_invoice(invoices=invoices)
    
    def _prepare_invoice_values(self, order, so_lines):
        self.ensure_one()
        lines = []
        # lines = [Command.create(
        #         line._prepare_invoice_line(
        #             name=self._get_down_payment_description(order),
        #             quantity=1.0,
        #         )
        #     ) for line in so_lines]
        # not l.display_type and not l.is_downpayment
        for line in so_lines:
            if not line.display_type and not line.is_downpayment:
                qty_invoice = line.qty_delivered if line.qty_invoiced == 0 else line.qty_delivered - line.qty_invoiced
                lines.append(Command.create(
                    line._prepare_invoice_line(
                        name=line.product_id.name,
                        quantity = qty_invoice,
                        # quantity=line.product_uom_qty,
                    )
                ))
            else: 
                lines.append(Command.create(
                    line._prepare_invoice_line(
                        name=self._get_down_payment_description(order),
                        quantity=1.0,
                        price_unit= line.price_unit
                    )
                ))

        return {
            **order._prepare_invoice(),
            
            'invoice_line_ids': lines
        }
    # def _prepare_down_payment_section_values(self, order):
    #     context = {'lang': order.partner_id.lang}

    #     so_values = {
    #         'name': _('Down Payments'),
    #         'product_uom_qty': 0.0,
    #         'order_id': order.id,
    #         'display_type': 'line_section',
    #         'is_downpayment': True,
    #         'sequence': order.order_line and order.order_line[-1].sequence + 1 or 10,
    #         'price_unit': -(self.dp_order),
    #     }

    #     del context
    #     return so_values

    def _create_invoices(self, sale_orders):
        self.ensure_one()
        self.sale_order_ids.ensure_one()
        self = self.with_company(self.company_id)
        order = self.sale_order_ids
        # order = sale_orders

        if not self.product_id:
            self.company_id.sudo().sale_down_payment_product_id = self.env['product.product'].create(
                self._prepare_down_payment_product_values()
            )
        self._compute_product_id()

        SaleOrderLine = self.env['sale.order.line'].with_context(sale_no_log_for_new_lines=True)
        if not any(line.display_type and line.is_downpayment for line in order.order_line):
            SaleOrderLine.create(
                self._prepare_down_payment_section_values(order)
            )
        
        line_ex_dp = order.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)

        down_payment_lines = SaleOrderLine.create(
            self._prepare_down_payment_lines_values(order)
        )
        
        down_payment_lines |=  line_ex_dp

        invoice = self.env['account.move'].sudo().create(
            self._prepare_invoice_values(order, down_payment_lines)
        )



        delta_amount = (invoice.amount_total - self.dp_order)
        if not order.currency_id.is_zero(delta_amount):
            receivable_line = invoice.line_ids.filtered(lambda aml: aml.account_id.account_type == 'asset_receivable')[
                              :1]
            product_lines = invoice.line_ids.filtered(lambda aml: aml.display_type == 'product')
            tax_lines = invoice.line_ids.filtered(lambda aml: aml.tax_line_id.amount_type not in (False, 'fixed'))

            if product_lines and tax_lines and receivable_line:
                line_commands = [Command.update(receivable_line.id, {
                    'amount_currency': receivable_line.amount_currency + delta_amount,
                })]
                delta_sign = 1 if delta_amount > 0 else -1

                for lines, attr, sign in (
                        (product_lines, 'price_total', -1),
                        (tax_lines, 'amount_currency', 1),
                ):
                    remaining = delta_amount
                    lines_len = len(lines)

                    for line in lines:
                        if order.currency_id.compare_amounts(remaining, 0) != delta_sign:
                            break

                        amt = delta_sign * max(
                            order.currency_id.rounding,
                            abs(order.currency_id.round(remaining / lines_len)),
                        )
                        remaining -= amt
                        line_commands.append(Command.update(line.id, {attr: line[attr] + amt * sign}))

                invoice.line_ids = line_commands

        invoice = invoice.sudo(self.env.su)
        poster = self.env.user._is_internal() and self.env.user.id or SUPERUSER_ID
        invoice.with_user(poster).message_post_with_source(
            'mail.message_origin_link',
            render_values={'self': invoice, 'origin': order},
            subtype_xmlid='mail.mt_note',
        )
        title = _("Down payment invoice")
        order.with_user(poster).message_post(
            body=_("%s has been created", invoice._get_html_link(title=title)),
        )
        return invoice

    def _prepare_down_payment_lines_values(self, order):
        """ Create down payment line with price_unit based on dp_order input.

            :param order: Order for which the down payment lines are created.
            :return:      An array of dicts with the down payment lines values.
        """
        self.ensure_one()

        price_unit = self.dp_order

        order_lines = order.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)
        base_downpayment_lines_values = self._prepare_base_downpayment_line_values(order)

        tax_base_line_dicts = [
            line._convert_to_tax_base_line_dict(
                analytic_distribution=line.analytic_distribution,
                handle_price_include=False
            )
            for line in order_lines
        ]
        computed_taxes = self.env['account.tax']._compute_taxes(
            tax_base_line_dicts)
        down_payment_values = []

        for line, tax_repartition in computed_taxes['base_lines_to_update']:
            taxes = line['taxes'].flatten_taxes_hierarchy()
            fixed_taxes = taxes.filtered(lambda tax: tax.amount_type == 'fixed')
            down_payment_values.append([
                taxes - fixed_taxes,
                line['analytic_distribution'],
                tax_repartition['price_subtotal']
            ])

            for fixed_tax in fixed_taxes:
                if fixed_tax.price_include:
                    continue
                if fixed_tax.include_base_amount:
                    pct_tax = taxes[list(taxes).index(fixed_tax) + 1:] \
                        .filtered(lambda t: t.is_base_affected and t.amount_type != 'fixed')
                else:
                    pct_tax = self.env['account.tax']
                down_payment_values.append([
                    pct_tax,
                    line['analytic_distribution'],
                    line['quantity'] * fixed_tax.amount
                ])

        downpayment_line_map = {}
        analytic_map = {}
        for tax_id, analytic_distribution, price_subtotal in down_payment_values:
            grouping_key = frozendict({'tax_id': tuple(sorted(tax_id.ids))})
            downpayment_line_map.setdefault(grouping_key, {
                **base_downpayment_lines_values,
                **grouping_key,
                'product_uom_qty': 0.0,
                'price_unit': 0.0,
            })
            downpayment_line_map[grouping_key]['price_unit'] += price_unit
            if analytic_distribution:
                analytic_map.setdefault(grouping_key, [])
                analytic_map[grouping_key].append((price_subtotal, analytic_distribution))

        lines_values = []
        for key, line_vals in downpayment_line_map.items():
            if order.currency_id.is_zero(line_vals['price_unit']):
                continue
            if analytic_map.get(key):
                line_analytic_distribution = {}
                for price_subtotal, account_distribution in analytic_map[key]:
                    for account, distribution in account_distribution.items():
                        line_analytic_distribution.setdefault(account, 0.0)
                        line_analytic_distribution[account] += price_subtotal / line_vals['price_unit'] * distribution
                line_vals['analytic_distribution'] = line_analytic_distribution
            # line_vals['price_unit'] = order.currency_id.round(price_unit)
            line_vals['price_unit'] = -(order.currency_id.round(price_unit))
            line_vals['product_uom_qty'] = 1
            lines_values.append(line_vals)

        return lines_values
