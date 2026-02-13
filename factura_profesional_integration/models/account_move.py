import base64
import json

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
    fp_external_id = fields.Char(string="Factura API ID", copy=False)
    fp_xml_attachment_id = fields.Many2one("ir.attachment", string="Factura XML", copy=False)
    fp_api_state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("sent", "Enviado"),
            ("done", "XML recibido"),
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
                raise UserError(_("La factura debe estar publicada antes de enviarse al API."))
            move._fp_send_and_store_xml()

    def action_fp_consult_api_document(self):
        for move in self:
            if not move.fp_external_id:
                raise UserError(_("La factura no tiene ID externo para consultar estado."))
            response_data = move._fp_call_api(
                endpoint=f"/documents/{move.fp_external_id}",
                payload=None,
                timeout=move.company_id.fp_api_timeout,
                token=move.company_id.fp_api_token,
                base_url=move.company_id.fp_api_base_url,
                method="GET",
            )
            status = (response_data.get("status") or "").lower()
            if status in ("accepted", "aceptada"):
                move.fp_invoice_status = "accepted"
            elif status in ("rejected", "rechazada"):
                move.fp_invoice_status = "rejected"
            elif status:
                move.fp_invoice_status = "sent"

    def _fp_send_and_store_xml(self):
        self.ensure_one()
        company = self.company_id
        if not company.fp_api_base_url or not company.fp_api_token:
            raise UserError(_("Configure URL y token en Ajustes > Contabilidad."))

        payload = self._fp_build_payload()
        self.fp_api_state = "sent"

        response_data = self._fp_call_api(
            endpoint="/documents",
            payload=payload,
            timeout=company.fp_api_timeout,
            token=company.fp_api_token,
            base_url=company.fp_api_base_url,
            method="POST",
        )

        xml_string = response_data.get("xml")
        if not xml_string:
            self.fp_api_state = "error"
            raise UserError(_("El API no devolvió el campo 'xml'."))

        self._fp_create_xml_attachment(xml_string)
        self.fp_external_id = response_data.get("id")
        self.fp_api_state = "done"
        self.fp_invoice_status = "sent"
        self.message_post(body=_("Factura enviada a Factura API y XML almacenado."))

    def _fp_build_payload(self):
        self.ensure_one()
        lines = []
        for line in self.invoice_line_ids.filtered(lambda l: not l.display_type):
            taxes_data = line.tax_ids.compute_all(
                price_unit=line.price_unit * (1 - (line.discount or 0.0) / 100.0),
                quantity=line.quantity,
                currency=self.currency_id,
                product=line.product_id,
                partner=self.partner_id,
            )
            tax_amount_by_id = {tax_line.get("id"): tax_line.get("amount") for tax_line in taxes_data.get("taxes", [])}
            line_taxes = []
            for tax in line.tax_ids:
                line_taxes.append(
                    {
                        "name": tax.name,
                        "type": tax.fp_tax_type,
                        "code": tax.fp_tax_code,
                        "rate": tax.fp_tax_rate or tax.amount,
                        "amount": tax_amount_by_id.get(tax.id, 0.0),
                    }
                )

            lines.append(
                {
                    "description": line.name,
                    "cabys": line.product_id.product_tmpl_id.fp_cabys_code,
                    "qty": line.quantity,
                    "unit": line.product_uom_id.fp_unit_code,
                    "unit_price": line.price_unit,
                    "discount": line.discount,
                    "taxes": line_taxes,
                    "subtotal": line.price_subtotal,
                    "total": line.price_total,
                }
            )

        return {
            "number": self.name,
            "date": str(self.invoice_date),
            "currency": self.currency_id.name,
            "document_type": self.fp_document_type,
            "economic_activity_code": self.fp_economic_activity_code or self.company_id.fp_economic_activity_code,
            "customer": {
                "name": self.partner_id.name,
                "vat": self.partner_id.vat,
                "identification_type": self.partner_id.fp_identification_type,
                "email": self.partner_id.email,
            },
            "lines": lines,
            "totals": {
                "untaxed": self.amount_untaxed,
                "tax": self.amount_tax,
                "total": self.amount_total,
            },
        }

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
            raise UserError(_("Error API (%s): %s") % (response.status_code, response.text))
        return response.json()

    def _fp_build_authorization_header(self, token):
        token = (token or "").strip()
        lower_token = token.lower()
        known_schemes = ("bearer ", "basic ", "token ", "apikey ", "aws4-hmac-sha256 ", "digest ")
        if lower_token.startswith(known_schemes):
            return token
        if any(symbol in token for symbol in ("=", ",")):
            return token
        return f"Bearer {token}"

    def _fp_create_xml_attachment(self, xml_string):
        self.ensure_one()
        xml_data = base64.b64encode(xml_string.encode("utf-8"))
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"{self.name}.xml",
                "type": "binary",
                "datas": xml_data,
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/xml",
            }
        )
        self.fp_xml_attachment_id = attachment
