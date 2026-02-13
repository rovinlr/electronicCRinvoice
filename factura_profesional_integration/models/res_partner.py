import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


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
    fp_canton_code = fields.Char(
        string="Cantón (FE)",
        size=2,
        help="Código de cantón según Anexos y Estructuras v4.4 (2 dígitos).",
    )
    fp_district_code = fields.Char(
        string="Distrito (FE)",
        size=2,
        help="Código de distrito según Anexos y Estructuras v4.4 (2 dígitos).",
    )
    fp_neighborhood_code = fields.Char(
        string="Barrio (FE)",
        size=2,
        help="Código de barrio según Anexos y Estructuras v4.4 (2 dígitos).",
    )

    def action_fp_fetch_hacienda_data(self):
        for partner in self:
            if not partner.vat:
                raise UserError(_("Debe indicar la cédula (VAT) para consultar Hacienda."))
            vat = "".join(ch for ch in partner.vat if ch.isdigit())
            endpoints = [
                f"https://api.hacienda.go.cr/fe/ae?identificacion={vat}",
                f"https://api.hacienda.go.cr/fe/cep?identificacion={vat}",
            ]
            data = None
            for endpoint in endpoints:
                response = requests.get(endpoint, timeout=15)
                if response.status_code < 400:
                    payload = response.json()
                    if payload:
                        data = payload
                        break
            if not data:
                raise UserError(_("No se encontraron datos en Hacienda para la identificación %s.") % partner.vat)

            partner.name = data.get("nombre") or data.get("nomre") or partner.name
            email = data.get("correo_electronico") or data.get("email")
            if email:
                partner.email = email
