import json
from datetime import datetime

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    fp_is_electronic_invoice = fields.Boolean(
        related="journal_id.fp_is_electronic_invoice",
        string="Factura electrónica",
        store=True,
        readonly=True,
    )
    fp_document_type = fields.Selection(
        [
            ("FE", "Factura Electrónica"),
            ("NC", "Nota de Crédito Electrónica"),
            ("ND", "Nota de Débito Electrónica"),
            ("TE", "Tiquete Electrónico"),
        ],
        string="Tipo de documento (FE)",
        default="FE",
    )
    fp_economic_activity_code = fields.Char(
        string="Actividad económica (FE)",
        help="Código de actividad económica para facturación electrónica.",
    )
    fp_external_id = fields.Char(string="Clave Hacienda", copy=False)
    fp_xml_attachment_id = fields.Many2one("ir.attachment", string="Factura XML", copy=False)
    fp_api_state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("sent", "Enviado"),
            ("done", "Procesado"),
            ("error", "Error"),
        ],
        default="pending",
        copy=False,
    )
    fp_invoice_status = fields.Selection(
        [
            ("sent", "Enviada"),
            ("accepted", "Aceptada"),
            ("rejected", "Rechazada"),
        ],
        string="Estado FE",
        copy=False,
    )

    def action_fp_send_to_api(self):
        for move in self:
            if not move.fp_is_electronic_invoice:
                raise UserError(_("El diario no está marcado como factura electrónica."))
            if move.move_type not in ("out_invoice", "out_refund"):
                raise UserError(_("Solo se permite facturación de cliente o nota de crédito."))
            if move.state != "posted":
                raise UserError(_("La factura debe estar publicada antes de enviarse a Hacienda."))
            move._fp_send_to_hacienda()

    def action_fp_consult_api_document(self):
        for move in self:
            if not move.fp_external_id:
                raise UserError(_("La factura no tiene Clave para consultar estado en Hacienda."))

            token = move._fp_get_hacienda_access_token()
            response_data = move._fp_call_api(
                endpoint=f"/recepcion/v1/recepcion/{move.fp_external_id}",
                payload=None,
                timeout=move.company_id.fp_api_timeout,
                token=token,
                base_url=move.company_id.fp_hacienda_api_base_url,
                method="GET",
            )
            status = (response_data.get("ind-estado") or "").lower()
            if status == "aceptado":
                move.fp_invoice_status = "accepted"
                move.fp_api_state = "done"
            elif status in ("rechazado", "error"):
                move.fp_invoice_status = "rejected"
                move.fp_api_state = "error"
            elif status:
                move.fp_invoice_status = "sent"

    def _fp_send_to_hacienda(self):
        self.ensure_one()
        company = self.company_id
        if not company.fp_hacienda_api_base_url or not company.fp_hacienda_token_url:
            raise UserError(_("Configure URLs de Hacienda en Ajustes > Contabilidad."))

        payload = self._fp_build_hacienda_payload()
        token = self._fp_get_hacienda_access_token()
        self.fp_api_state = "sent"

        self._fp_call_api(
            endpoint="/recepcion/v1/recepcion",
            payload=payload,
            timeout=company.fp_api_timeout,
            token=token,
            base_url=company.fp_hacienda_api_base_url,
            method="POST",
        )

        self.fp_external_id = payload["clave"]
        self.fp_invoice_status = "sent"
        self.message_post(body=_("Factura enviada directamente a Hacienda (Recepción v4.4)."))

    def _fp_get_hacienda_access_token(self):
        self.ensure_one()
        company = self.company_id
        if not company.fp_hacienda_username or not company.fp_hacienda_password:
            raise UserError(_("Configure usuario y contraseña de Hacienda en Ajustes > Contabilidad."))

        data = {
            "grant_type": "password",
            "client_id": company.fp_hacienda_client_id or "api-prod",
            "username": company.fp_hacienda_username,
            "password": company.fp_hacienda_password,
        }
        response = requests.post(
            company.fp_hacienda_token_url,
            data=data,
            timeout=company.fp_api_timeout,
        )
        if response.status_code >= 400:
            raise UserError(_("Error autenticando contra Hacienda (%s): %s") % (response.status_code, response.text))

        access_token = response.json().get("access_token")
        if not access_token:
            raise UserError(_("Hacienda no devolvió access_token."))
        return access_token

    def _fp_build_hacienda_payload(self):
        self.ensure_one()
        if not self.fp_xml_attachment_id or not self.fp_xml_attachment_id.datas:
            raise UserError(
                _("Debe adjuntar primero el XML firmado en la factura (campo Factura XML) para enviarlo a Hacienda.")
            )

        clave = self._fp_build_clave()
        consecutivo = clave[21:41] if len(clave) >= 41 else clave[-20:]
        partner_vat = "".join(ch for ch in (self.partner_id.vat or "") if ch.isdigit())

        payload = {
            "clave": clave,
            "fecha": datetime.now().astimezone().isoformat(),
            "emisor": {
                "tipoIdentificacion": self.company_id.partner_id.fp_identification_type or "02",
                "numeroIdentificacion": "".join(ch for ch in (self.company_id.vat or "") if ch.isdigit()),
            },
            "comprobanteXml": self.fp_xml_attachment_id.datas.decode("utf-8"),
            "consecutivoReceptor": consecutivo,
        }
        if partner_vat and self.partner_id.fp_identification_type:
            payload["receptor"] = {
                "tipoIdentificacion": self.partner_id.fp_identification_type,
                "numeroIdentificacion": partner_vat,
            }
        return payload

    def _fp_build_clave(self):
        self.ensure_one()
        if self.fp_external_id:
            return self.fp_external_id
        if self.ref and len(self.ref) >= 50:
            return self.ref[:50]
        seed = "".join(ch for ch in (self.name or "") if ch.isdigit())
        seed = (seed or str(self.id)).zfill(50)
        return seed[-50:]

    def _fp_call_api(self, endpoint, payload, timeout, token, base_url, method="POST"):
        url = f"{base_url.rstrip('/')}{endpoint}"
        headers = {
            "Authorization": self._fp_build_authorization_header(token),
            "Content-Type": "application/json",
        }
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=timeout)
        else:
            response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=timeout)
        if response.status_code >= 400:
            self.fp_api_state = "error"
            raise UserError(_("Error API Hacienda (%s): %s") % (response.status_code, response.text))
        if not response.text:
            return {}
        return response.json()

    def _fp_build_authorization_header(self, token):
        token = (token or "").strip()
        if token.lower().startswith("bearer "):
            return token
        return f"Bearer {token}"
