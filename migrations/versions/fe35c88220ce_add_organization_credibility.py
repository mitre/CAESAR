"""Add organization credibility

Revision ID: fe35c88220ce
Revises: 6bd1eb5fcb42
Create Date: 2024-11-14 22:00:12.405782

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = 'fe35c88220ce'
down_revision = '6bd1eb5fcb42'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organization', schema=None) as batch_op:
        if not column_exists('organization', 'credibility', op):
            batch_op.add_column(sa.Column('credibility', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('organization', schema=None) as batch_op:
        if column_exists('organization', 'credibility', op):
            batch_op.drop_column('credibility')