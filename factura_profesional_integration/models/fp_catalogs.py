from odoo import fields, models


class FpCabysCode(models.Model):
    _name = "fp.cabys.code"
    _description = "Código CABYS"
    _order = "code"

    code = fields.Char(string="Código", required=True)
    name = fields.Char(string="Descripción", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("fp_cabys_code_unique", "unique(code)", "El código CABYS debe ser único."),
    ]

    def name_get(self):
        return [(record.id, f"{record.code} - {record.name}") for record in self]


class FpEconomicActivity(models.Model):
    _name = "fp.economic.activity"
    _description = "Actividad Económica"
    _order = "code"

    code = fields.Char(string="Código", required=True)
    name = fields.Char(string="Descripción", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("fp_economic_activity_code_unique", "unique(code)", "El código de actividad económica debe ser único."),
    ]

    def name_get(self):
        return [(record.id, f"{record.code} - {record.name}") for record in self]
