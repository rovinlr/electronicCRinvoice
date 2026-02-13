from odoo import fields, models


class UomUom(models.Model):
    _inherit = "uom.uom"

    fp_unit_code = fields.Char(
        string="Código de unidad (FE)",
        help="Código de unidad de medida usado por facturación electrónica.",
    )
