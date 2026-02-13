from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fp_api_base_url = fields.Char(related="company_id.fp_api_base_url", readonly=False)
    fp_api_token = fields.Char(related="company_id.fp_api_token", readonly=False)
    fp_api_timeout = fields.Integer(related="company_id.fp_api_timeout", readonly=False)

    fp_economic_activity_code = fields.Char(related="company_id.fp_economic_activity_code", readonly=False)
