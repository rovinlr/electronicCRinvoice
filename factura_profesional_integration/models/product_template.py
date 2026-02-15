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

    fp_health_registry_number = fields.Char(
        string="Número de registro del Ministerio de Salud",
        help="Número de registro sanitario del producto cuando la normativa lo requiera.",
    )
    fp_medicine_presentation_code = fields.Char(
        string="Código de la presentación del medicamento",
        help="Código de presentación del medicamento cuando aplique.",
    )
    fp_commercial_code_type = fields.Selection(
        [("01", "01 - Código del producto"), ("02", "02 - Código del fabricante"), ("03", "03 - Código del sistema")],
        string="Tipo de código",
        help="Tipo de código comercial para el nodo CodigoComercial del XML.",
    )
    fp_tariff_heading = fields.Char(
        string="Partida arancelaria",
        help="Partida arancelaria para líneas de exportación o cuando aplique.",
    )
    fp_transport_vin_or_series = fields.Char(
        string="Número de VIN o Serie del medio de transporte",
        help="VIN o número de serie del medio de transporte cuando aplique.",
    )
