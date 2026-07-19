from datetime import date
import pytest
from enterprise_intelligence.models import Evidence, ReviewStatus, SharingLevel
from enterprise_intelligence.qa import EnterpriseQuestionService
from enterprise_intelligence.repository import JsonEnterpriseRepository
from enterprise_intelligence.service import EnterpriseIntelligenceService


def ev(
    project: str, record: str, text: str, sharing: SharingLevel = SharingLevel.ORGANIZATION_SHARED
) -> Evidence:
    return Evidence(
        project_id=project,
        record_type="canonical_record",
        record_id=record,
        citation={"record_id": record},
        excerpt=text,
        recorded_on=date(2026, 1, 1),
        confidentiality=sharing,
    )


def test_explicit_portfolio_and_project_authorization(tmp_path):
    service = EnterpriseIntelligenceService(JsonEnterpriseRepository(tmp_path))
    portfolio = service.create_portfolio("org-1", "Mission Critical", ("analyst",), "admin")
    portfolio = service.add_project(
        "org-1",
        portfolio.id,
        "project-a",
        ("analyst",),
        SharingLevel.PORTFOLIO_SHARED,
        "admin",
        taxonomy={"sector": "data_center"},
        eligible=True,
    )
    assert service.authorize("org-1", portfolio.id, "analyst", "project-a")
    with pytest.raises(PermissionError):
        service.authorize("org-1", portfolio.id, "outsider")
    with pytest.raises(PermissionError):
        service.authorize("org-1", portfolio.id, "analyst", "project-b")
    assert service.repository.get("portfolios", portfolio.id, "org-2") is None


def test_entity_matches_and_lessons_require_human_review(tmp_path):
    service = EnterpriseIntelligenceService(JsonEnterpriseRepository(tmp_path))
    left = service.create_entity("org", "supplier", "Acme Electric", (ev("p1", "s1", "Acme"),))
    right = service.create_entity("org", "supplier", "ACME Electric", (ev("p2", "s2", "ACME"),))
    candidate = service.propose_entity_match("org", left.id, right.id)
    assert not candidate.auto_merged and candidate.review_status == ReviewStatus.PROPOSED
    rejected = service.review_entity_match("org", candidate.id, False, "reviewer")
    assert rejected.review_status == ReviewStatus.REJECTED
    lesson = service.propose_lesson(
        "org",
        "p1",
        "Generator startup review",
        "Startup had reported controls gaps",
        (ev("p1", "risk1", "Controls gaps reported"),),
        {"sector": "data_center", "system": "generator"},
    )
    assert not lesson.approved_for_enterprise_reuse and "not causation" in lesson.uncertainty[0]
    assert service.lesson_applicability(lesson, {"sector": "data_center", "system": "generator"})[
        "human_review_required"
    ]


def test_benchmark_provenance_and_small_group_suppression(tmp_path):
    service = EnterpriseIntelligenceService(JsonEnterpriseRepository(tmp_path))
    portfolio = service.create_portfolio("org", "Benchmarks", ("analyst",), "admin")
    for project, value in (("p1", 100.0), ("p2", 120.0), ("p3", 140.0), ("p4", 160.0)):
        portfolio = service.add_project(
            "org",
            portfolio.id,
            project,
            ("analyst",),
            SharingLevel.PORTFOLIO_SHARED,
            "admin",
            eligible=True,
        )
        service.add_metric(
            "org",
            project,
            "switchgear_lead_time",
            value,
            "days",
            date(2026, 1, 1),
            (ev(project, f"proc-{project}", "Actual delivery duration"),),
            {"equipment": "switchgear"},
            "reviewer",
        )
    definition = service.create_benchmark_definition(
        "org",
        "MV switchgear lead time",
        "switchgear_lead_time",
        "days",
        "median",
        4,
        "reviewer",
        {"equipment": "switchgear"},
    )
    definition = service.review_benchmark_definition("org", definition.id, "reviewer")
    result = service.calculate_benchmark("org", definition.id, portfolio.id, "analyst")
    assert (
        result.value == 130
        and result.sample_size == 4
        and len(result.provenance.included_record_ids) == 4
    )
    small = service.create_portfolio("org", "Small", ("analyst",), "admin")
    small = service.add_project(
        "org",
        small.id,
        "p1",
        ("analyst",),
        SharingLevel.BENCHMARK_ONLY,
        "admin",
        eligible=True,
    )
    restricted = service.calculate_benchmark("org", definition.id, small.id, "analyst")
    assert (
        restricted.suppressed
        and restricted.value is None
        and not restricted.provenance.authorized_citations
    )


def test_comparables_quality_dashboard_and_qa_guardrails(tmp_path):
    service = EnterpriseIntelligenceService(JsonEnterpriseRepository(tmp_path))
    selection = service.select_comparables(
        "org",
        "p1",
        {
            "p1": {"sector": "dc", "type": "greenfield"},
            "p2": {"sector": "dc", "type": "expansion"},
            "p3": {"sector": "healthcare"},
        },
        ("sector", "type"),
    )
    assert selection.results[0].project_id == "p2" and selection.results[0].human_review_required
    quality = service.assess_quality("org", "p1", {}, 0, False)
    assert not quality.eligible
    portfolio = service.create_portfolio("org", "Portfolio", ("analyst",), "admin")
    portfolio = service.add_project(
        "org", portfolio.id, "p1", ("analyst",), SharingLevel.RESTRICTED, "admin"
    )
    assert service.dashboard("org", portfolio.id, "analyst").restricted_projects == 1
    answer = EnterpriseQuestionService(service).answer(
        "org", "Which is the best contractor to award?", portfolio.id, "analyst"
    )
    assert "cannot rank" in answer.answer
