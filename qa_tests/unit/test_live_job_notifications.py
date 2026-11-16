import importlib
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_match_alerts_cover_only_newly_fetched_jobs(monkeypatch):
    module = importlib.import_module('app.jobs.router')
    from app.vector_db.profile_store import ProfileStore
    monkeypatch.setattr(ProfileStore, 'get_profile', lambda uid: {'resume_text': 'Python API project'})
    monkeypatch.setattr(module.JobMatcher, 'match_jobs_for_user', lambda *args, **kwargs: [
        {'id': 'new', 'title': 'Software Engineer', 'company': 'Source Fixture', 'match_score': 90},
        {'id': 'old', 'title': 'Old Role', 'company': 'Old Fixture', 'match_score': 95},
    ])
    alert = MagicMock()
    monkeypatch.setattr(module.DBManager, 'add_notification', alert)
    await module.notify_live_matches(42, [{'id': 'new'}], 96)
    assert alert.call_count == 1
    assert alert.call_args.kwargs['user_id'] == 42
    assert 'Software Engineer' in alert.call_args.kwargs['message']
