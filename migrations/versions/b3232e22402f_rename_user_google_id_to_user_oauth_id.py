
"""Rename user.google_id to user.oauth_id

Revision ID: b3232e22402f
Revises: 7f1399fae812
Create Date: 2024-04-08 18:01:59.937836

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'b3232e22402f'
down_revision = '7f1399fae812'
branch_labels = None
depends_on = None

def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)

def upgrade():
    if column_exists('user', 'google_id'):
        op.alter_column('user', 'google_id', new_column_name='oauth_id')


def downgrade():
    if column_exists('user', 'oauth_id'):
        op.alter_column('user', 'oauth_id', new_column_name='google_id')