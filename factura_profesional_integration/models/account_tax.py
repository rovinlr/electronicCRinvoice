from odoo import fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    fp_tax_code = fields.Char(
        string="Código de impuesto (FE)",
        help="Código oficial de impuesto para facturación electrónica.",
    )
    fp_tax_rate = fields.Float(
        string="Tarifa de impuesto (FE)",
        help="Tarifa oficial de impuesto para facturación electrónica.",
    )
