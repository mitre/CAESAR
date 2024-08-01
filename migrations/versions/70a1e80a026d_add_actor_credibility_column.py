"""Add actor credibility column

Revision ID: 70a1e80a026d
Revises: 2a87f2bcf52a
Create Date: 2024-07-12 16:53:05.265984

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = '70a1e80a026d'
down_revision = '2a87f2bcf52a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('actor', schema=None) as batch_op:
        if not column_exists('actor', 'credibility', op):
            batch_op.add_column(sa.Column('credibility', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('actor', schema=None) as batch_op:
        if column_exists('actor', 'credibility', op):
            batch_op.drop_column('credibility')
