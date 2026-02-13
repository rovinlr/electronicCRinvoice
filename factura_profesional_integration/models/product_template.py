from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    fp_cabys_code_id = fields.Many2one(
        "fp.cabys.code",
        string="Código CABYS",
        help="Código CABYS del producto para facturación electrónica.",
    )
    fp_cabys_code = fields.Char(
        string="Código CABYS",
        related="fp_cabys_code_id.code",
        store=True,
        readonly=True,
    )
