# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "History Product",
    "summary": "History Product - SO PO",
    "version": "17.0.1.0.0",
    "category": "",
    "website": "",
    "author": "Yustaf Pramsistya",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ['stock', 'sale_management', 'purchase', 'analytic'],
    "data": [
        'views/stock_views.xml',
    ],
}
