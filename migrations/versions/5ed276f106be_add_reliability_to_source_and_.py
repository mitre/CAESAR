"""Add reliability to source and credibility to primary record

Revision ID: 5ed276f106be
Revises: 6dd1ac87ad7e
Create Date: 2024-06-26 12:56:36.035010

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = '5ed276f106be'
down_revision = '6dd1ac87ad7e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('source', schema=None) as batch_op:
        if not column_exists('source', 'reliability', op):
            batch_op.add_column(sa.Column('reliability', sa.String(), nullable=True))
    
    with op.batch_alter_table('bulletin', schema=None) as batch_op:
        if not column_exists('bulletin', 'credibility', op):
            batch_op.add_column(sa.Column('credibility', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('source', schema=None) as batch_op:
        if column_exists('source', 'reliability', op):
            batch_op.drop_column('reliability')
    
    with op.batch_alter_table('bulletin', schema=None) as batch_op:
        if column_exists('bulletin', 'credibility', op):
            batch_op.drop_column('credibility')
