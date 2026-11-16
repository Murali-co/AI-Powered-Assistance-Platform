from unittest.mock import Mock
import pytest


def test_only_missing_canonical_jobs_are_reindexed_without_claiming_new_verification(monkeypatch):
    from app.jobs.matcher import JobMatcher
    from app.jobs import repository
    from app.jobs import matcher
    jobs = [dict(id=identifier, title='Software Engineer', company='Synthetic Company',
        description='Python services', location='Any', source='test', url='https://example.com/job/' + identifier,
        posted_at='2026-11-15T12:00:00Z', live_verified=True) for identifier in ('existing', 'missing')]
    monkeypatch.setattr(repository, 'list_live_jobs', lambda hours: jobs)
    indexed = {'existing': {'canonical_id': 'existing'}}
    collection = Mock()
    collection.get.side_effect = lambda **kwargs: {'ids': list(indexed), 'metadatas': list(indexed.values())}
    collection.upsert.side_effect = lambda **kwargs: indexed.update(zip(kwargs['ids'], kwargs['metadatas']))
    monkeypatch.setattr(JobMatcher, 'get_collection', lambda: collection)
    embed = Mock(return_value=[[0.1, 0.2]])
    monkeypatch.setattr(matcher, 'embed_batch', embed)
    persist = Mock()
    monkeypatch.setattr(repository, 'persist_live_jobs', persist)
    assert JobMatcher.reconcile_live_index(168) == 1
    assert collection.upsert.call_args.kwargs['ids'] == ['missing']
    embed.assert_called_once_with(['Python services'])
    persist.assert_not_called()
    assert JobMatcher.reconcile_live_index(168) == 0
    assert embed.call_count == 1


def test_match_cache_cannot_republish_old_results_after_profile_or_catalog_invalidation():
    from app.jobs.matcher import MatchCache
    cache = MatchCache(max_entries=2)
    old_generation = cache.generation
    cache.clear()
    assert not cache.write(('user-a',), ['old result'], old_generation)
    assert cache.read(('user-a',)) is None
    assert cache.write(('user-a',), ['new result'], cache.generation)
    assert cache.read(('user-b',)) is None
    for key in ('b', 'c'):
        cache.write((key,), [key], cache.generation)
    assert len(cache.entries) == 2


def test_match_cache_expiration(monkeypatch):
    from app.jobs import matcher
    clock = [10.0]
    monkeypatch.setattr(matcher.time, 'monotonic', lambda: clock[0])
    cache = matcher.MatchCache(ttl=30)
    cache.write(('owner',), [], cache.generation)
    assert cache.read(('owner',)) == []
    clock[0] = 40.0
    assert cache.read(('owner',)) is None


@pytest.mark.parametrize('stage', ['unmatched', 'filter', 'query'])
def test_vector_outage_never_becomes_a_successful_empty_match_list(monkeypatch, stage):
    from fastapi import HTTPException
    from app.jobs.matcher import JobMatcher
    from app.jobs import matcher
    JobMatcher._match_cache.clear()
    monkeypatch.setattr(JobMatcher, 'reconcile_live_index', lambda *_, **__: 0)
    monkeypatch.setattr(matcher.DBManager, 'get_criteria', lambda _: {})
    monkeypatch.setattr(__import__('app.jobs.repository', fromlist=['list_live_jobs']), 'list_live_jobs', lambda *_, **__: [{'id': 'job'}])
    collection = Mock()
    collection.count.return_value = 1
    collection.get.return_value = {'ids': ['job']}
    collection.query.side_effect = RuntimeError('vector service unavailable')
    if stage in {'unmatched', 'filter'}:
        collection.get.side_effect = RuntimeError('vector service unavailable')
    monkeypatch.setattr(JobMatcher, 'get_collection', lambda: collection)
    profile = None if stage == 'unmatched' else {'resume_text': 'Python services', 'skills': ['Python']}
    monkeypatch.setattr(matcher.ProfileStore, 'get_profile', lambda _: profile)
    profile_collection = Mock()
    profile_collection.get.return_value = {'embeddings': [[0.1, 0.2]]}
    monkeypatch.setattr(matcher.ProfileStore, 'get_collection', lambda: profile_collection)
    with pytest.raises(HTTPException) as error:
        JobMatcher.match_jobs_for_user(42, hours_old=168)
    assert error.value.status_code == 503
    assert not JobMatcher._match_cache.entries
