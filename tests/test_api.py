from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_healthcheck():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    external_response = client.get("/api/healthz")
    assert external_response.status_code == 200
    assert external_response.json() == response.json()


def test_snapshot_contains_expected_cases_and_control():
    response = client.get("/api/snapshot")
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["metrics"]["frames_matched"] == 38
    findings = {case["case_id"]: case["status"] for case in snapshot["cases"]}
    assert findings["223-second-avenue"] == "no_current_permit_found"
    assert findings["74-78-eighth-avenue"] == "no_current_permit_found"
    assert findings["80-eighth-avenue-control"] == "valid_permit"


def test_human_review_decision_updates_case():
    response = client.post(
        "/api/cases/223-second-avenue/decision",
        json={"decision": "approve", "note": "frontage visually confirmed"},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "approve"
    case = client.get("/api/cases/223-second-avenue").json()
    assert case["decision"] == "approve"
    assert case["review_note"] == "frontage visually confirmed"


def test_unknown_case_returns_404():
    response = client.get("/api/cases/not-real")
    assert response.status_code == 404
