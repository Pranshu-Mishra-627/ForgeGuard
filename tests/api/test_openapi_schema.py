"""Tests verifying that all promised UI routes are exposed in the OpenAPI schema."""
from fastapi.testclient import TestClient
from app.main import app


def test_openapi_schema_contains_all_ui_routes():
    client = TestClient(app)
    res = client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    paths = schema["paths"]

    expected_routes = [
        "/health",
        "/api/status",
        "/api/simulation/start",
        "/api/simulation/pause",
        "/api/simulation/resume",
        "/api/simulation/step",
        "/api/simulation/reset",
        "/api/simulation/inject-failure",
        "/api/simulation/state",
        "/api/machines",
        "/api/machines/{machine_id}",
        "/api/jobs",
        "/api/jobs/{job_id}",
        "/api/technicians",
        "/api/schedule",
        "/api/schedule/replan",
        "/api/jobs/{job_id}/preemption/evaluate",
        "/api/jobs/{job_id}/preemption/execute",
        "/api/events",
        "/api/cost-analysis",
    ]

    for route in expected_routes:
        assert route in paths, f"Route {route} missing from generated OpenAPI schema!"
