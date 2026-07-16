import json
from datetime import date
from pathlib import Path
from sqlalchemy import select
from .database import SessionLocal, create_tables
from .models import Project, Organization, Person, Responsibility

DATA_FILE=Path(__file__).resolve().parents[2]/"sample_data"/"lesson_01"/"fictional_data_center_project.json"

def seed_database(session=None, data_file=DATA_FILE):
    owns=session is None
    if owns:create_tables()
    db=session or SessionLocal()
    try:
        data=json.loads(Path(data_file).read_text(encoding="utf-8")); p=data["project"]
        existing=db.scalar(select(Project).where(Project.project_number==p["project_number"]))
        if existing:return existing,False
        project=Project(**{**p,"start_date":date.fromisoformat(p["start_date"]),"target_completion_date":date.fromisoformat(p["target_completion_date"])})
        db.add(project);db.flush(); orgs={}
        for row in data["organizations"]:
            parent=row.pop("parent",None); obj=Organization(project_id=project.id,**row);db.add(obj);db.flush();orgs[obj.name]=obj
            if parent: obj.parent_organization_id=orgs[parent].id
        people={}
        for row in data["people"]:
            org=row.pop("organization");obj=Person(organization_id=orgs[org].id,**row);db.add(obj);db.flush();people[obj.full_name]=obj
        for row in data["responsibilities"]:
            org=row.pop("organization");person=row.pop("person",None)
            defaults={"decision_authority":"As recorded in the fictional responsibility matrix; verify before use","approval_authority":"No approval beyond the recorded project authority; human verification required","typical_documents_produced":"Project records related to this responsibility","typical_questions_received":"Questions related to this responsibility","source_type":"Responsibility Matrix","source_reference":"Fictional Lesson 01 Responsibility Matrix, Rev 0","status":"Active","notes":"Training data only"}
            db.add(Responsibility(project_id=project.id,organization_id=orgs[org].id,person_id=people[person].id if person else None,**{**defaults,**row}))
        db.commit();return project,True
    except: db.rollback();raise
    finally:
        if owns:db.close()

def main():
    project,created=seed_database();print(f"{'Created' if created else 'Already seeded'}: {project.name} (ID {project.id})")
if __name__=="__main__":main()
