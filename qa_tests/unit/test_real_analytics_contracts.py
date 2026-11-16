from datetime import date


def test_empty_market_never_becomes_simulated_hiring_or_demand():
    from app.market.router import trending_skills, hiring_timeline, parse_relative_date
    assert trending_skills([]) == []
    assert all(day['jobs_count'] == 0 for day in hiring_timeline([]))
    assert parse_relative_date('Recently') is None
    assert parse_relative_date('2026-11-12T12:00:00Z') == '2026-11-12'


def test_demand_counts_each_skill_once_per_actual_listing():
    from app.market.router import trending_skills, hiring_timeline
    jobs = [{'description': 'Python Python FastAPI', 'posted_at': '2026-11-15T10:00:00Z'},
            {'description': 'Python SQL', 'posted_at': '2026-11-14T10:00:00Z'}]
    counts = {entry['skill']: entry['count'] for entry in trending_skills(jobs)}
    assert counts['Python'] == 2 and counts['FastAPI'] == 1
    timeline = hiring_timeline(jobs, today=date(2026, 11, 15))
    assert sum(day['jobs_count'] for day in timeline) == 2


def test_score_distribution_uses_only_observed_scores_and_keeps_zero():
    from app.analytics.router import score_distribution
    empty = score_distribution([])
    assert empty['sample_size'] == 0 and empty['average_match'] is None
    jobs = [{'match_score': value} for value in [0, 20, 40, 60, 80, 100, None, float('nan')]]
    result = score_distribution(jobs)
    assert [entry['count'] for entry in result['bins']] == [1, 1, 1, 1, 2]
    assert result['average_match'] == 50 and result['sample_size'] == 6
