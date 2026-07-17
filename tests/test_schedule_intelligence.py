from datetime import date
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from app.api import app
from schedule_intelligence.models import Criticality, ScheduleType
from schedule_intelligence.repository import JsonScheduleRepository
from schedule_intelligence.service import ScheduleIntelligenceService

CSV1 = """activity_id,activity_name,wbs_id,activity_type,status,calendar_id,original_duration,remaining_duration,percent_complete,planned_start,planned_finish,forecast_finish,total_float,equipment_tags,predecessors
A100,Design Release,DES,task_dependent,completed,CAL-1,5,0,100,2027-01-04,2027-01-09,2027-01-09,20,,
A200,Switchgear Submittal,PROC,task_dependent,in_progress,CAL-1,10,5,50,2027-01-10,2027-01-20,2027-01-20,8,SWGR,A100:FS:0
A300,Generator Delivery,PROC,finish_milestone,not_started,CAL-1,0,0,0,2027-03-01,2027-03-01,2027-03-01,0,GEN,A200:FS:0
"""
CSV2 = (
    CSV1.replace("A200,Switchgear Submittal", "A200,Switchgear Approved Submittal")
    .replace("2027-01-20,2027-01-20,8", "2027-01-20,2027-01-27,-1")
    .replace("2027-03-01,2027-03-01,2027-03-01,0", "2027-03-08,2027-03-08,2027-03-08,-5")
    .replace("A200:FS:0\n", "A100:FS:0\n")
)


@pytest.fixture
def workflow(tmp_path):
    return ScheduleIntelligenceService(JsonScheduleRepository(tmp_path / "schedule"))


def write(path: Path, text: str):
    path.write_text(text, encoding="utf-8")
    return path


def test_csv_immutable_quality_cpm_citations_and_project_scope(workflow, tmp_path):
    rev = workflow.import_schedule(
        "p",
        write(tmp_path / "r1.csv", CSV1),
        "Master",
        ScheduleType.UPDATE,
        revision_label="U1",
        calendar_fallback=True,
    )
    assert rev.activity_count == 3 and rev.milestone_count == 1
    activities = workflow.activities("p", rev.id)
    assert next(x for x in activities if x.source_activity_id == "A100").citation.source_row == 2
    assert (
        workflow.import_schedule("p", tmp_path / "r1.csv", "Master", ScheduleType.UPDATE).id
        == rev.id
    )
    assert workflow.activities("other", rev.id) == ()
    assert workflow.assess_quality("p", rev.id).certification is False
    calculation = workflow.calculate_cpm("p", rev.id, calendar_fallback=True)
    assert calculation.supported and calculation.approximate
    milestone = next(x for x in activities if x.source_activity_id == "A300")
    assert workflow.criticality(milestone).classification == Criticality.CRITICAL


def test_lineage_comparison_sync_guardrails_dashboard_search(workflow, tmp_path):
    old = workflow.import_schedule(
        "p", write(tmp_path / "r1.csv", CSV1), "Master", ScheduleType.UPDATE, calendar_fallback=True
    )
    new = workflow.import_schedule(
        "p",
        write(tmp_path / "r2.csv", CSV2),
        "Master",
        ScheduleType.UPDATE,
        predecessor_revision_id=old.id,
        calendar_fallback=True,
    )
    assert any(
        x.status == "unchanged_identity" for x in workflow.resolve_lineage("p", old.id, new.id)
    )
    comparison = workflow.compare("p", old.id, new.id)
    assert comparison.project_finish_change_days == 7
    assert any("activity_delayed" in x.change_types for x in comparison.changes)
    assert any("resequenced" in x.change_types for x in comparison.changes)
    assert any("became_critical" in x.change_types for x in comparison.changes)
    generator = workflow.search("p", "Generator", new.id)[0]
    assert workflow.link_activity(
        "p", generator.id, "procurement_item", "PROC-001", "installed_for", "scheduler"
    ).workflow_links
    proposal = workflow.propose_sync(
        "p", generator.id, "procurement_item", "PROC-001", date(2027, 3, 1), "required_on_site"
    )
    assert workflow.review_proposal("p", proposal.id, "accept", "pm").downstream_updated is False
    assert workflow.dashboard("p", new.id).negative_float == 2
    assert len(workflow.repository.list("floats", "p")) == 6
    variances = workflow.repository.list("milestone_variances", "p")
    assert len(variances) == 2
    assert next(x for x in variances if x.revision_id == new.id).variance_from_prior_days == 7
    assert workflow.assess_exposures("p", new.id)
    from schedule_intelligence.qa import ScheduleQuestionService

    answer = ScheduleQuestionService(workflow).answer("p", "Who caused the delay?")
    assert "cannot determine" in answer.answer


def test_xml_and_xer_foundations(workflow, tmp_path):
    xml = "<Project><Tasks><Task><UID>1</UID><Name>Start</Name><Start>2027-01-01</Start><Finish>2027-01-01</Finish><Duration>0</Duration><Milestone>true</Milestone></Task></Tasks></Project>"
    assert (
        workflow.import_schedule(
            "p", write(tmp_path / "s.xml", xml), "XML", ScheduleType.UPDATE
        ).activity_count
        == 1
    )
    xer = "%T\tPROJECT\n%F\tproj_id\tlast_recalc_date\n%R\t1\t2027-01-01\n%T\tTASK\n%F\ttask_id\ttask_code\ttask_name\ttarget_drtn_hr_cnt\ttarget_start_date\ttarget_end_date\n%R\t1\tA1\tMobilize\t5\t2027-01-01\t2027-01-06\n"
    assert (
        workflow.import_schedule(
            "p", write(tmp_path / "s.xer", xer), "XER", ScheduleType.UPDATE
        ).activity_count
        == 1
    )


def test_api_openapi_has_no_writeback(monkeypatch, tmp_path):
    from app import schedule_api

    service = ScheduleIntelligenceService(JsonScheduleRepository(tmp_path / "api"))
    monkeypatch.setattr(schedule_api, "_service", lambda: service)
    source = write(tmp_path / "api.csv", CSV1)
    client = TestClient(app)
    response = client.post(
        "/projects/p/schedules",
        json={
            "file_path": str(source),
            "name": "Master",
            "schedule_type": "update",
            "calendar_fallback": True,
        },
    )
    assert response.status_code == 201
    revision = response.json()["id"]
    assert client.get(f"/projects/p/schedule-revisions/{revision}/activities").status_code == 200
    schema = client.get("/openapi.json").json()
    assert not any("write-back" in path or "writeback" in path for path in schema["paths"])
    assert "/projects/{project_id}/schedule-questions" in schema["paths"]
