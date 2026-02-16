from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    exclude_from_invoice_tab = fields.Boolean(
        string="Exclude From Invoice Tab",
        default=False,
        help="Compatibility field for invoice report templates expecting this flag.",
    )
