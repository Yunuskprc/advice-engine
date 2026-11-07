import time

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeLlm


def test_health_ok(settings) -> None:
    with TestClient(create_app(settings, llm=FakeLlm())) as client:
        body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["db"]["ok"] and "001_init" in body["db"]["migrations"]
    assert body["ollama"]["embed_model_present"] and body["ollama"]["chat_model_present"]


def test_health_ollama_down(settings) -> None:
    with TestClient(create_app(settings, llm=FakeLlm(reachable=False))) as client:
        body = client.get("/api/health").json()
    assert body["ok"] is False
    assert body["db"]["ok"] is True
    assert body["ollama"]["reachable"] is False


def test_demo_job_via_api(settings) -> None:
    with TestClient(create_app(settings, llm=FakeLlm())) as client:
        job_id = client.post("/api/jobs/demo").json()["id"]
        for _ in range(100):
            job = next(j for j in client.get("/api/jobs").json() if j["id"] == job_id)
            if job["status"] == "done":
                break
            time.sleep(0.05)
    assert job["status"] == "done"
    assert job["progress"] == job["total"] == settings.demo_job_steps
