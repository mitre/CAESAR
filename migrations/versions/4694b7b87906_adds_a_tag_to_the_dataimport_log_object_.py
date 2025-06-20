"""adds a tag to the dataimport log object to prevent duplicate downloads

Revision ID: 4694b7b87906
Revises: 788c189dc05c
Create Date: 2024-10-23 16:34:49.602520

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import column_exists

# revision identifiers, used by Alembic.
revision = '4694b7b87906'
down_revision = '788c189dc05c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('data_import', schema=None) as batch_op:
        if not column_exists('data_import', 'import_hash', op):
            batch_op.add_column(sa.Column('import_hash', sa.String(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###

    with op.batch_alter_table('data_import', schema=None) as batch_op:
        batch_op.drop_column('import_hash')

    # ### end Alembic commands ###
