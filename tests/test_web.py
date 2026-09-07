from fastapi.testclient import TestClient

from autoreference.web import app, service


def test_web_health_root_and_export() -> None:
    assert "zhizhen" not in service.providers

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["providers"] == ["openalex", "crossref", "zhizhen"]
        assert health.json()["unverified_providers"] == ["zhizhen"]

        root = client.get("/")
        assert root.status_code == 200
        assert "AutoReference" in root.text
        assert "候选引用" in root.text

        exported = client.post(
            "/api/export/bibtex",
            json={
                "candidates": [
                    {
                        "source": "test",
                        "title": "A test reference",
                        "authors": ["A Researcher"],
                        "year": 2026,
                        "doi": "10.1/test",
                    }
                ]
            },
        )
        assert exported.status_code == 200
        assert "@misc" in exported.text
        assert "10.1/test" in exported.text
