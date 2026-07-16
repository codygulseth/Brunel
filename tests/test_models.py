import pytest
from pydantic import ValidationError
from ai_project_engineer import models,schemas

def test_model_relationships_and_assignments(seeded_db):
    p=seeded_db.query(models.Project).one();org=p.organizations[0]
    assert len(p.organizations)==16 and len(p.responsibilities)==35
    assert org.people and org.people[0].organization is org
    assigned=next(r for r in p.responsibilities if r.person_id)
    assert assigned.person.organization_id==assigned.organization_id

def test_parent_relationship(seeded_db):
    child=seeded_db.query(models.Organization).filter_by(name="Red Mesa Concrete").one()
    assert child.parent_organization.name=="Keystone Mission Builders"

def test_required_field_validation():
    with pytest.raises(ValidationError):schemas.OrganizationCreate(name="",organization_type="Owner",primary_discipline="Owner",contractual_relationship="Owner")

def test_invalid_enum_validation():
    with pytest.raises(ValidationError):schemas.OrganizationCreate(name="X",organization_type="Wizard",primary_discipline="Owner",contractual_relationship="Owner")

