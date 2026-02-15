from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    fp_is_electronic_invoice = fields.Boolean(
        string="Usa FE 4.4",
        help="Si está activo, las facturas de este diario mostrarán campos y acciones de FE.",
    )
