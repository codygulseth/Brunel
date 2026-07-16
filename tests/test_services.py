from ai_project_engineer import models,schemas,services
from ai_project_engineer.seed import seed_database

def test_seed_is_idempotent(db):
    first,created=seed_database(db);second,created_again=seed_database(db)
    assert created and not created_again and first.id==second.id
    assert db.query(models.Project).count()==1 and db.query(models.Responsibility).count()==35

def test_filter_organizations(seeded_db):
    p=seeded_db.query(models.Project).one();items=services.list_organizations(seeded_db,p.id,models.OrganizationType.SUPPLIER)
    assert len(items)==2 and all(x.organization_type==models.OrganizationType.SUPPLIER for x in items)

def test_filter_people(seeded_db):
    p=seeded_db.query(models.Project).one();items=services.list_people(seeded_db,p.id,project_role="Engineer of Record",discipline=models.Discipline.ELECTRICAL)
    assert [x.full_name for x in items]==["Skyler Amp"]

def test_filter_responsibilities(seeded_db):
    p=seeded_db.query(models.Project).one();items=services.list_responsibilities(seeded_db,p.id,category=models.ResponsibilityCategory.PROCUREMENT)
    assert len(items)==3

def test_responsibility_text_search(seeded_db):
    p=seeded_db.query(models.Project).one();items=services.list_responsibilities(seeded_db,p.id,search="one-line")
    assert len(items)==1 and items[0].description=="Electrical one-line design"
    assert services.list_responsibilities(seeded_db,p.id,search="warranties")

def test_reject_person_from_other_organization(seeded_db):
    p=seeded_db.query(models.Project).one();orgs=services.list_organizations(seeded_db,p.id)
    person=orgs[0].people[0]
    data=schemas.ResponsibilityCreate(organization_id=orgs[1].id,person_id=person.id,category="Design",description="Test",decision_authority="None",approval_authority="None",source_type="Manual Entry",source_reference="Test")
    import pytest
    with pytest.raises(ValueError,match="Person must belong"):services.create_responsibility(seeded_db,p.id,data)

