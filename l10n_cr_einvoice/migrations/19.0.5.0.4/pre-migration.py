from odoo.tools.sql import column_exists


def _ensure_partner_fe_columns(cr):
    table = "res_partner"
    missing_columns = {
        "fp_identification_type": "varchar",
        "fp_canton_code": "varchar",
        "fp_district_code": "varchar",
        "fp_neighborhood_code": "varchar",
    }

    for column_name, sql_type in missing_columns.items():
        if not column_exists(cr, table, column_name):
            cr.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {sql_type}")


def migrate(cr, version):
    _ensure_partner_fe_columns(cr)
