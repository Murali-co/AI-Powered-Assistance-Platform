import pytest
import os
import json
from pathlib import Path
from app.auth.models import DBManager

def test_feedback_submission_endpoint(client):
    # 1. Register & Login
    client.post("/auth/register", json={
        "email": "feedback_tester@test.com",
        "password": "password123",
        "full_name": "Feedback Tester"
    })
    user = DBManager.get_user_by_email("feedback_tester@test.com")
    DBManager.verify_email(user["id"])
    login_res = client.post("/auth/login", json={
        "email": "feedback_tester@test.com",
        "password": "password123"
    })
    token = login_res.json()["access_token"]
    csrf_token = login_res.cookies.get("csrf_token")
    headers = {"Authorization": f"Bearer {token}"}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    # 2. Submit Feedback
    feedback_text = "This application is fantastic! The UI is very smooth."
    
    # Ensure any pre-existing feedback file is cleaned up first for clean test
    feedback_file = Path("./data/feedbacks.json")
    if feedback_file.exists():
        try:
            feedback_file.unlink()
        except Exception:
            pass

    response = client.post("/feedback/submit", json={"feedback": feedback_text}, headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Feedback submitted successfully. Thank you!"

    # 3. Verify local file persistence
    assert feedback_file.exists()
    with open(feedback_file, "r") as f:
        data = json.load(f)
    
    assert data[0]["user_name"] == "Feedback Tester"
    assert data[0]["user_email"] == "feedback_tester@test.com"
    assert data[0]["feedback"] == feedback_text

    # 4. Verify database persistence
    from app.db.session import SessionLocal
    from app.db.models import Feedback
    db = SessionLocal()
    try:
        db_feedbacks = db.query(Feedback).all()
        assert len(db_feedbacks) == 1
        assert db_feedbacks[0].feedback_text == feedback_text
    finally:
        db.close()
