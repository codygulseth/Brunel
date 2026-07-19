from datetime import date
import pytest
from commissioning_intelligence.models import DeficiencyStatus, Evidence, ReadinessStatus
from commissioning_intelligence.qa import CommissioningQuestionService
from commissioning_intelligence.repository import JsonCommissioningRepository
from commissioning_intelligence.service import CommissioningService


def ev(identifier: str, text: str, confirmed: bool = False) -> Evidence:
    return Evidence(
        record_type="document_revision",
        record_id=identifier,
        citation={"revision_id": identifier, "page": 1},
        excerpt=text,
        visual_region=(0.1, 0.1, 0.5, 0.3),
        human_confirmed=confirmed,
    )


def test_system_assets_lineage_requirements_and_project_scope(tmp_path):
    service = CommissioningService(JsonCommissioningRepository(tmp_path))
    system = service.create_system(
        "dc", "Medium Voltage Switchgear", evidence=(ev("drawing-r2", "MV switchgear SWGR-1"),)
    )
    asset = service.create_asset(
        "dc",
        system.id,
        "SWGR-1",
        "switchgear",
        product_lineage={"specified": "Model A", "delivered": "Model B"},
        evidence=(ev("submittal-1", "Model A"), ev("delivery-1", "Model B")),
    )
    assert asset.conflicts and service.repository.get("assets", asset.id, "other") is None
    requirements = service.extract_requirements(
        "dc",
        (ev("spec-1", "Provide startup testing, O&M manual, warranty, and owner training."),),
        system_id=system.id,
    )
    assert requirements and requirements[0].citation.visual_region


def test_procedures_tests_retests_calibration_and_readiness(tmp_path):
    service = CommissioningService(JsonCommissioningRepository(tmp_path))
    system = service.create_system("p", "UPS")
    service.extract_requirements(
        "p", (ev("spec", "UPS functional test required"),), system_id=system.id
    )
    procedure = service.create_procedure(
        "p",
        system.id,
        "UPS functional test",
        ({"id": "1", "expected": "transfer"},),
        (ev("proc-doc", "Expected transfer"),),
    )
    instrument = service.add_instrument("p", "meter", "M-1", expiration=date(2024, 1, 1))
    execution = service.record_test(
        "p",
        procedure.revision_id,
        system.id,
        date(2025, 1, 1),
        ("transfer",),
        ("no transfer",),
        "failed",
        (ev("test-report", "Failed as reported"),),
        instrument_ids=(instrument.id,),
    )
    assert service.instrument_findings("p", date(2025, 1, 1), (instrument.id,))
    retest = service.record_test(
        "p",
        procedure.revision_id,
        system.id,
        date(2025, 1, 2),
        ("transfer",),
        ("transfer reported",),
        "passed_as_reported",
        (ev("retest", "Pass reported"),),
        retest_of_id=execution.id,
    )
    assert retest.retest_of_id == execution.id
    assert (
        service.assess_readiness("p", system.id, "startup").status
        == ReadinessStatus.READY_FOR_HUMAN_REVIEW
    )


def test_deficiency_never_closes_without_authorized_evidence(tmp_path):
    service = CommissioningService(JsonCommissioningRepository(tmp_path))
    system = service.create_system("p", "Generators")
    item = service.create_deficiency(
        "p",
        system.id,
        "Generator alarm",
        "Alarm did not annunciate",
        (ev("test", "Failure reported"),),
    )
    item = service.transition_deficiency("p", item.id, DeficiencyStatus.UNDER_REVIEW, "cx-agent")
    item = service.transition_deficiency("p", item.id, DeficiencyStatus.OPEN, "cx-agent")
    item = service.transition_deficiency(
        "p", item.id, DeficiencyStatus.CORRECTION_REPORTED, "contractor"
    )
    item = service.transition_deficiency(
        "p", item.id, DeficiencyStatus.READY_FOR_VERIFICATION, "contractor"
    )
    with pytest.raises(ValueError):
        service.transition_deficiency("p", item.id, DeficiencyStatus.VERIFIED, "brunel")
    item = service.transition_deficiency(
        "p",
        item.id,
        DeficiencyStatus.VERIFIED,
        "authorized-reviewer",
        evidence=(ev("verification", "Verified by reviewer", True),),
        rationale="Witnessed retest",
    )
    item = service.transition_deficiency(
        "p",
        item.id,
        DeficiencyStatus.CLOSED,
        "authorized-reviewer",
        evidence=(ev("closure", "Closure authorized", True),),
        rationale="Closure accepted",
    )
    reopened = service.transition_deficiency(
        "p", item.id, DeficiencyStatus.REOPENED, "authorized-reviewer"
    )
    assert reopened.status == DeficiencyStatus.REOPENED


def test_turnover_and_qa_guardrails(tmp_path):
    service = CommissioningService(JsonCommissioningRepository(tmp_path))
    system = service.create_system("p", "Controls")
    package = service.create_turnover_package(
        "p",
        "system_turnover",
        ("om_manual", "warranty", "training", "as-built"),
        system_id=system.id,
    )
    assert service.turnover_dashboard("p").missing_items == 4
    package = service.add_turnover_item(
        "p",
        package.id,
        package.items[0].id,
        "manual-r1",
        (ev("manual-r1", "Controls O&M manual"),),
        "reviewer",
    )
    assert package.completeness_proposal == "incomplete" and not package.accepted_as_recorded
    answer = CommissioningQuestionService(service).answer(
        "p", "Can Brunel authorize startup and certify compliance?"
    )
    assert "cannot certify" in answer.answer
