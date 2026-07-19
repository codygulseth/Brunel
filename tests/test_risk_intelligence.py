from datetime import date
from risk_intelligence.models import Evidence, RiskStatus
from risk_intelligence.qa import RiskQuestionService
from risk_intelligence.repository import JsonRiskRepository
from risk_intelligence.service import RiskIntelligenceService


def evidence(record_id: str, text: str, location: str | None = "Electrical Room") -> Evidence:
    return Evidence(
        record_type="daily_report",
        record_id=record_id,
        citation={"source_locator": record_id},
        excerpt=text,
        location=location,
    )


def test_candidates_are_project_scoped_cited_and_human_reviewed(tmp_path):
    service = RiskIntelligenceService(JsonRiskRepository(tmp_path))
    generated = service.generate(
        "data-center",
        (
            evidence("daily-1", "Access constraint remains unresolved"),
            evidence("daily-2", "Access constraint remains unresolved"),
        ),
    )
    assert len(generated) == 1
    risk = generated[0]
    assert risk.status == RiskStatus.PROPOSED
    assert risk.correlations[0].strength.value == "strong"
    assert risk.evidence[0].citation["source_locator"] == "daily-1"
    assert service.repository.get("risks", risk.id, "other-project") is None
    reviewed = service.review(
        "data-center", risk.id, "confirm", "project-manager", "monitor switchgear access"
    )
    assert reviewed.status == RiskStatus.CONFIRMED_FOR_MONITORING


def test_commitments_need_completion_evidence_and_dependencies_preserve_evidence(tmp_path):
    service = RiskIntelligenceService(JsonRiskRepository(tmp_path))
    item = service.normalize_commitment(
        "p",
        "meeting_action",
        "action-1",
        "Confirm switchgear delivery",
        (evidence("meeting-1", "Commitment remains overdue"),),
        due_date=date(2025, 1, 1),
    )
    try:
        service.confirm_completion("p", item.id, (), "pm")
        assert False, "completion without evidence must fail"
    except ValueError:
        pass
    completed = service.confirm_completion(
        "p", item.id, (evidence("delivery-1", "Delivery accepted"),), "pm"
    )
    assert completed.completion_confirmed
    edge = service.add_dependency(
        "p",
        "activity-install",
        item.id,
        "activity depends on commitment",
        (evidence("schedule-1", "Install depends on delivery"),),
    )
    assert service.blockers("p", item.id) == (edge,)


def test_qa_does_not_make_prohibited_determinations(tmp_path):
    service = RiskIntelligenceService(JsonRiskRepository(tmp_path))
    service.generate("p", (evidence("rfi-1", "RFI remains unresolved near planned work"),))
    answer = RiskQuestionService(service).answer("p", "Who is responsible for this delay?")
    assert "cannot determine" in answer.answer
    normal = RiskQuestionService(service).answer("p", "What risks should I review?")
    assert normal.citations
