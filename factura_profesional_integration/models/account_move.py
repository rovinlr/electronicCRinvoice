import base64
import json

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

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

    def action_fp_send_to_api(self):
        for move in self:
            if move.move_type not in ("out_invoice", "out_refund"):
                raise UserError(_("Solo se permite facturación de cliente o nota de crédito."))
            if move.state != "posted":
                raise UserError(_("La factura debe estar publicada antes de enviarse al API."))
            move._fp_send_and_store_xml()

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
        )

        xml_string = response_data.get("xml")
        if not xml_string:
            self.fp_api_state = "error"
            raise UserError(_("El API no devolvió el campo 'xml'."))

        self._fp_create_xml_attachment(xml_string)
        self.fp_external_id = response_data.get("id")
        self.fp_api_state = "done"
        self.message_post(body=_("Factura enviada a Factura API y XML almacenado."))

    def _fp_build_payload(self):
        self.ensure_one()
        lines = []
        for line in self.invoice_line_ids.filtered(lambda l: not l.display_type):
            lines.append(
                {
                    "description": line.name,
                    "qty": line.quantity,
                    "unit_price": line.price_unit,
                    "discount": line.discount,
                    "taxes": [tax.amount for tax in line.tax_ids],
                    "subtotal": line.price_subtotal,
                    "total": line.price_total,
                }
            )

        return {
            "number": self.name,
            "date": str(self.invoice_date),
            "currency": self.currency_id.name,
            "customer": {
                "name": self.partner_id.name,
                "vat": self.partner_id.vat,
                "email": self.partner_id.email,
            },
            "lines": lines,
            "totals": {
                "untaxed": self.amount_untaxed,
                "tax": self.amount_tax,
                "total": self.amount_total,
            },
        }

    def _fp_call_api(self, endpoint, payload, timeout, token, base_url):
        url = f"{base_url.rstrip('/')}{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers=headers,
            timeout=timeout,
        )
        if response.status_code >= 400:
            self.fp_api_state = "error"
            raise UserError(_("Error API (%s): %s") % (response.status_code, response.text))
        return response.json()

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
