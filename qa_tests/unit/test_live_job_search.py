from datetime import datetime, timedelta, timezone
import importlib
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.jobs.dates import posted_datetime, posted_iso
from app.jobs.filter import JobFilter
from app.models.schemas import JobOut


def listing(days=2, **kwargs):
    return {'id': 'live-job', 'title': 'Software Engineer', 'company': 'Real Source Fixture',
            'location': 'Bangalore', 'description': 'Build software.', 'url': 'https://www.linkedin.com/jobs/view/123',
            'posted_at': posted_iso(datetime.now(timezone.utc) - timedelta(days=days)),
            'source': 'linkedin', 'live_verified': True, **kwargs}


@pytest.mark.parametrize('value', [None, '', 'Recently', 'NaT', 'nan', 'invalid', float('nan')])
def test_unknown_posting_date_never_becomes_now(value):
    assert posted_datetime(value) is None


def test_four_and_seven_day_windows_and_fake_listing_exclusion():
    jobs = [listing(2, id='two'), listing(5, id='five'), listing(8, id='eight'),
            listing(0, id='future', posted_at=posted_iso(datetime.now(timezone.utc) + timedelta(days=1))),
            listing(id='template', source='sample'), listing(id='unverified', live_verified=False),
            listing(id='unknown', posted_at='Recently', posted_ts=datetime.now(timezone.utc).timestamp())]
    assert [j['id'] for j in JobFilter.live_jobs(jobs, 96)] == ['two']
    assert [j['id'] for j in JobFilter.live_jobs(jobs, 168)] == ['two', 'five']


def test_numeric_posted_timestamp_serializes_in_api():
    job = JobOut(**listing(posted_ts=datetime.now(timezone.utc).timestamp()))
    assert isinstance(job.posted_ts, float)


def test_remote_arrangement_is_not_lost_when_city_is_present():
    job = listing(location='Bangalore', job_type='remote')
    assert JobFilter.filter_jobs([job], location='Remote', is_remote=True) == [job]


def test_bangalore_and_bengaluru_are_the_same_search_location():
    job = listing(location='Bengaluru, Karnataka, India')
    assert JobFilter.filter_jobs([job], location='Bangalore') == [job]
    reverse = listing(location='Bangalore, India')
    assert JobFilter.filter_jobs([reverse], location='Bengaluru') == [reverse]


def test_scraper_keeps_source_posting_date_and_drops_unknown_or_stale(monkeypatch):
    from app.jobs.scraper import JobScraper
    monkeypatch.setenv('TESTING', 'true')
    monkeypatch.setattr(JobScraper, 'run_jobspy', lambda *args: [listing(), listing(9), listing(posted_at='Recently')])
    jobs = JobScraper.scrape('Software Engineer', 'Bangalore', 10, 96)
    assert len(jobs) == 1
    assert jobs[0]['live_verified'] is True
    assert posted_datetime(jobs[0]['posted_at']) < datetime.now(timezone.utc) - timedelta(days=1)


def test_live_list_uses_explicit_title_instead_of_other_saved_role(monkeypatch):
    module = importlib.import_module('app.jobs.router')
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_current_user] = lambda: {'id': 42}
    monkeypatch.setattr(module.DBManager, 'get_criteria', lambda uid: {'title': 'Full Stack Developer', 'location': 'Any'})
    monkeypatch.setattr(module, 'list_live_jobs', lambda hours: [listing(), listing(title='Full Stack Developer', description='Frontend only')])
    with TestClient(app) as client:
        response = client.get('/jobs/list', params={'title': 'Software Engineer', 'hours_old': 96})
    assert response.status_code == 200
    assert [job['title'] for job in response.json()['jobs']] == ['Software Engineer']


@pytest.mark.asyncio
async def test_resume_role_search_preserves_explicit_user_title(monkeypatch):
    module = importlib.import_module('app.resume.router')
    save = MagicMock()
    scrape = MagicMock(return_value=[])
    monkeypatch.setattr(module.DBManager, 'get_criteria', lambda uid: {'title': 'Software Engineer'})
    monkeypatch.setattr(module.DBManager, 'save_criteria', save)
    monkeypatch.setattr(module.JobScraper, 'scrape', scrape)
    await module._trigger_role_based_live_search(42, ['Full Stack Developer', 'Backend Developer'], hours_old=168)
    save.assert_not_called()
    assert scrape.call_count == 1
    assert scrape.call_args.kwargs['search_term'] == 'Software Engineer'
