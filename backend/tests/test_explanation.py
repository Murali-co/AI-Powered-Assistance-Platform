import pytest
from unittest.mock import patch, MagicMock
from app.jobs.matcher import JobMatcher

@patch("app.llm.ollama_client.OllamaClient.generate")
@patch("app.vector_db.profile_store.ProfileStore.get_profile")
def test_job_explanation_endpoint(mock_get_profile, mock_llm, client):
    # Register & Login
    client.post("/auth/register", json={
        "email": "explain_tester@test.com",
        "password": "password123",
        "full_name": "Explain Tester"
    })
    from app.auth.models import DBManager
    user = DBManager.get_user_by_email("explain_tester@test.com")
    DBManager.verify_email(user["id"])

    login_res = client.post("/auth/login", json={
        "email": "explain_tester@test.com",
        "password": "password123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Setup profile mock
    mock_get_profile.return_value = {
        "skills": ["Python", "FastAPI"],
        "resume_text": "Experienced Python and FastAPI backend developer."
    }

    # Seed mock job into job_listings
    mock_job = [
        {
            "id": "job_to_explain",
            "title": "FastAPI developer",
            "company": "Fast Inc",
            "location": "Remote",
            "description": "Looking for a FastAPI and Python developer with Docker skills.",
            "url": "http://example.com/explain",
            "posted_at": "now",
            "source": "manual"
        }
    ]
    JobMatcher.upsert_jobs(mock_job)

    # Mock LLM JSON output
    mock_llm.return_value = """
    {
        "experience_gap": "No significant experience gap found.",
        "education_gap": "Education requirements met.",
        "keyword_gap": ["Docker"],
        "recommendations": ["Learn Docker containers next."]
    }
    """

    # Request explanation
    response = client.get("/jobs/explain/job_to_explain", headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert "score" in data
    assert "matched_skills" in data
    assert "missing_skills" in data
    assert "experience_gap" in data
    assert "education_gap" in data
    assert "keyword_gap" in data
    assert "recommendations" in data

    assert "Docker" in data["missing_skills"]
    assert "Python" in data["matched_skills"]
    assert "Docker" in data["keyword_gap"]
    assert "Learn Docker containers next." in data["recommendations"]
