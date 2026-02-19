import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    @staticmethod
    def _fp_extract_code_and_name(activity):
        if not isinstance(activity, dict):
            return False, False
        code = (
            activity.get("codigo")
            or activity.get("codigo_actividad")
            or activity.get("codigoActividad")
            or activity.get("cod_actividad")
            or activity.get("actividad")
            or activity.get("id")
        )
        name = (
            activity.get("descripcion")
            or activity.get("descripcion_actividad")
            or activity.get("desc_actividad")
            or activity.get("nombre")
        )
        code = str(code).strip() if code else False
        name = str(name).strip() if name else False
        return code, name

    @api.model
    def _fp_get_or_create_economic_activity(self, code, name=False):
        if not code:
            return self.env["fp.economic.activity"]
        activity_model = self.env["fp.economic.activity"].with_context(active_test=False)
        activity = activity_model.search([("code", "=", code)], limit=1)
        if activity:
            if name and not activity.name:
                activity.name = name
            return activity
        return activity_model.create({"code": code, "name": name or code})

    @api.model
    def _fp_extract_hacienda_main_activity(self, data):
        if not isinstance(data, dict):
            return False, False

        candidates = [
            data.get("actividad_principal"),
            data.get("actividadPrincipal"),
            data.get("actividad_economica"),
            data.get("actividadEconomica"),
            data.get("actividad"),
        ]
        for candidate in candidates:
            code, name = self._fp_extract_code_and_name(candidate)
            if code:
                return code, name

        activities = data.get("actividades") or data.get("actividades_economicas") or data.get("actividadesEconomicas")
        if isinstance(activities, list):
            principal = False
            for activity in activities:
                if not isinstance(activity, dict):
                    continue
                is_principal = activity.get("principal") or activity.get("es_principal") or activity.get("actividad_principal")
                if activity.get("tipo") == "P":
                    is_principal = True
                if is_principal:
                    principal = activity
                    break
                if not principal:
                    principal = activity
            if principal:
                return self._fp_extract_code_and_name(principal)

        return False, False

    def _auto_init(self):
        """Ensure FE columns exist before normal ORM reads on broken schemas.

        Some hosted databases can end up with a partial custom schema (for
        example `fp_identification_type` existing while `fp_canton_code` is
        missing). During module install/upgrade Odoo reads `res.partner` early,
        which crashes before migrations run.
        """
        result = super()._auto_init()

        missing_columns = {
            "fp_identification_type": "varchar",
            "fp_canton_code": "varchar",
            "fp_province_code": "varchar",
            "fp_district_code": "varchar",
            "fp_neighborhood_code": "varchar",
            "fp_economic_activity_id": "integer",
        }
        for column_name, sql_type in missing_columns.items():
            if not column_exists(self.env.cr, self._table, column_name):
                self.env.cr.execute(
                    f"ALTER TABLE {self._table} ADD COLUMN {column_name} {sql_type}"
                )
        return result

    fp_identification_type = fields.Selection(
        [
            ("01", "01 - Cédula física"),
            ("02", "02 - Cédula jurídica"),
            ("03", "03 - DIMEX"),
            ("04", "04 - NITE"),
            ("05", "05 - Extranjero no domiciliado"),
        ],
        string="Tipo de identificación (FE)",
        help="Catálogo de tipo de identificación para facturación electrónica.",
    )
    fp_province_id = fields.Many2one(
        "fp.province",
        string="Provincia (FE)",
        help="Provincia para facturación electrónica según catálogo FE.",
    )
    fp_canton_id = fields.Many2one(
        "fp.canton",
        string="Cantón (FE)",
        domain="[('province_id', '=', fp_province_id)]",
        help="Cantón para facturación electrónica según catálogo FE.",
    )
    fp_district_id = fields.Many2one(
        "fp.district",
        string="Distrito (FE)",
        domain="[('canton_id', '=', fp_canton_id)]",
        help="Distrito para facturación electrónica según catálogo FE.",
    )
    fp_canton_code = fields.Char(
        string="Cantón código (FE)",
        size=2,
        help="Código de cantón según Anexos y Estructuras v4.4 (2 dígitos).",
    )
    fp_province_code = fields.Char(
        string="Provincia código (FE)",
        size=1,
        help="Código de provincia según Anexos y Estructuras v4.4 (1 dígito).",
    )
    fp_district_code = fields.Char(
        string="Distrito código (FE)",
        size=2,
        help="Código de distrito según Anexos y Estructuras v4.4 (2 dígitos).",
    )
    fp_neighborhood_code = fields.Char(
        string="Barrio (FE)",
        size=64,
        help="Barrio para facturación electrónica. Permite texto o números.",
    )
    fp_economic_activity_id = fields.Many2one(
        "fp.economic.activity",
        string="Actividad económica principal (FE)",
        help="Actividad económica principal del cliente para facturación electrónica.",
    )
    fp_is_costa_rica = fields.Boolean(
        string="Es Costa Rica",
        compute="_compute_fp_is_costa_rica",
    )

    fp_use_exonerations = fields.Boolean(
        string="Usa Exoneraciones",
        help="Activa el uso de exoneraciones de Hacienda para este cliente.",
    )
    fp_exoneration_ids = fields.One2many(
        "fp.client.exoneration",
        "partner_id",
        string="Exoneraciones FE",
    )

    @api.depends("country_id")
    def _compute_fp_is_costa_rica(self):
        for partner in self:
            partner.fp_is_costa_rica = partner.country_id.code == "CR"


    @api.onchange("fp_province_id")
    def _onchange_fp_province_id(self):
        for partner in self:
            if partner.fp_canton_id and partner.fp_canton_id.province_id != partner.fp_province_id:
                partner.fp_canton_id = False
            if partner.fp_district_id and partner.fp_district_id.province_id != partner.fp_province_id:
                partner.fp_district_id = False
            partner.fp_province_code = partner.fp_province_id.code or False

    @api.onchange("fp_canton_id")
    def _onchange_fp_canton_id(self):
        for partner in self:
            if partner.fp_district_id and partner.fp_district_id.canton_id != partner.fp_canton_id:
                partner.fp_district_id = False
            if partner.fp_canton_id:
                partner.fp_province_id = partner.fp_canton_id.province_id
                partner.fp_canton_code = partner.fp_canton_id.code
                partner.city = partner.fp_canton_id.name
            else:
                partner.fp_canton_code = False
                if partner.country_id.code == "CR":
                    partner.city = False

    @api.onchange("fp_district_id")
    def _onchange_fp_district_id(self):
        for partner in self:
            if partner.fp_district_id:
                partner.fp_canton_id = partner.fp_district_id.canton_id
                partner.fp_province_id = partner.fp_district_id.province_id
                partner.fp_district_code = partner.fp_district_id.code
            else:
                partner.fp_district_code = False

    @api.onchange("country_id", "state_id")
    def _onchange_fp_sync_province_from_state(self):
        for partner in self:
            if partner.country_id.code == "CR" and partner.state_id and partner.state_id.code and not partner.fp_province_id:
                province_code = "".join(ch for ch in partner.state_id.code if ch.isdigit())[:1]
                if province_code:
                    partner.fp_province_id = self.env["fp.province"].search([("code", "=", province_code)], limit=1)
                partner.fp_province_code = province_code

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
                try:
                    response = requests.get(endpoint, timeout=15)
                except requests.exceptions.Timeout:
                    _logger.warning("Timeout consultando endpoint Hacienda de partner: %s", endpoint)
                    continue
                except requests.exceptions.RequestException:
                    _logger.exception("Error consultando endpoint Hacienda de partner: %s", endpoint)
                    continue

                if response.status_code < 400:
                    try:
                        payload = response.json()
                    except ValueError:
                        _logger.warning("Respuesta no JSON desde Hacienda para endpoint: %s", endpoint)
                        continue
                    if payload:
                        data = payload
                        break
            if not data:
                raise UserError(_("No se encontraron datos en Hacienda para la identificación %s.") % partner.vat)

            partner.name = data.get("nombre") or data.get("nomre") or partner.name
            email = data.get("correo_electronico") or data.get("email")
            if email:
                partner.email = email

            activity_code, activity_name = self._fp_extract_hacienda_main_activity(data)
            if activity_code:
                partner.fp_economic_activity_id = self._fp_get_or_create_economic_activity(activity_code, activity_name)
