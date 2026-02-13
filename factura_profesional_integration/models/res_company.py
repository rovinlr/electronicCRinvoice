from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    fp_hacienda_api_base_url = fields.Char(
        string="Hacienda API Base URL",
        company_dependent=True,
        default="https://api.comprobanteselectronicos.go.cr",
    )
    fp_hacienda_token_url = fields.Char(
        string="Hacienda OAuth Token URL",
        company_dependent=True,
        default=(
            "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/"
            "openid-connect/token"
        ),
    )
    fp_hacienda_client_id = fields.Char(
        string="Hacienda Client ID", company_dependent=True, default="api-prod"
    )
    fp_hacienda_username = fields.Char(string="Hacienda Username", company_dependent=True)
    fp_hacienda_password = fields.Char(string="Hacienda Password", company_dependent=True)
    fp_api_timeout = fields.Integer(
        string="Hacienda API Timeout (s)", default=30
    )
    fp_economic_activity_id = fields.Many2one(
        "fp.economic.activity",
        string="Actividad económica por defecto (FE)",
    )
    fp_economic_activity_code = fields.Char(
        related="fp_economic_activity_id.code",
        string="Código actividad económica por defecto (FE)",
        store=True,
        readonly=True,
    )
    fp_signing_certificate_file = fields.Binary(
        string="Certificado FE (.p12/.pfx)",
        attachment=True,
        help="Certificado con llave privada para firmar XML desde Odoo.",
    )
    fp_signing_certificate_filename = fields.Char(
        string="Nombre del certificado FE",
    )
    fp_signing_certificate_password = fields.Char(
        string="Contraseña certificado FE",
        company_dependent=True,
    )
    fp_auto_consult_after_send = fields.Boolean(
        string="Consultar estado automáticamente después de enviar",
        company_dependent=True,
        default=True,
    )
