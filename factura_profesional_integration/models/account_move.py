import base64
import hashlib
import json
import random
import uuid
from datetime import datetime
from json import JSONDecodeError
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree as LET

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError



XML_DOCUMENT_SPECS = {
    "FE": {
        "root": "FacturaElectronica",
        "namespace": "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica",
        "xsd": "facturaElectronica.xsd",
    },
    "NC": {
        "root": "NotaCreditoElectronica",
        "namespace": "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/notaCreditoElectronica",
        "xsd": "notaCreditoElectronica.xsd",
    },
    "ND": {
        "root": "NotaDebitoElectronica",
        "namespace": "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/notaDebitoElectronica",
        "xsd": "notaDebitoElectronica.xsd",
    },
    "FEE": {
        "root": "FacturaElectronicaExportacion",
        "namespace": "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronicaExportacion",
        "xsd": "facturaElectronicaExportacion.xsd",
    },
}
DS_XML_NS = "http://www.w3.org/2000/09/xmldsig#"
XADES_XML_NS = "http://uri.etsi.org/01903/v1.3.2#"
XADES_SIGNATURE_POLICY_IDENTIFIER = (
    "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/"
    "Resoluci%C3%B3n_General_sobre_disposiciones_t%C3%A9cnicas_comprobantes_electr%C3%B3nicos_para_efectos_tributarios.pdf"
)
XADES_SIGNATURE_POLICY_DESCRIPTION = "Política de firma para comprobantes electrónicos de Costa Rica"
XADES_SIGNATURE_POLICY_HASH_ALGORITHM = "http://www.w3.org/2001/04/xmlenc#sha256"
XADES_SIGNATURE_POLICY_HASH = "DWxin1xWOeI8OuWQXazh4VjLWAaCLAA954em7DMh0h8="

class AccountMove(models.Model):
    _inherit = "account.move"

    _FP_LOCKED_FIELDS_AFTER_SEND = {
        "fp_document_type",
        "fp_economic_activity_id",
        "fp_sale_condition",
        "fp_payment_method",
    }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("move_type") == "out_refund" and not vals.get("fp_document_type"):
                vals["fp_document_type"] = "NC"
        return super().create(vals_list)

    def write(self, vals):
        protected_fields = self._FP_LOCKED_FIELDS_AFTER_SEND.intersection(vals)
        if protected_fields:
            locked_moves = self.filtered(lambda move: move.fp_is_electronic_invoice and move.fp_api_state != "pending")
            if locked_moves:
                raise UserError(
                    _(
                        "No se permite editar Tipo de documento, Actividad económica, "
                        "Condición de venta o Medio de pago después de enviar a Hacienda."
                    )
                )
        return super().write(vals)

    @api.onchange("move_type")
    def _onchange_fp_document_type_from_move_type(self):
        for move in self:
            if move.move_type == "out_refund" and move.fp_is_electronic_invoice:
                move.fp_document_type = "NC"
            elif move.move_type == "out_invoice" and move.fp_document_type not in ("FE", "TE", "FEE"):
                move.fp_document_type = "FE"

    @api.constrains("move_type", "fp_document_type", "fp_is_electronic_invoice")
    def _check_fp_document_type_by_move_type(self):
        for move in self:
            if not move.fp_is_electronic_invoice:
                continue
            if move.move_type == "out_invoice" and move.fp_document_type not in ("FE", "TE", "FEE"):
                raise ValidationError(
                    _("Para facturas de cliente solo se permite FE, TE o Factura Electrónica de Exportación.")
                )
            if move.move_type == "out_refund" and move.fp_document_type != "NC":
                raise ValidationError(
                    _("Para rectificativas solo se permite Nota de Crédito Electrónica (NC).")
                )

    @api.onchange("reversed_entry_id", "fp_document_type")
    def _onchange_fp_reference_defaults(self):
        for move in self:
            move._fp_populate_reference_from_reversed_entry(force=False)


    def action_post(self):
        moves = super().action_post()
        electronic_moves = self.filtered(
            lambda move: move.fp_is_electronic_invoice
            and move.move_type in ("out_invoice", "out_refund")
            and move.state == "posted"
            and not move.fp_xml_attachment_id
        )
        for move in electronic_moves:
            move._fp_generate_and_sign_xml_attachment()
        return moves

    def _reverse_moves(self, default_values_list=None, cancel=False):
        reversed_moves = super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
        electronic_refunds = reversed_moves.filtered(
            lambda move: move.fp_is_electronic_invoice
            and move.move_type == "out_refund"
            and move.fp_document_type != "NC"
        )
        if electronic_refunds:
            electronic_refunds.write({"fp_document_type": "NC"})
        reversed_moves._fp_populate_reference_from_reversed_entry(force=True)
        return reversed_moves

    @api.model
    def _default_fp_economic_activity_id(self):
        """Safely resolve company default even during module bootstrap.

        During install/upgrade, ``account.move`` may be initialized before the
        ``res_company.fp_economic_activity_id`` column exists in the database.
        Accessing ``env.company.fp_economic_activity_id`` too early raises a
        database error and aborts module loading.
        """
        self.env.cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'res_company'
               AND column_name = 'fp_economic_activity_id'
            """
        )
        if not self.env.cr.fetchone():
            return False
        return self.env.company.fp_economic_activity_id

    fp_is_electronic_invoice = fields.Boolean(
        related="journal_id.fp_is_electronic_invoice",
        string="Factura electrónica",
        store=True,
        readonly=True,
    )
    fp_document_type = fields.Selection(
        [
            ("FE", "Factura Electrónica"),
            ("FEE", "Factura Electrónica de Exportación"),
            ("NC", "Nota de Crédito Electrónica"),
            ("TE", "Tiquete Electrónico"),
        ],
        string="Tipo de documento (FE)",
        default="FE",
    )
    fp_economic_activity_id = fields.Many2one(
        "fp.economic.activity",
        string="Actividad económica (FE)",
        default=_default_fp_economic_activity_id,
        help="Código de actividad económica para facturación electrónica.",
    )
    fp_economic_activity_code = fields.Char(
        related="fp_economic_activity_id.code",
        string="Código actividad económica (FE)",
        store=True,
        readonly=True,
    )
    fp_sale_condition = fields.Selection(
        [
            ("01", "01 - Contado"),
            ("02", "02 - Crédito"),
            ("03", "03 - Consignación"),
            ("04", "04 - Apartado"),
            ("05", "05 - Arrendamiento con opción de compra"),
            ("06", "06 - Arrendamiento en función financiera"),
            ("07", "07 - Cobro a favor de un tercero"),
            ("08", "08 - Servicios prestados al Estado"),
            ("09", "09 - Pago de servicios prestados al Estado"),
            ("10", "10 - Venta a crédito en IVA hasta 90 días"),
            ("11", "11 - Pago de venta a crédito en IVA hasta 90 días"),
            ("12", "12 - Venta mercancía no nacionalizada"),
            ("13", "13 - Venta bienes usados no contribuyente"),
            ("14", "14 - Arrendamiento operativo"),
            ("15", "15 - Arrendamiento financiero"),
            ("99", "99 - Otros"),
        ],
        string="Condición de venta (FE)",
        default="01",
        help="Condición de venta según nota 5 de Anexos y Estructuras v4.4.",
    )
    fp_payment_method = fields.Selection(
        [
            ("01", "01 - Efectivo"),
            ("02", "02 - Tarjeta"),
            ("03", "03 - Cheque"),
            ("04", "04 - Transferencia / depósito bancario"),
            ("05", "05 - Recaudado por terceros"),
            ("06", "06 - SINPE Móvil"),
            ("07", "07 - Plataforma Digital"),
            ("99", "99 - Otros"),
        ],
        string="Medio de pago (FE)",
        default="01",
        help="Medio de pago según nota 6 de Anexos y Estructuras v4.4.",
    )
    fp_reference_document_type = fields.Selection(
        [
            ("01", "01 - Factura Electrónica"),
            ("02", "02 - Nota de Débito Electrónica"),
            ("03", "03 - Nota de Crédito Electrónica"),
            ("04", "04 - Tiquete Electrónico"),
            ("05", "05 - Nota de Despacho"),
            ("06", "06 - Contrato"),
            ("07", "07 - Procedimiento"),
            ("08", "08 - Comprobante emitido en contingencia"),
            ("99", "99 - Otros"),
        ],
        string="Tipo de documento de referencia (FE)",
        help="Código de TipoDocIR para notas electrónicas en v4.4.",
        copy=False,
    )
    fp_reference_number = fields.Char(
        string="Clave numérica de referencia (FE)",
        help="Número o clave del documento que se referencia.",
        copy=False,
    )
    fp_reference_issue_datetime = fields.Datetime(
        string="Fecha emisión documento de referencia (FE)",
        help="Fecha y hora del documento de referencia (FechaEmisionIR).",
        copy=False,
    )
    fp_reference_code = fields.Selection(
        [
            ("01", "01 - Anula documento de referencia"),
            ("02", "02 - Corrige texto del documento de referencia"),
            ("03", "03 - Corrige monto"),
            ("04", "04 - Referencia a otro documento"),
            ("05", "05 - Sustituye comprobante provisional por contingencia"),
            ("99", "99 - Otros"),
        ],
        string="Código de referencia (FE)",
        default="01",
        help="Código del motivo de referencia según Anexos y Estructuras v4.4.",
        copy=False,
    )
    fp_reference_reason = fields.Char(
        string="Razón de referencia (FE)",
        help="Detalle del motivo de referencia (Razon).",
        copy=False,
    )
    fp_external_id = fields.Char(string="Clave Hacienda", copy=False)
    fp_consecutive_number = fields.Char(string="Consecutivo Hacienda", copy=False, readonly=True)
    fp_xml_attachment_id = fields.Many2one("ir.attachment", string="Factura XML", copy=False)
    fp_xml_signed_digest = fields.Char(string="Digest XML firmado", copy=False, readonly=True)
    fp_response_xml_attachment_id = fields.Many2one("ir.attachment", string="XML Respuesta Hacienda", copy=False)
    fp_xml_attachment_name = fields.Char(related="fp_xml_attachment_id.name", string="Nombre XML Factura", readonly=True)
    fp_response_xml_attachment_name = fields.Char(
        related="fp_response_xml_attachment_id.name",
        string="Nombre XML Respuesta Hacienda",
        readonly=True,
    )
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
            if move.fp_api_state != "pending":
                raise UserError(_("La factura ya fue enviada a Hacienda y no puede reenviarse desde este botón."))
            if move.move_type not in ("out_invoice", "out_refund"):
                raise UserError(_("Solo se permite facturación de cliente o nota de crédito."))
            if move.state != "posted":
                raise UserError(_("La factura debe estar publicada antes de enviarse a Hacienda."))
            move._fp_send_to_hacienda()

    def action_fp_consult_api_document(self):
        for move in self:
            if not move.fp_external_id:
                raise UserError(_("La factura no tiene Clave para consultar estado en Hacienda."))
            if move.fp_api_state in ("done", "error"):
                raise UserError(_("La factura ya recibió una respuesta final de Hacienda."))

            token = move._fp_get_hacienda_access_token()
            response_data = move._fp_call_api(
                endpoint=move._fp_get_hacienda_recepcion_endpoint(clave=move.fp_external_id),
                payload=None,
                timeout=move.company_id.fp_api_timeout,
                token=token,
                base_url=move.company_id.fp_hacienda_api_base_url,
                method="GET",
                params={"emisor": "".join(ch for ch in (move.company_id.vat or "") if ch.isdigit())},
            )
            move._fp_store_hacienda_response_xml(response_data)
            status = (response_data.get("ind-estado") or "").lower()
            if status == "aceptado":
                move.fp_invoice_status = "accepted"
                move.fp_api_state = "done"
            elif status in ("rechazado", "error"):
                move.fp_invoice_status = "rejected"
                move.fp_api_state = "error"
            elif status:
                move.fp_invoice_status = "sent"

    def action_fp_open_hacienda_documents(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "factura_profesional_integration.action_fp_electronic_documents"
        )
        domain = [
            ("fp_is_electronic_invoice", "=", True),
            ("move_type", "in", ["out_invoice", "out_refund"]),
        ]
        if self.fp_consecutive_number:
            domain.append(("fp_consecutive_number", "=", self.fp_consecutive_number))
            action["name"] = _("Hacienda: %s") % self.fp_consecutive_number
            action["res_id"] = self.id
            action["views"] = [
                (self.env.ref("factura_profesional_integration.view_move_form_fp_documents").id, "form"),
                (self.env.ref("factura_profesional_integration.view_move_tree_fp_documents").id, "list"),
            ]

        action["domain"] = domain
        action["context"] = {
            **self.env.context,
            "search_default_posted": 1,
            "search_default_fp_documents": 1,
        }
        return action

    def _fp_send_to_hacienda(self):
        self.ensure_one()
        company = self.company_id
        if not company.fp_hacienda_api_base_url or not company.fp_hacienda_token_url:
            raise UserError(_("Configure URLs de Hacienda en Ajustes > Contabilidad."))

        if not self.fp_xml_attachment_id:
            self._fp_generate_and_sign_xml_attachment()

        self._fp_ensure_signed_xml_integrity()
        payload = self._fp_build_hacienda_payload()
        token = self._fp_get_hacienda_access_token()
        self.fp_api_state = "sent"

        self._fp_call_api(
            endpoint=self._fp_get_hacienda_recepcion_endpoint(),
            payload=payload,
            timeout=company.fp_api_timeout,
            token=token,
            base_url=company.fp_hacienda_api_base_url,
            method="POST",
        )

        self.fp_external_id = payload["clave"]
        self.fp_invoice_status = "sent"
        self.message_post(body=_("Factura enviada directamente a Hacienda (Recepción v4.4)."))
        if company.fp_auto_consult_after_send:
            self.action_fp_consult_api_document()

    def _fp_get_hacienda_access_token(self):
        self.ensure_one()
        company = self.company_id
        if not company.fp_hacienda_username or not company.fp_hacienda_password:
            raise UserError(_("Configure usuario y contraseña de Hacienda en Ajustes > Contabilidad."))
        token_url = (company.fp_hacienda_token_url or "").strip()
        parsed_token_url = urlparse(token_url)
        if "openid-connect/token" not in (parsed_token_url.path or ""):
            raise UserError(
                _(
                    "La URL OAuth de Hacienda es inválida. Debe apuntar al endpoint de token "
                    "y terminar en '/protocol/openid-connect/token'."
                )
            )

        data = {
            "grant_type": "password",
            "client_id": company.fp_hacienda_client_id or self._fp_get_hacienda_client_id_default(),
            "username": company.fp_hacienda_username,
            "password": company.fp_hacienda_password,
        }
        response = requests.post(
            token_url,
            data=data,
            timeout=company.fp_api_timeout,
        )
        if response.status_code >= 400:
            raise UserError(_("Error autenticando contra Hacienda (%s): %s") % (response.status_code, response.text))

        response_data = self._fp_parse_json_response(response, response_context="autenticación")
        access_token = response_data.get("access_token")
        if not access_token:
            raise UserError(_("Hacienda no devolvió access_token."))
        return access_token

    def _fp_get_hacienda_environment(self):
        self.ensure_one()
        company = self.company_id
        configured_environment = company.fp_hacienda_environment or "auto"
        if configured_environment in ("prod", "sandbox"):
            return configured_environment

        token_url = (company.fp_hacienda_token_url or "").lower()
        base_url = (company.fp_hacienda_api_base_url or "").lower()
        if any(flag in token_url or flag in base_url for flag in ("rut-stag", "sandbox", "stag")):
            return "sandbox"
        return "prod"

    def _fp_get_hacienda_client_id_default(self):
        self.ensure_one()
        if self._fp_get_hacienda_environment() == "sandbox":
            return "api-stag"
        return "api-prod"

    def _fp_get_hacienda_recepcion_endpoint(self, clave=None):
        self.ensure_one()
        base_path = (urlparse(self.company_id.fp_hacienda_api_base_url or "").path or "").rstrip("/")

        # Hacienda (incluyendo sandbox actual) publica la recepción bajo /recepcion/v1.
        # Si la URL configurada ya incluye parte de esa ruta, agregamos solo el segmento faltante.
        if base_path.endswith("/recepcion/v1") or base_path.endswith("/recepcion-sandbox/v1"):
            endpoint = "/recepcion"
        elif base_path.endswith("/recepcion/v1/recepcion") or base_path.endswith("/recepcion-sandbox/v1/recepcion"):
            endpoint = ""
        else:
            endpoint = "/recepcion/v1/recepcion"

        if clave:
            return f"{endpoint}/{clave}" if endpoint else f"/{clave}"
        return endpoint or "/"

    def _fp_build_hacienda_payload(self):
        self.ensure_one()
        if not self.fp_xml_attachment_id or not self.fp_xml_attachment_id.datas:
            self._fp_generate_and_sign_xml_attachment()

        signed_xml_b64 = self._fp_get_signed_xml_payload_base64()
        clave = self._fp_build_clave()
        partner_vat = "".join(ch for ch in (self.partner_id.vat or "") if ch.isdigit())

        payload = {
            "clave": clave,
            "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
            "emisor": {
                "tipoIdentificacion": self.company_id.partner_id.fp_identification_type or "02",
                "numeroIdentificacion": "".join(ch for ch in (self.company_id.vat or "") if ch.isdigit()),
            },
            "comprobanteXml": signed_xml_b64,
        }
        if partner_vat and self.partner_id.fp_identification_type:
            payload["receptor"] = {
                "tipoIdentificacion": self.partner_id.fp_identification_type,
                "numeroIdentificacion": partner_vat,
            }
        return payload

    def _fp_generate_and_sign_xml_attachment(self):
        self.ensure_one()
        clave = self._fp_build_clave()
        xml_text = self._fp_generate_invoice_xml(clave=clave)
        signed_xml_text = self._fp_sign_xml(xml_text)
        signed_xml_bytes = signed_xml_text.encode("utf-8")
        signed_xml_b64 = base64.b64encode(signed_xml_bytes)
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"{self.name or 'factura'}-firmado.xml",
                "type": "binary",
                "datas": signed_xml_b64,
                "res_model": "account.move",
                "res_id": self.id,
                "mimetype": "application/xml",
            }
        )
        self.fp_xml_attachment_id = attachment
        self.fp_xml_signed_digest = hashlib.sha256(signed_xml_bytes).hexdigest()

    def _fp_ensure_signed_xml_integrity(self):
        self.ensure_one()
        attachment = self.fp_xml_attachment_id
        if not attachment or not attachment.datas:
            raise UserError(_("La factura no tiene XML firmado adjunto."))

        xml_bytes = base64.b64decode(attachment.datas)
        current_digest = hashlib.sha256(xml_bytes).hexdigest()
        if self.fp_xml_signed_digest and current_digest != self.fp_xml_signed_digest:
            raise UserError(
                _(
                    "El XML firmado fue alterado luego de la firma digital. "
                    "Genere y firme nuevamente antes de enviar a Hacienda."
                )
            )

        if not self.fp_xml_signed_digest:
            # Backward compatibility for documents signed before this guard existed.
            self.fp_xml_signed_digest = current_digest

        return xml_bytes

    def _fp_get_signed_xml_payload_base64(self):
        self.ensure_one()
        xml_bytes = self._fp_ensure_signed_xml_integrity()
        return base64.b64encode(xml_bytes).decode("utf-8")

    def _fp_get_xml_document_spec(self):
        self.ensure_one()
        if self.fp_document_type == "TE":
            raise UserError(
                _(
                    "El Tiquete Electrónico (TE) requiere una estructura XML específica de v4.4. "
                    "Configure FE/NC/ND o implemente el generador TE antes de enviar a Hacienda."
                )
            )
        spec = XML_DOCUMENT_SPECS.get(self.fp_document_type)
        if not spec:
            raise UserError(_("Tipo de documento FE no soportado: %s") % (self.fp_document_type or ""))
        return spec

    def _fp_generate_invoice_xml(self, clave=None):
        self.ensure_one()
        clave = clave or self._fp_build_clave()
        document_spec = self._fp_get_xml_document_spec()
        namespace = document_spec["namespace"]
        root = ET.Element(
            document_spec["root"],
            {
                "xmlns": namespace,
                "xmlns:ds": DS_XML_NS,
                "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "xsi:schemaLocation": f"{namespace} {namespace}/{document_spec['xsd']}",
            },
        )
        ET.SubElement(root, "Clave").text = clave
        if self.company_id.vat:
            ET.SubElement(root, "ProveedorSistemas").text = "".join(ch for ch in self.company_id.vat if ch.isdigit())
        if self.fp_economic_activity_code:
            ET.SubElement(root, "CodigoActividadEmisor").text = self.fp_economic_activity_code
        if self.partner_id.fp_economic_activity_id and self.partner_id.fp_economic_activity_id.code:
            ET.SubElement(root, "CodigoActividadReceptor").text = self.partner_id.fp_economic_activity_id.code
        ET.SubElement(root, "NumeroConsecutivo").text = self._fp_extract_consecutive_from_clave(clave)
        ET.SubElement(root, "FechaEmision").text = datetime.now().astimezone().isoformat(timespec="seconds")

        emisor = ET.SubElement(root, "Emisor")
        ET.SubElement(emisor, "Nombre").text = self.company_id.name or ""
        self._fp_append_identification_nodes(emisor, self.company_id.partner_id, self.company_id.vat)
        self._fp_append_location_nodes(emisor, self.company_id.partner_id)
        self._fp_append_contact_nodes(emisor, self.company_id.partner_id)

        receptor = ET.SubElement(root, "Receptor")
        ET.SubElement(receptor, "Nombre").text = self.partner_id.name or ""
        self._fp_append_identification_nodes(receptor, self.partner_id, self.partner_id.vat)
        self._fp_append_location_nodes(receptor, self.partner_id)
        self._fp_append_contact_nodes(receptor, self.partner_id)

        ET.SubElement(root, "CondicionVenta").text = self.fp_sale_condition or "01"

        lines = ET.SubElement(root, "DetalleServicio")
        detalle_vals = self._fp_build_detail_lines(lines)
        resumen = ET.SubElement(root, "ResumenFactura")
        currency_node = ET.SubElement(resumen, "CodigoTipoMoneda")
        ET.SubElement(currency_node, "CodigoMoneda").text = self.currency_id.name or "CRC"
        ET.SubElement(currency_node, "TipoCambio").text = f"{self.currency_id.rate or 1:.5f}"
        ET.SubElement(resumen, "TotalServGravados").text = self._fp_format_decimal(detalle_vals["total_serv_gravados"])
        ET.SubElement(resumen, "TotalServExentos").text = self._fp_format_decimal(detalle_vals["total_serv_exentos"])
        ET.SubElement(resumen, "TotalServExonerado").text = self._fp_format_decimal(detalle_vals["total_serv_exonerado"])
        ET.SubElement(resumen, "TotalServNoSujeto").text = self._fp_format_decimal(detalle_vals["total_serv_no_sujeto"])
        ET.SubElement(resumen, "TotalMercanciasGravadas").text = self._fp_format_decimal(detalle_vals["total_mercancias_gravadas"])
        ET.SubElement(resumen, "TotalMercanciasExentas").text = self._fp_format_decimal(detalle_vals["total_mercancias_exentas"])
        ET.SubElement(resumen, "TotalMercExonerada").text = self._fp_format_decimal(detalle_vals["total_merc_exonerada"])
        ET.SubElement(resumen, "TotalMercNoSujeta").text = self._fp_format_decimal(detalle_vals["total_merc_no_sujeta"])
        ET.SubElement(resumen, "TotalGravado").text = self._fp_format_decimal(detalle_vals["total_gravado"])
        ET.SubElement(resumen, "TotalExento").text = self._fp_format_decimal(detalle_vals["total_exento"])
        ET.SubElement(resumen, "TotalExonerado").text = self._fp_format_decimal(detalle_vals["total_exonerado"])
        ET.SubElement(resumen, "TotalNoSujeto").text = self._fp_format_decimal(detalle_vals["total_no_sujeto"])
        ET.SubElement(resumen, "TotalVenta").text = self._fp_format_decimal(detalle_vals["total_venta"])
        ET.SubElement(resumen, "TotalDescuentos").text = self._fp_format_decimal(detalle_vals["total_descuentos"])
        ET.SubElement(resumen, "TotalVentaNeta").text = self._fp_format_decimal(detalle_vals["total_venta_neta"])
        for (tax_code, tax_rate_code), tax_amount in sorted(detalle_vals["total_desglose_impuesto"].items()):
            desglose = ET.SubElement(resumen, "TotalDesgloseImpuesto")
            ET.SubElement(desglose, "Codigo").text = tax_code
            ET.SubElement(desglose, "CodigoTarifaIVA").text = tax_rate_code
            ET.SubElement(desglose, "TotalMontoImpuesto").text = self._fp_format_decimal(tax_amount)
        ET.SubElement(resumen, "TotalImpuesto").text = self._fp_format_decimal(detalle_vals["total_impuesto"])
        ET.SubElement(resumen, "TotalImpAsumEmisorFabrica").text = self._fp_format_decimal(
            detalle_vals["total_imp_asum_emisor_fabrica"]
        )
        ET.SubElement(resumen, "TotalIVADevuelto").text = self._fp_format_decimal(detalle_vals["total_iva_devuelto"])
        medio_pago = ET.SubElement(resumen, "MedioPago")
        ET.SubElement(medio_pago, "TipoMedioPago").text = self.fp_payment_method or "01"
        ET.SubElement(resumen, "TotalComprobante").text = self._fp_format_decimal(detalle_vals["total_comprobante"])

        self._fp_append_reference_information(root)

        ET.register_namespace("", namespace)
        ET.register_namespace("ds", DS_XML_NS)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    def _fp_append_reference_information(self, root_node):
        self.ensure_one()
        if self.fp_document_type not in ("NC", "ND"):
            return

        self._fp_populate_reference_from_reversed_entry(force=False)
        if not self.fp_reference_document_type or not self.fp_reference_number or not self.fp_reference_issue_datetime:
            raise UserError(
                _(
                    "La nota electrónica requiere información de referencia. "
                    "Complete Tipo de documento, Número y Fecha de emisión del documento de referencia."
                )
            )

        reference_node = ET.SubElement(root_node, "InformacionReferencia")
        ET.SubElement(reference_node, "TipoDocIR").text = self.fp_reference_document_type
        ET.SubElement(reference_node, "Numero").text = self.fp_reference_number
        reference_issue_datetime = fields.Datetime.context_timestamp(self, self.fp_reference_issue_datetime)
        ET.SubElement(reference_node, "FechaEmisionIR").text = reference_issue_datetime.isoformat(timespec="seconds")
        ET.SubElement(reference_node, "Codigo").text = self.fp_reference_code or "01"
        ET.SubElement(reference_node, "Razon").text = self.fp_reference_reason or _("Documento de referencia")

    def _fp_populate_reference_from_reversed_entry(self, force=False):
        for move in self:
            if move.fp_document_type not in ("NC", "ND"):
                continue

            referenced_move = move.reversed_entry_id
            if not referenced_move:
                continue

            should_set_type = force or not move.fp_reference_document_type
            should_set_number = force or not move.fp_reference_number
            should_set_date = force or not move.fp_reference_issue_datetime

            if should_set_type:
                move.fp_reference_document_type = referenced_move._fp_get_document_code()
            if should_set_number:
                move.fp_reference_number = (
                    referenced_move.fp_external_id
                    or referenced_move.fp_consecutive_number
                    or (referenced_move.name or "")
                )
            if should_set_date:
                reference_date = referenced_move.invoice_date or referenced_move.date or fields.Date.context_today(move)
                move.fp_reference_issue_datetime = datetime.combine(
                    reference_date,
                    datetime.now().astimezone().timetz(),
                ).replace(tzinfo=None)

            if force and not move.fp_reference_reason:
                move.fp_reference_reason = _("Documento de referencia para nota electrónica")

    def _fp_get_tax_rate_from_code(self, tax_rate_code):
        iva_rate_map = {
            "01": 0.0,
            "02": 1.0,
            "03": 2.0,
            "04": 4.0,
            "05": 0.0,
            "06": 4.0,
            "07": 8.0,
            "08": 13.0,
            "09": 0.5,
            "10": 0.0,
            "11": 0.0,
        }
        return iva_rate_map.get((tax_rate_code or "").strip(), 0.0)

    def _fp_build_detail_lines(self, lines_node):
        totals = {
            "total_serv_gravados": 0.0,
            "total_serv_exentos": 0.0,
            "total_serv_exonerado": 0.0,
            "total_serv_no_sujeto": 0.0,
            "total_mercancias_gravadas": 0.0,
            "total_mercancias_exentas": 0.0,
            "total_merc_exonerada": 0.0,
            "total_merc_no_sujeta": 0.0,
            "total_gravado": 0.0,
            "total_exento": 0.0,
            "total_exonerado": 0.0,
            "total_no_sujeto": 0.0,
            "total_venta": 0.0,
            "total_descuentos": 0.0,
            "total_venta_neta": 0.0,
            "total_desglose_impuesto": {},
            "total_impuesto": 0.0,
            "total_imp_asum_emisor_fabrica": 0.0,
            "total_iva_devuelto": 0.0,
            "total_comprobante": 0.0,
        }

        detail_lines = self.invoice_line_ids.filtered(
            lambda l: not l.display_type or l.display_type == "product"
        )
        if not detail_lines:
            raise UserError(_("La factura debe tener al menos una línea de detalle para generar XML FE v4.4."))

        for idx, line in enumerate(detail_lines, start=1):
            detail = ET.SubElement(lines_node, "LineaDetalle")
            ET.SubElement(detail, "NumeroLinea").text = str(idx)
            if line.product_id and line.product_id.fp_cabys_code:
                ET.SubElement(detail, "CodigoCABYS").text = line.product_id.fp_cabys_code
            self._fp_append_line_extra_nodes(detail, line)

            quantity = line.quantity or 0.0
            ET.SubElement(detail, "Cantidad").text = self._fp_format_decimal(quantity)
            unit_code = (line.product_uom_id.fp_unit_code or "").strip() if line.product_uom_id else ""
            ET.SubElement(detail, "UnidadMedida").text = unit_code or "Unid"
            ET.SubElement(detail, "Detalle").text = line.name or ""
            ET.SubElement(detail, "PrecioUnitario").text = self._fp_format_decimal(line.price_unit)

            monto_total = quantity * line.price_unit
            subtotal = line.price_subtotal
            discount_amount = max(monto_total - subtotal, 0.0)
            total_impuesto_linea = max(line.price_total - line.price_subtotal, 0.0)
            impuesto_neto_linea = total_impuesto_linea
            monto_total_linea = subtotal + impuesto_neto_linea

            tax = line.tax_ids[:1]
            tax_code = (tax.fp_tax_type or tax.fp_tax_code or "01") if tax else "01"
            tax_rate_code = (tax.fp_tax_rate_code_iva or "08") if tax else "08"
            configured_tax_rate = tax.fp_tax_rate if tax and tax.fp_tax_rate else 0.0
            odoo_tax_rate = tax.amount if tax else 0.0
            code_tax_rate = self._fp_get_tax_rate_from_code(tax_rate_code) if tax else 0.0
            tax_rate = configured_tax_rate or odoo_tax_rate or code_tax_rate
            total_impuesto_xml_linea = subtotal * (tax_rate / 100.0) if tax else 0.0
            has_tax = bool(tax)

            ET.SubElement(detail, "MontoTotal").text = self._fp_format_decimal(monto_total)
            ET.SubElement(detail, "SubTotal").text = self._fp_format_decimal(subtotal)
            exoneration = self.env["fp.client.exoneration"]
            exoneration_amount = 0.0
            has_exoneration = False
            if has_tax:
                ET.SubElement(detail, "BaseImponible").text = self._fp_format_decimal(subtotal)
                impuesto = ET.SubElement(detail, "Impuesto")
                ET.SubElement(impuesto, "Codigo").text = tax_code
                ET.SubElement(impuesto, "CodigoTarifaIVA").text = tax_rate_code
                ET.SubElement(impuesto, "Tarifa").text = self._fp_format_decimal(tax_rate)
                ET.SubElement(impuesto, "Monto").text = self._fp_format_decimal(total_impuesto_xml_linea)
                exoneration = self._fp_get_line_exoneration(line)
                exoneration_amount = self._fp_append_exoneracion_node(
                    impuesto,
                    exoneration,
                    subtotal,
                    tax_rate,
                )
                has_exoneration = bool(exoneration)
                impuesto_neto_linea = max(total_impuesto_xml_linea - exoneration_amount, 0.0)
                monto_total_linea = subtotal + impuesto_neto_linea
                ET.SubElement(detail, "ImpuestoAsumidoEmisorFabrica").text = self._fp_format_decimal(0.0)
                ET.SubElement(detail, "ImpuestoNeto").text = self._fp_format_decimal(impuesto_neto_linea)
                desglose_key = (tax_code, tax_rate_code)
                totals["total_desglose_impuesto"][desglose_key] = (
                    totals["total_desglose_impuesto"].get(desglose_key, 0.0) + impuesto_neto_linea
                )
            ET.SubElement(detail, "MontoTotalLinea").text = self._fp_format_decimal(monto_total_linea)

            product_type = line.product_id.product_tmpl_id.type if line.product_id else False
            is_service = product_type == "service"
            if has_tax and (total_impuesto_xml_linea > 0 or has_exoneration):
                if has_exoneration:
                    if is_service:
                        totals["total_serv_exonerado"] += subtotal
                    else:
                        totals["total_merc_exonerada"] += subtotal
                    totals["total_exonerado"] += subtotal
                else:
                    if is_service:
                        totals["total_serv_gravados"] += subtotal
                    else:
                        totals["total_mercancias_gravadas"] += subtotal
                    totals["total_gravado"] += subtotal
            elif has_tax and tax_rate_code in ("01", "05", "11"):
                if is_service:
                    totals["total_serv_no_sujeto"] += subtotal
                else:
                    totals["total_merc_no_sujeta"] += subtotal
                totals["total_no_sujeto"] += subtotal
            elif has_tax and tax_rate_code == "10":
                if is_service:
                    totals["total_serv_exentos"] += subtotal
                else:
                    totals["total_mercancias_exentas"] += subtotal
                totals["total_exento"] += subtotal
            else:
                if is_service:
                    totals["total_serv_exentos"] += subtotal
                else:
                    totals["total_mercancias_exentas"] += subtotal
                totals["total_exento"] += subtotal

            totals["total_venta"] += monto_total
            totals["total_descuentos"] += discount_amount
            totals["total_venta_neta"] += subtotal
            totals["total_impuesto"] += impuesto_neto_linea
            totals["total_comprobante"] += monto_total_linea

        return totals

    def _fp_append_line_extra_nodes(self, detail_node, line):
        product = line.product_id.product_tmpl_id if line.product_id else False
        if not product:
            return
        if product.fp_commercial_code_type and (line.product_id.default_code or product.default_code):
            code_node = ET.SubElement(detail_node, "CodigoComercial")
            ET.SubElement(code_node, "Tipo").text = product.fp_commercial_code_type
            ET.SubElement(code_node, "Codigo").text = line.product_id.default_code or product.default_code
        if product.fp_health_registry_number:
            ET.SubElement(detail_node, "NumeroRegistroMS").text = product.fp_health_registry_number
        if product.fp_medicine_presentation_code:
            ET.SubElement(detail_node, "CodigoPresentacionMedicamento").text = product.fp_medicine_presentation_code
        if product.fp_tariff_heading and self._fp_is_export_invoice():
            ET.SubElement(detail_node, "PartidaArancelaria").text = product.fp_tariff_heading
        if product.fp_transport_vin_or_series:
            ET.SubElement(detail_node, "NumeroVINoSerie").text = product.fp_transport_vin_or_series

    def _fp_is_export_invoice(self):
        self.ensure_one()
        return (self.partner_id.country_id.code or "CR") != "CR"

    def _fp_get_line_exoneration(self, line):
        self.ensure_one()
        partner = self.partner_id
        if not partner.fp_use_exonerations:
            return self.env["fp.client.exoneration"]
        invoice_date = self.invoice_date or fields.Date.context_today(self)
        domain = [
            ("partner_id", "=", partner.id),
            ("active", "=", True),
            ("issue_date", "<=", fields.Datetime.to_string(invoice_date)),
            "|",
            ("expiry_date", "=", False),
            ("expiry_date", ">=", invoice_date),
        ]
        exonerations = self.env["fp.client.exoneration"].search(domain, order="issue_date desc")
        if not exonerations:
            return self.env["fp.client.exoneration"]
        product_tmpl = line.product_id.product_tmpl_id if line.product_id else False
        cabys = product_tmpl.fp_cabys_code_id if product_tmpl else False
        for exoneration in exonerations:
            if not exoneration.line_ids:
                return exoneration
            for exo_line in exoneration.line_ids:
                product_match = exo_line.product_id and product_tmpl and exo_line.product_id == product_tmpl
                cabys_match = exo_line.cabys_code_id and cabys and exo_line.cabys_code_id == cabys
                if product_match or cabys_match:
                    return exoneration
        return self.env["fp.client.exoneration"]

    def _fp_append_exoneracion_node(self, impuesto_node, exoneration, taxable_base, tax_rate):
        if not exoneration:
            return 0.0
        exoneration_node = ET.SubElement(impuesto_node, "Exoneracion")
        # En v4.4, el nodo de exoneración utiliza TipoDocumentoEX1 (no TipoDocumento).
        ET.SubElement(exoneration_node, "TipoDocumentoEX1").text = exoneration.exoneration_type or "99"
        ET.SubElement(exoneration_node, "NumeroDocumento").text = (exoneration.exoneration_number or "")[:40]
        ET.SubElement(exoneration_node, "NombreInstitucion").text = (exoneration.institution_name or "")[:160]
        exoneration_issue_dt = fields.Datetime.to_datetime(exoneration.issue_date)
        ET.SubElement(exoneration_node, "FechaEmisionEX").text = exoneration_issue_dt.strftime("%Y-%m-%dT%H:%M:%S") if exoneration_issue_dt else ""
        percentage = max(min(exoneration.exoneration_percentage or 0.0, 100.0), 0.0)
        tax_discount = taxable_base * (percentage / 100.0)
        ET.SubElement(exoneration_node, "TarifaExonerada").text = self._fp_format_decimal(tax_rate)
        ET.SubElement(exoneration_node, "MontoExoneracion").text = self._fp_format_decimal(tax_discount)
        # En v4.4 del esquema FE, Exoneracion termina en MontoExoneracion.
        # Articulo/Inciso ya no son nodos válidos y causan rechazo XSD.
        return tax_discount

    def _fp_format_decimal(self, value):
        return f"{(value or 0.0):.5f}"


    def _fp_append_identification_nodes(self, parent_node, partner, vat_source):
        identification_node = ET.SubElement(parent_node, "Identificacion")
        ET.SubElement(identification_node, "Tipo").text = (partner.fp_identification_type or "02").strip()
        ET.SubElement(identification_node, "Numero").text = "".join(ch for ch in (vat_source or "") if ch.isdigit())

    def _fp_append_location_nodes(self, parent_node, partner):
        if partner.country_id.code == "CR":
            province_source = partner.state_id.code if partner.state_id and partner.state_id.code else partner.fp_province_code
            canton_source = partner.city or partner.fp_canton_code
            district_source = partner.fp_district_code
            neighborhood_source = partner.fp_neighborhood_code
        else:
            province_source = partner.fp_province_code if partner.fp_province_code else (partner.state_id.code if partner.state_id and partner.state_id.code else "1")
            canton_source = partner.fp_canton_code
            district_source = partner.fp_district_code
            neighborhood_source = partner.fp_neighborhood_code

        province = self._fp_pad_numeric_code(province_source, 1, "1")
        canton = self._fp_pad_numeric_code(canton_source, 2, "01")
        district = self._fp_pad_numeric_code(district_source, 2, "01")
        neighborhood = self._fp_format_neighborhood_code(neighborhood_source)

        location_node = ET.SubElement(parent_node, "Ubicacion")
        ET.SubElement(location_node, "Provincia").text = self._fp_pad_numeric_code(province, 1, "1")
        ET.SubElement(location_node, "Canton").text = canton
        ET.SubElement(location_node, "Distrito").text = district
        ET.SubElement(location_node, "Barrio").text = neighborhood
        if partner.street:
            ET.SubElement(location_node, "OtrasSenas").text = partner.street[:160]

    def _fp_append_contact_nodes(self, parent_node, partner):
        phone_number = self._fp_normalize_phone_number(partner.phone)
        if phone_number:
            phone_node = ET.SubElement(parent_node, "Telefono")
            ET.SubElement(phone_node, "CodigoPais").text = "506"
            ET.SubElement(phone_node, "NumTelefono").text = phone_number
        if partner.email:
            ET.SubElement(parent_node, "CorreoElectronico").text = partner.email

    def _fp_normalize_phone_number(self, phone):
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        if not digits:
            return ""
        if digits == "506":
            return ""
        if digits.startswith("506") and len(digits) > 8:
            digits = digits[3:]
        return digits[:20]

    def _fp_pad_numeric_code(self, value, length, default):
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if not digits:
            digits = default
        return digits.zfill(length)[-length:]

    def _fp_format_neighborhood_code(self, value):
        code = (value or "").strip()
        if not code:
            return "01"
        return code[:64]

    def _fp_sign_xml(self, xml_text):
        self.ensure_one()
        company = self.company_id
        cert_file = company.fp_signing_certificate_file
        if not cert_file:
            raise UserError(_("Configure el certificado FE (.p12/.pfx) para firmar XML en Ajustes > Contabilidad."))

        cert_bytes = base64.b64decode(cert_file)
        password = (company.fp_signing_certificate_password or "").encode("utf-8") or None

        try:
            private_key, certificate, _additional_certs = pkcs12.load_key_and_certificates(cert_bytes, password)
        except Exception as error:
            raise UserError(_("No fue posible abrir el certificado FE. Verifique archivo y contraseña. Detalle: %s") % error)

        if not private_key or not certificate:
            raise UserError(_("El certificado FE no contiene llave privada o certificado válido."))

        parser = LET.XMLParser(remove_blank_text=True)
        root = LET.fromstring(xml_text.encode("utf-8"), parser=parser)

        signature_token = str(uuid.uuid4())
        reference_token = str(uuid.uuid4())
        object_token = str(uuid.uuid4())
        qualifying_props_token = str(uuid.uuid4())

        signature_id = f"Signature-{signature_token}"
        reference_id = f"Reference-{reference_token}"
        key_info_id = f"KeyInfoId-{signature_id}"
        signed_properties_id = f"SignedProperties-{signature_id}"

        canonical_document = LET.tostring(root, method="c14n", exclusive=False, with_comments=False)
        root_digest = hashlib.sha256(canonical_document).digest()

        signature_node = LET.SubElement(root, LET.QName(DS_XML_NS, "Signature"), nsmap={"ds": DS_XML_NS, "xades": XADES_XML_NS})
        signature_node.set("Id", signature_id)

        signed_info = LET.SubElement(signature_node, LET.QName(DS_XML_NS, "SignedInfo"))
        LET.SubElement(
            signed_info,
            LET.QName(DS_XML_NS, "CanonicalizationMethod"),
            {"Algorithm": "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"},
        )
        LET.SubElement(
            signed_info,
            LET.QName(DS_XML_NS, "SignatureMethod"),
            {"Algorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"},
        )

        reference_document = LET.SubElement(
            signed_info,
            LET.QName(DS_XML_NS, "Reference"),
            {"Id": reference_id, "URI": ""},
        )
        transforms = LET.SubElement(reference_document, LET.QName(DS_XML_NS, "Transforms"))
        LET.SubElement(
            transforms,
            LET.QName(DS_XML_NS, "Transform"),
            {"Algorithm": "http://www.w3.org/2000/09/xmldsig#enveloped-signature"},
        )
        LET.SubElement(
            transforms,
            LET.QName(DS_XML_NS, "Transform"),
            {"Algorithm": "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"},
        )
        LET.SubElement(
            reference_document,
            LET.QName(DS_XML_NS, "DigestMethod"),
            {"Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"},
        )
        LET.SubElement(reference_document, LET.QName(DS_XML_NS, "DigestValue")).text = base64.b64encode(root_digest).decode("utf-8")

        key_info = LET.SubElement(signature_node, LET.QName(DS_XML_NS, "KeyInfo"), {"Id": key_info_id})
        x509_data = LET.SubElement(key_info, LET.QName(DS_XML_NS, "X509Data"))
        cert_der = certificate.public_bytes(serialization.Encoding.DER)
        LET.SubElement(x509_data, LET.QName(DS_XML_NS, "X509Certificate")).text = base64.b64encode(cert_der).decode("utf-8")

        public_key = certificate.public_key()
        key_value = LET.SubElement(key_info, LET.QName(DS_XML_NS, "KeyValue"))
        rsa_key_value = LET.SubElement(key_value, LET.QName(DS_XML_NS, "RSAKeyValue"))
        public_numbers = public_key.public_numbers()
        modulus_size = max(1, (public_numbers.n.bit_length() + 7) // 8)
        exponent_size = max(1, (public_numbers.e.bit_length() + 7) // 8)
        LET.SubElement(rsa_key_value, LET.QName(DS_XML_NS, "Modulus")).text = base64.b64encode(
            public_numbers.n.to_bytes(modulus_size, "big")
        ).decode("utf-8")
        LET.SubElement(rsa_key_value, LET.QName(DS_XML_NS, "Exponent")).text = base64.b64encode(
            public_numbers.e.to_bytes(exponent_size, "big")
        ).decode("utf-8")

        reference_key_info = LET.SubElement(
            signed_info,
            LET.QName(DS_XML_NS, "Reference"),
            {"Id": "ReferenceKeyInfo", "URI": f"#{key_info_id}"},
        )
        key_info_transforms = LET.SubElement(reference_key_info, LET.QName(DS_XML_NS, "Transforms"))
        LET.SubElement(
            key_info_transforms,
            LET.QName(DS_XML_NS, "Transform"),
            {"Algorithm": "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"},
        )
        LET.SubElement(
            reference_key_info,
            LET.QName(DS_XML_NS, "DigestMethod"),
            {"Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"},
        )
        key_info_c14n = LET.tostring(key_info, method="c14n", exclusive=False, with_comments=False)
        LET.SubElement(reference_key_info, LET.QName(DS_XML_NS, "DigestValue")).text = base64.b64encode(
            hashlib.sha256(key_info_c14n).digest()
        ).decode("utf-8")

        reference_signed_properties = LET.SubElement(
            signed_info,
            LET.QName(DS_XML_NS, "Reference"),
            {
                "Type": "http://uri.etsi.org/01903#SignedProperties",
                "URI": f"#{signed_properties_id}",
            },
        )
        signed_properties_transforms = LET.SubElement(reference_signed_properties, LET.QName(DS_XML_NS, "Transforms"))
        LET.SubElement(
            signed_properties_transforms,
            LET.QName(DS_XML_NS, "Transform"),
            {"Algorithm": "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"},
        )
        LET.SubElement(
            reference_signed_properties,
            LET.QName(DS_XML_NS, "DigestMethod"),
            {"Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"},
        )
        reference_signed_properties_digest = LET.SubElement(reference_signed_properties, LET.QName(DS_XML_NS, "DigestValue"))

        object_node = LET.SubElement(signature_node, LET.QName(DS_XML_NS, "Object"), {"Id": f"XadesObjectId-{object_token}"})
        qualifying_properties = LET.SubElement(
            object_node,
            LET.QName(XADES_XML_NS, "QualifyingProperties"),
            {
                "Id": f"QualifyingProperties-{qualifying_props_token}",
                "Target": f"#{signature_id}",
            },
        )
        signed_properties = LET.SubElement(
            qualifying_properties,
            LET.QName(XADES_XML_NS, "SignedProperties"),
            {"Id": signed_properties_id},
        )
        signed_signature_properties = LET.SubElement(signed_properties, LET.QName(XADES_XML_NS, "SignedSignatureProperties"))
        LET.SubElement(signed_signature_properties, LET.QName(XADES_XML_NS, "SigningTime")).text = datetime.now().astimezone().replace(microsecond=0).isoformat()

        signing_certificate = LET.SubElement(signed_signature_properties, LET.QName(XADES_XML_NS, "SigningCertificate"))
        cert_node = LET.SubElement(signing_certificate, LET.QName(XADES_XML_NS, "Cert"))
        cert_digest_node = LET.SubElement(cert_node, LET.QName(XADES_XML_NS, "CertDigest"))
        LET.SubElement(
            cert_digest_node,
            LET.QName(DS_XML_NS, "DigestMethod"),
            {"Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"},
        )
        LET.SubElement(cert_digest_node, LET.QName(DS_XML_NS, "DigestValue")).text = base64.b64encode(
            hashlib.sha256(cert_der).digest()
        ).decode("utf-8")
        issuer_serial = LET.SubElement(cert_node, LET.QName(XADES_XML_NS, "IssuerSerial"))
        LET.SubElement(issuer_serial, LET.QName(DS_XML_NS, "X509IssuerName")).text = certificate.issuer.rfc4514_string()
        LET.SubElement(issuer_serial, LET.QName(DS_XML_NS, "X509SerialNumber")).text = str(certificate.serial_number)

        signature_policy_identifier = LET.SubElement(
            signed_signature_properties,
            LET.QName(XADES_XML_NS, "SignaturePolicyIdentifier"),
        )
        signature_policy_id = LET.SubElement(signature_policy_identifier, LET.QName(XADES_XML_NS, "SignaturePolicyId"))
        sig_policy_id = LET.SubElement(signature_policy_id, LET.QName(XADES_XML_NS, "SigPolicyId"))
        LET.SubElement(sig_policy_id, LET.QName(XADES_XML_NS, "Identifier")).text = XADES_SIGNATURE_POLICY_IDENTIFIER
        LET.SubElement(sig_policy_id, LET.QName(XADES_XML_NS, "Description")).text = ""

        sig_policy_hash = LET.SubElement(signature_policy_id, LET.QName(XADES_XML_NS, "SigPolicyHash"))
        LET.SubElement(
            sig_policy_hash,
            LET.QName(DS_XML_NS, "DigestMethod"),
            {"Algorithm": XADES_SIGNATURE_POLICY_HASH_ALGORITHM},
        )
        LET.SubElement(sig_policy_hash, LET.QName(DS_XML_NS, "DigestValue")).text = XADES_SIGNATURE_POLICY_HASH

        signer_role = LET.SubElement(signed_signature_properties, LET.QName(XADES_XML_NS, "SignerRole"))
        claimed_roles = LET.SubElement(signer_role, LET.QName(XADES_XML_NS, "ClaimedRoles"))
        LET.SubElement(claimed_roles, LET.QName(XADES_XML_NS, "ClaimedRole")).text = "ObligadoTributario"

        signed_data_object_properties = LET.SubElement(signed_properties, LET.QName(XADES_XML_NS, "SignedDataObjectProperties"))
        data_object_format = LET.SubElement(
            signed_data_object_properties,
            LET.QName(XADES_XML_NS, "DataObjectFormat"),
            {"ObjectReference": f"#{reference_id}"},
        )
        LET.SubElement(data_object_format, LET.QName(XADES_XML_NS, "MimeType")).text = "text/xml"
        LET.SubElement(data_object_format, LET.QName(XADES_XML_NS, "Encoding")).text = "UTF-8"

        signed_properties_c14n = LET.tostring(signed_properties, method="c14n", exclusive=False, with_comments=False)
        reference_signed_properties_digest.text = base64.b64encode(hashlib.sha256(signed_properties_c14n).digest()).decode("utf-8")

        signed_info_c14n = LET.tostring(signed_info, method="c14n", exclusive=False, with_comments=False)
        signature = private_key.sign(signed_info_c14n, padding.PKCS1v15(), hashes.SHA256())
        signature_value_node = LET.SubElement(
            signature_node,
            LET.QName(DS_XML_NS, "SignatureValue"),
            {"Id": f"SignatureValue-{signature_token}"},
        )
        signature_value_node.text = base64.b64encode(signature).decode("utf-8")
        signature_node.insert(1, signature_value_node)

        return LET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    def _fp_store_hacienda_response_xml(self, response_data):
        self.ensure_one()
        xml_keys = ["respuesta-xml", "respuestaXml", "xmlRespuesta", "xml"]
        xml_payload = next((response_data.get(key) for key in xml_keys if response_data.get(key)), None)
        if not xml_payload:
            return

        if xml_payload.lstrip().startswith("<"):
            xml_text = xml_payload
        else:
            try:
                xml_text = base64.b64decode(xml_payload).decode("utf-8")
            except Exception:
                xml_text = xml_payload

        attachment = self.env["ir.attachment"].create(
            {
                "name": f"{self.name or 'factura'}-respuesta-hacienda.xml",
                "type": "binary",
                "datas": base64.b64encode(xml_text.encode("utf-8")),
                "res_model": "account.move",
                "res_id": self.id,
                "mimetype": "application/xml",
            }
        )
        self.fp_response_xml_attachment_id = attachment


    def action_fp_download_invoice_xml(self):
        self.ensure_one()
        if not self.fp_xml_attachment_id:
            raise UserError(_("La factura no tiene XML adjunto."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.fp_xml_attachment_id.id}?download=true",
            "target": "self",
        }

    def action_fp_download_response_xml(self):
        self.ensure_one()
        if not self.fp_response_xml_attachment_id:
            raise UserError(_("El documento no tiene XML de respuesta de Hacienda adjunto."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.fp_response_xml_attachment_id.id}?download=true",
            "target": "self",
        }

    def _fp_get_document_code(self):
        self.ensure_one()
        document_map = {
            "FE": "01",
            "FEE": "09",
            "NC": "03",
            "TE": "04",
        }
        return document_map.get(self.fp_document_type, "99")

    def _fp_get_company_consecutive_field_name(self):
        self.ensure_one()
        return {
            "FE": "fp_consecutive_fe",
            "FEE": "fp_consecutive_others",
            "NC": "fp_consecutive_nc",
            "TE": "fp_consecutive_te",
        }.get(self.fp_document_type, "fp_consecutive_others")

    def _fp_get_company_last_consecutive_sequence(self):
        self.ensure_one()
        company = self.company_id
        field_name = self._fp_get_company_consecutive_field_name()
        digits = "".join(ch for ch in (company[field_name] or "") if ch.isdigit())
        if not digits:
            return 0
        if len(digits) >= 20:
            return int(digits[-10:])
        return int(digits[-10:])

    def _fp_get_company_consecutive(self):
        self.ensure_one()
        branch = "".join(ch for ch in (self.company_id.fp_branch_code or "") if ch.isdigit()).zfill(3)[-3:]
        terminal = "".join(ch for ch in (self.company_id.fp_terminal_code or "") if ch.isdigit()).zfill(5)[-5:]
        document_code = self._fp_get_document_code()
        sequence = self._fp_get_company_last_consecutive_sequence()
        if self.fp_consecutive_number:
            return self.fp_consecutive_number

        next_sequence = sequence + 1
        consecutive = f"{branch}{terminal}{document_code}{next_sequence:010d}"

        field_name = self._fp_get_company_consecutive_field_name()
        self.company_id.sudo()[field_name] = str(next_sequence)
        self.fp_consecutive_number = consecutive
        return consecutive

    def _fp_extract_consecutive_from_clave(self, clave):
        # Estructura clave CR (50 dígitos):
        # país(3) + fecha(6) + identificación(12) + consecutivo(20) + situación(1) + seguridad(8)
        if len(clave or "") >= 41:
            return clave[21:41]
        return (clave or "").zfill(20)[-20:]

    def _fp_build_clave(self):
        self.ensure_one()
        if self.fp_external_id:
            return self.fp_external_id

        country_code = "506"
        invoice_date = fields.Date.context_today(self)
        date_token = invoice_date.strftime("%d%m%y")
        company_vat = "".join(ch for ch in (self.company_id.vat or "") if ch.isdigit()).zfill(12)[-12:]
        consecutive = self.fp_consecutive_number or self._fp_get_company_consecutive()
        situation = "1"
        security_code = f"{random.SystemRandom().randrange(0, 100000000):08d}"
        # El tipo de documento ya viene embebido en el consecutivo (20 dígitos),
        # no debe duplicarse dentro de la clave.
        clave = f"{country_code}{date_token}{company_vat}{consecutive}{situation}{security_code}"
        # Persistimos la clave al primer cálculo para reutilizar exactamente el
        # mismo valor en XML, payload y reintentos de envío.
        self.fp_external_id = clave
        return clave

    def _fp_call_api(self, endpoint, payload, timeout, token, base_url, method="POST", params=None):
        url = f"{base_url.rstrip('/')}{endpoint}"
        headers = {
            "Authorization": self._fp_build_authorization_header(token),
            "Content-Type": "application/json",
        }
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=timeout, params=params)
        else:
            response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=timeout)
        if response.status_code >= 400:
            self.fp_api_state = "error"
            raise UserError(_("Error API Hacienda (%s): %s") % (response.status_code, response.text))
        if not response.text:
            return {}
        return self._fp_parse_json_response(response, response_context="API")

    def _fp_parse_json_response(self, response, response_context="API"):
        self.ensure_one()
        try:
            return response.json()
        except (ValueError, JSONDecodeError):
            content_type = response.headers.get("Content-Type", "")
            preview = (response.text or "")[:400]
            raise UserError(
                _(
                    "Respuesta inválida de Hacienda durante %(context)s. "
                    "Código: %(status)s, Content-Type: %(content_type)s, cuerpo: %(preview)s"
                )
                % {
                    "context": response_context,
                    "status": response.status_code,
                    "content_type": content_type or "desconocido",
                    "preview": preview or _("<vacío>"),
                }
            )

    def _fp_build_authorization_header(self, token):
        token = (token or "").strip().replace("\r", "").replace("\n", "")
        if token.lower().startswith("authorization:"):
            token = token.split(":", 1)[1].strip()
        if token.lower().startswith("bearer"):
            token = token.split(" ", 1)[-1].strip()
        token = token.strip("\"'")
        if not token:
            raise UserError(_("No se obtuvo un token OAuth válido para autenticarse con Hacienda."))
        return f"Bearer {token}"

    def _fp_cron_consult_pending_documents(self):
        moves = self.search(
            [
                ("fp_is_electronic_invoice", "=", True),
                ("fp_external_id", "!=", False),
                ("fp_invoice_status", "in", ["sent", False]),
                ("state", "=", "posted"),
            ],
            limit=200,
        )
        for move in moves:
            try:
                move.action_fp_consult_api_document()
            except Exception:
                move.fp_api_state = "error"
