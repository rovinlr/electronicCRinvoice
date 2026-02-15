from odoo import api, fields, models


class FpClientExoneration(models.Model):
    _name = "fp.client.exoneration"
    _description = "Exoneraciones de Clientes"
    _order = "issue_date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", required=True, ondelete="cascade")
    exoneration_number = fields.Char(string="Número de Exoneración", required=True)
    institution_name = fields.Char(string="Nombre de Institución", required=True)
    exoneration_type = fields.Selection(
        [
            ("01", "(01) Compras autorizadas"),
            ("02", "(02) Ventas exentas a diplomáticos"),
            ("03", "(03) Orden de compra"),
            ("04", "(04) Exenciones Dirección General de Hacienda"),
            ("05", "(05) Zonas Francas"),
            ("99", "(99) Otros"),
        ],
        string="Tipo de Exoneración",
        required=True,
    )
    article = fields.Char(string="Article")
    incise = fields.Char(string="Incised")
    issue_date = fields.Datetime(string="Fecha de Emisión", required=True)
    expiry_date = fields.Date(string="Fecha de Vencimiento")
    exoneration_percentage = fields.Float(string="Porcentaje de Exoneración (%)", default=0.0)
    line_ids = fields.One2many("fp.client.exoneration.line", "exoneration_id", string="Códigos CABYS")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("fp_client_exoneration_unique", "unique(exoneration_number, partner_id)", "Ya existe esta exoneración para el cliente."),
    ]

    @api.depends("exoneration_number", "exoneration_percentage")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.exoneration_number or ''} - {rec.exoneration_percentage or 0.0}%"


class FpClientExonerationLine(models.Model):
    _name = "fp.client.exoneration.line"
    _description = "Detalle CABYS Exoneración"

    exoneration_id = fields.Many2one("fp.client.exoneration", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.template", string="Producto")
    cabys_code_id = fields.Many2one("fp.cabys.code", string="Código CABYS")
    exoneration_code = fields.Char(string="Código exoneración")

    _sql_constraints = [
        (
            "fp_client_exoneration_line_unique",
            "unique(exoneration_id, product_id, cabys_code_id)",
            "No puede repetir el mismo producto/CABYS en la misma exoneración.",
        ),
    ]
