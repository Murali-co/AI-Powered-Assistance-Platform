from app.auth.models import DBManager

def test_register_user(client):
    response = client.post("/auth/register", json={
        "email": "tester@test.com",
        "password": "password123",
        "full_name": "Test User"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" not in data
    assert "message" in data

def test_register_duplicate_user(client):
    # Register first
    client.post("/auth/register", json={
        "email": "tester2@test.com",
        "password": "password123",
        "full_name": "Test User"
    })
    
    # Register second
    response = client.post("/auth/register", json={
        "email": "tester2@test.com",
        "password": "password123",
        "full_name": "Test User"
    })
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

def test_login_user(client):
    # Register first
    client.post("/auth/register", json={
        "email": "tester3@test.com",
        "password": "password123",
        "full_name": "Test User"
    })
    user = DBManager.get_user_by_email("tester3@test.com")
    DBManager.verify_email(user["id"])
    
    # Login
    response = client.post("/auth/login", json={
        "email": "tester3@test.com",
        "password": "password123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

def test_get_current_user_profile(client):
    # Register
    client.post("/auth/register", json={
        "email": "tester4@test.com",
        "password": "password123",
        "full_name": "Test User"
    })
    user = DBManager.get_user_by_email("tester4@test.com")
    DBManager.verify_email(user["id"])
    login_res = client.post("/auth/login", json={"email": "tester4@test.com", "password": "password123"})
    token = login_res.json()["access_token"]
    
    # Access profile
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "tester4@test.com"
    assert data["full_name"] == "Test User"

