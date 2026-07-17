from datetime import date
from fastapi.testclient import TestClient
import pytest
from app.api import app
from procurement.models import ProcurementCategory, ProcurementStatus
from procurement.repository import JsonProcurementRepository
from procurement.service import ProcurementService


@pytest.fixture
def workflow(tmp_path):
    return ProcurementService(JsonProcurementRepository(tmp_path / "procurement"))


def test_candidate_review_numbering_and_isolation(workflow):
    sources = [
        {
            "source_id": "spec-1",
            "source_type": "specification",
            "document_id": "doc-1",
            "page_number": 4,
            "text": "Provide main switchgear. Long lead equipment shall be delivered before startup.",
        }
    ]
    candidates = workflow.extract_candidates("p1", sources)
    assert candidates[0].citations[0].page_number == 4
    reviewed, item = workflow.review_candidate("p1", candidates[0].id, "accept", "pe-1")
    assert reviewed.review_status == "accept" and item.procurement_number == "PROC-001"
    assert workflow.list_items("p2") == ()
    assert workflow.extract_candidates("p1", sources)[0].id == candidates[0].id


def test_lead_time_date_planning_history_and_guardrail(workflow):
    item = workflow.create_item(
        "p",
        "Main switchgear",
        category=ProcurementCategory.SWITCHGEAR,
        required_on_site=date(2027, 3, 1),
    )
    item = workflow.add_lead_time(
        "p",
        item.id,
        24,
        "weeks",
        "release_to_ready_to_ship",
        "meeting_record",
        actor="pe",
        confirmed=False,
    )
    plan = workflow.calculate_dates(
        "p",
        item.id,
        shipping_days=14,
        procurement_processing_days=7,
        design_review_days=21,
        receiving_days=2,
        buffer_days=3,
    )
    assert plan.latest_release_date == date(2026, 8, 19)
    assert "contractual" in plan.warnings[0]
    workflow.update_item("p", item.id, product="SWGR-X", related_submittal_ids=("sub-1",))
    workflow.transition("p", item.id, ProcurementStatus.READY_FOR_RELEASE, "pe")
    workflow.transition("p", item.id, ProcurementStatus.RELEASE_PENDING_AUTHORIZATION, "pe")
    with pytest.raises(ValueError, match="authorization"):
        workflow.transition("p", item.id, ProcurementStatus.RELEASED, "system")
    workflow.authorize_release("p", item.id, "pm", "approval-1")
    assert (
        workflow.transition("p", item.id, ProcurementStatus.RELEASED, "pm").status
        == ProcurementStatus.RELEASED
    )


def test_exposure_delivery_snapshots_and_comparison(workflow):
    item = workflow.create_item("p", "Generator", category=ProcurementCategory.GENERATORS)
    assessment = workflow.assess_exposure("p", item.id)
    assert (
        assessment.confirmed_project_delay is False
        and "incomplete_information" in assessment.exposure_types
    )
    old = workflow.snapshot("p", "pm")
    workflow.record_delivery(
        "p", item.id, date(2027, 1, 2), "partial", "receiver", quantity=1, partial=True
    )
    current = workflow._require_item("p", item.id)
    assert current.status == ProcurementStatus.DELIVERED and not current.deliveries[-1].accepted
    current = workflow.record_acceptance("p", item.id, "superintendent", "receiving-1")
    assert current.status == ProcurementStatus.ACCEPTED and current.deliveries[-1].accepted
    new = workflow.snapshot("p", "pm")
    comparison = workflow.compare_plans("p", old.id, new.id)
    assert any(x.field == "status" for x in comparison.changes)
    assert workflow.dashboard("p").total_active == 1


def test_product_and_submittal_links_are_explicit_and_do_not_authorize_release(workflow):
    item = workflow.create_item("p", "UPS")
    linked = workflow.link_product_and_submittal(
        "p", item.id, actor="pe", submittal_id="sub-1", product="UPS-X"
    )
    assert linked.related_submittal_ids == ("sub-1",)
    assert workflow.assess_release_readiness("p", item.id)["authorization_recorded"] is False


def test_api_openapi_and_project_scope(monkeypatch, tmp_path):
    from app import procurement_api

    repository = JsonProcurementRepository(tmp_path / "api")
    monkeypatch.setattr(procurement_api, "_service", lambda: ProcurementService(repository))
    client = TestClient(app)
    created = client.post("/projects/p/procurement-items", json={"title": "UPS", "category": "UPS"})
    assert created.status_code == 201
    assert client.get("/projects/other/procurement-items").json() == []
    assert "/projects/{project_id}/procurement-items" in client.get("/openapi.json").json()["paths"]
