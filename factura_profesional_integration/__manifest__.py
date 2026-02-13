{
    "name": "Factura Profesional API Connector",
    "summary": "Envía facturas de Odoo 19 a un API externo para generar XML",
    "version": "19.0.2.0.0",
    "category": "Accounting",
    "license": "LGPL-3",
    "depends": ["account", "product", "uom"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
        "views/account_move_views.xml",
        "views/account_tax_views.xml",
        "views/account_journal_views.xml",
        "views/product_template_views.xml",
        "views/uom_uom_views.xml",
    ],
    "installable": True,
    "application": True,
}
