from odoo.tools.sql import column_exists


def _add_missing_m2o_column(cr, table_name):
    if not column_exists(cr, table_name, "fp_economic_activity_id"):
        cr.execute(f"ALTER TABLE {table_name} ADD COLUMN fp_economic_activity_id integer")


def _backfill_from_code(cr, table_name):
    if not column_exists(cr, table_name, "fp_economic_activity_code"):
        return

    cr.execute(
        f"""
        UPDATE {table_name} AS t
           SET fp_economic_activity_id = a.id
          FROM fp_economic_activity AS a
         WHERE t.fp_economic_activity_id IS NULL
           AND t.fp_economic_activity_code IS NOT NULL
           AND a.code = t.fp_economic_activity_code
        """
    )


def migrate(cr, version):
    _add_missing_m2o_column(cr, "res_company")
    _add_missing_m2o_column(cr, "account_move")

    _backfill_from_code(cr, "res_company")
    _backfill_from_code(cr, "account_move")
