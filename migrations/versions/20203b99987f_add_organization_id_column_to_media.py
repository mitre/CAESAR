"""Add organization_id column to media

Revision ID: 20203b99987f
Revises: fe35c88220ce
Create Date: 2024-11-15 14:55:23.357962

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = '20203b99987f'
down_revision = 'fe35c88220ce'
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists('media', 'organization_id', op):
        with op.batch_alter_table('media', schema=None) as batch_op:
            batch_op.add_column(sa.Column('organization_id', sa.Integer(), nullable=True))


def downgrade():
    if column_exists('media', 'organization_id', op):
        with op.batch_alter_table('media', schema=None) as batch_op:
            batch_op.drop_column('organization_id')