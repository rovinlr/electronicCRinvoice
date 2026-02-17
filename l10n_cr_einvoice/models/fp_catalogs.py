from odoo import api, fields, models


class FpCabysCode(models.Model):
    _name = "fp.cabys.code"
    _description = "Código CABYS"
    _order = "code"

    code = fields.Char(string="Código", required=True)
    name = fields.Char(string="Descripción", required=True)
    active = fields.Boolean(default=True)

    _fp_cabys_code_unique = models.Constraint("UNIQUE(code)", "El código CABYS debe ser único.")

    def name_get(self):
        return [(record.id, f"{record.code} - {record.name}") for record in self]


class FpEconomicActivity(models.Model):
    _name = "fp.economic.activity"
    _description = "Actividad Económica"
    _order = "code"

    code = fields.Char(string="Código", required=True)
    name = fields.Char(string="Descripción", required=True)
    active = fields.Boolean(default=True)

    _fp_economic_activity_code_unique = models.Constraint(
        "UNIQUE(code)", "El código de actividad económica debe ser único."
    )

    def name_get(self):
        return [(record.id, f"{record.code} - {record.name}") for record in self]


class FpProvince(models.Model):
    _name = "fp.province"
    _description = "Provincia"
    _order = "code"

    code = fields.Char(string="Código", required=True)
    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)

    canton_ids = fields.One2many("fp.canton", "province_id", string="Cantones")

    _fp_province_code_unique = models.Constraint("UNIQUE(code)", "El código de provincia debe ser único.")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("install_mode"):
            return super().create(vals_list)

        records = self.browse()
        for vals in vals_list:
            existing = self.search([("code", "=", vals.get("code"))], limit=1)
            if existing:
                existing.write({"name": vals.get("name", existing.name), "active": vals.get("active", existing.active)})
                records |= existing
            else:
                records |= super(FpProvince, self).create([vals])
        return records

    def name_get(self):
        return [(record.id, f"{record.code} - {record.name}") for record in self]


class FpCanton(models.Model):
    _name = "fp.canton"
    _description = "Cantón"
    _order = "province_id, code"

    code = fields.Char(string="Código", required=True)
    name = fields.Char(string="Nombre", required=True)
    province_id = fields.Many2one("fp.province", string="Provincia", required=True, ondelete="restrict")
    active = fields.Boolean(default=True)

    district_ids = fields.One2many("fp.district", "canton_id", string="Distritos")

    _fp_canton_code_unique_per_province = models.Constraint(
        "UNIQUE(province_id, code)",
        "El código de cantón debe ser único por provincia.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("install_mode"):
            return super().create(vals_list)

        records = self.browse()
        for vals in vals_list:
            province_id = vals.get("province_id")
            existing = self.search([("province_id", "=", province_id), ("code", "=", vals.get("code"))], limit=1)
            if existing:
                existing.write({"name": vals.get("name", existing.name), "active": vals.get("active", existing.active)})
                records |= existing
            else:
                records |= super(FpCanton, self).create([vals])
        return records

    def name_get(self):
        return [(record.id, f"{record.code} - {record.name}") for record in self]


class FpDistrict(models.Model):
    _name = "fp.district"
    _description = "Distrito"
    _order = "canton_id, code"

    code = fields.Char(string="Código", required=True)
    name = fields.Char(string="Nombre", required=True)
    canton_id = fields.Many2one("fp.canton", string="Cantón", required=True, ondelete="restrict")
    province_id = fields.Many2one(
        "fp.province",
        string="Provincia",
        related="canton_id.province_id",
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)

    _fp_district_code_unique_per_canton = models.Constraint(
        "UNIQUE(canton_id, code)",
        "El código de distrito debe ser único por cantón.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("install_mode"):
            return super().create(vals_list)

        records = self.browse()
        for vals in vals_list:
            canton_id = vals.get("canton_id")
            existing = self.search([("canton_id", "=", canton_id), ("code", "=", vals.get("code"))], limit=1)
            if existing:
                existing.write({"name": vals.get("name", existing.name), "active": vals.get("active", existing.active)})
                records |= existing
            else:
                records |= super(FpDistrict, self).create([vals])
        return records

    def name_get(self):
        return [(record.id, f"{record.code} - {record.name}") for record in self]
