# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Multicurrency revaluation",
    "summary": "Manage revaluation for multicurrency environment",
    "version": "17.0.1.0.0",
    "category": "Accounting",
    "website": "https://github.com/OCA/account-closing",
    "author": "Camptocamp, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["account"],
    "demo": ["demo/account_demo.xml", "demo/currency_demo.xml"],
    "data": [
        "views/res_config_view.xml",
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/account_view.xml",
        "views/account_move_views.xml",
        "views/account_move_line_views.xml",
        "wizard/print_currency_unrealized_report_view.xml",
        "wizard/wizard_currency_revaluation_view.xml",
        "wizard/wizard_reverse_currency_revaluation_view.xml",
        "report/report.xml",
        "report/unrealized_currency_gain_loss.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "om_account_multicurrency_revaluation/static/src/css/reports.css",
        ],
    },
}
