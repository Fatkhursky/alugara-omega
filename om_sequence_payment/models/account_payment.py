from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        res = super(AccountPayment, self).action_post()
        for rec in self:
            if rec.journal_id:
                if rec.is_internal_transfer == False and rec.payment_type == 'outbound' and rec.partner_id == True:
                    rec.name = self.env['ir.sequence'].next_by_code('pp.sequence')
                elif rec.is_internal_transfer == False and rec.payment_type == 'inbound' and rec.partner_id == True:
                    rec.name = self.env['ir.sequence'].next_by_code('cr.sequence')
                elif rec.is_internal_transfer == True and rec.payment_type == 'inbound' or rec.partner_id == rec.company_id.id:
                    rec.name = self.env['ir.sequence'].next_by_code('bkm.sequence')
                elif rec.is_internal_transfer == True and rec.payment_type == 'outbound' or rec.partner_id == rec.company_id.id:
                    rec.name = self.env['ir.sequence'].next_by_code('bkk.sequence')

            if rec.destination_journal_id:
                if rec.is_internal_transfer == True and rec.payment_type == 'inbound' or rec.partner_id == rec.company_id.id:
                    rec.name = self.env['ir.sequence'].next_by_code('bkm.sequence')
                elif rec.is_internal_transfer == True and rec.payment_type == 'outbound' or rec.partner_id == rec.company_id.id:
                    rec.name = self.env['ir.sequence'].next_by_code('bkk.sequence')
        return res
