from fastapi import HTTPException
import pytest

from app.jobs.matcher import cosine_match_score, MatchNarrative


def test_explanation_score_uses_the_requested_jobs_vector():
    assert cosine_match_score([1, 0], [1, 0]) == 100
    assert cosine_match_score([1, 0], [0, 1]) == 0
    assert cosine_match_score([1, 0], [-1, 0]) == 0


@pytest.mark.parametrize('left,right', [([0, 0], [1, 0]), ([1], [1, 0]), ([float('nan')], [1])])
def test_invalid_vectors_never_become_a_default_match_score(left, right):
    with pytest.raises(HTTPException):
        cosine_match_score(left, right)


def test_match_explanation_rejects_fields_that_would_crash_the_ui():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        MatchNarrative(experience_gap='Unknown', education_gap='Unknown', keyword_gap='Docker', recommendations='Learn Docker')
