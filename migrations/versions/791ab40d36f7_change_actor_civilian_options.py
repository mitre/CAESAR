"""Change actor.civilian options

Revision ID: 791ab40d36f7
Revises: 1c7dfa336404
Create Date: 2024-11-14 19:47:49.233714

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '791ab40d36f7'
down_revision = '1c7dfa336404'
branch_labels = None
depends_on = None


def upgrade():
    # Unset actor.civilian when it's 'Non-Civilian'
    op.execute(f"UPDATE actor SET civilian=NULL WHERE civilian='Non-Civilian';")


def downgrade():
    # Unset actor.civilian when it's 'Legislator'
    op.execute(f"UPDATE actor SET civilian=NULL WHERE civilian='Legislator';")
    
    # Unset actor.civilian when it's 'Govt Official (non-military)'
    op.execute(f"UPDATE actor SET civilian=NULL WHERE civilian='Govt Official (non-military)';")
    
    # Unset actor.civilian when it's 'Military'
    op.execute(f"UPDATE actor SET civilian=NULL WHERE civilian='Military';")
    
    # Unset actor.civilian when it's 'Paramilitary'
    op.execute(f"UPDATE actor SET civilian=NULL WHERE civilian='Paramilitary';")
