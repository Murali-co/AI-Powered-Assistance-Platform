"""Synchronize all remaining SQLAlchemy models with Alembic schema

Revision ID: 0015_sync_all_models
Revises: 0014_auth_audit_lockout_repair
Create Date: 2026-10-29 18:25:00.000000

This migration ensures that workflows, workflow_tasks, job_applications,
push_tokens, feedbacks, application_status_history, and missing columns
on users, applications_history, saved_jobs, and user_criteria are fully
reflected in the migration history for Neon PostgreSQL and test environments.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0015_sync_all_models'
down_revision = '0014_auth_audit_lockout_repair'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    # 1. Feedbacks table
    if 'feedbacks' not in tables:
        op.create_table(
            'feedbacks',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('feedback_text', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index('ix_feedbacks_id', 'feedbacks', ['id'])
        op.create_index('ix_feedbacks_user_id', 'feedbacks', ['user_id'])

    # 2. Job applications table
    if 'job_applications' not in tables:
        op.create_table(
            'job_applications',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('job_id', sa.String(), nullable=False),
            sa.Column('company', sa.String(), nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('location', sa.String(), nullable=True),
            sa.Column('job_url', sa.String(), nullable=True),
            sa.Column('applied_date', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('status', sa.String(), nullable=False, server_default='pending'),
            sa.Column('cover_letter', sa.Text(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index('ix_job_applications_id', 'job_applications', ['id'])
        op.create_index('ix_job_applications_user_id', 'job_applications', ['user_id'])
        op.create_index('ix_job_applications_job_id', 'job_applications', ['job_id'])

    # 3. Push tokens table
    if 'push_tokens' not in tables:
        op.create_table(
            'push_tokens',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('token', sa.String(), nullable=False, unique=True),
            sa.Column('device_type', sa.String(), nullable=True, server_default='web'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index('ix_push_tokens_id', 'push_tokens', ['id'])
        op.create_index('ix_push_tokens_user_id', 'push_tokens', ['user_id'])

    # 4. Application status history table
    if 'application_status_history' not in tables:
        if 'applications_history' not in tables:
            op.create_table(
                'applications_history',
                sa.Column('id', sa.String(), primary_key=True),
                sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
                sa.Column('job_id', sa.String(), nullable=False),
                sa.Column('job_title', sa.String(), nullable=False),
                sa.Column('company', sa.String(), nullable=False),
                sa.Column('applied_at', sa.DateTime(timezone=True), nullable=False),
                sa.Column('status', sa.String(), nullable=False, server_default='applied'),
                sa.Column('cover_letter', sa.Text(), nullable=False, server_default=''),
                sa.Column('resume_bullets', sa.Text(), nullable=False, server_default=''),
                sa.Column('notes', sa.Text(), nullable=False, server_default=''),
                sa.Column('location', sa.String(), nullable=True),
                sa.Column('job_url', sa.String(), nullable=True),
                sa.Column('resume_version_id', sa.Integer(), nullable=True),
                sa.Column('tone', sa.String(), nullable=True),
            )
            op.create_index('ix_applications_history_id', 'applications_history', ['id'])
            op.create_index('ix_applications_history_user_id', 'applications_history', ['user_id'])
            tables.append('applications_history')

        op.create_table(
            'application_status_history',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('application_id', sa.String(), sa.ForeignKey('applications_history.id'), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index('ix_application_status_history_id', 'application_status_history', ['id'])
        op.create_index('ix_application_status_history_application_id', 'application_status_history', ['application_id'])

    # 5. Workflows table
    if 'workflows' not in tables:
        op.create_table(
            'workflows',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('goal', sa.Text(), nullable=False),
            sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_workflows_id', 'workflows', ['id'])
        op.create_index('ix_workflows_user_id', 'workflows', ['user_id'])

    # 6. Workflow tasks table
    if 'workflow_tasks' not in tables:
        op.create_table(
            'workflow_tasks',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('task_id', sa.String(), nullable=False),
            sa.Column('workflow_id', sa.String(), sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
            sa.Column('task_type', sa.String(), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
            sa.Column('input_json', sa.Text(), nullable=True),
            sa.Column('output_json', sa.Text(), nullable=True),
            sa.Column('dependencies_json', sa.Text(), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_workflow_tasks_id', 'workflow_tasks', ['id'])
        op.create_index('ix_workflow_tasks_task_id', 'workflow_tasks', ['task_id'])
        op.create_index('ix_workflow_tasks_workflow_id', 'workflow_tasks', ['workflow_id'])

    # 7. Add missing columns to users
    if 'users' in tables:
        user_cols = [c['name'] for c in insp.get_columns('users')]
        with op.batch_alter_table('users') as batch_op:
            if 'email_notifications' not in user_cols:
                batch_op.add_column(sa.Column('email_notifications', sa.Boolean(), nullable=True, server_default='true'))
            if 'daily_digest' not in user_cols:
                batch_op.add_column(sa.Column('daily_digest', sa.Boolean(), nullable=True, server_default='true'))
            if 'scrape_frequency_hours' not in user_cols:
                batch_op.add_column(sa.Column('scrape_frequency_hours', sa.Integer(), nullable=True, server_default='12'))
            if 'auto_approve_external_actions' not in user_cols:
                batch_op.add_column(sa.Column('auto_approve_external_actions', sa.Boolean(), nullable=False, server_default='false'))

    # 8. Add missing columns to applications_history
    if 'applications_history' in tables:
        app_cols = [c['name'] for c in insp.get_columns('applications_history')]
        with op.batch_alter_table('applications_history') as batch_op:
            if 'location' not in app_cols:
                batch_op.add_column(sa.Column('location', sa.String(), nullable=True))
            if 'job_url' not in app_cols:
                batch_op.add_column(sa.Column('job_url', sa.String(), nullable=True))
            if 'resume_version_id' not in app_cols:
                batch_op.add_column(sa.Column('resume_version_id', sa.Integer(), nullable=True))
            if 'tone' not in app_cols:
                batch_op.add_column(sa.Column('tone', sa.String(), nullable=True))

    # 9. Add missing columns to saved_jobs
    if 'saved_jobs' in tables:
        saved_cols = [c['name'] for c in insp.get_columns('saved_jobs')]
        with op.batch_alter_table('saved_jobs') as batch_op:
            if 'notes' not in saved_cols:
                batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))
            if 'stage' not in saved_cols:
                batch_op.add_column(sa.Column('stage', sa.String(), nullable=True, server_default='saved'))

    # 10. Add missing columns to user_criteria
    if 'user_criteria' in tables:
        crit_cols = [c['name'] for c in insp.get_columns('user_criteria')]
        with op.batch_alter_table('user_criteria') as batch_op:
            if 'job_type' not in crit_cols:
                batch_op.add_column(sa.Column('job_type', sa.String(), nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()
    import logging
    mig_logger = logging.getLogger('alembic.runtime.migration')

    # Non-destructive downgrade: verify row counts before dropping to protect user data
    order = [
        'workflow_tasks', 'workflows', 'application_status_history',
        'push_tokens', 'job_applications', 'feedbacks'
    ]
    for tbl in order:
        if tbl in tables:
            try:
                count = conn.execute(sa.text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
                if count == 0:
                    op.drop_table(tbl)
                else:
                    mig_logger.warning(
                        "Preserving table '%s' during rollback because it contains %d records. "
                        "Manual backup and data migration required before dropping.",
                        tbl, count
                    )
            except Exception as e:
                mig_logger.error("Error inspecting table '%s' row count during rollback: %s", tbl, e)

