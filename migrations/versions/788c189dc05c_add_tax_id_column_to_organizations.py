"""Add tax_id column to organizations

Revision ID: 788c189dc05c
Revises: 7fda62cc1156
Create Date: 2024-10-11 20:47:30.292313

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = '788c189dc05c'
down_revision = '7fda62cc1156'
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists('organization', 'tax_id', op):
        with op.batch_alter_table('organization', schema=None) as batch_op:
            batch_op.add_column(sa.Column('tax_id', sa.String(length=255), nullable=True))


def downgrade():
    if column_exists('organization', 'tax_id', op):
        with op.batch_alter_table('organization', schema=None) as batch_op:
            batch_op.drop_column('tax_id')
