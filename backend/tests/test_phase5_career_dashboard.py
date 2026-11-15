import pytest
import json
from unittest.mock import patch
from app.auth.models import DBManager
from app.services.privacy_service import PrivacyPreservingEngine
from app.resume.tailor_constrained import ConstrainedCareerTailor


def test_privacy_preservation_and_factual_verification():
    """Verify Presidio PII anonymization and constrained factual claim verification."""
    # 1. PII Anonymization
    raw_text = (
        "John Doe is a Senior Python Developer reachable at john.doe@example.com or +1-555-019-2834. "
        "Resides at 1234 Elm Street, Austin, TX. Built high throughput backend systems."
    )
    anon_result = PrivacyPreservingEngine.anonymize_text(raw_text)
    masked_text = anon_result["anonymized_text"]
    
    # Must mask email, phone, and name
    assert "john.doe@example.com" not in masked_text
    assert "+1-555-019-2834" not in masked_text
    assert anon_result["masked_count"] > 0
    assert len(anon_result["entities_detected"]) > 0

    # 2. Reversible de-anonymization / restoration
    restored = PrivacyPreservingEngine.restore_text(masked_text, anon_result["mapping"])
    assert "john.doe@example.com" in restored
    assert "+1-555-019-2834" in restored

    # 3. Constrained Factual Verification
    verified_profile = {
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "experience": [
            {
                "title": "Backend Engineer",
                "company": "Acme Corp",
                "bullets": ["Optimized SQL queries reducing query response latency by 35%"]
            }
        ]
    }
    # Candidate text with true claim vs fabricated claim
    grounded_bullet = "Optimized SQL queries reducing query response latency by 35% with PostgreSQL."
    fabricated_bullet = "Engineered deep learning self-driving car models increasing revenue by $500M at Apple."

    v_true = ConstrainedCareerTailor.verify_factual_grounding(grounded_bullet, verified_profile)
    v_false = ConstrainedCareerTailor.verify_factual_grounding(fabricated_bullet, verified_profile)

    assert v_true["is_grounded"] is True
    assert v_false["is_grounded"] is False
    assert len(v_false["unsupported_claims"]) > 0


def test_dashboard_overview_and_career_roadmap_workflows(client):
    """Integration test: verifies /dashboard/overview, roadmap milestones, and milestone status toggle."""
    # 1. Register & verify user
    client.post("/auth/register", json={
        "email": "dashboard_user@cognis.ai",
        "password": "Password123!",
        "full_name": "Dashboard Tester"
    })
    user = DBManager.get_user_by_email("dashboard_user@cognis.ai")
    DBManager.verify_email(user["id"])
    login_res = client.post("/auth/login", json={"email": "dashboard_user@cognis.ai", "password": "Password123!"})
    token = login_res.json()["access_token"]
    csrf = login_res.cookies.get("csrf_token")
    headers = {"Authorization": f"Bearer {token}"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
        client.cookies.set("csrf_token", csrf)

    # 2. Save verified profile via POST /profile/verified
    save_res = client.post(
        "/profile/verified",
        json={
            "full_name": "Dashboard Tester",
            "headline": "Senior Systems Engineer",
            "summary": "Experienced in distributed systems and cloud native architectures.",
            "skills": ["Python", "Go", "Kubernetes", "PostgreSQL"],
            "work_experience": [{"title": "Senior Engineer", "company": "TechCorp", "bullets": ["Built microservices"]}]
        },
        headers=headers
    )
    assert save_res.status_code == 200

    # 3. Call /dashboard/overview
    overview_res = client.get("/dashboard/overview", headers=headers)
    assert overview_res.status_code == 200
    ov_data = overview_res.json()
    assert ov_data["user"]["id"] == user["id"]
    assert "profile" in ov_data
    assert ov_data["profile"]["skills_count"] >= 4

    # 4. Call /profile/roadmap
    roadmap_res = client.get("/profile/roadmap", headers=headers)
    assert roadmap_res.status_code == 200
    rm_data = roadmap_res.json()
    assert "milestones" in rm_data
    assert len(rm_data["milestones"]) > 0
    milestone_id = rm_data["milestones"][0]["id"]
    initial_status = rm_data["milestones"][0]["is_completed"]

    # 5. Toggle milestone completion status
    toggle_res = client.patch(
        f"/profile/roadmap/milestones/{milestone_id}",
        json={"is_completed": not initial_status},
        headers=headers
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_completed"] == (not initial_status)


def test_multi_resume_version_crud_and_isolation(client):
    """Integration test: create, preview, compare, download, and delete resume versions with ownership enforcement."""
    # 1. Register User 1
    client.post("/auth/register", json={
        "email": "resume_owner@cognis.ai",
        "password": "Password123!",
        "full_name": "Resume Owner"
    })
    user1 = DBManager.get_user_by_email("resume_owner@cognis.ai")
    DBManager.verify_email(user1["id"])
    login1 = client.post("/auth/login", json={"email": "resume_owner@cognis.ai", "password": "Password123!"})
    token1 = login1.json()["access_token"]
    csrf1 = login1.cookies.get("csrf_token")
    headers1 = {"Authorization": f"Bearer {token1}"}
    if csrf1:
        headers1["X-CSRF-Token"] = csrf1
        client.cookies.set("csrf_token", csrf1)

    # 2. Register User 2 (Attacker/Separate user)
    client.post("/auth/register", json={
        "email": "resume_intruder@cognis.ai",
        "password": "Password123!",
        "full_name": "Resume Intruder"
    })
    user2 = DBManager.get_user_by_email("resume_intruder@cognis.ai")
    DBManager.verify_email(user2["id"])
    login2 = client.post("/auth/login", json={"email": "resume_intruder@cognis.ai", "password": "Password123!"})
    token2 = login2.json()["access_token"]
    csrf2 = login2.cookies.get("csrf_token")
    headers2 = {"Authorization": f"Bearer {token2}"}
    if csrf2:
        headers2["X-CSRF-Token"] = csrf2

    # Switch cookie back to User 1
    if csrf1:
        client.cookies.set("csrf_token", csrf1)

    # 3. User 1 creates Version A
    create_res_a = client.post(
        "/resume/versions/create",
        json={
            "version_label": "Senior Backend Architect v1",
            "target_role": "Backend Architect",
            "resume_text": "Experienced Python and distributed systems architect with 8 years building cloud platforms."
        },
        headers=headers1
    )
    assert create_res_a.status_code == 200
    v1_id = create_res_a.json()["id"]

    # 4. User 1 creates Version B
    create_res_b = client.post(
        "/resume/versions/create",
        json={
            "version_label": "Machine Learning Platform Engineer v2",
            "target_role": "MLOps Engineer",
            "resume_text": "Specialized in scalable model serving, PyTorch inference optimization, and Kubernetes pipelines."
        },
        headers=headers1
    )
    assert create_res_b.status_code == 200
    v2_id = create_res_b.json()["id"]

    # 5. Preview Version A
    prev_res = client.get(f"/resume/versions/{v1_id}/preview", headers=headers1)
    assert prev_res.status_code == 200
    assert "distributed systems" in prev_res.json()["resume_text"]
    assert prev_res.json()["target_role"] == "Backend Architect"

    # 6. Compare Version A vs Version B
    comp_res = client.get(f"/resume/versions/compare?id1={v1_id}&id2={v2_id}", headers=headers1)
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert "diff_lines" in comp_data
    assert comp_data["version_1"]["id"] == v1_id
    assert comp_data["version_2"]["id"] == v2_id

    # 7. Download Version A
    dl_res = client.get(f"/resume/versions/{v1_id}/download", headers=headers1)
    assert dl_res.status_code == 200
    dl_data = dl_res.json()
    assert "distributed systems" in dl_data["content"]
    assert dl_data["target_role"] == "Backend Architect"

    # 8. User Isolation Check: User 2 tries to delete User 1's version -> must be rejected (404)
    if csrf2:
        client.cookies.set("csrf_token", csrf2)
    unauth_del = client.delete(f"/resume/versions/{v1_id}", headers=headers2)
    assert unauth_del.status_code == 404

    # 9. User 1 successfully deletes own version
    if csrf1:
        client.cookies.set("csrf_token", csrf1)
    del_res = client.delete(f"/resume/versions/{v1_id}", headers=headers1)
    assert del_res.status_code == 200
