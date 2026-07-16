from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload
from . import models, schemas

def get_project(db:Session, project_id:int):
    return db.get(models.Project, project_id)

def list_organizations(db:Session, project_id:int, organization_type=None, discipline=None):
    q=select(models.Organization).where(models.Organization.project_id==project_id).options(joinedload(models.Organization.parent_organization))
    if organization_type: q=q.where(models.Organization.organization_type==organization_type)
    if discipline: q=q.where(models.Organization.primary_discipline==discipline)
    return list(db.scalars(q.order_by(models.Organization.name)).unique())

def list_people(db:Session, project_id:int, organization_id=None, project_role=None, discipline=None, active=None):
    q=select(models.Person).join(models.Organization).where(models.Organization.project_id==project_id).options(joinedload(models.Person.organization))
    if organization_id: q=q.where(models.Person.organization_id==organization_id)
    if project_role: q=q.where(models.Person.project_role==project_role)
    if discipline: q=q.where(models.Person.discipline==discipline)
    if active is not None: q=q.where(models.Person.active==active)
    return list(db.scalars(q.order_by(models.Person.full_name)).unique())

def list_responsibilities(db:Session, project_id:int, category=None, organization_id=None, person_id=None, status=None, source_type=None, search=None):
    q=select(models.Responsibility).where(models.Responsibility.project_id==project_id).options(joinedload(models.Responsibility.organization),joinedload(models.Responsibility.person))
    for col,val in [(models.Responsibility.category,category),(models.Responsibility.organization_id,organization_id),(models.Responsibility.person_id,person_id),(models.Responsibility.status,status),(models.Responsibility.source_type,source_type)]:
        if val is not None: q=q.where(col==val)
    if search:
        term=f"%{search.strip()}%"
        q=q.where(or_(models.Responsibility.description.ilike(term),models.Responsibility.typical_documents_produced.ilike(term),models.Responsibility.typical_questions_received.ilike(term)))
    return list(db.scalars(q.order_by(models.Responsibility.category,models.Responsibility.description)).unique())

def create_organization(db, project_id, data:schemas.OrganizationCreate):
    if not db.get(models.Project,project_id): raise ValueError("Project not found")
    if data.parent_organization_id:
        parent=db.get(models.Organization,data.parent_organization_id)
        if not parent or parent.project_id!=project_id: raise ValueError("Parent organization must belong to this project")
    obj=models.Organization(project_id=project_id,**data.model_dump()); db.add(obj); db.commit(); db.refresh(obj); return obj

def create_person(db, project_id, data:schemas.PersonCreate):
    org=db.get(models.Organization,data.organization_id)
    if not org or org.project_id!=project_id: raise ValueError("Organization must belong to this project")
    obj=models.Person(**data.model_dump()); db.add(obj); db.commit(); db.refresh(obj); return obj

def create_responsibility(db, project_id, data:schemas.ResponsibilityCreate):
    org=db.get(models.Organization,data.organization_id)
    if not org or org.project_id!=project_id: raise ValueError("Organization must belong to this project")
    if data.person_id:
        person=db.get(models.Person,data.person_id)
        if not person or person.organization_id!=data.organization_id: raise ValueError("Person must belong to the responsible organization")
    obj=models.Responsibility(project_id=project_id,**data.model_dump()); db.add(obj); db.commit(); db.refresh(obj); return obj

def dashboard_counts(db, project_id):
    return {"organizations":db.scalar(select(func.count()).select_from(models.Organization).where(models.Organization.project_id==project_id)),"people":db.scalar(select(func.count()).select_from(models.Person).join(models.Organization).where(models.Organization.project_id==project_id)),"responsibilities":db.scalar(select(func.count()).select_from(models.Responsibility).where(models.Responsibility.project_id==project_id))}

