"""Add media.blur

Revision ID: 80502355e29d
Revises: 9a14bfc4d02d
Create Date: 2024-02-02 15:00:15.052310

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '80502355e29d'
down_revision = '9a14bfc4d02d'
branch_labels = None
depends_on = None

def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('media', schema=None) as batch_op:
        if not column_exists('media', 'blur'):
            batch_op.add_column(sa.Column('blur', sa.Boolean(), nullable=True, server_default='f'))
        batch_op.alter_column('time',
               existing_type=sa.REAL(),
               type_=sa.Float(precision=2),
               existing_nullable=True)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.alter_column('time',
               existing_type=sa.Float(precision=2),
               type_=sa.REAL(),
               existing_nullable=True)
        batch_op.drop_column('blur')

    # ### end Alembic commands ###
