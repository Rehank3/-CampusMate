from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_home_endpoint():
    response = client.get("/")
    assert response.status_code == 200


def test_docs_endpoint():
    response = client.get("/docs")
    assert response.status_code == 200
