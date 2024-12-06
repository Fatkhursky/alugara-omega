from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super(AccountMove, self).action_post()
        for rec in self:
            if rec.journal_id and self.journal_id.type == 'general' and rec.move_type == 'entry':
                rec.name = self.env['ir.sequence'].next_by_code('jv.sequence')
            elif rec.move_type == 'out_invoice':
                rec.name = self.env['ir.sequence'].next_by_code('si.sequence')
            elif rec.move_type == 'in_invoice':
                rec.name = self.env['ir.sequence'].next_by_code('pi.sequence')
        return res
