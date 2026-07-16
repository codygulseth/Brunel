from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import models, schemas, services
from .database import create_tables, get_db

BASE=Path(__file__).parent
templates=Jinja2Templates(directory=BASE/"templates")

@asynccontextmanager
async def lifespan(app):
    create_tables(); yield

app=FastAPI(title="AI Project Engineer",version="0.1.0",lifespan=lifespan)
app.mount("/static",StaticFiles(directory=BASE/"static"),name="static")

def project_or_404(db, project_id):
    item=db.get(models.Project,project_id)
    if not item: raise HTTPException(404,"Project not found")
    return item
def first_project(db):
    item=db.scalar(select(models.Project).order_by(models.Project.id))
    if not item: raise HTTPException(404,"No project found. Run: python -m ai_project_engineer.seed")
    return item

@app.get("/",response_class=HTMLResponse)
def dashboard(request:Request,db:Session=Depends(get_db)):
    p=first_project(db); orgs=services.list_organizations(db,p.id); rs=services.list_responsibilities(db,p.id)
    grouped_orgs={t.value:sum(o.organization_type==t for o in orgs) for t in models.OrganizationType}
    grouped_rs={c.value:sum(r.category==c for r in rs) for c in models.ResponsibilityCategory}
    return templates.TemplateResponse(request,"index.html",{"project":p,"counts":services.dashboard_counts(db,p.id),"phases":list(models.ProjectPhase),"grouped_orgs":grouped_orgs,"grouped_rs":grouped_rs})

@app.get("/projects/{project_id}",response_class=HTMLResponse)
def project_detail(request:Request,project_id:int,db:Session=Depends(get_db)):
    p=project_or_404(db,project_id); return templates.TemplateResponse(request,"project_detail.html",{"project":p,"counts":services.dashboard_counts(db,p.id)})

@app.get("/organizations",response_class=HTMLResponse)
def organizations_page(request:Request,organization_type:str|None=None,discipline:str|None=None,db:Session=Depends(get_db)):
    p=first_project(db); items=services.list_organizations(db,p.id,organization_type,discipline)
    return templates.TemplateResponse(request,"organizations.html",{"project":p,"items":items,"types":models.OrganizationType,"disciplines":models.Discipline,"filters":request.query_params})

@app.get("/people",response_class=HTMLResponse)
def people_page(request:Request,organization_id:int|None=None,project_role:str|None=None,discipline:str|None=None,active:bool|None=None,db:Session=Depends(get_db)):
    p=first_project(db); items=services.list_people(db,p.id,organization_id,project_role,discipline,active); orgs=services.list_organizations(db,p.id)
    roles=sorted({x.project_role for x in services.list_people(db,p.id)})
    return templates.TemplateResponse(request,"people.html",{"project":p,"items":items,"organizations":orgs,"roles":roles,"disciplines":models.Discipline,"filters":request.query_params})

@app.get("/responsibilities",response_class=HTMLResponse)
def responsibilities_page(request:Request,category:str|None=None,organization_id:int|None=None,person_id:int|None=None,status:str|None=None,source_type:str|None=None,search:str|None=None,db:Session=Depends(get_db)):
    p=first_project(db); items=services.list_responsibilities(db,p.id,category,organization_id,person_id,status,source_type,search)
    return templates.TemplateResponse(request,"responsibilities.html",{"project":p,"items":items,"organizations":services.list_organizations(db,p.id),"people":services.list_people(db,p.id),"categories":models.ResponsibilityCategory,"statuses":models.ResponsibilityStatus,"sources":models.SourceType,"filters":request.query_params})

@app.get("/api/projects",response_model=list[schemas.ProjectOut])
def api_projects(db:Session=Depends(get_db)): return list(db.scalars(select(models.Project).order_by(models.Project.name)))
@app.get("/api/projects/{project_id}",response_model=schemas.ProjectOut)
def api_project(project_id:int,db:Session=Depends(get_db)): return project_or_404(db,project_id)
@app.get("/api/projects/{project_id}/organizations",response_model=list[schemas.OrganizationOut])
def api_organizations(project_id:int,organization_type:models.OrganizationType|None=None,discipline:models.Discipline|None=None,db:Session=Depends(get_db)):
    project_or_404(db,project_id); return services.list_organizations(db,project_id,organization_type,discipline)
@app.post("/api/projects/{project_id}/organizations",response_model=schemas.OrganizationOut,status_code=201)
def api_add_organization(project_id:int,data:schemas.OrganizationCreate,db:Session=Depends(get_db)):
    try:return services.create_organization(db,project_id,data)
    except ValueError as e:raise HTTPException(400,str(e))
@app.get("/api/projects/{project_id}/people",response_model=list[schemas.PersonOut])
def api_people(project_id:int,organization_id:int|None=None,project_role:str|None=None,discipline:models.Discipline|None=None,active:bool|None=None,db:Session=Depends(get_db)):
    project_or_404(db,project_id); return services.list_people(db,project_id,organization_id,project_role,discipline,active)
@app.post("/api/projects/{project_id}/people",response_model=schemas.PersonOut,status_code=201)
def api_add_person(project_id:int,data:schemas.PersonCreate,db:Session=Depends(get_db)):
    try:return services.create_person(db,project_id,data)
    except ValueError as e:raise HTTPException(400,str(e))
@app.get("/api/projects/{project_id}/responsibilities",response_model=list[schemas.ResponsibilityOut])
def api_responsibilities(project_id:int,category:models.ResponsibilityCategory|None=None,organization_id:int|None=None,person_id:int|None=None,status:models.ResponsibilityStatus|None=None,source_type:models.SourceType|None=None,search:str|None=None,db:Session=Depends(get_db)):
    project_or_404(db,project_id); return services.list_responsibilities(db,project_id,category,organization_id,person_id,status,source_type,search)
@app.post("/api/projects/{project_id}/responsibilities",response_model=schemas.ResponsibilityOut,status_code=201)
def api_add_responsibility(project_id:int,data:schemas.ResponsibilityCreate,db:Session=Depends(get_db)):
    try:return services.create_responsibility(db,project_id,data)
    except ValueError as e:raise HTTPException(400,str(e))
@app.get("/api/responsibilities/{responsibility_id}",response_model=schemas.ResponsibilityOut)
def api_responsibility(responsibility_id:int,db:Session=Depends(get_db)):
    item=db.get(models.Responsibility,responsibility_id)
    if not item:raise HTTPException(404,"Responsibility not found")
    return item

