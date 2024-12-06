from odoo import models, fields

class AccountAccount(models.Model):
    _inherit = 'account.account'

    active = fields.Boolean(string="Active", default=True)

    # def action_archive(self):
    #     for record in self:
    #         record.active = False
    #
    # def action_unarchive(self):
    #     for record in self:
    #         record.active = True
