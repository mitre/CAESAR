"""Add Archive Link and Translation Verified Fields

Revision ID: 1c7dfa336404
Revises: 20203b99987f
Create Date: 2024-11-20 17:02:12.807376

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = '1c7dfa336404'
down_revision = '20203b99987f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bulletin', schema=None) as batch_op:
        if not column_exists('bulletin', 'archive_link', op):
            batch_op.add_column(sa.Column('archive_link', sa.Text(), nullable=True))
        if not column_exists('bulletin', 'translation_verified', op):
            batch_op.add_column(sa.Column('translation_verified', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('bulletin', schema=None) as batch_op:
        if column_exists('bulletin', 'translation_verified', op):
            batch_op.drop_column('translation_verified')
        if column_exists('bulletin', 'archive_link', op):
            batch_op.drop_column('archive_link')
