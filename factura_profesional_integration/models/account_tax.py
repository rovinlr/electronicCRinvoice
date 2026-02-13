from odoo import fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    fp_tax_type = fields.Selection(
        [
            ("01", "01 - IVA"),
            ("02", "02 - Selectivo de Consumo"),
            ("03", "03 - Único a los Combustibles"),
            ("04", "04 - Impuesto específico de Bebidas Alcohólicas"),
            ("05", "05 - Impuesto específico sobre bebidas sin contenido alcohólico y jabones de tocador"),
            ("06", "06 - Impuesto a los Productos de Tabaco"),
            ("07", "07 - IVA (cálculo especial)"),
            ("08", "08 - IVA Régimen de Bienes Usados (Factor)"),
            ("12", "12 - Impuesto Específico al Cemento"),
            ("99", "99 - Otro"),
        ],
        string="Tipo de impuesto (FE)",
        help="Tipo de impuesto según nota 8 de Anexos y Estructuras v4.4.",
    )
    fp_tax_rate_code_iva = fields.Selection(
        [
            ("01", "01 - Tarifa 0% (Artículo 32, num 1, RLIVA)"),
            ("02", "02 - Tarifa reducida 1%"),
            ("03", "03 - Tarifa reducida 2%"),
            ("04", "04 - Tarifa reducida 4%"),
            ("05", "05 - Transitorio 0%"),
            ("06", "06 - Transitorio 4%"),
            ("07", "07 - Tarifa transitoria 8%"),
            ("08", "08 - Tarifa general 13%"),
            ("09", "09 - Tarifa reducida 0.5%"),
            ("10", "10 - Tarifa exenta"),
            ("11", "11 - Tarifa 0% sin derecho a crédito"),
        ],
        string="Código tarifa IVA (FE)",
        help="Código de tarifa del IVA según nota 8.1 de Anexos y Estructuras v4.4.",
    )
    fp_tax_code = fields.Char(
        string="Código de impuesto (FE)",
        help="Código oficial de impuesto para facturación electrónica.",
    )
    fp_tax_rate = fields.Float(
        string="Tarifa de impuesto (FE)",
        help="Tarifa oficial de impuesto para facturación electrónica.",
    )
