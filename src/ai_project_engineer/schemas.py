from datetime import date
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .models import Discipline, OrganizationType, ProjectPhase, ResponsibilityCategory, ResponsibilityStatus, SourceType

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class ProjectOut(ORMModel):
    id:int; name:str; project_number:str; project_type:str; description:str; location:str; current_phase:ProjectPhase; start_date:date; target_completion_date:date

class OrganizationCreate(BaseModel):
    name:str=Field(min_length=1,max_length=200); organization_type:OrganizationType; primary_discipline:Discipline
    contractual_relationship:str=Field(min_length=1,max_length=250); parent_organization_id:int|None=None; notes:str=""
class OrganizationOut(OrganizationCreate,ORMModel):
    id:int; project_id:int

class PersonCreate(BaseModel):
    organization_id:int; full_name:str=Field(min_length=1,max_length=150); job_title:str=Field(min_length=1,max_length=150)
    email:str=Field(min_length=3,max_length=200); phone:str=Field(min_length=1,max_length=50); project_role:str=Field(min_length=1,max_length=150)
    discipline:Discipline; active:bool=True; notes:str=""
class PersonOut(PersonCreate,ORMModel):
    id:int

class ResponsibilityCreate(BaseModel):
    organization_id:int; person_id:int|None=None; category:ResponsibilityCategory; description:str=Field(min_length=1)
    decision_authority:str=Field(min_length=1); approval_authority:str=Field(min_length=1)
    typical_documents_produced:str=""; typical_questions_received:str=""; source_type:SourceType
    source_reference:str=Field(min_length=1,max_length=250); status:ResponsibilityStatus=ResponsibilityStatus.ACTIVE; notes:str=""
class ResponsibilityOut(ResponsibilityCreate,ORMModel):
    id:int; project_id:int

