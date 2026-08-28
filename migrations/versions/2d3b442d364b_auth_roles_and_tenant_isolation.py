"""auth roles and tenant isolation

Revision ID: 2d3b442d364b
Revises: ef01b3d6fa0c
Create Date: 2026-08-28 00:51:54.647837

Adds the ``users`` table, a ``tenant_id`` on ``payment_events``, and the reviewer
columns on ``outcomes``.

``tenant_id`` is NOT NULL with a server default, so existing rows land in the
``default`` tenant rather than blocking the upgrade. The idempotency key moves from
``(payment_id, attempt_id)`` to ``(tenant_id, payment_id, attempt_id)``: a gateway
identifier only has meaning inside the account that issued it, and a global key would
let one tenant discover another's payment IDs through the duplicate response. Existing
rows keep their uniqueness because they all share the default tenant.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d3b442d364b'
down_revision: Union[str, Sequence[str], None] = 'ef01b3d6fa0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('user_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('tenant_id', sa.String(length=80), server_default='default', nullable=False),
    sa.Column('is_active', sa.Integer(), server_default='1', nullable=False),
    sa.Column('created_at', sa.String(length=64), nullable=False),
    sa.Column('last_login_at', sa.String(length=64), nullable=True),
    sa.CheckConstraint("role IN ('VIEWER', 'OPERATOR', 'ADMIN')", name='ck_users_role_known'),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('username', name='uq_users_username')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index('ix_users_tenant_id', ['tenant_id'], unique=False)

    with op.batch_alter_table('outcomes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('resolved_by', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('resolved_at', sa.String(length=64), nullable=True))

    with op.batch_alter_table('payment_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=80), server_default='default', nullable=False))
        batch_op.drop_constraint(batch_op.f('uq_payment_events_payment_attempt'), type_='unique')
        batch_op.create_index('ix_payment_events_tenant_id', ['tenant_id'], unique=False)
        batch_op.create_unique_constraint('uq_payment_events_tenant_payment_attempt', ['tenant_id', 'payment_id', 'attempt_id'])



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('payment_events', schema=None) as batch_op:
        batch_op.drop_constraint('uq_payment_events_tenant_payment_attempt', type_='unique')
        batch_op.drop_index('ix_payment_events_tenant_id')
        batch_op.create_unique_constraint(batch_op.f('uq_payment_events_payment_attempt'), ['payment_id', 'attempt_id'])
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('outcomes', schema=None) as batch_op:
        batch_op.drop_column('resolved_at')
        batch_op.drop_column('resolved_by')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_tenant_id')

    op.drop_table('users')
