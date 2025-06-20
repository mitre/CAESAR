"""add file discovery name field to bulletin

Revision ID: d010e7127040
Revises: 3a3d22d748e9
Create Date: 2024-05-29 19:30:56.465942

"""
from alembic import op
import sqlalchemy as sa
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = 'd010e7127040'
down_revision = '3a3d22d748e9'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('bulletin', schema=None) as batch_op:
        if not column_exists('bulletin', 'discovery_file_name', op):
            batch_op.add_column(sa.Column('discovery_file_name', sa.String(length=255), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('bulletin', schema=None) as batch_op:
        if column_exists('bulletin', 'discovery_file_name', op):
            batch_op.drop_column('discovery_file_name')

    # ### end Alembic commands ###
