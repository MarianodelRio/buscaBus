"""tests/test_main.py — /health y /metrics, sin arrancar el lifespan (los
datos de horarios los instala el fixture autouse `_datos_cargados`)."""
from fastapi.testclient import TestClient

from app.main import app
from app.services.horarios import datos as horarios_datos

client = TestClient(app)


def test_health_ok_when_data_loaded():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["datos"]["lineas"] > 0
    assert body["datos"]["viajes"] > 0


def test_health_503_when_no_data(monkeypatch):
    monkeypatch.setattr(horarios_datos, "_actual", None)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"


def test_metrics_endpoint_returns_json():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "uptime_seconds" in resp.json()
