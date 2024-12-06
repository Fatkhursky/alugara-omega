# Copyright 2018 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_compare
from odoo.tools.misc import format_date


class BlanketOrder(models.Model):
    _name = "sale.blanket.order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Blanket Order"
    _check_company_auto = True

    @api.model
    def _default_note(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("account.use_invoice_terms")
            and self.env.company.invoice_terms
            or ""
        )

    @api.depends("line_ids.price_total")
    def _compute_amount_all(self):
        for order in self.filtered("currency_id"):
            amount_untaxed = amount_tax = 0.0
            for line in order.line_ids:
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax
            order.update(
                {
                    "amount_untaxed": order.currency_id.round(amount_untaxed),
                    "amount_tax": order.currency_id.round(amount_tax),
                    "amount_total": amount_untaxed + amount_tax,
                }
            )

    name = fields.Char(default="Draft", readonly=True, copy=False)
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner",
    )
    line_ids = fields.One2many(
        "sale.blanket.order.line", "order_id", string="Order lines", copy=True
    )
    line_count = fields.Integer(
        string="Sale Blanket Order Line count",
        compute="_compute_line_count",
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        related="line_ids.product_id",
        string="Product",
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Pricelist",
        required=True,
    )
    currency_id = fields.Many2one("res.currency", related="pricelist_id.currency_id")
    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Analytic Account",
        copy=False,
        check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Payment Terms",
    )
    confirmed = fields.Boolean(copy=False)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("open", "Open"),
            ("done", "Done"),
            ("expired", "Expired"),
        ],
        compute="_compute_state",
        store=True,
        copy=False,
    )
    validity_date = fields.Date()
    client_order_ref = fields.Char(
        string="Customer Reference",
        copy=False,
    )
    note = fields.Text(default=_default_note)
    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
    )
    team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        change_default=True,
        default=lambda self: self.env["crm.team"]._get_default_team_id(),
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    sale_count = fields.Integer(compute="_compute_sale_count")

    fiscal_position_id = fields.Many2one(
        "account.fiscal.position", string="Fiscal Position"
    )

    amount_untaxed = fields.Monetary(
        string="Untaxed Amount",
        store=True,
        readonly=True,
        compute="_compute_amount_all",
        tracking=True,
    )
    amount_tax = fields.Monetary(
        string="Taxes", store=True, readonly=True, compute="_compute_amount_all"
    )
    amount_total = fields.Monetary(
        string="Total", store=True, readonly=True, compute="_compute_amount_all"
    )

    # Fields use to filter in tree view
    original_uom_qty = fields.Float(
        string="Original quantity",
        compute="_compute_uom_qty",
        search="_search_original_uom_qty",
        default=0.0,
    )
    ordered_uom_qty = fields.Float(
        string="Ordered quantity",
        compute="_compute_uom_qty",
        search="_search_ordered_uom_qty",
        default=0.0,
    )
    invoiced_uom_qty = fields.Float(
        string="Invoiced quantity",
        compute="_compute_uom_qty",
        search="_search_invoiced_uom_qty",
        default=0.0,
    )
    remaining_uom_qty = fields.Float(
        string="Remaining quantity",
        compute="_compute_uom_qty",
        search="_search_remaining_uom_qty",
        default=0.0,
    )
    delivered_uom_qty = fields.Float(
        string="Delivered quantity",
        compute="_compute_uom_qty",
        search="_search_delivered_uom_qty",
        default=0.0,
    )
    down_payment = fields.Float(string='Down Payment', readonly=True, copy=True, force_save=True)
    dp_order = fields.Float(
        string="Order Down Payment", readonly=True,
        # compute="_compute_dp_order"
    )
    dp_sisa = fields.Float(
        string="Remaining Down Payment", readonly=True,
        compute="_compute_dp_sisa"
    )

    @api.depends('down_payment', 'dp_order')
    def _compute_dp_sisa(self):
        for order in self:
            order.dp_sisa = order.down_payment - order.dp_order

    # wizard_sale_blanket = fields.One2many(
    #     "sale.blanket.order.wizard",
    #     string="Blanket Order Wizard"
    # )
    invoice_count = fields.Integer(string='Invoice Count', compute='_get_invoiced', store=True)
    invoice_ids = fields.Many2many(comodel_name='account.move', string='Invoices', compute="_get_invoiced", search='_search_invoice_ids', copy=False, store=True)
    amount_to_invoice = fields.Monetary(string="Amount to invoice", store=True, compute='_compute_amount_invoiced')
    amount_invoiced = fields.Monetary(string="Already invoiced", compute='_compute_amount_invoiced')

    @api.depends('invoice_ids')
    def _compute_amount_invoiced(self):
        for wizard in self:
            wizard.amount_invoiced = sum(wizard.invoice_ids._origin.mapped('amount_invoiced'))
            wizard.amount_to_invoice = sum(wizard.invoice_ids._origin.mapped('amount_to_invoice'))

    # @api.depends('order_line.dp_blanket_line', 'order_line.dp_order_line')
    # def _compute_dp_order(self):
    #     for order in self:
    #         dp_order_value = 0.0
    #
    #         for line in order.order_line:
    #             if line.price_unit < 0:
    #                 dp_order_value += line.price_unit
    #
    #         order.dp_order = dp_order_value

    def action_view_invoice(self, invoices=False):
        if not invoices:
            invoices = self.mapped('invoice_ids')
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        if len(invoices) > 1:
            action['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            form_view = [(self.env.ref('account.view_move_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = invoices.id
        else:
            action = {'type': 'ir.actions.act_window_close'}

        context = {
            'default_move_type': 'out_invoice',
        }
        if len(self) == 1:
            context.update({
                'default_partner_id': self.partner_id.id,
                # 'default_partner_shipping_id': self.partner_shipping_id.id,
                'default_invoice_payment_term_id': self.payment_term_id.id or self.partner_id.property_payment_term_id.id or self.env['account.move'].default_get(['invoice_payment_term_id']).get('invoice_payment_term_id'),
                'default_invoice_origin': self.name,
            })
        action['context'] = context
        return action

    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a blanket order.
        """
        self.ensure_one()
        partner = self.partner_id
        invoice_vals = {
            'ref': self.client_order_ref or '',
            'move_type': 'out_invoice',
            'narration': self.note,
            'currency_id': self.currency_id.id,
            'invoice_user_id': self.user_id and self.user_id.id,
            'partner_id': partner.id,
            # 'partner_shipping_id': self.partner_shipping_id.id,
            # 'fiscal_position_id': (self.fiscal_position_id or self.env['account.fiscal.position'].with_company(self.company_id)._get_fiscal_position(partner.id)).id,
            'team_id': self.team_id.id,
            # 'campaign_id': self.campaign_id.id,
            # 'medium_id': self.medium_id.id,
            # 'source_id': self.source_id.id,
            'invoice_origin': self.name,
            'invoice_payment_term_id': self.payment_term_id.id,
            'invoice_line_ids': [],
            'company_id': self.company_id.id,
            'sale_blanket_order_ids': [(6, 0, [self.id])],
            'user_id': self.env.user.id,
        }
        return invoice_vals

    # @api.depends('invoice_ids.state', 'currency_id', 'amount_total')
    # def _compute_amount_to_invoice(self):
    #     for order in self:
    #         # If the invoice status is 'Fully Invoiced' force the amount to invoice to equal zero and return early.
    #         if order.state == 'invoiced':
    #             order.amount_to_invoice = 0.0
    #             continue
    #
    #         invoices = order.invoice_ids.filtered(lambda x: x.state == 'posted')
    #         order.amount_to_invoice = order.amount_total - invoices._get_sale_order_invoiced_amount(order)


    @api.depends('amount_total', 'amount_to_invoice')
    def _compute_amount_invoiced(self):
        for order in self:
            order.amount_invoiced = order.amount_total - order.amount_to_invoice

    # @api.depends('invoice_ids')
    # def _compute_invoice_count(self):
    #     for order in self:
    #         order.invoice_count = len(order.invoice_ids)

    # @api.depends('line_ids.invoice_lines')
    # def _get_invoiced(self):
    #     for order in self:
    #         invoices = order.line_ids.mapped('invoice_lines.move_id').filtered(
    #             lambda move: move.move_type in ('out_invoice', 'out_refund')
    #         )
    #         order.invoice_ids = invoices

    @api.depends('line_ids.invoice_lines')
    def _get_invoiced(self):
        for order in self:
            invoices = order.line_ids.mapped('invoice_lines.move_id').filtered(
                lambda r: r.move_type in ('out_invoice', 'out_refund')
            )
            order.invoice_ids = invoices
            order.invoice_count = len(invoices)

    def _search_invoice_ids(self, operator, value):
        if operator == 'in' and value:
            self.env.cr.execute("""
                    SELECT array_agg(so.id)
                    FROM sale_blanket_order so
                    JOIN sale_blanket_order_line sol ON sol.order_id = so.id
                    JOIN sale_order_line_invoice_rel soli_rel ON soli_rel.order_line_id = sol.id
                    JOIN account_move_line aml ON aml.id = soli_rel.invoice_line_id
                    JOIN account_move am ON am.id = aml.move_id
                    WHERE
                        am.move_type in ('out_invoice', 'out_refund') AND
                        am.id = ANY(%s)
                """, (list(value),))
            so_ids = self.env.cr.fetchone()[0] or []
            return [('id', 'in', so_ids)]
        elif operator == '=' and not value:
            # Handle case for [('invoice_ids', '=', False)]
            order_ids = self._search([
                ('line_ids.invoice_lines.move_id.move_type', 'in', ('out_invoice', 'out_refund'))
            ])
            return [('id', 'not in', order_ids)]
        return [
            ('line_ids.invoice_lines.move_id.move_type', 'in', ('out_invoice', 'out_refund')),
            ('line_ids.invoice_lines.move_id', operator, value),
        ]

    def _get_sale_orders(self):
        return self.mapped("line_ids.sale_lines.order_id")

    @api.depends("line_ids")
    def _compute_line_count(self):
        self.line_count = len(self.mapped("line_ids"))

    def _compute_sale_count(self):
        for blanket_order in self:
            blanket_order.sale_count = len(blanket_order._get_sale_orders())

    @api.depends(
        "line_ids.remaining_uom_qty",
        "validity_date",
        "confirmed",
    )
    def _compute_state(self):
        today = fields.Date.today()
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for order in self:
            if not order.confirmed:
                order.state = "draft"
            elif order.validity_date <= today:
                order.state = "expired"
            elif float_is_zero(
                sum(
                    order.line_ids.filtered(lambda line: not line.display_type).mapped(
                        "remaining_uom_qty"
                    )
                ),
                precision_digits=precision,
            ):
                order.state = "done"
            else:
                order.state = "open"

    def _compute_uom_qty(self):
        for bo in self:
            bo.original_uom_qty = sum(bo.mapped("line_ids.original_uom_qty"))
            bo.ordered_uom_qty = sum(bo.mapped("line_ids.ordered_uom_qty"))
            bo.invoiced_uom_qty = sum(bo.mapped("line_ids.invoiced_uom_qty"))
            bo.delivered_uom_qty = sum(bo.mapped("line_ids.delivered_uom_qty"))
            bo.remaining_uom_qty = sum(bo.mapped("line_ids.remaining_uom_qty"))

    @api.onchange("partner_id")
    def onchange_partner_id(self):
        """
        Update the following fields when the partner is changed:
        - Pricelist
        - Payment term
        - Fiscal position
        """
        if not self.partner_id:
            self.payment_term_id = False
            self.fiscal_position_id = False
            return

        values = {
            "pricelist_id": (
                self.partner_id.property_product_pricelist
                and self.partner_id.property_product_pricelist.id
                or False
            ),
            "payment_term_id": (
                self.partner_id.property_payment_term_id
                and self.partner_id.property_payment_term_id.id
                or False
            ),
            "fiscal_position_id": self.env["account.fiscal.position"]
            .with_context(company_id=self.company_id.id)
            ._get_fiscal_position(self.partner_id),
        }

        if self.partner_id.user_id:
            values["user_id"] = self.partner_id.user_id.id
        if self.partner_id.team_id:
            values["team_id"] = self.partner_id.team_id.id
        self.update(values)

    def unlink(self):
        for order in self:
            if order.state not in ("draft", "expired") or order._check_active_orders():
                raise UserError(
                    _(
                        "You can not delete an open blanket or "
                        "with active sale orders! "
                        "Try to cancel it before."
                    )
                )
        return super().unlink()

    def _validate(self):
        try:
            today = fields.Date.today()
            for order in self:
                assert order.validity_date, _("Validity date is mandatory")
                assert order.validity_date > today, _(
                    "Validity date must be in the future"
                )
                assert order.partner_id, _("Partner is mandatory")
                assert len(order.line_ids) > 0, _("Must have some lines")
                order.line_ids._validate()
        except AssertionError as e:
            raise UserError(e) from e

    def set_to_draft(self):
        for order in self:
            order.write({"state": "draft", "confirmed": False})
        return True

    def action_confirm(self):
        self._validate()
        for order in self:
            sequence_obj = self.env["ir.sequence"]
            if order.company_id:
                sequence_obj = sequence_obj.with_company(order.company_id.id)
            name = sequence_obj.next_by_code("sale.blanket.order")
            order.write({"confirmed": True, "name": name})
        return True

    def _check_active_orders(self):
        for order in self.filtered("sale_count"):
            for so in order._get_sale_orders():
                if so.state not in ("cancel"):
                    return True
        return False

    def action_cancel(self):
        for order in self:
            if order._check_active_orders():
                raise UserError(
                    _(
                        "You can not delete a blanket order with opened "
                        "sale orders! "
                        "Try to cancel them before."
                    )
                )
            order.write({"state": "expired"})
        return True

    def action_view_sale_orders(self):
        sale_orders = self._get_sale_orders()
        action = self.env["ir.actions.act_window"]._for_xml_id("sale.action_orders")
        if len(sale_orders) > 0:
            action["domain"] = [("id", "in", sale_orders.ids)]
            action["context"] = [("id", "in", sale_orders.ids)]
        else:
            action = {"type": "ir.actions.act_window_close"}
        return action

    def action_view_sale_blanket_order_line(self):
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sale_blanket_order.act_open_sale_blanket_order_lines_view_tree"
        )
        lines = self.mapped("line_ids")
        if len(lines) > 0:
            action["domain"] = [("id", "in", lines.ids)]
        return action

    # def action_view_invoices(self, invoices=False):
    #     if not invoices:
    #         invoices = self.mapped('invoice_ids')
    #     action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
    #     # print(action)
    #     if len(invoices) > 1:
    #         action['domain'] = [('id', 'in', invoices.ids)]
    #     elif len(invoices) == 1:
    #         form_view = [(self.env.ref('account.view_move_form').id, 'form')]
    #         if 'views' in action:
    #             action['views'] = form_view + [(state, view) for state, view in action['views'] if view != 'form']
    #         else:
    #             action['views'] = form_view
    #         action['res_id'] = invoices.id
    #     else:
    #         action = {'type': 'ir.actions.act_window_close'}
    #
    #     context = {
    #         'default_move_type': 'out_invoice',
    #     }
    #     if len(self) == 1:
    #         context.update({
    #             'default_partner_id': self.partner_id.id,
    #             # 'default_partner_shipping_id': self.partner_shipping_id.id,
    #             'default_invoice_payment_term_id': self.payment_term_id.id or self.partner_id.property_payment_term_id.id or
    #                                                self.env['account.move'].default_get(
    #                                                    ['invoice_payment_term_id']).get('invoice_payment_term_id'),
    #             'default_invoice_origin': self.name,
    #         })
    #     # print(context)
    #     action['context'] = context
    #     return action

    @api.model
    def expire_orders(self):
        today = fields.Date.today()
        expired_orders = self.search(
            [("state", "=", "open"), ("validity_date", "<=", today)]
        )
        expired_orders.modified(["validity_date"])
        expired_orders.flush_recordset()

    @api.model
    def _search_original_uom_qty(self, operator, value):
        bo_line_obj = self.env["sale.blanket.order.line"]
        res = []
        bo_lines = bo_line_obj.search([("original_uom_qty", operator, value)])
        order_ids = bo_lines.mapped("order_id")
        res.append(("id", "in", order_ids.ids))
        return res

    @api.model
    def _search_ordered_uom_qty(self, operator, value):
        bo_line_obj = self.env["sale.blanket.order.line"]
        res = []
        bo_lines = bo_line_obj.search([("ordered_uom_qty", operator, value)])
        order_ids = bo_lines.mapped("order_id")
        res.append(("id", "in", order_ids.ids))
        return res

    @api.model
    def _search_invoiced_uom_qty(self, operator, value):
        bo_line_obj = self.env["sale.blanket.order.line"]
        res = []
        bo_lines = bo_line_obj.search([("invoiced_uom_qty", operator, value)])
        order_ids = bo_lines.mapped("order_id")
        res.append(("id", "in", order_ids.ids))
        return res

    @api.model
    def _search_delivered_uom_qty(self, operator, value):
        bo_line_obj = self.env["sale.blanket.order.line"]
        res = []
        bo_lines = bo_line_obj.search([("delivered_uom_qty", operator, value)])
        order_ids = bo_lines.mapped("order_id")
        res.append(("id", "in", order_ids.ids))
        return res

    @api.model
    def _search_remaining_uom_qty(self, operator, value):
        bo_line_obj = self.env["sale.blanket.order.line"]
        res = []
        bo_lines = bo_line_obj.search([("remaining_uom_qty", operator, value)])
        order_ids = bo_lines.mapped("order_id")
        res.append(("id", "in", order_ids.ids))
        return res


class BlanketOrderLine(models.Model):
    _name = "sale.blanket.order.line"
    _description = "Blanket Order Line"
    _inherit = ["mail.thread", "mail.activity.mixin", "analytic.mixin"]
    _rec_names_search = ['name', 'order_id.name']
    _order = 'order_id, sequence, id'
    _check_company_auto = True

    _sql_constraints = [
        ('accountable_required_fields',
         "CHECK(display_type IS NOT NULL OR (product_id IS NOT NULL AND product_uom_qty IS NOT NULL))",
         "Missing required fields on accountable sale blanket order line."),
        ('non_accountable_null_fields',
         "CHECK(display_type IS NULL OR (product_id IS NULL AND price_unit = 0 AND product_uom_qty = 0 AND product_uom_qty IS NULL AND customer_lead = 0))",
         "Forbidden values on non-accountable sale blanket order line"),
    ]

    @api.depends(
        "original_uom_qty",
        "price_unit",
        "taxes_id",
        "order_id.partner_id",
        "product_id",
        "currency_id",
    )
    def _compute_amount(self):
        for line in self:
            price = line.price_unit
            taxes = line.taxes_id.compute_all(
                price,
                line.currency_id,
                line.original_uom_qty,
                product=line.product_id,
                partner=line.order_id.partner_id,
            )
            line.update(
                {
                    "price_tax": sum(
                        t.get("amount", 0.0) for t in taxes.get("taxes", [])
                    ),
                    "price_total": taxes["total_included"],
                    "price_subtotal": taxes["total_excluded"],
                }
            )

    name = fields.Char("Description", tracking=True)
    sequence = fields.Integer()
    order_id = fields.Many2one("sale.blanket.order", required=True, ondelete="cascade")
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        domain=[("sale_ok", "=", True)],
    )
    product_uom = fields.Many2one("uom.uom", string="Unit of Measure", compute='_compute_product_uom', store=True)
    price_unit = fields.Float(string="Price", digits="Product Price")
    taxes_id = fields.Many2many(
        "account.tax",
        string="Taxes",
        domain=["|", ("active", "=", False), ("active", "=", True)],
    )
    date_schedule = fields.Date(string="Scheduled Date")
    original_uom_qty = fields.Float(
        string="Original quantity", default=1, digits="Product Unit of Measure"
    )
    ordered_uom_qty = fields.Float(
        string="Ordered quantity", compute="_compute_quantities", store=True
    )
    invoiced_uom_qty = fields.Float(
        string="Invoiced quantity", compute="_compute_quantities", store=True
    )
    remaining_uom_qty = fields.Float(
        string="Remaining quantity", compute="_compute_quantities", store=True
    )
    remaining_qty = fields.Float(
        string="Remaining quantity in base UoM",
        compute="_compute_quantities",
        store=True,
    )
    delivered_uom_qty = fields.Float(
        string="Delivered quantity", compute="_compute_quantities", store=True
    )
    sale_lines = fields.One2many(
        "sale.order.line",
        "blanket_order_line",
        string="Sale order lines",
        readonly=True,
        copy=False,
    )
    company_id = fields.Many2one(
        related="order_id.company_id", store=True, index=True, precompute=True
    )
    currency_id = fields.Many2one("res.currency", related="order_id.currency_id")
    partner_id = fields.Many2one(related="order_id.partner_id", string="Customer")
    user_id = fields.Many2one(related="order_id.user_id", string="Responsible")
    payment_term_id = fields.Many2one(
        related="order_id.payment_term_id", string="Payment Terms"
    )
    pricelist_id = fields.Many2one(related="order_id.pricelist_id", string="Pricelist")

    price_subtotal = fields.Monetary(
        compute="_compute_amount", string="Subtotal", store=True
    )
    price_total = fields.Monetary(compute="_compute_amount", string="Total", store=True)
    price_tax = fields.Float(compute="_compute_amount", string="Tax", store=True)
    display_type = fields.Selection(
        [("line_section", "Section"), ("line_note", "Note")],
        default=False,
        help="Technical field for UX purpose.",
    )
    pricelist_item_id = fields.Many2one(
        comodel_name="product.pricelist.item", compute="_compute_pricelist_item_id"
    )
    invoice_lines = fields.Many2many(
        comodel_name='account.move.line',
        relation='sale_blanket_order_line_invoice_rel',
        column1='blanket_order_line_id',
        column2='invoice_line_id',
        string="Invoice Lines",
        copy=False
    )
    is_downpayment = fields.Boolean(
        copy=False,
        string="Is a down payment",
        help="Down payments are made when creating invoices from a purchase order."
             " They are not copied when duplicating a purchase order.")
    product_uom_qty = fields.Float(
        string="Quantity",
        compute='_compute_product_uom_qty',
        digits='Product Unit of Measure', default=1.0,
        store=True, readonly=False, required=True, precompute=True)
    product_packaging_id = fields.Many2one(
        comodel_name='product.packaging',
        string="Packaging",
        compute='_compute_product_packaging_id',
        store=True, readonly=False, precompute=True,
        domain="[('sales', '=', True), ('product_id','=',product_id)]",
        check_company=True)
    product_packaging_qty = fields.Float(
        string="Packaging Quantity",
        compute='_compute_product_packaging_qty',
        store=True, readonly=False, precompute=True)
    discount = fields.Float(
        string="Discount (%)",
        compute='_compute_discount',
        digits='Discount',
        store=True, readonly=False, precompute=True)
    dp_blanket = fields.Float(
        string="Down Payment",
        related="order_id.down_payment", store=True, force_save=True
    )
    # down_payment = fields.Float(related='order_id.down_payment', force_save=True)
    dp_order = fields.Float(
        string="Order Down Payment",
        # compute="_compute_dp",
    )
    dp_sisa = fields.Float(
        string="Remaining Down Payment",
        compute="_compute_dp_sisa"
    )
    

    @api.depends('dp_blanket', 'dp_order')
    def _compute_dp_sisa(self):
        for order in self:
            order.dp_sisa = order.dp_blanket - order.dp_order
            # if order.order_id:
            #     total_dp_order = sum(
            #         o.dp_order for o in self.search([('order_id', '=', order.order_id.id)])
            #     )
            # else:
            #     total_dp_order = 0.0
    
            # order.dp_sisa = order.dp_blanket - total_dp_order

    @api.depends('order_id')
    def _compute_dp(self):
        for line in self:
            line.dp_blanket = line.dp_blanket

            if line.order_id:
                sale_orders = self.env['sale.order'].search([('order_line.blanket_order_line', '=', line.id)])
                total_dp_order = sum(order.dp_order for order in sale_orders)
            else:
                total_dp_order = 0.0

            line.dp_order = total_dp_order

    @api.depends('product_id')
    def _compute_product_uom(self):
        for line in self:
            if not line.product_uom or (line.product_id.uom_id.id != line.product_uom.id):
                line.product_uom = line.product_id.uom_id

    def _prepare_invoice_line(self):
        """Prepare the dict of values to create a new invoice line for a blanket order line."""
        self.ensure_one()

        # Find the income account for the product (or category if not defined)
        account_id = self.product_id.property_account_income_id.id or self.product_id.categ_id.property_account_income_categ_id.id

        if not account_id:
            raise UserError(_('Please define an income account for this product: "%s".') % (self.product_id.name,))

        # Prepare the invoice line values
        return {
            'name': self.name or self.product_id.name,
            'product_id': self.product_id.id,
            'account_id': account_id,
            'price_unit': self.price_unit,
            'quantity': self.product_uom_qty,
            'discount': self.discount,
            'uom_id': self.product_uom.id,
            'sale_line_ids': [(6, 0, [self.id])],
            'tax_ids': [(6, 0, self.tax_id.ids)],
            'analytic_account_id': self.order_id.analytic_account_id.id if self.order_id.analytic_account_id else False,
        }

    @api.depends('product_id', 'product_uom', 'product_uom_qty')
    def _compute_discount(self):
        for line in self:
            if not line.product_id or line.display_type:
                line.discount = 0.0

            if not (
                    line.order_id.pricelist_id
                    and line.order_id.pricelist_id.discount_policy == 'without_discount'
            ):
                continue

            line.discount = 0.0

            if not line.pricelist_item_id:
                # No pricelist rule was found for the product
                # therefore, the pricelist didn't apply any discount/change
                # to the existing sales price.
                continue

            line = line.with_company(line.company_id)
            pricelist_price = line._get_pricelist_price()
            base_price = line._get_pricelist_price_before_discount()

            if base_price != 0:  # Avoid division by zero
                discount = (base_price - pricelist_price) / base_price * 100
                if (discount > 0 and base_price > 0) or (discount < 0 and base_price < 0):
                    # only show negative discounts if price is negative
                    # otherwise it's a surcharge which shouldn't be shown to the customer
                    line.discount = discount

    @api.depends('product_id', 'product_uom_qty', 'product_uom')
    def _compute_product_packaging_id(self):
        for line in self:
            # remove packaging if not match the product
            if line.product_packaging_id.product_id != line.product_id:
                line.product_packaging_id = False
            # suggest biggest suitable packaging matching the SO's company
            if line.product_id and line.product_uom_qty and line.product_uom:
                suggested_packaging = line.product_id.packaging_ids \
                    .filtered(lambda p: p.sales and (p.product_id.company_id <= p.company_id <= line.company_id)) \
                    ._find_suitable_product_packaging(line.product_uom_qty, line.product_uom)
                line.product_packaging_id = suggested_packaging or line.product_packaging_id

    @api.depends('product_packaging_id', 'product_uom', 'product_uom_qty')
    def _compute_product_packaging_qty(self):
        self.product_packaging_qty = 0
        for line in self:
            if not line.product_packaging_id:
                continue
            line.product_packaging_qty = line.product_packaging_id._compute_qty(line.product_uom_qty, line.product_uom)

    @api.depends('display_type', 'product_id', 'product_packaging_qty')
    def _compute_product_uom_qty(self):
        for line in self:
            if line.display_type:
                line.product_uom_qty = 0.0
                continue

            if not line.product_packaging_id:
                continue
            packaging_uom = line.product_packaging_id.product_uom_id
            qty_per_packaging = line.product_packaging_id.qty
            product_uom_qty = packaging_uom._compute_quantity(
                line.product_packaging_qty * qty_per_packaging, line.product_uom)
            if float_compare(product_uom_qty, line.product_uom_qty, precision_rounding=line.product_uom.rounding) != 0:
                line.product_uom_qty = product_uom_qty

    # def _convert_to_tax_base_line_dict(self, **kwargs):
    #     """ Convert the current record to a dictionary in order to use the generic taxes computation method
    #     defined on account.tax.
    #
    #     :return: A python dictionary.
    #     """
    #     self.ensure_one()
    #     return self.env['account.tax']._convert_to_tax_base_line_dict(
    #         self,
    #         partner=self.order_id.partner_id,
    #         currency=self.order_id.currency_id,
    #         product=self.product_id,
    #         taxes=self.taxes_id,
    #         price_unit=self.price_unit,
    #         quantity=self.product_uom,
    #         discount=self.discount,
    #         price_subtotal=self.price_subtotal,
    #         **kwargs,
    #     )

    def _convert_to_tax_base_line_dict(self, analytic_distribution=None, handle_price_include=True):
        """ Method to generate tax base line dictionary from the blanket order line """
        self.ensure_one()
        tax_base_dict = {
            'product_id': self.product_id.id,
            'price_unit': self.price_unit,
            'quantity': self.product_uom,
            # 'discount': self.discount,
            'analytic_distribution': analytic_distribution or self.analytic_distribution,
            'taxes': self.taxes_id,
            'handle_price_include': handle_price_include,
        }
        return tax_base_dict

    @api.depends(
        "order_id.name", "date_schedule", "remaining_uom_qty", "product_uom.name"
    )
    @api.depends_context("from_sale_order")
    def _compute_display_name(self):
        if self.env.context.get("from_sale_order"):
            for record in self:
                name = "[%s]" % record.order_id.name
                if record.date_schedule:
                    formatted_date = format_date(record.env, record.date_schedule)
                    name += " - {}: {}".format(_("Date Scheduled"), formatted_date)
                name += " ({}: {} {})".format(
                    _("remaining"),
                    record.remaining_uom_qty,
                    record.product_uom.name,
                )
                record.display_name = name
        else:
            return super()._compute_display_name()

    def _get_real_price_currency(self, product, rule_id, qty, uom, pricelist_id):
        """Retrieve the price before applying the pricelist
        :param obj product: object of current product record
        :param float qty: total quentity of product
        :param tuple price_and_rule: tuple(price, suitable_rule) coming
               from pricelist computation
        :param obj uom: unit of measure of current order line
        :param integer pricelist_id: pricelist id of sale order"""
        # Copied and adapted from the sale module
        PricelistItem = self.env["product.pricelist.item"]
        field_name = "lst_price"
        currency_id = None
        product_currency = None
        if rule_id:
            pricelist_item = PricelistItem.browse(rule_id)
            if pricelist_item.pricelist_id.discount_policy == "without_discount":
                while (
                    pricelist_item.base == "pricelist"
                    and pricelist_item.base_pricelist_id
                    and pricelist_item.base_pricelist_id.discount_policy
                    == "without_discount"
                ):
                    price, rule_id = pricelist_item.base_pricelist_id.with_context(
                        uom=uom.id
                    )._get_product_price_rule(product, qty, uom)
                    pricelist_item = PricelistItem.browse(rule_id)

            if pricelist_item.base == "standard_price":
                field_name = "standard_price"
            if pricelist_item.base == "pricelist" and pricelist_item.base_pricelist_id:
                field_name = "price"
                product = product.with_context(
                    pricelist=pricelist_item.base_pricelist_id.id
                )
                product_currency = pricelist_item.base_pricelist_id.currency_id
            currency_id = pricelist_item.pricelist_id.currency_id

        product_currency = (
            product_currency
            or (product.company_id and product.company_id.currency_id)
            or self.env.company.currency_id
        )
        if not currency_id:
            currency_id = product_currency
            cur_factor = 1.0
        else:
            if currency_id.id == product_currency.id:
                cur_factor = 1.0
            else:
                cur_factor = currency_id._get_conversion_rate(
                    product_currency, currency_id
                )

        product_uom = product.uom_id.id
        if uom and uom.id != product_uom:
            # the unit price is in a different uom
            uom_factor = uom._compute_price(1.0, product.uom_id)
        else:
            uom_factor = 1.0

        return product[field_name] * uom_factor * cur_factor, currency_id.id

    def _get_display_price(self):
        # Copied and adapted from the sale module
        self.ensure_one()
        self.product_id.ensure_one()

        pricelist_price = self.pricelist_item_id._compute_price(
            product=self.product_id,
            quantity=self.original_uom_qty or 1.0,
            uom=self.product_uom,
            date=fields.Date.today(),
            currency=self.currency_id,
        )

        if self.order_id.pricelist_id.discount_policy == "with_discount":
            return pricelist_price

        if not self.pricelist_item_id:
            # No pricelist rule found => no discount from pricelist
            return pricelist_price

        base_price = self._get_pricelist_price_before_discount()

        # negative discounts (= surcharge) are included in the display price
        return max(base_price, pricelist_price)

    def _get_pricelist_price_before_discount(self):
        # Copied and adapted from the sale module
        self.ensure_one()
        self.product_id.ensure_one()

        return self.pricelist_item_id._compute_price_before_discount(
            product=self.product_id,
            quantity=self.product_uom_qty or 1.0,
            uom=self.product_uom,
            date=fields.Date.today(),
            currency=self.currency_id,
        )

    @api.onchange("product_id", "original_uom_qty")
    def onchange_product(self):
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        if self.product_id:
            name = self.product_id.name
            if not self.product_uom:
                self.product_uom = self.product_id.uom_id.id
            if self.order_id.partner_id and float_is_zero(
                self.price_unit, precision_digits=precision
            ):
                self.price_unit = self._get_display_price()
            if self.product_id.code:
                name = f"[{name}] {self.product_id.code}"
            if self.product_id.description_sale:
                name += "\n" + self.product_id.description_sale
            self.name = name

            fpos = self.order_id.fiscal_position_id
            if self.env.uid == SUPERUSER_ID:
                company_id = self.env.company.id
                self.taxes_id = fpos.map_tax(
                    self.product_id.taxes_id.filtered(
                        lambda r: r.company_id.id == company_id
                    )
                )
            else:
                self.taxes_id = fpos.map_tax(self.product_id.taxes_id)

    @api.depends(
        "sale_lines.order_id.state",
        "sale_lines.blanket_order_line",
        "sale_lines.product_uom_qty",
        "sale_lines.product_uom",
        "sale_lines.qty_delivered",
        "sale_lines.qty_invoiced",
        "original_uom_qty",
        "product_uom",
    )
    def _compute_quantities(self):
        for line in self:
            sale_lines = line.sale_lines
            line.ordered_uom_qty = sum(
                sl.product_uom._compute_quantity(sl.product_uom_qty, line.product_uom)
                for sl in sale_lines
                if sl.order_id.state != "cancel" and sl.product_id == line.product_id
            )
            line.invoiced_uom_qty = sum(
                sl.product_uom._compute_quantity(sl.qty_invoiced, line.product_uom)
                for sl in sale_lines
                if sl.order_id.state != "cancel" and sl.product_id == line.product_id
            )
            line.delivered_uom_qty = sum(
                sl.product_uom._compute_quantity(sl.qty_delivered, line.product_uom)
                for sl in sale_lines
                if sl.order_id.state != "cancel" and sl.product_id == line.product_id
            )
            line.remaining_uom_qty = line.original_uom_qty - line.ordered_uom_qty
            line.remaining_qty = line.product_uom._compute_quantity(
                line.remaining_uom_qty, line.product_id.uom_id
            )

    @api.depends("product_id", "product_uom", "original_uom_qty")
    def _compute_pricelist_item_id(self):
        # Copied and adapted from the sale module
        for line in self:
            if (
                not line.product_id
                or line.display_type
                or not line.order_id.pricelist_id
            ):
                line.pricelist_item_id = False
            else:
                line.pricelist_item_id = line.order_id.pricelist_id._get_product_rule(
                    line.product_id,
                    quantity=line.original_uom_qty or 1.0,
                    uom=line.product_uom,
                    date=fields.Date.today(),
                )

    def _validate(self):
        try:
            for line in self:
                assert (
                    not line.display_type and line.price_unit > 0.0
                ) or line.display_type, _("Price must be greater than zero")
                assert (
                    not line.display_type and line.original_uom_qty > 0.0
                ) or line.display_type, _("Quantity must be greater than zero")
        except AssertionError as e:
            raise UserError(e) from e

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get(
                "display_type", self.default_get(["display_type"])["display_type"]
            ):
                values.update(product_id=False, price_unit=0, product_uom=False)

        return super().create(vals_list)

    def write(self, values):
        if "display_type" in values and self.filtered(
            lambda line: line.display_type != values.get("display_type")
        ):
            raise UserError(
                _(
                    """
                    You cannot change the type of a sale order line.
                    Instead you should delete the current line and create a new line
                    of the proper type.
                    """
                )
            )
        return super().write(values)
