from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fp_hacienda_api_base_url = fields.Char(related="company_id.fp_hacienda_api_base_url", readonly=False)
    fp_hacienda_token_url = fields.Char(related="company_id.fp_hacienda_token_url", readonly=False)
    fp_hacienda_client_id = fields.Char(related="company_id.fp_hacienda_client_id", readonly=False)
    fp_hacienda_sandbox_mode = fields.Boolean(related="company_id.fp_hacienda_sandbox_mode", readonly=False)
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
    fp_auto_send_email_when_accepted = fields.Boolean(
        related="company_id.fp_auto_send_email_when_accepted",
        readonly=False,
    )

    fp_invoice_template_style = fields.Selection(
        related="company_id.fp_invoice_template_style",
        readonly=False,
    )

    fp_certificate_subject = fields.Char(related="company_id.fp_certificate_subject", readonly=True)
    fp_certificate_serial_subject = fields.Char(related="company_id.fp_certificate_serial_subject", readonly=True)
    fp_certificate_issue_date = fields.Date(related="company_id.fp_certificate_issue_date", readonly=True)
    fp_certificate_expiration_date = fields.Date(related="company_id.fp_certificate_expiration_date", readonly=True)
    fp_certificate_issuer = fields.Char(related="company_id.fp_certificate_issuer", readonly=True)
    fp_certificate_serial_number = fields.Char(related="company_id.fp_certificate_serial_number", readonly=True)
    fp_certificate_version = fields.Char(related="company_id.fp_certificate_version", readonly=True)

    fp_branch_code = fields.Char(related="company_id.fp_branch_code", readonly=False)
    fp_terminal_code = fields.Char(related="company_id.fp_terminal_code", readonly=False)
    fp_consecutive_fe = fields.Char(related="company_id.fp_consecutive_fe", readonly=False)
    fp_consecutive_te = fields.Char(related="company_id.fp_consecutive_te", readonly=False)
    fp_consecutive_fec = fields.Char(related="company_id.fp_consecutive_fec", readonly=False)
    fp_consecutive_nc = fields.Char(related="company_id.fp_consecutive_nc", readonly=False)
    fp_consecutive_nd = fields.Char(related="company_id.fp_consecutive_nd", readonly=False)
    fp_consecutive_others = fields.Char(related="company_id.fp_consecutive_others", readonly=False)


    def action_fp_refresh_certificate_info(self):
        self.ensure_one()
        self.company_id.action_fp_refresh_certificate_info()
