"""add column buy_price to Asset

Revision ID: 44efa297005a
Revises: 
Create Date: 2023-02-02 12:20:23.890434

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '44efa297005a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('asset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('buy_price', sa.Float(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('asset', schema=None) as batch_op:
        batch_op.drop_column('buy_price')

    # ### end Alembic commands ###
