from odoo import fields, models


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

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
        help="Condición de venta según nota 5 de Anexos y Estructuras v4.4.",
    )
