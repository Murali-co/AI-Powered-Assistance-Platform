"""Synthetic filter boundary fixtures in real isolated Neon; no live-source claim."""
from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest

from qa_tests.guards import require_test_database


@pytest.fixture(scope='module')
def catalog():
    require_test_database(os.environ.get('TEST_DATABASE_URL'), os.environ.get('APPLICATION_DATABASE_URL'))
    from app.db.session import SessionLocal
    from app.db.models import JobPosting
    marker = 'filter-check-' + uuid.uuid4().hex
    role = 'SyntheticAuditRole' + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    ids = [marker + '-' + str(index) for index in range(204)]
    rows = [dict(id=identifier, title='Unrelated Fixture Role', company='Synthetic Test Company',
        location='Delhi, India', description='Synthetic filter boundary fixture.',
        source_url='https://example.com/fixture/' + identifier, source_id='live:linkedin:' + identifier,
        posted_at=now - timedelta(minutes=1), is_active=True, job_type='onsite') for identifier in ids]
    rows[-3].update(title=role, location='Bengaluru, India', posted_at=now - timedelta(days=2), job_type='hybrid')
    rows[-2].update(title='Literal % ' + role, posted_at=now - timedelta(days=2))
    rows[-1].update(title=role, posted_at=now + timedelta(days=1))
    try:
        with SessionLocal.begin() as db:
            db.bulk_insert_mappings(JobPosting, rows)
        yield role, ids[-3], ids[-2], ids[-1]
    finally:
        with SessionLocal.begin() as db:
            db.query(JobPosting).filter(JobPosting.id.in_(ids)).delete(synchronize_session=False)


def test_criteria_are_applied_before_result_limit_and_city_aliases_agree(catalog):
    from app.jobs.repository import list_live_jobs
    role, target, _, future = catalog
    assert target not in {row['id'] for row in list_live_jobs(168)}
    selected = list_live_jobs(168, title=role, location='Bangalore', job_type='HYBRID')
    assert [row['id'] for row in selected] == [target]
    assert future not in {row['id'] for row in list_live_jobs(168, title=role)}


def test_search_wildcards_are_literal_keywords(catalog):
    from app.jobs.repository import list_live_jobs
    role, _, literal, _ = catalog
    assert [row['id'] for row in list_live_jobs(168, title='Literal % ' + role)] == [literal]
