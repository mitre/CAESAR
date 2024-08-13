"""Split Primary Record datetimes to date and time

Revision ID: 3f5a4c7479f9
Revises: 70a1e80a026d
Create Date: 2024-08-02 18:44:17.063582

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from migrations.utils import create_datetime, column_exists, split_datetime

# revision identifiers, used by Alembic.
revision = '3f5a4c7479f9'
down_revision = '70a1e80a026d'
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists('bulletin', 'publish_time', op):
        split_datetime('bulletin', 'publish_date', 'publish_time', op)
    if not column_exists('event', 'from_time', op):
        split_datetime('event', 'from_date', 'from_time', op)
    if not column_exists('event', 'to_time', op):
        split_datetime('event', 'to_date', 'to_time', op)

def downgrade():
    if column_exists('bulletin', 'publish_time', op):
        create_datetime('bulletin', 'publish_date', 'publish_time', op)
    if column_exists('event', 'from_time', op):
        create_datetime('event', 'from_date', 'from_time', op)
    if column_exists('event', 'to_time', op):
        create_datetime('event', 'to_date', 'to_time', op)
