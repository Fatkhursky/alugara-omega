# -*- coding: utf-8 -*-
# from odoo import http


# class AlugaraAccount(http.Controller):
#     @http.route('/alugara_account/alugara_account', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/alugara_account/alugara_account/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('alugara_account.listing', {
#             'root': '/alugara_account/alugara_account',
#             'objects': http.request.env['alugara_account.alugara_account'].search([]),
#         })

#     @http.route('/alugara_account/alugara_account/objects/<model("alugara_account.alugara_account"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('alugara_account.object', {
#             'object': obj
#         })

