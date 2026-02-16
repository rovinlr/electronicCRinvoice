import base64
import binascii

from cryptography.hazmat.primitives.serialization import pkcs12
from odoo import api, fields, models
from odoo.exceptions import ValidationError



class ResCompany(models.Model):
    _inherit = "res.company"

    fp_branch_code = fields.Char(
        string="Sucursal FE",
        company_dependent=True,
        default="001",
        help="Código de sucursal de 3 dígitos usado para formar el consecutivo FE.",
    )
    fp_terminal_code = fields.Char(
        string="Terminal FE",
        company_dependent=True,
        default="00001",
        help="Código de terminal de 5 dígitos usado para formar el consecutivo FE.",
    )

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
    fp_hacienda_environment = fields.Selection(
        [
            ("auto", "Auto (detectar por URLs)"),
            ("prod", "Producción"),
            ("sandbox", "Pruebas / Sandbox"),
        ],
        string="Ambiente Hacienda",
        company_dependent=True,
        default="auto",
        help="Define el ambiente para endpoints/client_id de Hacienda. En Auto se detecta según las URLs configuradas.",
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

    fp_invoice_template_style = fields.Selection(
        [
            ("standard", "Estándar Odoo"),
            ("modern", "Moderna Azul (legacy)"),
            ("modern_blue", "Moderna Azul"),
            ("modern_dark", "Moderna Oscura"),
            ("modern_clean", "Moderna Clara"),
            ("modern_emerald", "Moderna Esmeralda"),
            ("modern_sunset", "Moderna Atardecer"),
        ],
        string="Plantilla factura electrónica",
        company_dependent=True,
        help="Selecciona el estilo del PDF FE. Usa 'Estándar Odoo' para el formato original; el resto aplica plantillas personalizadas.",
    )
    fp_auto_consult_after_send = fields.Boolean(
        string="Consultar estado automáticamente después de enviar",
        company_dependent=True,
        default=True,
    )
    fp_auto_send_email_when_accepted = fields.Boolean(
        string="Enviar correo automáticamente al aceptar en Hacienda",
        company_dependent=True,
        default=False,
        help="Envía la factura al cliente automáticamente cuando Hacienda responde Aceptado.",
    )
    fp_consecutive_fe = fields.Char(
        string="Consecutivo FE (01)",
        company_dependent=True,
        default="1",
        help="Último consecutivo utilizado para Factura Electrónica (tipo 01).",
    )
    fp_consecutive_te = fields.Char(
        string="Consecutivo TE (04)",
        company_dependent=True,
        default="1",
        help="Último consecutivo utilizado para Tiquete Electrónico (tipo 04).",
    )
    fp_consecutive_fec = fields.Char(
        string="Consecutivo FEC (08)",
        company_dependent=True,
        default="1",
        help="Último consecutivo utilizado para Factura Electrónica de Compra (tipo 08).",
    )
    fp_consecutive_nc = fields.Char(
        string="Consecutivo NC (03)",
        company_dependent=True,
        default="1",
        help="Último consecutivo utilizado para Nota de Crédito Electrónica (tipo 03).",
    )
    fp_consecutive_nd = fields.Char(
        string="Consecutivo ND (02)",
        company_dependent=True,
        default="1",
        help="Último consecutivo utilizado para Nota de Débito Electrónica (tipo 02).",
    )
    fp_consecutive_others = fields.Char(
        string="Consecutivo otros comprobantes",
        company_dependent=True,
        help="Último consecutivo utilizado para otros comprobantes electrónicos según Hacienda 4.4.",
    )

    fp_certificate_subject = fields.Char(
        string="Organización (Asunto)",
        compute="_compute_fp_certificate_info",
    )
    fp_certificate_serial_subject = fields.Char(
        string="Número de Serie (Sujeto)",
        compute="_compute_fp_certificate_info",
    )
    fp_certificate_issue_date = fields.Date(
        string="Fecha emisión",
        compute="_compute_fp_certificate_info",
    )
    fp_certificate_expiration_date = fields.Date(
        string="Fecha expiración",
        compute="_compute_fp_certificate_info",
    )
    fp_certificate_issuer = fields.Char(
        string="Organización (Emisor)",
        compute="_compute_fp_certificate_info",
    )
    fp_certificate_serial_number = fields.Char(
        string="Número de Serie (Certificado)",
        compute="_compute_fp_certificate_info",
    )
    fp_certificate_version = fields.Char(
        string="Versión",
        compute="_compute_fp_certificate_info",
    )


    @api.constrains("fp_hacienda_token_url")
    def _check_fp_hacienda_token_url(self):
        for company in self:
            token_url = (company.fp_hacienda_token_url or "").strip()
            if token_url and "openid-connect/token" not in token_url:
                raise ValidationError(
                    "La URL OAuth de Hacienda debe apuntar al endpoint '/protocol/openid-connect/token'."
                )

    def action_fp_refresh_certificate_info(self):
        for company in self:
            company._compute_fp_certificate_info()

    def _extract_name_attribute(self, x509_name, key):
        attrs = [attr.value for attr in x509_name if attr.oid._name == key]
        return ", ".join(attrs) if attrs else ""

    @api.depends("fp_signing_certificate_file", "fp_signing_certificate_password")
    def _compute_fp_certificate_info(self):
        for company in self:
            company.fp_certificate_subject = False
            company.fp_certificate_serial_subject = False
            company.fp_certificate_issue_date = False
            company.fp_certificate_expiration_date = False
            company.fp_certificate_issuer = False
            company.fp_certificate_serial_number = False
            company.fp_certificate_version = False

            cert_file = company.fp_signing_certificate_file
            if not cert_file:
                continue

            try:
                cert_bytes = base64.b64decode(cert_file, validate=True)
            except (binascii.Error, ValueError):
                # Cuando Odoo evalúa con contexto bin_size=True, los binarios pueden venir
                # como una etiqueta de tamaño (ej: "2.5kb") en lugar del contenido base64.
                cert_file = company.with_context(bin_size=False).read(["fp_signing_certificate_file"])[0].get(
                    "fp_signing_certificate_file"
                )
                if not cert_file:
                    continue
                try:
                    cert_bytes = base64.b64decode(cert_file, validate=True)
                except (binascii.Error, ValueError):
                    continue

            password = (company.fp_signing_certificate_password or "").encode("utf-8") or None
            try:
                _private_key, certificate, _additional_certs = pkcs12.load_key_and_certificates(cert_bytes, password)
            except Exception:
                continue

            if not certificate:
                continue

            company.fp_certificate_subject = company._extract_name_attribute(certificate.subject, "organizationName") or str(certificate.subject.rfc4514_string())
            company.fp_certificate_serial_subject = company._extract_name_attribute(certificate.subject, "serialNumber")
            company.fp_certificate_issue_date = certificate.not_valid_before_utc.date()
            company.fp_certificate_expiration_date = certificate.not_valid_after_utc.date()
            company.fp_certificate_issuer = company._extract_name_attribute(certificate.issuer, "commonName") or str(certificate.issuer.rfc4514_string())
            company.fp_certificate_serial_number = str(certificate.serial_number)
            company.fp_certificate_version = f"Version.v{certificate.version.value}"
