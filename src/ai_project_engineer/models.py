from __future__ import annotations

from datetime import date
from enum import Enum

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TextEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ProjectPhase(TextEnum):
    PLANNING="Planning"; DESIGN="Design"; PERMITTING="Permitting"; PROCUREMENT="Procurement"; SITEWORK="Sitework"; FOUNDATIONS="Foundations"; STRUCTURE="Structure"; BUILDING_ENVELOPE="Building Envelope"; MEP_ROUGH_IN="MEP Rough-In"; EQUIPMENT_INSTALLATION="Equipment Installation"; TESTING="Testing"; COMMISSIONING="Commissioning"; PUNCH_LIST="Punch List"; TURNOVER="Turnover"

class OrganizationType(TextEnum):
    OWNER="Owner"; ARCHITECT="Architect"; ENGINEER="Engineer"; GENERAL_CONTRACTOR="General Contractor"; SUBCONTRACTOR="Subcontractor"; SUPPLIER="Supplier"; COMMISSIONING_AGENT="Commissioning Agent"; AHJ="Authority Having Jurisdiction"; CONSULTANT="Consultant"

class Discipline(TextEnum):
    OWNER="Owner"; ARCHITECTURE="Architecture"; CIVIL="Civil"; STRUCTURAL="Structural"; MECHANICAL="Mechanical"; ELECTRICAL="Electrical"; PLUMBING="Plumbing"; FIRE_PROTECTION="Fire Protection"; CONTROLS="Controls"; LOW_VOLTAGE="Low Voltage"; GENERAL_CONSTRUCTION="General Construction"; COMMISSIONING="Commissioning"; SAFETY="Safety"; QUALITY="Quality"; PROCUREMENT="Procurement"; OTHER="Other"

class ResponsibilityCategory(TextEnum):
    DESIGN="Design"; FIELD_EXECUTION="Field Execution"; COST="Cost"; SCHEDULE="Schedule"; SAFETY="Safety"; QUALITY="Quality"; PROCUREMENT="Procurement"; COMMISSIONING="Commissioning"; PERMITTING="Permitting"; OWNER_DECISION="Owner Decision"; DOCUMENT_CONTROL="Document Control"; COORDINATION="Coordination"; TURNOVER="Turnover"

class SourceType(TextEnum):
    CONTRACT="Contract"; RESPONSIBILITY_MATRIX="Responsibility Matrix"; MEETING_MINUTES="Meeting Minutes"; MANUAL_ENTRY="Manual Entry"; PROJECT_DIRECTORY="Project Directory"; UNKNOWN="Unknown"

class ResponsibilityStatus(TextEnum):
    ACTIVE="Active"; DRAFT="Draft"; INACTIVE="Inactive"


def enum_col(enum_type):
    return SAEnum(enum_type, values_callable=lambda items: [item.value for item in items], validate_strings=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    project_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    project_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200))
    current_phase: Mapped[ProjectPhase] = mapped_column(enum_col(ProjectPhase))
    start_date: Mapped[date] = mapped_column(Date)
    target_completion_date: Mapped[date] = mapped_column(Date)
    organizations: Mapped[list[Organization]] = relationship(back_populates="project", cascade="all, delete-orphan")
    responsibilities: Mapped[list[Responsibility]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    organization_type: Mapped[OrganizationType] = mapped_column(enum_col(OrganizationType))
    primary_discipline: Mapped[Discipline] = mapped_column(enum_col(Discipline))
    contractual_relationship: Mapped[str] = mapped_column(String(250))
    parent_organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    project: Mapped[Project] = relationship(back_populates="organizations")
    parent_organization: Mapped[Organization | None] = relationship(remote_side=[id], back_populates="child_organizations")
    child_organizations: Mapped[list[Organization]] = relationship(back_populates="parent_organization")
    people: Mapped[list[Person]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    responsibilities: Mapped[list[Responsibility]] = relationship(back_populates="organization")


class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    job_title: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50))
    project_role: Mapped[str] = mapped_column(String(150), index=True)
    discipline: Mapped[Discipline] = mapped_column(enum_col(Discipline))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    organization: Mapped[Organization] = relationship(back_populates="people")
    responsibilities: Mapped[list[Responsibility]] = relationship(back_populates="person")


class Responsibility(Base):
    __tablename__ = "responsibilities"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"), nullable=True, index=True)
    category: Mapped[ResponsibilityCategory] = mapped_column(enum_col(ResponsibilityCategory))
    description: Mapped[str] = mapped_column(Text)
    decision_authority: Mapped[str] = mapped_column(Text)
    approval_authority: Mapped[str] = mapped_column(Text)
    typical_documents_produced: Mapped[str] = mapped_column(Text)
    typical_questions_received: Mapped[str] = mapped_column(Text)
    source_type: Mapped[SourceType] = mapped_column(enum_col(SourceType))
    source_reference: Mapped[str] = mapped_column(String(250))
    status: Mapped[ResponsibilityStatus] = mapped_column(enum_col(ResponsibilityStatus), default=ResponsibilityStatus.ACTIVE)
    notes: Mapped[str] = mapped_column(Text, default="")
    project: Mapped[Project] = relationship(back_populates="responsibilities")
    organization: Mapped[Organization] = relationship(back_populates="responsibilities")
    person: Mapped[Person | None] = relationship(back_populates="responsibilities")

