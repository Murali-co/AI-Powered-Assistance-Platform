from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest


@pytest.mark.asyncio
async def test_malformed_ai_never_becomes_template_resume_or_invented_score(monkeypatch):
    from app.llm.ollama_client import OllamaClient
    from app.llm.skill_gap import SkillGapAnalyzer
    from app.llm.resume_tailor import ResumeTailorEngine, ResumeBulletTailor
    monkeypatch.setattr(OllamaClient, 'generate', AsyncMock(return_value='invalid JSON'))
    for call in (
        SkillGapAnalyzer.analyze(['Python'], 'Software Engineer'),
        ResumeTailorEngine.tailor('Built Python APIs.', 'Software Engineer'),
        ResumeBulletTailor.tailor_bullets('Built Python APIs.', 'Software Engineer'),
    ):
        with pytest.raises(HTTPException) as error:
            await call
        assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_empty_cover_letter_is_not_replaced_by_a_template(monkeypatch):
    from app.llm.cover_letter import CoverLetterGenerator
    from app.llm.ollama_client import OllamaClient
    monkeypatch.setattr(OllamaClient, 'generate', AsyncMock(return_value=''))
    with pytest.raises(HTTPException) as error:
        await CoverLetterGenerator.generate('Built Python APIs.', 'Software Engineer')
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_gap_analysis_rejects_invented_present_skills_and_invalid_scores(monkeypatch):
    import json
    from app.llm.ollama_client import OllamaClient
    from app.llm.skill_gap import SkillGapAnalyzer
    for skills, score in [(['Kubernetes'], 80), (['Python'], 101)]:
        result = {'present_skills': skills, 'missing_skills': ['Go'], 'skill_score': score,
                  'recommendations': [], 'learning_resources': []}
        monkeypatch.setattr(OllamaClient, 'generate', AsyncMock(return_value=json.dumps(result)))
        with pytest.raises(HTTPException) as error:
            await SkillGapAnalyzer.analyze(['Python'], 'Software Engineer')
        assert error.value.status_code == 503


def test_two_stage_matching_keeps_results_outside_the_rerank_window(monkeypatch):
    from app.jobs import two_stage_matcher as module
    monkeypatch.setattr(module, 'get_cross_encoder_model', lambda *_: None)
    jobs = [{'id': str(i), 'description': 'Python APIs', 'bi_encoder_score': 70-i} for i in range(3)]
    result = module.TwoStageJobMatcher.rerank_with_cross_encoder('Python APIs', jobs, top_n=1)
    assert len(result) == 3
    assert result[1]['final_score'] == 69
    assert result[2]['final_score'] == 68
