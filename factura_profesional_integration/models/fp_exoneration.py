from odoo import api, fields, models


class FpClientExoneration(models.Model):
    _name = "fp.client.exoneration"
    _description = "Exoneraciones de Clientes"
    _order = "issue_date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", required=True, ondelete="cascade")
    exoneration_number = fields.Char(string="Número de Exoneración", required=True)
    institution_name = fields.Selection(
        [
            ("01", "01 - Ministerio de Hacienda"),
            ("02", "02 - Ministerio de Relaciones Exteriores y Culto"),
            ("03", "03 - Ministerio de Agricultura y Ganadería"),
            ("04", "04 - Ministerio de Economía, Industria y Comercio"),
            ("05", "05 - Cruz Roja Costarricense"),
            ("06", "06 - Benemérito Cuerpo de Bomberos de Costa Rica"),
            ("07", "07 - Asociación Obras del Espíritu Santo"),
            ("08", "08 - Federación Cruzada Nacional de Protección al Anciano (FECRUNAPA)"),
            ("09", "09 - Escuela de Agricultura de la Región Húmeda (EARTH)"),
            ("10", "10 - Instituto Centroamericano de Administración de Empresas (INCAE)"),
            ("11", "11 - Junta de Protección Social (JPS)"),
            ("12", "12 - Autoridad Reguladora de los Servicios Públicos (ARESEP)"),
            ("99", "99 - Otros"),
        ],
        string="Institución",
        required=True,
        help="Nombre de la institución o dependencia que emitió la exoneración según Nota 23 de Anexos y Estructuras v4.4.",
    )
    exoneration_type = fields.Selection(
        [
            ("01", "01 - Compras autorizadas por la Dirección General de Tributación"),
            ("02", "02 - Ventas exentas a diplomáticos"),
            ("03", "03 - Autorizado por Ley especial"),
            ("04", "04 - Exenciones DGH autorización local genérica"),
            ("05", "05 - Exenciones DGH Transitorio V (ingeniería, arquitectura, topografía, obra civil)"),
            ("06", "06 - Servicios turísticos inscritos ante el ICT"),
            ("07", "07 - Transitorio XVII (recolección, clasificación, almacenamiento de reciclaje y reutilizable)"),
            ("08", "08 - Exoneración a Zona Franca"),
            ("09", "09 - Exoneración de servicios complementarios para la exportación (art. 11 RLIVA)"),
            ("10", "10 - Órgano de las corporaciones municipales"),
            ("11", "11 - Exenciones DGH autorización de impuesto local concreta"),
            ("99", "99 - Otros"),
        ],
        string="Tipo de Exoneración",
        required=True,
        help="Tipo de documento de exoneración o autorización según Nota 10.1 de Anexos y Estructuras v4.4.",
    )
    article = fields.Char(string="Article")
    incise = fields.Char(string="Incised")
    issue_date = fields.Datetime(string="Fecha de Emisión", required=True)
    expiry_date = fields.Date(string="Fecha de Vencimiento")
    exoneration_percentage = fields.Float(string="Porcentaje de Exoneración (%)", default=0.0)
    line_ids = fields.One2many("fp.client.exoneration.line", "exoneration_id", string="Códigos CABYS")
    active = fields.Boolean(default=True)

    _fp_client_exoneration_unique = models.Constraint(
        "UNIQUE(exoneration_number, partner_id)",
        "Ya existe esta exoneración para el cliente.",
    )

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

    _fp_client_exoneration_line_unique = models.Constraint(
        "UNIQUE(exoneration_id, product_id, cabys_code_id)",
        "No puede repetir el mismo producto/CABYS en la misma exoneración.",
    )
