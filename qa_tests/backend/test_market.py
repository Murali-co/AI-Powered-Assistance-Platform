import pytest
from app.auth.models import DBManager

def test_market_intelligence_endpoints(client):
    # Register & Login
    client.post("/auth/register", json={
        "email": "market_tester@test.com",
        "password": "password123",
        "full_name": "Market Tester"
    })
    user = DBManager.get_user_by_email("market_tester@test.com")
    DBManager.verify_email(user["id"])
    login_res = client.post("/auth/login", json={
        "email": "market_tester@test.com",
        "password": "password123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test Trending Skills
    skills_res = client.get("/market/trending-skills", headers=headers)
    assert skills_res.status_code == 200
    skills_data = skills_res.json()
    assert isinstance(skills_data, list)
    if len(skills_data) > 0:
        assert "skill" in skills_data[0]
        assert "count" in skills_data[0]

    # 2. Test Salary Insights
    salary_res = client.get("/market/salary-insights", headers=headers)
    assert salary_res.status_code == 200
    salary_data = salary_res.json()
    assert isinstance(salary_data, list)
    if len(salary_data) > 0:
        assert "role" in salary_data[0]
        assert "min" in salary_data[0]
        assert "max" in salary_data[0]
        assert "median" in salary_data[0]

    # 3. Test Hiring Trends
    trends_res = client.get("/market/hiring-trends", headers=headers)
    assert trends_res.status_code == 200
    trends_data = trends_res.json()
    assert isinstance(trends_data, list)
    if len(trends_data) > 0:
        assert "date" in trends_data[0]
        assert "jobs_count" in trends_data[0]
