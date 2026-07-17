import requests


def test_status_fallback_contract():
    response = requests.get("http://127.0.0.1:5000/api/status/not-a-real-job", timeout=3)
    assert response.status_code == 404
