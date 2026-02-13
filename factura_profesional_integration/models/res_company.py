from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    fp_hacienda_api_base_url = fields.Char(
        string="Hacienda API Base URL",
        default="https://api.comprobanteselectronicos.go.cr",
    )
    fp_hacienda_token_url = fields.Char(
        string="Hacienda OAuth Token URL",
        default=(
            "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/"
            "openid-connect/token"
        ),
    )
    fp_hacienda_client_id = fields.Char(string="Hacienda Client ID", default="api-prod")
    fp_hacienda_username = fields.Char(string="Hacienda Username")
    fp_hacienda_password = fields.Char(string="Hacienda Password")
    fp_api_timeout = fields.Integer(string="Hacienda API Timeout (s)", default=30)
    fp_economic_activity_code = fields.Char(string="Actividad económica por defecto (FE)")
