# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # amount_residual_currency = fields.Monetary(
    #     string='Residual Amount in Currency',
    #     compute='_compute_amount_residual', store=True,
    #     group_operator=None,
    #     help="The residual amount on a journal item expressed in its currency (possibly not the "
    #          "company currency).",
    # )

    cumulated_balance_2 = fields.Monetary(
        string='Cumulated Balance #2',
        compute='_compute_cumulated_balance_2',
        currency_field='currency_id',
        exportable=False,
        help="Cumulated balance #2 depending on the domain and the order chosen in the view.")
    
    @api.depends_context('order_cumulated_balance', 'domain_cumulated_balance')
    def _compute_cumulated_balance_2(self):
        if not self.env.context.get('order_cumulated_balance'):
            # We do not come from search_fetch, so we are not in a list view, so it doesn't make any sense to compute the cumulated balance
            self.cumulated_balance_2 = 0
            return

        # get the where clause
        query = self._where_calc(list(self.env.context.get('domain_cumulated_balance') or []))
        sql_order = self._order_to_sql(self.env.context.get('order_cumulated_balance'), query, reverse=True)
        order_string = self.env.cr.mogrify(sql_order).decode()
        from_clause, where_clause, where_clause_params = query.get_sql()
        sql = """
            SELECT account_move_line.id, SUM(account_move_line.amount_currency) OVER (
                ORDER BY %(order_by)s
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )
            FROM %(from)s
            WHERE %(where)s
        """ % {'from': from_clause, 'where': where_clause or 'TRUE', 'order_by': order_string}
        self.env.cr.execute(sql, where_clause_params)
        result = {r[0]: r[1] for r in self.env.cr.fetchall()}
        for record in self:
            # record.cumulated_balance_2 = result[record.id] / record._get_currency_rate()
            record.cumulated_balance_2 = result[record.id] 

    # amount_residual_convert = fields.Monetary(
    #     string='Convert Residual Amount',
    #     compute='_compute_convert_amount_residual',
    #     currency_field='company_currency_id',
    #     # store=True
        
    #     )


    # @api.depends('amount_currency','amount_residual_currency')
    # def _compute_convert_amount_residual(self):
       
    def _get_currency_rate(self):     
        for rec in self:
            currency = rec.currency_id
            company_currency = rec.company_currency_id
            # currency = rec.company_currency_id
            # rec.amount_residual_convert = currency._convert(rec.amount_residual_currency, company_currency)
            current_rate =  self.env['res.currency']._get_conversion_rate(
                    from_currency=currency,
                    to_currency=company_currency,
                    company=rec.company_id,
                    date=rec._get_rate_date(),
                )
            return current_rate
            # rec.amount_residual_convert = rec.amount_residual_currency * current_rate
            
    def _get_rate_date(self):
        self.ensure_one()
        return fields.Date.context_today(self)
