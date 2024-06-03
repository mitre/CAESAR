from sqlalchemy import inspect

def column_exists(table_name, column_name, op):
    bind = op.get_context().bind
    insp = inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)
