from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    fp_identification_type = fields.Selection(
        [
            ("01", "01 - Cédula física"),
            ("02", "02 - Cédula jurídica"),
            ("03", "03 - DIMEX"),
            ("04", "04 - NITE"),
        ],
        string="Tipo de identificación (FE)",
        help="Catálogo de tipo de identificación para facturación electrónica.",
    )
