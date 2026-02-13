from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    fp_cabys_code = fields.Char(
        string="Código CABYS",
        help="Código CABYS del producto para facturación electrónica.",
    )
