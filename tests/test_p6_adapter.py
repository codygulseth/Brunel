from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.api import app
from integration_adapters.models import ConnectionStatus, ExportStatus
from integration_adapters.reference import TestSecretProvider
from integration_adapters.registry import AdapterRegistry
from integration_adapters.repository import JsonIntegrationRepository
from integration_adapters.service import IntegrationService
from p6_adapter import PrimaveraP6Adapter, PrimaveraP6Service
from p6_adapter.parser import P6XMLParser, P6XERParser
from schedule_intelligence.repository import JsonScheduleRepository
from schedule_intelligence.service import ScheduleIntelligenceService


XER = """ERMHDR\t21.12\t2027-01-10
%T\tPROJECT
%F\tproj_id\tproj_short_name\tproj_name\tlast_recalc_date\tplan_start_date\tscd_end_date
%R\t10\tDC01\tData Center Expansion\t2027-01-10\t2027-01-01\t2027-09-30
%T\tPROJWBS
%F\twbs_id\tproj_id\tparent_wbs_id\twbs_short_name\twbs_name
%R\t20\t10\t\tELEC\tElectrical
%T\tCALENDAR
%F\tclndr_id\tproj_id\tclndr_name\tday_hr_cnt\tweek_hr_cnt
%R\t30\t10\t5 Day\t8\t40
%T\tTASK
%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_code\ttask_name\tstatus_code\ttask_type\ttarget_drtn_hr_cnt\tremain_drtn_hr_cnt\ttarget_start_date\ttarget_end_date\tact_start_date\tact_end_date\tphys_complete_pct\ttotal_float_hr_cnt
%R\t101\t10\t20\t30\tA100\tUtility Coordination\tTK_Complete\tTT_Task\t40\t0\t2027-01-01\t2027-01-05\t2027-01-01\t2027-01-05\t100\t40
%R\t102\t10\t20\t30\tA200\tMedium Voltage Switchgear\tTK_Active\tTT_Task\t80\t40\t2027-01-06\t2027-01-20\t2027-01-06\t\t50\t8
%T\tTASKPRED
%F\ttask_pred_id\tproj_id\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt
%R\t500\t10\t102\t101\tPR_FS\t0
%T\tUDFTYPE
%F\tudf_type_id\tproj_id\tudf_type_label\ttable_name
%R\t600\t10\tBrunel Reference\tTASK
%T\tUNKNOWN_VENDOR_TABLE
%F\tid\tvalue
%R\t1\tpreserved
%E
"""


XML = """<?xml version="1.0"?>
<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V1">
  <Project><ObjectId>10</ObjectId><Id>DC01</Id><Name>Data Center Expansion</Name><DataDate>2027-01-10</DataDate>
    <WBS><ObjectId>20</ObjectId><Code>ELEC</Code><Name>Electrical</Name></WBS>
    <Calendar><ObjectId>30</ObjectId><Name>5 Day</Name><HoursPerDay>8</HoursPerDay></Calendar>
    <Activity><ObjectId>101</ObjectId><Id>A100</Id><Name>Utility Coordination</Name><WBSObjectId>20</WBSObjectId><CalendarObjectId>30</CalendarObjectId><PlannedStart>2027-01-01</PlannedStart><PlannedFinish>2027-01-05</PlannedFinish><OriginalDuration>40</OriginalDuration><Status>Completed</Status></Activity>
    <Activity><ObjectId>102</ObjectId><Id>A200</Id><Name>Switchgear</Name><WBSObjectId>20</WBSObjectId><CalendarObjectId>30</CalendarObjectId><PlannedStart>2027-01-06</PlannedStart><PlannedFinish>2027-01-20</PlannedFinish><OriginalDuration>80</OriginalDuration><Status>In Progress</Status></Activity>
    <Relationship><PredecessorActivityObjectId>101</PredecessorActivityObjectId><SuccessorActivityObjectId>102</SuccessorActivityObjectId><Type>Finish to Start</Type><Lag>0</Lag></Relationship>
  </Project>
</APIBusinessObjects>"""


def write(path: Path, content: str):
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def services(tmp_path):
    adapter = PrimaveraP6Adapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    integrations = IntegrationService(
        JsonIntegrationRepository(tmp_path / "integrations"), registry, TestSecretProvider()
    )
    schedules = ScheduleIntelligenceService(JsonScheduleRepository(tmp_path / "schedules"))
    return PrimaveraP6Service(integrations, schedules, adapter), adapter


def connection(service, *, write_enabled=False):
    item = service.integrations.create_connection(
        "org",
        "project",
        "primavera_p6",
        "P6 Test",
        "scheduler",
        configuration={"transport": "test_in_memory" if write_enabled else "xer_file"},
        write_enabled=write_enabled,
        authorized_principal_ids=("scheduler", "approver"),
        external_write_approver_ids=("approver",) if write_enabled else (),
    )
    tested = service.integrations.test_connection("org", "project", item.id, "scheduler")
    assert tested.status == ConnectionStatus.ACTIVE
    return tested


def test_capabilities_read_only_default_and_safe_parsers(tmp_path, services):
    service, _ = services
    manifest = service.capabilities()
    assert manifest.adapter_version == "1.0.0" and manifest.write_capable
    assert "api_write" not in {x.value for x in manifest.supported_operations}
    parsed = P6XERParser().parse(write(tmp_path / "project.xer", XER))
    assert parsed.projects[0].external_project_id == "10"
    assert any("UNKNOWN_VENDOR_TABLE" in warning for warning in parsed.warnings)
    xml = P6XMLParser().parse(write(tmp_path / "project.xml", XML))
    assert len(xml.projects[0].activities) == 2
    with pytest.raises(ValueError, match="Unsafe XML"):
        P6XMLParser().parse(
            write(tmp_path / "unsafe.xml", "<!DOCTYPE x [<!ENTITY e 'x'>]><Project/>")
        )


def test_explicit_mapping_canonical_admission_identity_and_idempotency(tmp_path, services):
    service, _ = services
    item = connection(service)
    source = write(tmp_path / "project.xer", XER)
    discovered = service.discover_projects("org", "project", item.id, "scheduler", source)
    assert discovered[0].requires_mapping_review and discovered[0].activity_count == 2
    with pytest.raises(ValueError, match="mapping"):
        service.import_schedule("org", "project", item.id, "scheduler", source)
    service.map_project("org", "project", item.id, "10", "scheduler")
    session, revision = service.import_schedule("org", "project", item.id, "scheduler", source)
    assert session.status == "completed" and session.cursor_committed
    assert revision.activity_count == 2 and revision.relationship_count == 1
    activities = service.schedules.activities("project", revision.id)
    assert {x.source_fields["p6_object_id"] for x in activities} == {"101", "102"}
    assert service.schedules.relationships("project", revision.id)[0].validation_status == "valid"
    assert service.integrations.repository.list("raw", "org", "project")
    assert service.integrations.repository.list("mappings", "org", "project")
    _, replay = service.import_schedule("org", "project", item.id, "scheduler", source)
    assert replay.id == revision.id
    assert service.revisions("other") == ()


def test_same_data_date_changed_content_comparison_quality_and_cited_qa(tmp_path, services):
    service, _ = services
    item = connection(service)
    service.map_project("org", "project", item.id, "10", "scheduler")
    _, old = service.import_schedule(
        "org", "project", item.id, "scheduler", write(tmp_path / "old.xer", XER)
    )
    changed = XER.replace("Medium Voltage Switchgear", "Switchgear Released").replace(
        "2027-01-20", "2027-01-27"
    )
    _, new = service.import_schedule(
        "org", "project", item.id, "scheduler", write(tmp_path / "new.xer", changed)
    )
    assert new.id != old.id and new.data_date == old.data_date
    comparison = service.compare("project", old.id, new.id)
    assert any(
        "renamed" in x.change_types or "activity_delayed" in x.change_types
        for x in comparison.changes
    )
    assert service.quality("project", new.id).certification is False
    answer = service.answer("org", "project", item.id, "What is the latest P6 data date?")
    assert answer.citations and "imported P6 data date" in answer.answer
    prohibited = service.answer("org", "project", item.id, "Who caused the delay?")
    assert "cannot determine" in prohibited.answer


def test_export_requires_supported_field_approval_version_and_reconciliation(tmp_path, services):
    service, adapter = services
    item = connection(service, write_enabled=True)
    service.map_project("org", "project", item.id, "10", "scheduler")
    _, revision = service.import_schedule(
        "org", "project", item.id, "scheduler", write(tmp_path / "project.xer", XER)
    )
    activity = next(
        x
        for x in service.schedules.activities("project", revision.id)
        if x.source_activity_id == "A200"
    )
    adapter.seed_test_activity("102", {"percent_complete": 50}, "7")
    mapping = next(
        x
        for x in service.activity_mapping_candidates("org", "project", item.id)
        if x.brunel_record_id == activity.id
    )
    service.review_activity_mapping("org", "project", mapping.id, "confirm", "scheduler")
    proposal = service.create_export_proposal(
        "org",
        "project",
        item.id,
        activity.id,
        "percent_complete",
        60,
        ({"citation": activity.citation.model_dump(mode="json")},),
        "Scheduler reviewed accepted field evidence",
        "scheduler",
        "7",
    )
    with pytest.raises(ValueError, match="approved"):
        service.integrations.execute_export("org", "project", proposal.id, "approver")
    validated = service.integrations.validate_export("org", "project", proposal.id, "scheduler")
    assert validated.status == ExportStatus.READY_FOR_REVIEW
    approved = service.integrations.approve_export(
        "org",
        "project",
        proposal.id,
        "approver",
        "Explicit schedule export approval",
        datetime.now(UTC) + timedelta(hours=1),
    )
    assert approved.status == ExportStatus.APPROVED
    execution = service.integrations.execute_export("org", "project", proposal.id, "approver")
    replay = service.integrations.execute_export("org", "project", proposal.id, "approver")
    assert replay.replayed and execution.external_version == "8"
    reconciliation = service.integrations.reconcile(
        "org", "project", proposal.id, execution.id, "approver"
    )
    assert reconciliation.status == "matched"
    bad = service.create_export_proposal(
        "org",
        "project",
        item.id,
        activity.id,
        "relationship",
        "A100",
        ({"citation": "reviewed"},),
        "Not supported",
        "scheduler",
        "8",
    )
    assert (
        "unsupported_p6_export_field"
        in service.integrations.validate_export(
            "org", "project", bad.id, "scheduler"
        ).validation_errors
    )


def test_export_approval_invalidates_when_activity_mapping_changes(tmp_path, services):
    service, adapter = services
    item = connection(service, write_enabled=True)
    service.map_project("org", "project", item.id, "10", "scheduler")
    _, revision = service.import_schedule(
        "org", "project", item.id, "scheduler", write(tmp_path / "project.xer", XER)
    )
    activity = next(
        x
        for x in service.schedules.activities("project", revision.id)
        if x.source_activity_id == "A200"
    )
    mapping = next(
        x
        for x in service.activity_mapping_candidates("org", "project", item.id)
        if x.brunel_record_id == activity.id
    )
    service.review_activity_mapping("org", "project", mapping.id, "confirm", "scheduler")
    adapter.seed_test_activity("102", {"percent_complete": 50}, "7")
    proposal = service.create_export_proposal(
        "org",
        "project",
        item.id,
        activity.id,
        "percent_complete",
        60,
        ({"citation": "reviewed"},),
        "Reviewed evidence",
        "scheduler",
        "7",
    )
    service.integrations.validate_export("org", "project", proposal.id, "scheduler")
    service.integrations.approve_export(
        "org",
        "project",
        proposal.id,
        "approver",
        "Approved",
        datetime.now(UTC) + timedelta(hours=1),
    )
    service.review_activity_mapping("org", "project", mapping.id, "reject", "scheduler")
    with pytest.raises(ValueError, match="no longer valid"):
        service.integrations.execute_export("org", "project", proposal.id, "approver")


def test_openapi_exposes_p6_without_autonomous_writeback():
    schema = TestClient(app).get("/openapi.json").json()
    paths = schema["paths"]
    assert (
        "/organizations/{organization_id}/projects/{project_id}/p6/connections/{connection_id}/imports"
        in paths
    )
    assert (
        "/organizations/{organization_id}/projects/{project_id}/p6/export-proposals/{proposal_id}/execute"
        in paths
    )
    assert not any("writeback" in path or "write-back" in path for path in paths)
