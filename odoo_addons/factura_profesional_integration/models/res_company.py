from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    fp_api_base_url = fields.Char(string="Factura API Base URL")
    fp_api_token = fields.Char(string="Factura API Token")
    fp_api_timeout = fields.Integer(string="Factura API Timeout (s)", default=30)
