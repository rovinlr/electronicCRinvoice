from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fp_hacienda_api_base_url = fields.Char(related="company_id.fp_hacienda_api_base_url", readonly=False)
    fp_hacienda_token_url = fields.Char(related="company_id.fp_hacienda_token_url", readonly=False)
    fp_hacienda_client_id = fields.Char(related="company_id.fp_hacienda_client_id", readonly=False)
    fp_hacienda_username = fields.Char(related="company_id.fp_hacienda_username", readonly=False)
    fp_hacienda_password = fields.Char(related="company_id.fp_hacienda_password", readonly=False)
    fp_api_timeout = fields.Integer(related="company_id.fp_api_timeout", readonly=False)

    fp_economic_activity_id = fields.Many2one(related="company_id.fp_economic_activity_id", readonly=False)
    fp_signing_certificate_file = fields.Binary(
        related="company_id.fp_signing_certificate_file",
        readonly=False,
    )
    fp_signing_certificate_filename = fields.Char(
        related="company_id.fp_signing_certificate_filename",
        readonly=False,
    )
    fp_signing_certificate_password = fields.Char(
        related="company_id.fp_signing_certificate_password",
        readonly=False,
    )
    fp_auto_consult_after_send = fields.Boolean(
        related="company_id.fp_auto_consult_after_send",
        readonly=False,
    )
