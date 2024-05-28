"""Add ingested column to the media table

Revision ID: 7f1399fae812
Revises: 80502355e29d
Create Date: 2024-03-28 12:41:32.194804

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '7f1399fae812'
down_revision = '80502355e29d'
branch_labels = None
depends_on = None

def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)

def upgrade():
    with op.batch_alter_table('media', schema=None) as batch_op:
        if not column_exists('media', 'ingested'):
            batch_op.add_column(sa.Column('ingested', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.drop_column('ingested')
