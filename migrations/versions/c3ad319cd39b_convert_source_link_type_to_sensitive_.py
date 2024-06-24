"""Convert source_link_type to sensitive_data

Revision ID: c3ad319cd39b
Revises: d010e7127040
Create Date: 2024-06-20 12:58:49.433496

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = 'c3ad319cd39b'
down_revision = 'd010e7127040'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('actor', schema=None) as batch_op:
        if column_exists('actor', 'source_link_type', op):
            batch_op.drop_column('source_link_type')

        if not column_exists('actor', 'sensitive_data', op):
            batch_op.add_column(sa.Column('sensitive_data', sa.Boolean(), nullable=True, server_default='False'))

    with op.batch_alter_table('bulletin', schema=None) as batch_op:
        if column_exists('bulletin', 'source_link_type', op):
            batch_op.drop_column('source_link_type')

        if not column_exists('bulletin', 'sensitive_data', op):
            batch_op.add_column(sa.Column('sensitive_data', sa.Boolean(), nullable=True, server_default='False'))

def downgrade():
    with op.batch_alter_table('bulletin', schema=None) as batch_op:
        if column_exists('bulletin', 'sensitive_data', op):
            batch_op.drop_column('sensitive_data')

        if not column_exists('bulletin', 'source_link_type', op):
            batch_op.add_column(sa.Column('source_link_type', sa.BOOLEAN(), autoincrement=False, nullable=True, server_default='False'))

    with op.batch_alter_table('actor', schema=None) as batch_op:
        if column_exists('actor', 'sensitive_data', op):
            batch_op.drop_column('sensitive_data')
        
        if not column_exists('actor', 'source_link_type', op):
            batch_op.add_column(sa.Column('source_link_type', sa.BOOLEAN(), autoincrement=False, nullable=True, server_default='False'))
