from odoo import fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    fp_tax_type = fields.Selection(
        [
            ("01", "01 - IVA"),
            ("02", "02 - Selectivo de Consumo"),
            ("03", "03 - Único a los Combustibles"),
            ("04", "04 - Especial"),
            ("99", "99 - Otro"),
        ],
        string="Tipo de impuesto (FE)",
        help="Tipo de impuesto según catálogo de FE.",
    )
    fp_tax_code = fields.Char(
        string="Código de impuesto (FE)",
        help="Código oficial de impuesto para facturación electrónica.",
    )
    fp_tax_rate = fields.Float(
        string="Tarifa de impuesto (FE)",
        help="Tarifa oficial de impuesto para facturación electrónica.",
    )
