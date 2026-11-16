"""Add refresh_tokens and auth_audit_log tables

Revision ID: 0006_refresh_tokens_and_audit_log
Revises: 0005_email_verification
Create Date: 2026-08-13 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006_refresh_and_audit_log'
down_revision = '0005_email_verification'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'refresh_tokens' not in tables:
        op.create_table(
            'refresh_tokens',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('token_hash', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('user_agent', sa.String(), nullable=True),
            sa.Column('ip_address', sa.String(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_refresh_tokens_id'), 'refresh_tokens', ['id'], unique=False)
        op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
        op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=False)

    if 'auth_audit_log' not in tables:
        op.create_table(
            'auth_audit_log',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('event_type', sa.String(length=50), nullable=False),
            sa.Column('ip_address', sa.String(), nullable=True),
            sa.Column('user_agent', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column('detail', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_auth_audit_log_id'), 'auth_audit_log', ['id'], unique=False)
        op.create_index(op.f('ix_auth_audit_log_user_id'), 'auth_audit_log', ['user_id'], unique=False)



def downgrade():
    op.drop_index(op.f('ix_auth_audit_log_user_id'), table_name='auth_audit_log')
    op.drop_index(op.f('ix_auth_audit_log_id'), table_name='auth_audit_log')
    op.drop_table('auth_audit_log')

    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
