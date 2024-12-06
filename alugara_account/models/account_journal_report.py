# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools import format_date, date_utils, get_lang
from collections import defaultdict
from odoo.exceptions import UserError, RedirectWarning
class JournalReportCustomHandler(models.AbstractModel):
    # _name = 'account.journal.report.handler.inherit'
    _inherit = 'account.journal.report.handler'

    def _get_lines_for_group(self, options, parent_line_id, journal, progress, offset):
        """ Create the report lines for a group of moves. A group is either a journal, or a month if the report is grouped by month."""
        def cumulate_balance(line, current_balances, is_unreconciled_payment):
            # For bank journals, we want to cumulate the balances and display their evolution line by line until the end.
            for column_group_key in options['column_groups']:
                # For bank journals, we want to cumulate the balances and display their evolution line by line until the end.
                if journal.type == 'bank' and line[column_group_key]['account_type'] not in ('liability_credit_card', 'asset_cash') and not is_unreconciled_payment:
                    current_balances[column_group_key] += -line[column_group_key]['balance']
                    line[column_group_key]['cumulated_balance'] = current_balances[column_group_key]
        
        # TESTING

        def cumulate_balance_2(line, current_balances, is_unreconciled_payment):
            # For bank journals, we want to cumulate the balances and display their evolution line by line until the end.
            for column_group_key in options['column_groups']:
                # For bank journals, we want to cumulate the balances and display their evolution line by line until the end.
                if journal.type == 'bank' and line[column_group_key]['account_type'] not in ('liability_credit_card', 'asset_cash') and not is_unreconciled_payment:
                    current_balances[column_group_key] += -line[column_group_key]['balance']
                    line[column_group_key]['cumulated_balance_2'] = current_balances[column_group_key]

        # TESTING

        lines, after_load_more_lines = [], []
        current_balances, next_progress = {}, {}
        # Treated result count also consider the lines not rendered in the report, and is used for the query offset.
        # Rendered line count does not consider the lines not rendered, and allows to stop rendering more when the quota has been reached.
        treated_results_count = 0
        has_more_lines = False

        eval_dict = self._query_aml(options, offset, journal)
        if offset == 0:
            lines.append(self._get_columns_line(options, parent_line_id, journal.type))

        if journal.type == 'bank':
            # Get initial balance, only if the journal is of type 'bank', and we have no offset yet (first unfolding)
            if offset == 0:
                if journal.type == 'bank':
                    init_balance_by_col_group = self._get_journal_initial_balance(options, journal.id)
                    initial_balance_line = self._get_journal_balance_line(
                        options, parent_line_id, init_balance_by_col_group, is_starting_balance=True)
                    if initial_balance_line:
                        lines.append(initial_balance_line)
                        # For the first expansion of the line, the initial balance line gives the progress
                        progress = {
                            column['column_group_key']: line_col.get('no_format', 0.0)
                            for column, line_col in zip(options['columns'], initial_balance_line['columns'])
                            if column['expression_label'] == 'additional_col_1'
                        }
            # Weither we just fetched them or not, the balance is now in the progress.
            for column_group_key in options['column_groups']:
                current_balances[column_group_key] = progress.get(column_group_key, 0.0)

        # Group the lines by moves, to simplify the following code.
        line_dict_grouped = self._group_lines_by_move(options, eval_dict, parent_line_id)

        report = self.env.ref('account_reports.journal_report')

        treated_amls_count = 0
        for move_key, move_line_vals_list in line_dict_grouped.items():
            # All move lines for a move will share static values, like if the move is multicurrency, the journal,..
            # These can be fetched using any column groups or lines for this move.
            first_move_line = move_line_vals_list[0]
            general_line_vals = next(col_group_val for col_group_val in first_move_line.values())
            if report.load_more_limit and len(move_line_vals_list) + treated_amls_count > report.load_more_limit and options['export_mode'] != 'print':
                # This element won't generate a line now, but we use it to know that we'll need to add a load_more line.
                has_more_lines = True
                if treated_amls_count == 0:
                    # A single move lines count exceed the load more limit, we need to raise to inform the user
                    msg = _("The 'load more limit' setting of this report is too low to display all the lines of the entry you're trying to show.")
                    if self.env.user.has_group('account.group_account_manager'):
                        action = {
                            "view_mode": "form",
                            "res_model": "account.report",
                            "type": "ir.actions.act_window",
                            "res_id" : report.id,
                            "views": [[self.env.ref("account_reports.account_report_form").id, "form"]],
                        }
                        title = _('Go to report configuration')

                        raise RedirectWarning(msg, action, title)
                    raise UserError(msg)
                break
            is_unreconciled_payment = journal.type == 'bank' and not any(line for line in move_line_vals_list if next(col_group_val for col_group_val in line.values())['account_type'] in ('liability_credit_card', 'asset_cash'))
            if journal.type == 'bank':
                cumulate_balance(first_move_line, current_balances, is_unreconciled_payment)
                cumulate_balance_2(first_move_line, current_balances, is_unreconciled_payment)

            # Do not display payments move on bank journal if the options isn't enabled.
            if not options.get('show_payment_lines') and is_unreconciled_payment:
                treated_results_count += len(move_line_vals_list)   # used to get the offset
                continue
            # Create the first line separately, as we want to give it some specific behavior and styling
            lines.append(self._get_first_move_line(options, parent_line_id, move_key, first_move_line, is_unreconciled_payment))
            treated_amls_count += len(move_line_vals_list)
            treated_results_count += 1
            for line_index, move_line_vals in enumerate(move_line_vals_list[1:]):
                if journal.type == 'bank':
                    cumulate_balance(move_line_vals, current_balances, is_unreconciled_payment)
                    cumulate_balance_2(move_line_vals, current_balances, is_unreconciled_payment)
                line = self._get_aml_line(options, parent_line_id, move_line_vals, line_index, journal, is_unreconciled_payment)
                treated_results_count += 1
                if line:
                    lines.append(line)

                multicurrency_name = self._get_aml_line_name(options, journal, -1, first_move_line, is_unreconciled_payment)
                # Add a currency line if we have a foreign currency on the move but no place to put this info beforehand in the name of a line.
                # This can happen if we have two lines only and a ref: the ref take the name of the second line and we need a new one for the currency.
                if general_line_vals['is_multicurrency'] \
                        and len(move_line_vals_list) == 2 \
                        and self.user_has_groups('base.group_multi_currency') \
                        and lines[-1]['name'] != multicurrency_name \
                        and journal.type != 'bank':
                    lines.append({
                        'id': report._get_generic_line_id('account.move.line', general_line_vals['move_id'], parent_line_id=parent_line_id, markup='amount_currency_total'),
                        'name': multicurrency_name,
                        'level': 3,
                        'parent_id': parent_line_id,
                        'columns': [{} for column in options['columns']],
                    })
                if journal.type == 'bank':
                    next_progress = {
                        column['column_group_key']: line_col.get('no_format', 0.0)
                        for column, line_col in zip(options['columns'], lines[-1]['columns'])
                        if column['expression_label'] == 'additional_col_1'
                    }
        # If we have no offsets, check if we can create a tax line: This line will contain two tables, one for the tax summary and one for the tax grid summary.
        if offset == 0:
            # It is faster to first check that we need a tax section; this avoids computing a tax report for nothing.
            aml_has_tax_domain = [('journal_id', '=', journal.id), ('tax_ids', '!=', False)]
            if options.get('date', {}).get('date_from'):
                aml_has_tax_domain.append(('date', '>=', options['date']['date_from']))
            if options.get('date', {}).get('date_to'):
                aml_has_tax_domain.append(('date', '<=', options['date']['date_to']))
            journal_has_tax = bool(self.env['account.move.line'].search_count(aml_has_tax_domain, limit=1))
            if journal_has_tax:
                tax_data = {
                    'date_from': options.get('date', {}).get('date_from'),
                    'date_to': options.get('date', {}).get('date_to'),
                    'journal_id': journal.id,
                    'journal_type': journal.type,
                }
                # This is a special line with a special template to render it.
                # It will contain two tables, which are the tax report and tax grid summary sections.
                tax_report_lines = self._get_generic_tax_summary_for_sections(options, tax_data)

                tax_non_deductible_column = any(line.get('tax_non_deductible_no_format') for country in tax_report_lines.values() for line in country)
                tax_deductible_column = any(line.get('tax_deductible_no_format') for country in tax_report_lines.values() for line in country)
                tax_due_column = any(line.get('tax_due_no_format') for country in tax_report_lines.values() for line in country)
                extra_columns = int(tax_non_deductible_column) + int(tax_deductible_column) + int(tax_due_column)

                tax_grid_summary_lines = self._get_tax_grids_summary(options, tax_data)
                if tax_report_lines or tax_grid_summary_lines:
                    after_load_more_lines.append({
                        'id': report._get_generic_line_id(False, False, parent_line_id=parent_line_id, markup='tax_report_section'),
                        'name': '',
                        'parent_id': parent_line_id,
                        'journal_id': journal.id,
                        'is_tax_section_line': True,
                        'tax_report_lines': tax_report_lines,
                        'tax_non_deductible_column': tax_non_deductible_column,
                        'tax_deductible_column': tax_deductible_column,
                        'tax_due_column': tax_due_column,
                        'extra_columns': extra_columns,
                        'tax_grid_summary_lines': tax_grid_summary_lines,
                        'date_from': tax_data['date_from'],
                        'date_to': tax_data['date_to'],
                        'columns': [],
                        'colspan': len(options['columns']) + 1,
                        'level': 3,
                    })

        return lines, after_load_more_lines, has_more_lines, treated_results_count, next_progress, current_balances
