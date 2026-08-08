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
    assert snapshot["metrics"]["frames_matched"] >= 38
    findings = {case["case_id"]: case["status"] for case in snapshot["cases"]}
    assert findings["223-second-avenue"] == "no_current_permit_found"
    assert findings["74-78-eighth-avenue"] == "no_current_permit_found"
    assert findings["80-eighth-avenue-control"] == "valid_permit"

    cases = {case["case_id"]: case for case in snapshot["cases"]}
    gap = cases["223-second-avenue"]
    assert gap["permit_evidence"]["active_registry_checked"] is True
    assert gap["permit_evidence"]["active_registry_matches"] == 0
    assert gap["permit_evidence"]["records"]
    assert gap["permit_evidence"]["source_links"]

    control = cases["80-eighth-avenue-control"]
    assert control["permit_evidence"]["current_permit"]["permit_id"] == "M00950093-I1-SH"
    assert control["permit_evidence"]["current_permit"]["record_url"].startswith("https://")

    citywide = [case for case in snapshot["cases"] if case["case_id"].startswith("citywide-")]
    assert all(case["detection"]["verification_passes"] == 2 for case in citywide)


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
