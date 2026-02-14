import base64
import hashlib
import json
from datetime import datetime
import random
from xml.etree import ElementTree as ET

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12

from odoo import _, api, fields, models
from odoo.exceptions import UserError


FE_XML_NS = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica"
DS_XML_NS = "http://www.w3.org/2000/09/xmldsig#"


class AccountMove(models.Model):
    _inherit = "account.move"

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
            ("NC", "Nota de Crédito Electrónica"),
            ("ND", "Nota de Débito Electrónica"),
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
    fp_external_id = fields.Char(string="Clave Hacienda", copy=False)
    fp_consecutive_number = fields.Char(string="Consecutivo Hacienda", copy=False, readonly=True)
    fp_xml_attachment_id = fields.Many2one("ir.attachment", string="Factura XML", copy=False)
    fp_response_xml_attachment_id = fields.Many2one("ir.attachment", string="XML Respuesta Hacienda", copy=False)
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

    def _fp_send_to_hacienda(self):
        self.ensure_one()
        company = self.company_id
        if not company.fp_hacienda_api_base_url or not company.fp_hacienda_token_url:
            raise UserError(_("Configure URLs de Hacienda en Ajustes > Contabilidad."))

        if not self.fp_xml_attachment_id:
            self._fp_generate_and_sign_xml_attachment()

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
        if company.fp_auto_consult_after_send:
            self.action_fp_consult_api_document()

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
            self._fp_generate_and_sign_xml_attachment()

        clave = self._fp_build_clave()
        consecutivo = self._fp_extract_consecutive_from_clave(clave)
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

    def _fp_generate_and_sign_xml_attachment(self):
        self.ensure_one()
        xml_text = self._fp_generate_invoice_xml()
        signed_xml_text = self._fp_sign_xml(xml_text)
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"{self.name or 'factura'}-firmado.xml",
                "type": "binary",
                "datas": base64.b64encode(signed_xml_text.encode("utf-8")),
                "res_model": "account.move",
                "res_id": self.id,
                "mimetype": "application/xml",
            }
        )
        self.fp_xml_attachment_id = attachment

    def _fp_generate_invoice_xml(self):
        self.ensure_one()
        clave = self._fp_build_clave()
        root = ET.Element(
            "FacturaElectronica",
            {
                "xmlns": FE_XML_NS,
                "xmlns:ds": DS_XML_NS,
                "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                "xsi:schemaLocation": (
                    "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica "
                    "FacturaElectronica_V4.4.xsd"
                ),
            },
        )
        ET.SubElement(root, "Clave").text = clave
        if self.company_id.vat:
            ET.SubElement(root, "ProveedorSistemas").text = "".join(ch for ch in self.company_id.vat if ch.isdigit())
        if self.fp_economic_activity_code:
            ET.SubElement(root, "CodigoActividadEmisor").text = self.fp_economic_activity_code
        ET.SubElement(root, "NumeroConsecutivo").text = self._fp_extract_consecutive_from_clave(clave)
        ET.SubElement(root, "FechaEmision").text = datetime.now().astimezone().isoformat()

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
        ET.SubElement(resumen, "TotalMercanciasGravadas").text = self._fp_format_decimal(detalle_vals["total_mercancias_gravadas"])
        ET.SubElement(resumen, "TotalMercanciasExentas").text = self._fp_format_decimal(detalle_vals["total_mercancias_exentas"])
        ET.SubElement(resumen, "TotalGravado").text = self._fp_format_decimal(detalle_vals["total_gravado"])
        ET.SubElement(resumen, "TotalExento").text = self._fp_format_decimal(detalle_vals["total_exento"])
        ET.SubElement(resumen, "TotalVenta").text = self._fp_format_decimal(detalle_vals["total_venta"])
        ET.SubElement(resumen, "TotalDescuentos").text = self._fp_format_decimal(detalle_vals["total_descuentos"])
        ET.SubElement(resumen, "TotalVentaNeta").text = self._fp_format_decimal(detalle_vals["total_venta_neta"])
        ET.SubElement(resumen, "TotalImpuesto").text = self._fp_format_decimal(detalle_vals["total_impuesto"])
        medio_pago = ET.SubElement(resumen, "MedioPago")
        ET.SubElement(medio_pago, "TipoMedioPago").text = self.fp_payment_method or "01"
        ET.SubElement(resumen, "TotalComprobante").text = self._fp_format_decimal(detalle_vals["total_comprobante"])

        ET.register_namespace("", FE_XML_NS)
        ET.register_namespace("ds", DS_XML_NS)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    def _fp_build_detail_lines(self, lines_node):
        totals = {
            "total_serv_gravados": 0.0,
            "total_serv_exentos": 0.0,
            "total_mercancias_gravadas": 0.0,
            "total_mercancias_exentas": 0.0,
            "total_gravado": 0.0,
            "total_exento": 0.0,
            "total_venta": 0.0,
            "total_descuentos": 0.0,
            "total_venta_neta": 0.0,
            "total_impuesto": 0.0,
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
            monto_total_linea = subtotal + total_impuesto_linea

            ET.SubElement(detail, "MontoTotal").text = self._fp_format_decimal(monto_total)
            ET.SubElement(detail, "SubTotal").text = self._fp_format_decimal(subtotal)
            if total_impuesto_linea > 0:
                impuesto = ET.SubElement(detail, "Impuesto")
                tax = line.tax_ids[:1]
                ET.SubElement(impuesto, "Codigo").text = (tax.fp_tax_type or tax.fp_tax_code or "01") if tax else "01"
                ET.SubElement(impuesto, "CodigoTarifaIVA").text = (tax.fp_tax_rate_code_iva or "08") if tax else "08"
                ET.SubElement(impuesto, "Tarifa").text = self._fp_format_decimal((tax.amount if tax else 13.0))
                ET.SubElement(impuesto, "Monto").text = self._fp_format_decimal(total_impuesto_linea)
            ET.SubElement(detail, "MontoTotalLinea").text = self._fp_format_decimal(monto_total_linea)

            product_type = line.product_id.product_tmpl_id.type if line.product_id else False
            is_service = product_type == "service"
            if total_impuesto_linea > 0:
                if is_service:
                    totals["total_serv_gravados"] += subtotal
                else:
                    totals["total_mercancias_gravadas"] += subtotal
                totals["total_gravado"] += subtotal
            else:
                if is_service:
                    totals["total_serv_exentos"] += subtotal
                else:
                    totals["total_mercancias_exentas"] += subtotal
                totals["total_exento"] += subtotal

            totals["total_venta"] += monto_total
            totals["total_descuentos"] += discount_amount
            totals["total_venta_neta"] += subtotal
            totals["total_impuesto"] += total_impuesto_linea
            totals["total_comprobante"] += monto_total_linea

        return totals

    def _fp_format_decimal(self, value):
        return f"{(value or 0.0):.5f}"


    def _fp_append_identification_nodes(self, parent_node, partner, vat_source):
        identification_node = ET.SubElement(parent_node, "Identificacion")
        ET.SubElement(identification_node, "Tipo").text = (partner.fp_identification_type or "02").strip()
        ET.SubElement(identification_node, "Numero").text = "".join(ch for ch in (vat_source or "") if ch.isdigit())

    def _fp_append_location_nodes(self, parent_node, partner):
        province = partner.state_id.code if partner.state_id and partner.state_id.code else "1"
        canton = self._fp_pad_numeric_code(partner.fp_canton_code, 2, "01")
        district = self._fp_pad_numeric_code(partner.fp_district_code, 2, "01")
        neighborhood = self._fp_pad_numeric_code(partner.fp_neighborhood_code, 2, "01")

        location_node = ET.SubElement(parent_node, "Ubicacion")
        ET.SubElement(location_node, "Provincia").text = self._fp_pad_numeric_code(province, 1, "1")
        ET.SubElement(location_node, "Canton").text = canton
        ET.SubElement(location_node, "Distrito").text = district
        ET.SubElement(location_node, "Barrio").text = neighborhood

    def _fp_append_contact_nodes(self, parent_node, partner):
        if partner.phone:
            phone_node = ET.SubElement(parent_node, "Telefono")
            ET.SubElement(phone_node, "CodigoPais").text = "506"
            ET.SubElement(phone_node, "NumTelefono").text = "".join(ch for ch in partner.phone if ch.isdigit())[:20]
        if partner.email:
            ET.SubElement(parent_node, "CorreoElectronico").text = partner.email

    def _fp_pad_numeric_code(self, value, length, default):
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if not digits:
            digits = default
        return digits.zfill(length)[-length:]

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

        root = ET.fromstring(xml_text.encode("utf-8"))
        root_digest = hashlib.sha256(xml_text.encode("utf-8")).digest()

        signature_node = ET.SubElement(root, ET.QName(DS_XML_NS, "Signature"))
        signed_info = ET.SubElement(signature_node, ET.QName(DS_XML_NS, "SignedInfo"))
        ET.SubElement(
            signed_info,
            ET.QName(DS_XML_NS, "CanonicalizationMethod"),
            {"Algorithm": "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"},
        )
        ET.SubElement(
            signed_info,
            ET.QName(DS_XML_NS, "SignatureMethod"),
            {"Algorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"},
        )
        reference = ET.SubElement(signed_info, ET.QName(DS_XML_NS, "Reference"), {"URI": ""})
        transforms = ET.SubElement(reference, ET.QName(DS_XML_NS, "Transforms"))
        ET.SubElement(
            transforms,
            ET.QName(DS_XML_NS, "Transform"),
            {"Algorithm": "http://www.w3.org/2000/09/xmldsig#enveloped-signature"},
        )
        ET.SubElement(
            transforms,
            ET.QName(DS_XML_NS, "Transform"),
            {"Algorithm": "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"},
        )
        ET.SubElement(
            reference,
            ET.QName(DS_XML_NS, "DigestMethod"),
            {"Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"},
        )
        ET.SubElement(reference, ET.QName(DS_XML_NS, "DigestValue")).text = base64.b64encode(root_digest).decode("utf-8")

        signed_info_xml = ET.tostring(signed_info, encoding="utf-8")
        signature = private_key.sign(signed_info_xml, padding.PKCS1v15(), hashes.SHA256())
        ET.SubElement(signature_node, ET.QName(DS_XML_NS, "SignatureValue")).text = base64.b64encode(signature).decode(
            "utf-8"
        )

        key_info = ET.SubElement(signature_node, ET.QName(DS_XML_NS, "KeyInfo"))
        x509_data = ET.SubElement(key_info, ET.QName(DS_XML_NS, "X509Data"))
        ET.SubElement(x509_data, ET.QName(DS_XML_NS, "X509Certificate")).text = base64.b64encode(
            certificate.public_bytes(serialization.Encoding.DER)
        ).decode("utf-8")

        ET.register_namespace("", FE_XML_NS)
        ET.register_namespace("ds", DS_XML_NS)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

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

    def _fp_get_document_code(self):
        self.ensure_one()
        document_map = {
            "FE": "01",
            "NC": "03",
            "ND": "02",
            "TE": "04",
        }
        return document_map.get(self.fp_document_type, "99")

    def _fp_get_company_consecutive_field_name(self):
        self.ensure_one()
        return {
            "FE": "fp_consecutive_fe",
            "NC": "fp_consecutive_nc",
            "ND": "fp_consecutive_nd",
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
        if len(clave or "") >= 43:
            return clave[23:43]
        return (clave or "").zfill(20)[-20:]

    def _fp_build_clave(self):
        self.ensure_one()
        if self.fp_external_id:
            return self.fp_external_id

        country_code = "506"
        invoice_date = fields.Date.context_today(self)
        date_token = invoice_date.strftime("%d%m%y")
        company_vat = "".join(ch for ch in (self.company_id.vat or "") if ch.isdigit()).zfill(12)[-12:]
        document_code = self._fp_get_document_code()
        consecutive = self.fp_consecutive_number or self._fp_get_company_consecutive()
        situation = "1"
        security_code = f"{random.SystemRandom().randrange(0, 100000000):08d}"
        return f"{country_code}{date_token}{company_vat}{document_code}{consecutive}{situation}{security_code}"

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
