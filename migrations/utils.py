import sqlalchemy as sa

def column_exists(table_name, column_name, op):
    bind = op.get_context().bind
    insp = sa.inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)

""" 
Splits the existing timestamp column into separate date and time columns.
The new date column will have the same name as the date_column provided.
"""
def split_datetime(table_name, date_column, time_column, op):
    transition_column = f'{date_column}_original'

    # Add the time column
    op.add_column(table_name, sa.Column(time_column, sa.Time(), nullable=True))

    # Set time to the time part of date
    op.execute(f"UPDATE {table_name} SET {time_column} = CAST({date_column} as TIME);")

    # Rename date_column to transition_column
    op.alter_column(table_name, date_column, new_column_name=transition_column)

    # Add date_column column back
    op.add_column(table_name, sa.Column(date_column, sa.Date(), nullable=True))

    # Set publish_date to date part of publish_datetime
    op.execute(f"UPDATE {table_name} SET {date_column} = CAST({transition_column} as DATE);")

    # Drop transition column
    op.drop_column(table_name, transition_column)

"""
Takes a date_column and time_column and combines them into a single column 
with the same name as the existing date_column.
It drops the time column
"""
def create_datetime(table_name, date_column, time_column, op):
    transition_column = f'{date_column}_original'
    
    # Rename date column to date_column_original
    op.alter_column(table_name, date_column, new_column_name=transition_column)

    # Add date_column back in
    op.add_column(table_name, sa.Column(date_column, sa.DateTime(), nullable=True))

    # Combine publish_date_original and publish_time into a datetime for publish_date
    op.execute(f"UPDATE {table_name} SET {date_column} = (CAST({transition_column} as date) + CAST({time_column} as time))::TIMESTAMP;")

    # Drop the transition_column
    op.drop_column(table_name, transition_column)
    
    # Drop time_column
    op.drop_column(table_name, time_column)