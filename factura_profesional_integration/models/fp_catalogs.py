from odoo import fields, models


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

    def name_get(self):
        return [(record.id, f"{record.code} - {record.name}") for record in self]
