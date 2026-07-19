from datetime import date
from contract_intelligence.models import Evidence
from contract_intelligence.qa import ContractQuestionService
from contract_intelligence.repository import JsonContractRepository
from contract_intelligence.service import ContractIntelligenceService


def ev(identifier: str, text: str, on: date | None = None) -> Evidence:
    return Evidence(
        record_type="document_revision",
        record_id=identifier,
        citation={"revision_id": identifier, "page": 1},
        exact_text=text,
        source_date=on,
    )


def setup_contract(tmp_path):
    service = ContractIntelligenceService(JsonContractRepository(tmp_path))
    document = service.ingest_contract(
        "dc",
        "prime-r1",
        "prime_contract",
        "Data Center Prime Contract",
        (ev("prime-r1", "Prime contract exact text"),),
    )
    clauses = service.extract_clauses(
        "dc",
        document.id,
        (ev("prime-r1-c1", "7.3 Notice shall be delivered to Owner within 5 business days."),),
    )
    return service, document, clauses[0]


def test_documents_clauses_relationships_and_project_scope(tmp_path):
    service, document, clause = setup_contract(tmp_path)
    relationship = service.create_relationship(
        "dc",
        ("Owner", "Contractor"),
        {"Owner": "owner as stated", "Contractor": "contractor as stated"},
        (ev("prime-r1", "Parties as stated"),),
    )
    assert clause.full_source_text.startswith("7.3") and clause.normalized_summary != ""
    assert service.repository.get("documents", document.id, "other") is None
    exhibit = service.ingest_contract(
        "dc",
        "exhibit-r1",
        "scope_exhibit",
        "Electrical Scope",
        (ev("exhibit-r1", "Exhibit incorporated by reference"),),
        relationship_id=relationship.id,
    )
    edge = service.link_hierarchy(
        "dc",
        document.id,
        exhibit.id,
        "incorporates",
        "Exhibit is incorporated",
        ev("prime-r1-c2", "Exhibit is incorporated"),
    )
    assert "not determined" in edge.uncertainty[0]


def test_deadlines_are_explainable_and_ambiguous_inputs_withheld(tmp_path):
    service, _, clause = setup_contract(tmp_path)
    requirement = service.create_requirement(
        "dc",
        clause.id,
        "Change notice",
        "Potential notice language",
        time_limit=5,
        calendar_basis="business_days",
        recipient="Owner",
        delivery_method="written",
        trigger="event",
    )
    calculation = service.calculate_deadline(
        "dc", requirement.id, date(2026, 7, 17), holidays=(date(2026, 7, 20),)
    )
    assert calculation.calculated_date == date(2026, 7, 27)
    assert calculation.excluded_dates and calculation.review_required
    ambiguous = requirement.model_copy(update={"calendar_basis": None})
    service.repository.save("requirements", requirement.id, ambiguous)
    withheld = service.calculate_deadline("dc", requirement.id, date(2026, 7, 17))
    assert withheld.calculated_date is None and "withheld" in withheld.explanation


def test_notice_draft_obligation_events_conflicts_and_no_external_send(tmp_path):
    service, _, clause = setup_contract(tmp_path)
    first = service.create_requirement(
        "dc",
        clause.id,
        "Change notice",
        "Five-day notice",
        time_limit=5,
        calendar_basis="calendar_days",
        recipient="Owner",
    )
    second_clause = service.extract_clauses(
        "dc", clause.document_id, (ev("prime-r1-c2", "8.2 Notice to Architect within 10 days"),)
    )[0]
    service.create_requirement(
        "dc",
        second_clause.id,
        "Change notice",
        "Ten-day notice",
        time_limit=10,
        calendar_basis="calendar_days",
        recipient="Architect",
    )
    assert service.detect_conflicts("dc")
    candidate = service.generate_notice_candidate(
        "dc",
        first.id,
        "change-1",
        (ev("change-1", "Change observed", date(2026, 7, 1)),),
        trigger_date=date(2026, 7, 1),
        notice_type="change_notice",
    )
    draft = service.draft_notice(
        "dc",
        candidate.id,
        "Contractor",
        "Owner",
        "Potential change notice",
        ("Change observed",),
        "project-manager",
    )
    assert not draft.external_delivery_performed and not draft.issued_as_recorded
    obligation = service.normalize_obligation(
        "dc", first.id, "project_change", "change-1", "Review notice candidate"
    )
    try:
        service.confirm_obligation("dc", obligation.id, (), "pm")
        assert False
    except ValueError:
        pass
    service.confirm_obligation("dc", obligation.id, (ev("review", "Completion confirmed"),), "pm")
    event = service.create_event(
        "dc",
        "delay_evidence",
        "Procurement status reported later than milestone",
        (ev("procurement-1", "Late forecast as reported", date(2026, 7, 2)),),
        start=date(2026, 7, 2),
        links=("activity-1",),
    )
    assert not event.legal_conclusion and service.chronology("dc")[0].citations


def test_qa_refuses_legal_conclusions(tmp_path):
    service, _, _ = setup_contract(tmp_path)
    answer = ContractQuestionService(service).answer(
        "dc", "Is the contractor entitled and who is responsible?"
    )
    assert "cannot provide legal advice" in answer.answer
